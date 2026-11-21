"""Review sample of import edges (R14-A3 gate, criteria 2 and 4).

Draws a seeded random sample of the import edges of `--structure` on a real project
and, for every row, recomputes the answer *independently* of the structure code: the
flags from the syntax tree, the standard-library test from `sys.stdlib_module_names`,
the repository test from the file system, and where a package is declared from every
section of `pyproject.toml`. The reviewer then reads each row and records a verdict.

The sample is a function of the tree and the seed only: the edges are sorted by
location and requested name, then drawn with `random.Random(seed)`. It is a simple
random sample, so rare classes are as rare in it as in the project.

A verdict file has one `<row> <verdict> [note...]` per line; the verdicts are
`correct`, `wrong`, `ambiguous` and `undecidable`. Lines that start with `#` are
ignored.

With `--audit-external` it also checks, for the whole project (not a sample), every
external package: what the structure says, what the manifests say, and where the two
differ.

With `--rereview OLD.tsv` it does not draw a sample: it takes the rows of an earlier
review (matched by location and evidence), computes the answer of the *current*
structure code for each, and writes both side by side. The earlier file is only read;
the verdict column of the new file is filled from `--verdicts`, with the reason.

Usage:
    python scripts/structure_eval_imports.py PROJECT --out FILE.tsv [--seed 14]
        [--sample 50] [--verdicts FILE] [--audit-external]
    python scripts/structure_eval_imports.py PROJECT --out NEW.tsv --rereview OLD.tsv
        [--verdicts FILE] [--audit-external]

نمونه‌ی بازبینی importها با seed ثابت و بازمحاسبه‌ی مستقل هر ردیف (معیارهای ۲ و ۴ گیت).
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import random
import re
import sys
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any

from sarand.structure import build_structure
from sarand.structure.serialize import structure_payload

SKIPPED_DIRS = frozenset(
    {".git", "__pycache__", "node_modules", "target", ".venv", "venv", ".tox", "build"}
)
SIZE_LIMIT = 1_000_000
VERDICTS = ("correct", "wrong", "ambiguous", "undecidable")
# The verdict and the note come early and the evidence (never empty) comes last, so
# no line ends in a tab: git would report that as trailing whitespace.
# verdict و note زودتر می‌آیند و evidence (هیچ‌وقت خالی نیست) آخر، تا خط به تب ختم نشود.
HEADER = (
    "row",
    "location",
    "verdict",
    "note",
    "class",
    "target",
    "method",
    "confidence",
    "flags",
    "auto",
    "indep_class",
    "indep_flags",
    "declared_in",
    "indep_declared_in",
    "evidence",
)
VERDICT_COLUMN = 2
NOTE_COLUMN = 3
# The side-by-side file of a re-review: the earlier verdict, the new verdict and why.
REREVIEW_HEADER = (
    "row",
    "location",
    "old_verdict",
    "verdict",
    "reason",
    "old_class",
    "class",
    "confidence",
    "method",
    "flags",
    "auto",
    "declared_in",
    "indep_declared_in",
    "old_declared_in",
    "evidence",
)
REREVIEW_VERDICT_COLUMN = 3
REREVIEW_NOTE_COLUMN = 4
# Import names that differ from their distribution names: the reviewer's own short
# list, kept apart from the table in `sarand/structure/distributions.py` on purpose.
# A row that depends on a pair missing here is reported as a disagreement to read.
IMPORT_TO_DIST: dict[str, tuple[str, ...]] = {
    "yaml": ("pyyaml",),
    "PIL": ("pillow", "pillow-simd"),
    "bs4": ("beautifulsoup4",),
    "cv2": (
        "opencv-contrib-python",
        "opencv-contrib-python-headless",
        "opencv-python",
        "opencv-python-headless",
    ),
    "dateutil": ("python-dateutil",),
    "sklearn": ("scikit-learn",),
}
GUARDING = frozenset(
    {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}
)


def collect(root: Path) -> tuple[list[Path], list[tuple[Path, int]]]:
    """Every file below `root` (relative paths), the over-size ones apart."""
    included: list[Path] = []
    skipped: list[tuple[Path, int]] = []
    for current, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIPPED_DIRS)
        for name in sorted(names):
            path = Path(current, name)
            rel = path.relative_to(root)
            size = path.stat().st_size
            if size > SIZE_LIMIT:
                skipped.append((rel, size))
            else:
                included.append(rel)
    return included, skipped


def _is_type_checking(test: ast.expr) -> bool:
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _guards(handler: ast.ExceptHandler) -> bool:
    kind = handler.type
    if kind is None:
        return True
    names = kind.elts if isinstance(kind, ast.Tuple) else [kind]
    return any(
        (isinstance(n, ast.Name) and n.id in GUARDING)
        or (
            isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name)
            and n.value.id == "builtins"
            and n.attr in GUARDING
        )
        for n in names
    )


def _extra_flags(node: ast.AST, field: str) -> frozenset[str]:
    """The flags a child field adds to the imports it contains (docs/STRUCTURE.md)."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        return frozenset({"lazy"}) if field == "body" else frozenset()
    if isinstance(node, ast.If) and field in ("body", "orelse"):
        test = node.test
        negated = isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not)
        inner = test.operand if isinstance(test, ast.UnaryOp) else test
        if _is_type_checking(inner):
            typed = (field == "body") != negated
            return frozenset({"conditional", "type_only"} if typed else {"conditional"})
        return frozenset({"conditional"})
    if isinstance(node, (ast.For, ast.AsyncFor, ast.While)) and field in (
        "body",
        "orelse",
    ):
        return frozenset({"conditional"})
    if isinstance(node, ast.match_case) and field == "body":
        return frozenset({"conditional"})
    if isinstance(node, ast.ExceptHandler) and field == "body":
        return frozenset({"conditional"})
    if isinstance(node, (ast.Try, ast.TryStar)):
        if field == "orelse":
            return frozenset({"conditional"})
        if field == "body" and any(_guards(h) for h in node.handlers):
            return frozenset({"conditional"})
    return frozenset()


