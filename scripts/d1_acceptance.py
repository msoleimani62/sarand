"""Real-run acceptance of the R14-D1 contracts (slice C, criterion 10).

For each project it runs the real `sarand` command on a COPY of the project (the original
is never touched) and checks, from the real outputs only:

  A1  the reference run (JSON, `--structure`, snapshot) exits 0 and writes valid JSON;
  A2  every key of that report is documented in `docs/JSON_SCHEMA.md` (both languages);
  A3  a run against the reference of the same, unchanged project exits 0 with the gate
      `pass`;
  A4  the findings comparison of that run has nothing new, fixed or changed;
  A5  its structural comparison is `comparable` with nothing added, removed, changed or
      uncertain;
  A6  after adding a text file with a planted secret and a Python file, and removing
      another Python file, the same command with `--baseline-gate new` exits with code 3
      (a file with a secret is left out of the structure on purpose, so the added Python
      file is a separate one);
  A7  the gate failed on the planted secret (a new `hardcoded_secrets` finding);
  A8  the structural comparison reports the added and the removed file;
  A9  the keys of that run (including `baseline`, its `gate` and `structure_comparison`)
      are documented;
  A10 a waiver for the planted secret turns the same run into exit 0 with one waived item;
  A11 the SARIF result of the planted secret carries the id the gate printed as its
      `partialFingerprints.sarandFindingId/v1`.

The planted credential is built at run time and exists only in the copy.

    python scripts/d1_acceptance.py --out DIR --project LABEL=PATH [--project ...]
        [--code PYTHON_DIR]

Exit code 0 when every check passes, 1 otherwise. `acceptance.json` is the record and
`acceptance.md` the same for reading.

پذیرش واقعی قراردادهای R14-D1: فرمان واقعی `sarand` روی یک کپی از پروژه اجرا می‌شود (اصل هرگز
دست نمی‌خورد) و فقط از خروجی واقعی بررسی می‌شود.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CODE = _ROOT / "python"
_IGNORED = shutil.ignore_patterns(
    ".git",
    ".venv",
    "venv",
    "target",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "dist",
    "build",
    "*.egg-info",
)
PLANTED_NAME = "d1_acceptance_secret.txt"
ADDED_NAME = "d1_acceptance_added.py"
_NESTED = (
    ("baseline", ("schema", "reference", "current", "summary", "findings", "gate")),
    ("gate", ("policy", "verdict", "failed_on", "waived", "uncertain", "waivers")),
    (
        "structure_comparison",
        (
            "schema",
            "verdict",
            "reasons",
            "fingerprints_comparable",
            "old",
            "new",
            "uncertain_paths",
            "summary",
            "changes",
        ),
    ),
)


# ------------------------------------------------------------------- documentation


def documented_top_level(text: str) -> set[str]:
    """The keys of the top-level table of `docs/JSON_SCHEMA.md` (or its Persian twin).
    کلیدهای جدول سطح بالای سند schema."""
    parts = text.split("\n## ", 3)
    table = next(p for p in parts if p.startswith(("Top-level", "کلیدهای")))
    return set(re.findall(r"^\| `(\w+)` \|", table, re.MULTILINE))


def mentioned(text: str, name: str) -> bool:
    """Whether `name` appears as inline code in the document."""
    return f"`{name}`" in text


def undocumented(report: Mapping[str, Any], docs: Mapping[str, str]) -> list[str]:
    """What a real report writes that the schema documents do not list: a top-level key
    missing from a table, or a key of `baseline`, its `gate` or `structure_comparison`
    that no page mentions."""
    problems: list[str] = []
    for lang, text in docs.items():
        for key in sorted(set(report) - documented_top_level(text)):
            problems.append(f"top-level key `{key}` is not in the {lang} table")
    combined = "\n".join(docs.values())
    nested = {
        "baseline": report.get("baseline"),
        "gate": (report.get("baseline") or {}).get("gate"),
        "structure_comparison": report.get("structure_comparison"),
    }
    for label, keys in _NESTED:
        body = nested.get(label)
        if not isinstance(body, Mapping):
            continue
        for key in sorted(set(body) - set(keys)):
            problems.append(f"`{label}` has the undocumented key `{key}`")
        for key in keys:
            if key in body and not mentioned(combined, key):
                problems.append(f"`{key}` of `{label}` is not mentioned in the schema")
    version = str(report.get("schema_version", ""))
    for lang, text in docs.items():
        if version not in text:
            problems.append(
                f"schema version {version} is not stated in the {lang} page"
            )
    return problems


# ------------------------------------------------------------------------ running


def _env(code_dir: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(code_dir), *filter(None, [env.get("PYTHONPATH")])]
    )
    return env


def run_cli(
    code_dir: Path, project: Path, out_dir: Path, name: str, extra: Sequence[str]
) -> tuple[int, str]:
    """Run the real command once; return its exit code and the path of the output."""
    command = [
        sys.executable,
        "-m",
        "sarand",
        "--project",
        str(project),
        "--skip-tests",
        "--output-dir",
        str(out_dir),
        "--output-name",
        name,
        *extra,
    ]
    done = subprocess.run(  # nosec B603
        command, env=_env(code_dir), capture_output=True, text=True, check=False
    )
    return done.returncode, str(out_dir / name)


def _load(path: str) -> dict[str, Any] | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _planted_secret() -> str:
    # Built from pieces so that no secret-looking literal sits in this repository.
    # از تکه‌ها ساخته می‌شود تا literal شبیه secret در مخزن نماند.
    return 'AWS_KEY = "' + "AKIA" + 'IOSFODNN7EXAMPLE"\n'


def mutate(copy: Path) -> dict[str, str | None]:
    """Plant a secret in a new text file, add a clean Python file and remove one existing
    Python file of the copy."""
    (copy / PLANTED_NAME).write_text(_planted_secret(), encoding="utf-8")
    (copy / ADDED_NAME).write_text(
        "def d1_acceptance_added() -> int:\n    return 1\n", encoding="utf-8"
    )
    candidates = sorted(
        p
        for p in copy.rglob("*.py")
        if p.name not in {ADDED_NAME, "__init__.py", "conftest.py"}
        and p.stat().st_size < 20_000
    )
    removed: str | None = None
    if candidates:
        removed = candidates[-1].relative_to(copy).as_posix()
        candidates[-1].unlink()
    return {"planted": PLANTED_NAME, "added": ADDED_NAME, "removed": removed}


def _check(ident: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"id": ident, "ok": bool(ok), "detail": detail}


def _sum(summary: Mapping[str, Any], *states: str) -> int:
    return sum(
        int(group.get(state, 0))
        for group in summary.values()
        if isinstance(group, Mapping)
        for state in states
    )


def acceptance_for(
    code_dir: Path, source: Path, work: Path, docs: Mapping[str, str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run every check on a copy of `source`; return the checks and facts about the run."""
    copy = work / "project"
    shutil.copytree(source, copy, ignore=_IGNORED)
    out = work / "out"
    out.mkdir()
    checks: list[dict[str, Any]] = []
    facts: dict[str, Any] = {}
    snapshot = str(work / "snap.json")

    code, ref_path = run_cli(
        code_dir,
        copy,
        out,
        "ref.json",
        ["--format", "json", "--structure", "--structure-snapshot", snapshot],
    )
    reference = _load(ref_path)
    checks.append(_check("A1", code == 0 and reference is not None, f"exit {code}"))
    if reference is None:
        return checks, facts
    facts["schema_version"] = reference.get("schema_version")
    facts["files"] = len(reference.get("included_files", []))
    problems = undocumented(reference, docs)
    checks.append(_check("A2", not problems, "; ".join(problems) or "all documented"))

    base = ["--format", "json", "--structure", "--structure-baseline", snapshot]
    base += ["--baseline", ref_path, "--baseline-gate", "new"]
    code, path = run_cli(code_dir, copy, out, "same.json", base)
    same = _load(path)
    gate = ((same or {}).get("baseline") or {}).get("gate") or {}
    checks.append(
        _check(
            "A3",
            code == 0 and gate.get("verdict") == "pass",
            f"exit {code}, gate {gate.get('verdict')}",
        )
    )
    summary = ((same or {}).get("baseline") or {}).get("summary") or {}
    moved = _sum(summary, "new", "fixed", "changed")
    checks.append(
        _check(
            "A4",
            same is not None and moved == 0,
            f"{moved} finding(s) new, fixed or changed",
        )
    )
    comparison = (same or {}).get("structure_comparison") or {}
    changed = _sum(
        comparison.get("summary") or {}, "added", "removed", "changed", "uncertain"
    )
    checks.append(
        _check(
            "A5",
            comparison.get("verdict") == "comparable" and changed == 0,
            f"verdict {comparison.get('verdict')}, {changed} structural change(s)",
        )
    )

    facts["mutation"] = mutate(copy)
    code, path = run_cli(code_dir, copy, out, "changed.json", base)
    changed_report = _load(path)
    checks.append(_check("A6", code == 3, f"exit {code} (3 expected)"))
    failed = (((changed_report or {}).get("baseline") or {}).get("gate") or {}).get(
        "failed_on", []
    )
    secret_ids = [
        i["id"] for i in failed if str(i.get("id", "")).startswith("hardcoded_secrets:")
    ]
    checks.append(
        _check(
            "A7",
            bool(secret_ids),
            f"{len(secret_ids)} new secret finding(s) failed the gate",
        )
    )
    files = (
        ((changed_report or {}).get("structure_comparison") or {})
        .get("summary", {})
        .get("files", {})
    )
    wanted_removed = 1 if facts["mutation"]["removed"] else 0
    checks.append(
        _check(
            "A8",
            files.get("added", 0) >= 1 and files.get("removed", 0) >= wanted_removed,
            f"files added {files.get('added')}, removed {files.get('removed')}",
        )
    )
    problems = undocumented(changed_report or {}, docs)
    checks.append(
        _check(
            "A9",
            changed_report is not None and not problems,
            "; ".join(problems) or "all documented",
        )
    )

    if secret_ids:
        today = date.today()
        (copy / ".sarand.toml").write_text(
            "[[waivers]]\n"
            f'id = "{secret_ids[0]}"\n'
            'reason = "planted by the acceptance run"\n'
            'owner = "d1-acceptance"\n'
            f"created = {today.isoformat()}\n"
            f"expires = {(today + timedelta(days=7)).isoformat()}\n",
            encoding="utf-8",
        )
        code, path = run_cli(code_dir, copy, out, "waived.json", base)
        waived = (((_load(path) or {}).get("baseline") or {}).get("gate") or {}).get(
            "waived", []
        )
        other_failures = len(failed) - 1
        checks.append(
            _check(
                "A10",
                code == (3 if other_failures else 0) and len(waived) == 1,
                f"exit {code}, {len(waived)} waived, {other_failures} other failure(s)",
            )
        )
        code, path = run_cli(
            code_dir, copy, out, "changed.sarif", ["--format", "sarif"]
        )
        log = _load(path)
        fingerprints = [
            r.get("partialFingerprints", {}).get("sarandFindingId/v1")
            for r in ((log or {}).get("runs") or [{}])[0].get("results", [])
        ]
        checks.append(
            _check(
                "A11",
                secret_ids[0] in fingerprints,
                f"exit {code}, {len(fingerprints)} fingerprinted result(s)",
            )
        )
    else:
        checks.append(_check("A10", False, "no secret id to waive (A7 failed)"))
        checks.append(_check("A11", False, "no secret id to look for (A7 failed)"))
    return checks, facts


