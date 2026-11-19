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

With `--audit-unmatched` it also lists, for the whole project (not a sample), every
`external_unmatched` package with the `pyproject.toml` sections that declare it, which
shows how much of that list is really declared elsewhere.

Usage:
    python scripts/structure_eval_imports.py PROJECT --out FILE.tsv [--seed 14]
        [--sample 50] [--verdicts FILE] [--audit-unmatched]

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
    "flags",
    "auto",
    "indep_class",
    "indep_flags",
    "declared_in",
    "evidence",
)
VERDICT_COLUMN = 2
NOTE_COLUMN = 3
# Import names that differ from their distribution names; a reviewer aid only.
IMPORT_TO_DIST = {
    "yaml": "pyyaml",
    "PIL": "pillow",
    "bs4": "beautifulsoup4",
    "cv2": "opencv-python",
    "dateutil": "python-dateutil",
    "sklearn": "scikit-learn",
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


def declared_sections(root: Path) -> dict[str, list[str]]:
    """Normalised distribution name -> the `pyproject.toml` sections that declare it."""
    path = root / "pyproject.toml"
    if not path.is_file():
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return {}
    found: dict[str, list[str]] = {}

    def add(items: object, section: str) -> None:
        if not isinstance(items, list):
            return
        for item in items:
            match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", str(item))
            if match:
                name = re.sub(r"[-_.]+", "-", match.group(1)).lower()
                found.setdefault(name, [])
                if section not in found[name]:
                    found[name].append(section)

    project = data.get("project", {})
    add(project.get("dependencies"), "runtime")
    for group, items in (project.get("optional-dependencies") or {}).items():
        add(items, f"optional:{group}")
    for group, items in (data.get("dependency-groups") or {}).items():
        add(items, f"group:{group}")
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
) -> tuple[str, set[str], str]:
    """(boundary class, flags, declared-in) recomputed without the structure code."""
    if node is None:
        return "NO-NODE", set(), ""
    out = set(flags)
    if isinstance(node, ast.ImportFrom) and node.level:
        out.add("relative")
    if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
        out.add("star")
    if isinstance(node, ast.ImportFrom) and node.level:
        return "internal", out, ""
    parts = requested.split(".")
    top = parts[0]
    if top in sys.stdlib_module_names:
        return "stdlib", out, ""
    if repository_has(root, importer, parts) or repository_has(
        root, importer, parts[:-1]
    ):
        return "internal", out, ""
    dist = IMPORT_TO_DIST.get(top, top)
    key = re.sub(r"[-_.]+", "-", dist).lower()
    where = declared.get(key, [])
    note = ",".join(where) if where else "none"
    if top in IMPORT_TO_DIST and where:
        note = f"{note} (distribution {dist})"
    return "external", out, note


def load_edges(root: Path) -> list[dict[str, Any]]:
    """Every import edge of the project, sorted by location and requested name."""
    included, skipped = collect(root)
    payload = structure_payload(build_structure(root, included, skipped))
    edges: list[dict[str, Any]] = payload["edges"]
    return sorted(
        edges,
        key=lambda e: (
            e["location"]["path"],
            e["location"]["line"],
            e["location"]["col"],
            e["requested"],
        ),
    )


def audit_unmatched(root: Path, edges: list[dict[str, Any]]) -> dict[str, object]:
    """Every `external_unmatched` package with the sections that declare it."""
    declared = declared_sections(root)
    packages: dict[str, dict[str, object]] = {}
    for edge in edges:
        if edge["target_class"] != "external_unmatched":
            continue
        top = str(edge["requested"]).split(".")[0]
        dist = IMPORT_TO_DIST.get(top, top)
        where = declared.get(re.sub(r"[-_.]+", "-", dist).lower(), [])
        entry = packages.setdefault(top, {"edges": 0, "declared_in": where})
        entry["edges"] = int(str(entry["edges"])) + 1
    total = sum(int(str(v["edges"])) for v in packages.values())
    inside = sum(int(str(v["edges"])) for v in packages.values() if v["declared_in"])
    return {
        "external_unmatched_edges": total,
        "declared_somewhere_in_pyproject": inside,
        "packages": packages,
    }


def build_rows(
    root: Path, edges: list[dict[str, Any]], seed: int, count: int
) -> list[list[str]]:
    # A seeded generator on purpose: a reproducible review sample, not a secret.
    generator = random.Random(seed)  # nosec B311
    chosen = generator.sample(edges, min(count, len(edges)))
    declared = declared_sections(root)
    contexts: dict[str, dict[int, tuple[ast.stmt, frozenset[str]]]] = {}
    rows: list[list[str]] = []
    for index, edge in enumerate(chosen, 1):
        rel = edge["location"]["path"]
        line = edge["location"]["line"]
        if rel not in contexts:
            try:
                tree = ast.parse((root / rel).read_text(encoding="utf-8"))
                contexts[rel] = import_contexts(tree)
            except (OSError, SyntaxError, UnicodeDecodeError):
                contexts[rel] = {}
        node, flags = contexts[rel].get(line, (None, frozenset()))
        boundary, expected, where = independent(
            root, rel, node, flags, edge["requested"], declared
        )
        got = str(edge["target_class"])
        got_boundary = "external" if got.startswith("external") else got
        agree = got_boundary == boundary and set(edge["flags"]) == expected
        rows.append(
            [
                str(index),
                f"{rel}:{line}:{edge['location']['col']}",
                "",
                "",
                got,
                str(edge["target"]),
                str(edge["resolution_method"]),
                ",".join(sorted(edge["flags"])),
                "agree" if agree else "DISAGREE",
                boundary,
                ",".join(sorted(expected)),
                where,
                str(edge["evidence"]).strip(),
            ]
        )
    return rows


def clean(text: str) -> str:
    return text.replace("\t", " ").replace("\n", " ").replace("\r", " ")


def write_rows(path: Path, rows: list[list[str]]) -> None:
    lines = ["\t".join(HEADER), *("\t".join(clean(c) for c in row) for row in rows)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def apply_verdicts(path: Path, verdict_file: Path) -> dict[str, int]:
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
        cells[VERDICT_COLUMN], cells[NOTE_COLUMN] = found[0], clean(found[1])
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
    parser.add_argument("--audit-unmatched", action="store_true")
    args = parser.parse_args(argv)
    root = args.project.resolve()
    edges = load_edges(root)
    rows = build_rows(root, edges, args.seed, args.sample)
    write_rows(args.out, rows)
    report: dict[str, object] = {
        "rows": len(rows),
        "seed": args.seed,
        "classes": dict(Counter(row[4] for row in rows)),
        "independent_agrees": sum(1 for row in rows if row[8] == "agree"),
        "independent_disagrees": [row[0] for row in rows if row[8] != "agree"],
    }
    if args.verdicts is not None:
        report["tally"] = apply_verdicts(args.out, args.verdicts)
    if args.audit_unmatched:
        report["unmatched_audit"] = audit_unmatched(root, edges)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