def import_contexts(tree: ast.AST) -> dict[int, tuple[ast.stmt, frozenset[str]]]:
    """Every import statement by line, with the flags its position implies."""
    found: dict[int, tuple[ast.stmt, frozenset[str]]] = {}
    stack: list[tuple[ast.AST, frozenset[str]]] = [(tree, frozenset())]
    while stack:
        node, flags = stack.pop()
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            found.setdefault(node.lineno, (node, flags))
        for field, value in ast.iter_fields(node):
            extra = flags | _extra_flags(node, field)
            children = value if isinstance(value, list) else [value]
            stack.extend((c, extra) for c in children if isinstance(c, ast.AST))
    return found


def _names(items: object) -> list[str]:
    """Normalised names of the requirement strings in a list (other items skipped)."""
    out: list[str] = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, str):
                match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", item)
                if match:
                    out.append(re.sub(r"[-_.]+", "-", match.group(1)).lower())
    return out


def _poetry(table: object) -> list[str]:
    if not isinstance(table, dict):
        return []
    names = (re.sub(r"[-_.]+", "-", str(k)).lower() for k in table)
    return [n for n in names if n != "python"]


def _directory_declarations(
    directory: Path, prefix: str, found: dict[str, list[str]]
) -> None:
    """Add the declarations of the manifests directly in `directory` to `found`."""

    def add(names: list[str], label: str) -> None:
        for name in names:
            labels = found.setdefault(name, [])
            if label not in labels:
                labels.append(label)

    path = directory / "pyproject.toml"
    if path.is_file():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError):
            data = {}
        head = f"{prefix}pyproject.toml#"
        project = data.get("project") or {}
        add(_names(project.get("dependencies")), f"{head}project.dependencies")
        for extra, items in (project.get("optional-dependencies") or {}).items():
            add(_names(items), f"{head}project.optional-dependencies.{extra}")
        for group, items in (data.get("dependency-groups") or {}).items():
            add(_names(items), f"{head}dependency-groups.{group}")
        add(
            _names((data.get("build-system") or {}).get("requires")),
            f"{head}build-system.requires",
        )
        poetry = (data.get("tool") or {}).get("poetry") or {}
        add(_poetry(poetry.get("dependencies")), f"{head}tool.poetry.dependencies")
        add(
            _poetry(poetry.get("dev-dependencies")),
            f"{head}tool.poetry.dev-dependencies",
        )
        for group, body in (poetry.get("group") or {}).items():
            if isinstance(body, dict):
                add(
                    _poetry(body.get("dependencies")),
                    f"{head}tool.poetry.group.{group}.dependencies",
                )
    requirements = directory / "requirements.txt"
    if requirements.is_file():
        text = requirements.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith(("#", "-")):
                add(_names([line]), f"{prefix}requirements.txt")