# ---------------------------------------------------------------------- reporting


def render_markdown(report: Mapping[str, Any]) -> str:
    """The acceptance record as a readable page."""
    env = report["environment"]
    lines = [
        "# R14-D1 real-run acceptance",
        "",
        (
            f"Python {env['python']}, {env['platform']}, {env['cpu_count']} CPUs; "
            f"code `{env['code']}`."
        ),
        "",
    ]
    for project in report["projects"]:
        facts = project["facts"]
        lines += [
            f"## {project['label']}",
            "",
            (
                f"{facts.get('files', '?')} files; schema {facts.get('schema_version')}; "
                f"planted `{facts.get('mutation', {}).get('planted')}`, added "
                f"`{facts.get('mutation', {}).get('added')}`, removed "
                f"`{facts.get('mutation', {}).get('removed')}`."
            ),
            "",
            "| check | result | detail |",
            "|---|---|---|",
        ]
        for c in project["checks"]:
            lines.append(
                f"| {c['id']} | {'Pass' if c['ok'] else 'FAIL'} | {c['detail']} |"
            )
        lines.append("")
    verdict = "all checks passed" if report["passed"] else "AT LEAST ONE CHECK FAILED"
    return "\n".join([*lines, f"**{verdict}**", ""])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--project", action="append", default=[], metavar="LABEL=PATH")
    parser.add_argument("--code", type=Path, default=_DEFAULT_CODE)
    args = parser.parse_args(argv)
    projects: list[tuple[str, Path]] = []
    for item in args.project:
        label, sep, raw = item.partition("=")
        if not sep or not label or not Path(raw).is_dir():
            parser.error(f"--project expects LABEL=DIRECTORY, got {item!r}")
        projects.append((label, Path(raw)))
    if not projects:
        parser.error("at least one --project is required")
    docs = {
        "en": (_ROOT / "docs" / "JSON_SCHEMA.md").read_text(encoding="utf-8"),
        "fa": (_ROOT / "docs" / "JSON_SCHEMA.fa.md").read_text(encoding="utf-8"),
    }
    results: list[dict[str, Any]] = []
    for label, source in projects:
        print(f"acceptance {label}", file=sys.stderr, flush=True)
        with tempfile.TemporaryDirectory() as tmp:
            checks, facts = acceptance_for(args.code, source, Path(tmp), docs)
        results.append({"label": label, "checks": checks, "facts": facts})
    report = {
        "schema": 1,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            "code": str(args.code),
        },
        "projects": results,
        "passed": all(c["ok"] for r in results for c in r["checks"]),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "acceptance.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.out / "acceptance.md").write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {args.out / 'acceptance.json'} and {args.out / 'acceptance.md'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
