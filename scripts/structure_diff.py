"""Compare two structure outputs of the same project (R14-A3 regression evidence).

Run `dump` once with each version of the code on the same project (select the code with
`PYTHONPATH`), then `diff` the two files. The diff says which parts of the output are
identical and, for the parts that changed, exactly what changed, so that a change meant
for one kind of result (for example the classification of external imports) can be shown
not to have touched anything else.

Usage:
    PYTHONPATH=OLD/python python scripts/structure_diff.py dump PROJECT OLD.json
    PYTHONPATH=NEW/python python scripts/structure_diff.py dump PROJECT NEW.json
    python scripts/structure_diff.py diff OLD.json NEW.json

مقایسه‌ی دو خروجی ساختار از یک پروژه با دو نسخه‌ی کد؛ نشان می‌دهد چه چیزی عوض شده و چه چیزی نه.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from sarand.structure import build_structure
from sarand.structure.serialize import structure_payload

SKIPPED_DIRS = frozenset(
    {".git", "__pycache__", "node_modules", "target", ".venv", "venv", ".tox", "build"}
)
SIZE_LIMIT = 1_000_000
# The top-level parts compared whole; `edges`, `externals`, `summary` and `sites` are
# compared in detail below.
WHOLE_PARTS = (
    "cycles",
    "entry_points",
    "files",
    "language",
    "modules",
    "relations",
    "symbols",
)


def dump(project: Path, out: Path) -> dict[str, Any]:
    """Write the structure payload of `project`, built by the code on `PYTHONPATH`."""
    root = project.resolve()
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
    payload: dict[str, Any] = structure_payload(
        build_structure(root, included, skipped)
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return payload


def _changed(old: dict[str, Any], new: dict[str, Any]) -> dict[str, list[Any]]:
    return {
        k: [old.get(k), new.get(k)]
        for k in sorted(set(old) | set(new))
        if old.get(k) != new.get(k)
    }


def compare(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """What differs between two payloads, and whether only external imports changed."""
    report: dict[str, Any] = {
        "schema": [old.get("schema"), new.get("schema")],
        "identical_parts": [p for p in WHOLE_PARTS if old.get(p) == new.get(p)],
        "changed_parts": [p for p in WHOLE_PARTS if old.get(p) != new.get(p)],
        "meta_changed": _changed(old.get("meta", {}), new.get("meta", {})),
        "summary_changed": _changed(old.get("summary", {}), new.get("summary", {})),
        "sites_changed": _changed(old.get("sites", {}), new.get("sites", {})),
    }
    old_edges, new_edges = old.get("edges", []), new.get("edges", [])
    report["edge_counts"] = [len(old_edges), len(new_edges)]
    if len(old_edges) != len(new_edges):
        report["only_external_edges_changed"] = False
        changed_edges: list[tuple[dict[str, Any], dict[str, Any]]] = []
    else:
        changed_edges = [
            (a, b) for a, b in zip(old_edges, new_edges, strict=True) if a != b
        ]
        report["only_external_edges_changed"] = all(
            str(a.get("target_class", "")).startswith("external")
            and str(b.get("target_class", "")).startswith("external")
            and (a.get("location"), a.get("requested"))
            == (b.get("location"), b.get("requested"))
            for a, b in changed_edges
        )
    report["edges_changed"] = len(changed_edges)
    report["edge_fields_changed"] = dict(
        Counter(
            f
            for a, b in changed_edges
            for f in sorted(set(a) | set(b))
            if a.get(f) != b.get(f)
        )
    )
    old_ext = {x["name"]: x for x in old.get("externals", [])}
    new_ext = {x["name"]: x for x in new.get("externals", [])}
    report["externals_same_names"] = set(old_ext) == set(new_ext)
    report["externals_changed"] = [
        {
            "name": name,
            "class": [
                old_ext[name].get("target_class"),
                new_ext[name].get("target_class"),
            ],
            "declared_in": [
                old_ext[name].get("declared_in"),
                new_ext[name].get("declared_in"),
            ],
        }
        for name in sorted(set(old_ext) & set(new_ext))
        if old_ext[name] != new_ext[name]
    ]
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("dump")
    one.add_argument("project", type=Path)
    one.add_argument("out", type=Path)
    two = sub.add_parser("diff")
    two.add_argument("old", type=Path)
    two.add_argument("new", type=Path)
    args = parser.parse_args(argv)
    if args.command == "dump":
        payload = dump(args.project, args.out)
        print(
            f"wrote {args.out} ({sys.version.split()[0]}, schema {payload['schema']})"
        )
        return 0
    old = json.loads(args.old.read_text(encoding="utf-8"))
    new = json.loads(args.new.read_text(encoding="utf-8"))
    print(json.dumps(compare(old, new), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