def declared_sections(root: Path) -> dict[str, list[str]]:
    """Normalised distribution name -> where the manifests of the project declare it.

    Written without the structure code: `<dir>/pyproject.toml#<section>` for the
    sections the documentation lists and `<dir>/requirements.txt`, for the manifests of
    every directory of the project (like the structure, a declaration anywhere counts
    for the whole project; the audit reports how many are outside the importer's tree).
    """
    found: dict[str, list[str]] = {}
    for current, dirs, _names_ in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIPPED_DIRS)
        directory = Path(current)
        relative = directory.relative_to(root).as_posix()
        _directory_declarations(
            directory, "" if relative == "." else f"{relative}/", found
        )
    return found


def repository_has(root: Path, importer: str, parts: list[str]) -> bool:
    """Whether a module or package with these name parts exists in the repository."""
    if not parts:
        return False
    bases = [root, root / "src", root / "python", (root / importer).parent]
    tails = [Path(*parts).with_suffix(".py"), Path(*parts, "__init__.py")]
    return any((base / tail).is_file() for base in bases for tail in tails)


def independent(
    root: Path,
    importer: str,
    node: ast.stmt | None,
    flags: frozenset[str],
    requested: str,
    declared: dict[str, list[str]],
) -> tuple[str, set[str], list[str]]:
    """(boundary class, flags, declared-in labels) recomputed without the structure
    code. The labels are empty unless the boundary class is `external`."""
    if node is None:
        return "NO-NODE", set(), []
    out = set(flags)
    if isinstance(node, ast.ImportFrom) and node.level:
        out.add("relative")
    if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
        out.add("star")
    if isinstance(node, ast.ImportFrom) and node.level:
        return "internal", out, []
    parts = requested.split(".")
    top = parts[0]
    if top in sys.stdlib_module_names:
        return "stdlib", out, []
    if repository_has(root, importer, parts) or repository_has(
        root, importer, parts[:-1]
    ):
        return "internal", out, []
    labels: set[str] = set(declared.get(re.sub(r"[-_.]+", "-", top).lower(), []))
    for dist in IMPORT_TO_DIST.get(top, ()):
        labels.update(declared.get(dist, []))
    return "external", out, sorted(labels)


def load(root: Path) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """The import edges of the project, sorted by location and requested name, and the
    `declared_in` the structure gives each external package."""
    included, skipped = collect(root)
    payload = structure_payload(build_structure(root, included, skipped))
    edges: list[dict[str, Any]] = sorted(
        payload["edges"],
        key=lambda e: (
            e["location"]["path"],
            e["location"]["line"],
            e["location"]["col"],
            e["requested"],
        ),
    )
    externals = {x["name"]: list(x["declared_in"]) for x in payload["externals"]}
    return edges, externals


class Reviewer:
    """Recomputes one edge independently and compares it with the structure's answer."""

    def __init__(self, root: Path, externals: dict[str, list[str]]) -> None:
        self.root = root
        self.externals = externals
        self.declared = declared_sections(root)
        self.contexts: dict[str, dict[int, tuple[ast.stmt, frozenset[str]]]] = {}

    def _context(self, rel: str, line: int) -> tuple[ast.stmt | None, frozenset[str]]:
        if rel not in self.contexts:
            try:
                tree = ast.parse((self.root / rel).read_text(encoding="utf-8"))
                self.contexts[rel] = import_contexts(tree)
            except (OSError, SyntaxError, UnicodeDecodeError):
                self.contexts[rel] = {}
        found = self.contexts[rel].get(line)
        return (found[0], found[1]) if found else (None, frozenset())

    def check(self, edge: dict[str, Any]) -> dict[str, str]:
        """The comparison columns of one edge."""
        rel = edge["location"]["path"]
        node, flags = self._context(rel, edge["location"]["line"])
        boundary, expected, labels = independent(
            self.root, rel, node, flags, edge["requested"], self.declared
        )
        got = str(edge["target_class"])
        got_boundary = "external" if got.startswith("external") else got
        tool_labels = sorted(self.externals.get(str(edge["target"]), []))
        agree = got_boundary == boundary and set(edge["flags"]) == expected
        if boundary == "external" and got_boundary == "external":
            declared_state = "external_declared" if labels else "external_unmatched"
            agree = agree and got == declared_state and tool_labels == labels
        return {
            "class": got,
            "target": str(edge["target"]),
            "method": str(edge["resolution_method"]),
            "confidence": str(edge["confidence"]),
            "flags": ",".join(sorted(edge["flags"])),
            "auto": "agree" if agree else "DISAGREE",
            "indep_class": boundary,
            "indep_flags": ",".join(sorted(expected)),
            "declared_in": ",".join(tool_labels),
            "indep_declared_in": ",".join(labels),
            "evidence": str(edge["evidence"]).strip(),
        }


def build_rows(
    root: Path,
    edges: list[dict[str, Any]],
    externals: dict[str, list[str]],
    seed: int,
    count: int,
) -> list[list[str]]:
    # A seeded generator on purpose: a reproducible review sample, not a secret.
    generator = random.Random(seed)  # nosec B311
    chosen = generator.sample(edges, min(count, len(edges)))
    reviewer = Reviewer(root, externals)
    rows: list[list[str]] = []
    for index, edge in enumerate(chosen, 1):
        loc = edge["location"]
        cols = reviewer.check(edge)
        rows.append(
            [
                str(index),
                f"{loc['path']}:{loc['line']}:{loc['col']}",
                "",
                "",
                *(cols[name] for name in HEADER[4:]),
            ]
        )
    return rows


def read_review(path: Path) -> list[dict[str, str]]:
    """The rows of an earlier review file, by column name (the file is not changed)."""
    lines = path.read_text(encoding="utf-8").split("\n")
    names = lines[0].split("\t")
    return [
        dict(zip(names, line.split("\t"), strict=False)) for line in lines[1:] if line
    ]


def rereview_rows(
    root: Path,
    edges: list[dict[str, Any]],
    externals: dict[str, list[str]],
    old: list[dict[str, str]],
) -> list[list[str]]:
    """The earlier rows with the current structure's answer beside the old one."""
    reviewer = Reviewer(root, externals)
    by_key = {
        (
            f"{e['location']['path']}:{e['location']['line']}:{e['location']['col']}",
            str(e["evidence"]).strip(),
        ): e
        for e in edges
    }
    rows: list[list[str]] = []
    for item in old:
        edge = by_key.get((item["location"], item["evidence"]))
        if edge is None:
            raise SystemExit(f"row {item['row']} not found in the current edges")
        cols = reviewer.check(edge)
        rows.append(
            [
                item["row"],
                item["location"],
                item["verdict"],
                "",
                "",
                item["class"],
                cols["class"],
                cols["confidence"],
                cols["method"],
                cols["flags"],
                cols["auto"],
                cols["declared_in"],
                cols["indep_declared_in"],
                item.get("declared_in", ""),
                cols["evidence"],
            ]
        )
    return rows


def _unscoped_edges(
    edges: list[dict[str, Any]], externals: dict[str, list[str]]
) -> int:
    """External edges the structure calls declared whose declarations all sit in
    directories that are not above the importing file: the declaration is matched
    project-wide, so such an edge is declared only by a manifest of another part of
    the project."""
    count = 0
    for edge in edges:
        if edge["target_class"] != "external_declared":
            continue
        path = str(edge["location"]["path"])
        folder = path.rsplit("/", 1)[0] + "/" if "/" in path else ""
        above = False
        for label in externals.get(str(edge["target"]), []):
            manifest_dir = label.split("#", 1)[0].rsplit("/", 1)
            owner = manifest_dir[0] + "/" if len(manifest_dir) == 2 else ""
            if folder.startswith(owner):
                above = True
                break
        if not above:
            count += 1
    return count


def audit_external(
    root: Path, edges: list[dict[str, Any]], externals: dict[str, list[str]]
) -> dict[str, object]:
    """Every external package of the whole project: the structure's class and
    declarations against the manifests, and every package where they differ."""
    declared = declared_sections(root)
    packages: dict[str, dict[str, Any]] = {}
    for edge in edges:
        if not str(edge["target_class"]).startswith("external"):
            continue
        top = str(edge["requested"]).split(".")[0]
        labels: set[str] = set(declared.get(re.sub(r"[-_.]+", "-", top).lower(), []))
        for dist in IMPORT_TO_DIST.get(top, ()):
            labels.update(declared.get(dist, []))
        entry = packages.setdefault(
            top,
            {
                "edges": 0,
                "classes": Counter(),
                "tool_declared_in": sorted(externals.get(str(edge["target"]), [])),
                "indep_declared_in": sorted(labels),
            },
        )
        entry["edges"] += 1
        entry["classes"][str(edge["target_class"])] += 1
    unscoped = _unscoped_edges(edges, externals)
    by_class: Counter[str] = Counter()
    different: list[str] = []
    for top, entry in sorted(packages.items()):
        entry["classes"] = dict(entry["classes"])
        for name, count in entry["classes"].items():
            by_class[name] += count
        if entry["tool_declared_in"] != entry["indep_declared_in"]:
            different.append(top)
    return {
        "external_edges": sum(p["edges"] for p in packages.values()),
        "edges_by_class": dict(by_class),
        "packages": packages,
        "packages_where_structure_and_manifests_differ": different,
        "declared_edges_without_a_declaring_manifest_above_the_importer": unscoped,
    }


def clean(text: str) -> str:
    return text.replace("\t", " ").replace("\n", " ").replace("\r", " ")


def write_rows(path: Path, header: tuple[str, ...], rows: list[list[str]]) -> None:
    lines = ["\t".join(header), *("\t".join(clean(c) for c in row) for row in rows)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def apply_verdicts(
    path: Path,
    verdict_file: Path,
    verdict_column: int = VERDICT_COLUMN,
    note_column: int = NOTE_COLUMN,
) -> dict[str, int]:
    given: dict[int, tuple[str, str]] = {}
    for raw in verdict_file.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        parts = raw.strip().split(None, 2)
        if len(parts) < 2 or parts[1] not in VERDICTS:
            raise SystemExit(f"bad verdict line: {raw!r}")
        given[int(parts[0])] = (parts[1], parts[2] if len(parts) > 2 else "")
    lines = path.read_text(encoding="utf-8").split("\n")
    counts = {name: 0 for name in VERDICTS}
    counts["unreviewed"] = 0
    for number, text in enumerate(lines[1:], 1):
        if not text:
            continue
        cells = text.split("\t")
        found = given.get(int(cells[0]))
        if found is None:
            counts["unreviewed"] += 1
            continue
        cells[verdict_column], cells[note_column] = found[0], clean(found[1])
        counts[found[0]] += 1
        lines[number] = "\t".join(cells)
    path.write_text("\n".join(lines), encoding="utf-8")
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("project", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=14)
    parser.add_argument("--sample", type=int, default=50)
    parser.add_argument("--verdicts", type=Path)
    parser.add_argument("--rereview", type=Path)
    parser.add_argument("--audit-external", action="store_true")
    args = parser.parse_args(argv)
    root = args.project.resolve()
    edges, externals = load(root)
    report: dict[str, object] = {"seed": args.seed}
    if args.rereview is not None:
        old = read_review(args.rereview)
        rows = rereview_rows(root, edges, externals, old)
        write_rows(args.out, REREVIEW_HEADER, rows)
        report["rows"] = len(rows)
        report["old_classes"] = dict(Counter(row[5] for row in rows))
        report["new_classes"] = dict(Counter(row[6] for row in rows))
        report["class_changed"] = [row[0] for row in rows if row[5] != row[6]]
        report["independent_agrees"] = sum(1 for row in rows if row[10] == "agree")
        report["independent_disagrees"] = [row[0] for row in rows if row[10] != "agree"]
        if args.verdicts is not None:
            report["tally"] = apply_verdicts(
                args.out, args.verdicts, REREVIEW_VERDICT_COLUMN, REREVIEW_NOTE_COLUMN
            )
            changed = [
                row[0]
                for row in (
                    line.split("\t")
                    for line in args.out.read_text(encoding="utf-8").split("\n")[1:]
                    if line
                )
                if row[2] != row[3]
            ]
            report["verdict_changed"] = changed
    else:
        rows = build_rows(root, edges, externals, args.seed, args.sample)
        write_rows(args.out, HEADER, rows)
        report["rows"] = len(rows)
        report["edges_in_project"] = len(edges)
        report["classes"] = dict(Counter(row[4] for row in rows))
        report["independent_agrees"] = sum(1 for row in rows if row[9] == "agree")
        report["independent_disagrees"] = [row[0] for row in rows if row[9] != "agree"]
        if args.verdicts is not None:
            report["tally"] = apply_verdicts(args.out, args.verdicts)
    if args.audit_external:
        report["external_audit"] = audit_external(root, edges, externals)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
