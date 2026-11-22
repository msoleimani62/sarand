"""Structural baseline, slice S1: snapshots and the comparison of two of them.

What these tests defend (the acceptance criteria of `docs/R14D1_PLAN.md` section 5):
identical snapshots are unchanged; add, remove and change are told apart for files,
symbols, relations, edges, cycles and entry points; a content change is not an identity
change; a coverage change (a file not fully read, a path that moved into the secret
exclusion) is `uncertain` and never a removal; every verdict has its test; the output
is deterministic; and nothing in the inputs is changed.

مقایسه‌ی ساختاری (قطعه‌ی S1): یکسان = بدون تغییر؛ افزودن/حذف/تغییر جدا؛ تغییر محتوا ≠ تغییر هویت؛
تغییر پوشش «نامطمئن» است نه حذف؛ هر حکم تست دارد؛ خروجی قطعی؛ ورودی دست‌نخورده.
"""

from __future__ import annotations

import copy
import json
import random
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from sarand.structure import build_structure
from sarand.structure.compare import (
    VERDICT_COMPARABLE,
    VERDICT_IDS_ONLY,
    VERDICT_INCOMPATIBLE,
    VERDICT_INVALID,
    VERDICT_PARTIAL,
    VERDICTS,
    compare_structures,
)
from sarand.structure.serialize import structure_payload
from sarand.structure.snapshot import (
    PROBLEM_INCOMPATIBLE,
    PROBLEM_INVALID,
    SNAPSHOT_FORMAT,
    SUPPORTED_SCHEMAS,
    make_snapshot,
    read_reference,
    snapshot_text,
)

BASE = {
    "pyproject.toml": (
        '[project]\nname = "demo"\nversion = "1"\ndependencies = ["requests"]\n'
        '[project.scripts]\ndemo = "pkg.a:A"\n'
    ),
    "pkg/__init__.py": "",
    "pkg/a.py": "import os\nfrom . import b\n\n\nclass A:\n    def m(self):\n        return b.f()\n",
    "pkg/b.py": "def f():\n    return 1\n",
    "pkg/c.py": "def h():\n    return 3\n",
}


def _project(root: Path, name: str, files: dict[str, str]) -> Path:
    project = root / name
    for rel, text in files.items():
        target = project / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return project


def _payload(project: Path) -> dict[str, Any]:
    included = sorted(p.relative_to(project) for p in project.rglob("*") if p.is_file())
    return json.loads(json.dumps(structure_payload(build_structure(project, included))))


def _ref(payload: dict[str, Any], excluded: tuple[str, ...] = ()) -> Any:
    reference = read_reference(make_snapshot(payload, excluded_secret_files=excluded))
    assert reference.usable, reference.problem
    return reference


def _pair(tmp_path: Path, new_files: Mapping[str, str | None]) -> tuple[Any, Any]:
    """The reference of BASE and the reference of BASE changed by `new_files`
    (a value of None deletes the file)."""
    old = _project(tmp_path, "old", BASE)
    merged = {**BASE, **new_files}
    new = _project(tmp_path, "new", {k: v for k, v in merged.items() if v is not None})
    return _ref(_payload(old)), _ref(_payload(new))


def _statuses(result: Any, part: str) -> dict[str, int]:
    return {k: v for k, v in result.payload["summary"][part].items() if v}


# ---------------------------------------------------------------- snapshots


def test_identical_snapshots_are_unchanged_everywhere(tmp_path: Path) -> None:
    old, _ = _pair(tmp_path, {})
    result = compare_structures(old, old)
    assert result.verdict == VERDICT_COMPARABLE
    assert result.payload["reasons"] == []
    assert result.payload["uncertain_paths"] == []
    assert all(entries == [] for entries in result.payload["changes"].values())
    for part, counts in result.payload["summary"].items():
        assert {k: v for k, v in counts.items() if k != "unchanged" and v} == {}, part
    assert result.payload["summary"]["symbols"]["unchanged"] == 4


def test_two_builds_of_the_same_project_are_unchanged(tmp_path: Path) -> None:
    old, new = _pair(tmp_path, {})
    result = compare_structures(old, new)
    assert result.verdict == VERDICT_COMPARABLE
    assert all(entries == [] for entries in result.payload["changes"].values())


def test_a_snapshot_has_no_time_and_a_stable_digest(tmp_path: Path) -> None:
    payload = _payload(_project(tmp_path, "p", BASE))
    first = snapshot_text(make_snapshot(payload))
    second = snapshot_text(make_snapshot(copy.deepcopy(payload)))
    assert first == second
    data = json.loads(first)
    assert data["digest"].startswith("sha256:")
    assert data["snapshot_format"] == SNAPSHOT_FORMAT
    assert set(data) == {
        "kind",
        "snapshot_format",
        "structure_schema",
        "language",
        "fingerprint_basis",
        "settings",
        "structure",
        "digest",
    }
    assert read_reference(data).source == "snapshot"


def test_the_settings_are_part_of_the_digest(tmp_path: Path) -> None:
    payload = _payload(_project(tmp_path, "p", BASE))
    plain = make_snapshot(payload)
    other = make_snapshot(payload, excluded_secret_files=["x.py"], max_file_size=10)
    assert plain["digest"] != other["digest"]
    assert read_reference(other).excluded_secret_files == ("x.py",)
    assert read_reference(other).max_file_size == 10


def test_a_report_with_a_structure_key_is_a_reference(tmp_path: Path) -> None:
    payload = _payload(_project(tmp_path, "p", BASE))
    report = {
        "schema_version": "1.10",
        "structure": payload,
        "excluded_secret_files": ["s.py"],
    }
    reference = read_reference(report)
    assert reference.usable
    assert reference.source == "report"
    assert reference.excluded_secret_files == ("s.py",)


def test_the_builder_schema_is_one_the_comparison_supports(tmp_path: Path) -> None:
    payload = _payload(_project(tmp_path, "p", BASE))
    assert payload["schema"] in SUPPORTED_SCHEMAS
    assert payload["meta"]["fingerprint_basis"]


# ------------------------------------------------------------ what changed


def test_a_content_change_is_not_an_identity_change(tmp_path: Path) -> None:
    old, new = _pair(tmp_path, {"pkg/b.py": "def f():\n    return 2\n"})
    result = compare_structures(old, new)
    assert result.verdict == VERDICT_COMPARABLE
    (entry,) = result.payload["changes"]["symbols"]
    assert entry["status"] == "content_changed"
    assert entry["old"] == entry["new"]  # the same id on both sides
    assert _statuses(result, "symbols") == {"content_changed": 1, "unchanged": 3}
    (file_entry,) = result.payload["changes"]["files"]
    assert file_entry["status"] == "changed"
    assert file_entry["fields"] == ["content"]


def test_a_formatting_change_is_not_a_structural_change(tmp_path: Path) -> None:
    old, new = _pair(tmp_path, {"pkg/b.py": "def f( ):\n\n    return  1  # note\n"})
    result = compare_structures(old, new)
    assert result.payload["changes"]["symbols"] == []
    assert _statuses(result, "files")["changed"] == 1  # the file hash did change


def test_added_symbol_file_module_and_relation(tmp_path: Path) -> None:
    new_c = (
        "from . import b\n\n\ndef h():\n    return b.f()\n\n\ndef k():\n    return 4\n"
    )
    old, new = _pair(
        tmp_path, {"pkg/c.py": new_c, "pkg/d.py": "def n():\n    return 5\n"}
    )
    result = compare_structures(old, new)
    assert result.verdict == VERDICT_COMPARABLE
    added = [
        e["qualname"]
        for e in result.payload["changes"]["symbols"]
        if e["status"] == "added"
    ]
    assert sorted(added) == ["k", "n"]
    assert [
        e["path"] for e in result.payload["changes"]["files"] if e["status"] == "added"
    ] == ["pkg/d.py"]
    assert [
        e["name"]
        for e in result.payload["changes"]["modules"]
        if e["status"] == "added"
    ] == ["pkg.d"]
    relations = result.payload["changes"]["relations"]
    assert [(e["status"], e["source"], e["target"]) for e in relations] == [
        ("added", "h", "f")
    ]
    edges = result.payload["changes"]["edges"]
    assert [(e["status"], e["source"]) for e in edges] == [("added", "pkg.c")]


def test_removed_file_takes_its_symbols_and_relations_with_it(tmp_path: Path) -> None:
    old, new = _pair(tmp_path, {"pkg/b.py": None, "pkg/a.py": "import os\n"})
    result = compare_structures(old, new)
    removed = {
        e["qualname"]
        for e in result.payload["changes"]["symbols"]
        if e["status"] == "removed"
    }
    assert removed == {"f", "A", "A.m"}
    # the one relation belonged to symbols that are gone: counted, not listed twice
    counts = result.payload["summary"]["relations"]
    assert counts["removed_with_symbol"] == 1
    assert counts["removed"] == 0
    assert result.payload["changes"]["relations"] == []


def test_a_changed_relation_count_is_a_changed_relation(tmp_path: Path) -> None:
    twice = BASE["pkg/a.py"].replace("return b.f()", "return b.f() + b.f()")
    old, new = _pair(tmp_path, {"pkg/a.py": twice})
    result = compare_structures(old, new)
    (entry,) = result.payload["changes"]["relations"]
    assert (entry["status"], entry["source"], entry["target"]) == (
        "changed",
        "A.m",
        "f",
    )
    assert [v["count"] for v in entry["old"]] == [1]
    assert [v["count"] for v in entry["new"]] == [2]
    assert result.payload["summary"]["relations"]["removed"] == 0
    assert result.payload["summary"]["relations"]["added_with_symbol"] == 0


def test_a_moved_symbol_is_probable_and_never_a_definite_match(tmp_path: Path) -> None:
    moved_old = {"pkg/b.py": "def f():\n    return 1\n"}
    moved_new = {"pkg/b.py": None, "pkg/e.py": "def f():\n    return 1\n"}
    old = _ref(_payload(_project(tmp_path, "o", {**BASE, **moved_old})))
    new = _ref(
        _payload(
            _project(
                tmp_path, "n", {k: v for k, v in {**BASE, **moved_new}.items() if v}
            )
        )
    )
    result = compare_structures(old, new)
    moved = [e for e in result.payload["changes"]["symbols"] if e["status"] == "moved"]
    assert [e["qualname"] for e in moved] == ["f"]
    assert moved[0]["old"] != moved[0]["new"]


def test_a_changed_cycle_and_entry_point(tmp_path: Path) -> None:
    cyclic = {
        "pkg/a.py": "from . import b\n\n\nclass A:\n    pass\n",
        "pkg/b.py": "from . import a\n\n\ndef f():\n    return a.A\n",
        "pyproject.toml": BASE["pyproject.toml"].replace("pkg.a:A", "pkg.b:f"),
    }
    old, new = _pair(tmp_path, cyclic)
    result = compare_structures(old, new)
    cycles = result.payload["changes"]["cycles"]
    assert [(c["status"], c["modules"]) for c in cycles] == [
        ("added", ["pkg.a", "pkg.b"])
    ]
    points = result.payload["changes"]["entry_points"]
    assert {(p["status"], p["target"]) for p in points} == {
        ("removed", "pkg.a:A"),
        ("added", "pkg.b:f"),
    }


def test_external_packages_added_and_removed(tmp_path: Path) -> None:
    changed = {"pkg/a.py": "import json\nfrom . import b\n\n\nclass A:\n    pass\n"}
    old, new = _pair(tmp_path, changed)
    externals = compare_structures(old, new).payload["changes"]["externals"]
    assert {(e["status"], e["name"]) for e in externals} == {
        ("removed", "os"),
        ("added", "json"),
    }


# --------------------------------------------------------------- verdicts


def test_ids_only_when_the_fingerprint_bases_differ(tmp_path: Path) -> None:
    old, new = _pair(tmp_path, {"pkg/b.py": "def f():\n    return 2\n"})
    other = copy.deepcopy(dict(new.structure))
    other["meta"]["fingerprint_basis"] = "fp1/python-3.99"
    result = compare_structures(old, _ref(other))
    assert result.verdict == VERDICT_IDS_ONLY
    assert result.payload["fingerprints_comparable"] is False
    statuses = {e["status"] for e in result.payload["changes"]["symbols"]}
    assert "content_changed" not in statuses
    assert statuses == {"content_unknown"}
    assert any("fingerprint bases differ" in r for r in result.payload["reasons"])


def test_a_file_that_is_not_fully_parsed_makes_its_changes_uncertain(
    tmp_path: Path,
) -> None:
    old, new = _pair(tmp_path, {"pkg/c.py": "def h(:\n"})
    result = compare_structures(old, new)
    assert result.verdict == VERDICT_PARTIAL
    paths = result.payload["uncertain_paths"]
    assert [p["path"] for p in paths] == ["pkg/c.py"]
    assert any("failed" in r for r in paths[0]["reasons"])
    symbols = result.payload["changes"]["symbols"]
    assert [(e["qualname"], e["status"]) for e in symbols] == [("h", "uncertain")]
    assert result.payload["summary"]["symbols"]["removed"] == 0
    (file_entry,) = [
        e for e in result.payload["changes"]["files"] if e["path"] == "pkg/c.py"
    ]
    assert file_entry["status"] == "uncertain"


def test_a_path_moving_into_the_secret_exclusion_is_uncertain_not_removed(
    tmp_path: Path,
) -> None:
    old = _ref(_payload(_project(tmp_path, "o", BASE)))
    new_files = {k: v for k, v in BASE.items() if k != "pkg/c.py"}
    new = _ref(_payload(_project(tmp_path, "n", new_files)), excluded=("pkg/c.py",))
    result = compare_structures(old, new)
    assert result.verdict == VERDICT_PARTIAL
    assert result.payload["uncertain_paths"] == [
        {"path": "pkg/c.py", "reasons": ["secret_exclusion_changed"]}
    ]
    assert result.payload["summary"]["symbols"]["removed"] == 0
    assert result.payload["summary"]["symbols"]["uncertain"] == 1
    assert result.payload["summary"]["files"]["removed"] == 0


def test_an_external_that_vanishes_with_uncertain_files_is_uncertain(
    tmp_path: Path,
) -> None:
    old, new = _pair(tmp_path, {"pkg/c.py": "def h(:\n"})
    # the reference imported `zzz` somewhere; the current state cannot say
    with_extra = copy.deepcopy(dict(old.structure))
    with_extra["externals"].append(
        {"name": "zzz", "target_class": "external_unmatched", "declared_in": []}
    )
    result = compare_structures(_ref(with_extra), new)
    entry = next(
        e for e in result.payload["changes"]["externals"] if e["name"] == "zzz"
    )
    assert entry["status"] == "uncertain"


def test_ambiguous_symbols_and_the_relations_that_touch_them(tmp_path: Path) -> None:
    old, new = _pair(tmp_path, {})
    doubled = copy.deepcopy(dict(new.structure))
    original = next(s for s in doubled["symbols"] if s["qualname"] == "f")
    twin = {**original, "id": "sym:0000000000aa", "fingerprint": "fp1:aaaaaaaaaaaa"}
    doubled["symbols"].append(twin)
    original["fingerprint"] = "fp1:bbbbbbbbbbbb"
    result = compare_structures(old, _ref(doubled))
    assert result.payload["summary"]["symbols"]["ambiguous"] == 1
    uncertain = [
        e for e in result.payload["changes"]["relations"] if e["status"] == "uncertain"
    ]
    assert uncertain
    assert {e["reason"] for e in uncertain} == {"ambiguous_symbol"}


def test_incompatible_and_invalid_references_compare_nothing(tmp_path: Path) -> None:
    payload = _payload(_project(tmp_path, "p", BASE))
    good = _ref(payload)
    future = copy.deepcopy(payload)
    future["schema"] = 99
    odd = read_reference({"schema_version": "9", "structure": future})
    assert odd.problem_kind == PROBLEM_INCOMPATIBLE
    result = compare_structures(good, odd)
    assert result.verdict == VERDICT_INCOMPATIBLE
    assert result.payload["changes"] == {}
    assert "current:" in result.payload["reasons"][0]

    broken = read_reference({"kind": "sarand-structure-snapshot"})
    assert broken.problem_kind == PROBLEM_INVALID
    result = compare_structures(broken, good)
    assert result.verdict == VERDICT_INVALID
    assert result.payload["reasons"][0].startswith("reference:")
    assert result.payload["summary"] == {}


def test_invalid_beats_incompatible(tmp_path: Path) -> None:
    payload = _payload(_project(tmp_path, "p", BASE))
    future = copy.deepcopy(payload)
    future["schema"] = 99
    incompatible = read_reference({"structure": future})
    invalid = read_reference(["not", "an", "object"])
    assert compare_structures(incompatible, invalid).verdict == VERDICT_INVALID


def test_every_way_a_snapshot_can_be_unusable(tmp_path: Path) -> None:
    payload = _payload(_project(tmp_path, "p", BASE))
    snap = make_snapshot(payload)

    def with_change(change: Any) -> Any:
        data = copy.deepcopy(snap)
        change(data)
        return read_reference(data)

    tampered = with_change(lambda d: d["structure"]["symbols"].pop())
    assert tampered.problem_kind == PROBLEM_INVALID
    assert "digest" in tampered.problem
    assert (
        with_change(lambda d: d.update(snapshot_format=2)).problem_kind
        == PROBLEM_INCOMPATIBLE
    )
    assert (
        with_change(lambda d: d.update(snapshot_format="1")).problem_kind
        == PROBLEM_INVALID
    )
    assert with_change(lambda d: d.pop("digest")).problem_kind == PROBLEM_INVALID
    assert with_change(lambda d: d.pop("settings")).problem_kind == PROBLEM_INVALID
    assert read_reference({"schema_version": "1.10"}).problem_kind == PROBLEM_INVALID
    assert "without --structure" in read_reference({"schema_version": "1.10"}).problem
    assert read_reference(None).problem_kind == PROBLEM_INVALID
    missing = copy.deepcopy(payload)
    missing["symbols"][0].pop("qualname")
    assert read_reference({"structure": missing}).problem_kind == PROBLEM_INVALID
    wrong_language = copy.deepcopy(payload)
    wrong_language["language"] = "go"
    assert (
        read_reference({"structure": wrong_language}).problem_kind
        == PROBLEM_INCOMPATIBLE
    )
    with pytest.raises(ValueError):
        make_snapshot({"schema": 4})


def test_a_snapshot_whose_envelope_disagrees_with_its_structure_is_invalid(
    tmp_path: Path,
) -> None:
    snap = make_snapshot(_payload(_project(tmp_path, "p", BASE)))
    from sarand.structure.snapshot import digest_of

    snap["fingerprint_basis"] = "fp1/python-3.99"
    snap["digest"] = digest_of(snap)  # a consistent digest does not hide the mismatch
    assert read_reference(snap).problem_kind == PROBLEM_INVALID


def test_the_size_limits_differing_make_the_comparison_partial(tmp_path: Path) -> None:
    payload = _payload(_project(tmp_path, "p", BASE))
    old = read_reference(make_snapshot(payload, max_file_size=100))
    new = read_reference(make_snapshot(payload, max_file_size=200))
    result = compare_structures(old, new)
    assert result.verdict == VERDICT_PARTIAL
    assert any("size limits differ" in r for r in result.payload["reasons"])


# ---------------------------------------------- determinism and no side effects


def _shuffled(structure: dict[str, Any], seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    data = copy.deepcopy(structure)
    for name in (
        "files",
        "modules",
        "externals",
        "edges",
        "cycles",
        "symbols",
        "relations",
        "entry_points",
    ):
        rng.shuffle(data[name])
    return data


def test_the_output_does_not_depend_on_the_order_of_the_input(tmp_path: Path) -> None:
    changed = {
        "pkg/b.py": "def f():\n    return 2\n\n\ndef g():\n    return f()\n",
        "pkg/d.py": "import json\n",
        "pkg/c.py": None,
    }
    old, new = _pair(tmp_path, changed)
    reference = compare_structures(old, new).to_json()
    assert json.loads(reference)["verdict"] == VERDICT_COMPARABLE
    for seed in range(5):
        again = compare_structures(
            _ref(_shuffled(dict(old.structure), seed)),
            _ref(_shuffled(dict(new.structure), seed + 100)),
        )
        assert again.to_json() == reference


def test_a_comparison_changes_neither_input(tmp_path: Path) -> None:
    old, new = _pair(
        tmp_path, {"pkg/b.py": "def f():\n    return 2\n", "pkg/c.py": None}
    )
    before = (
        json.dumps(old.structure, sort_keys=True),
        json.dumps(new.structure, sort_keys=True),
    )
    compare_structures(old, new)
    after = (
        json.dumps(old.structure, sort_keys=True),
        json.dumps(new.structure, sort_keys=True),
    )
    assert before == after


def test_the_verdict_vocabulary_is_closed(tmp_path: Path) -> None:
    old, new = _pair(tmp_path, {})
    assert compare_structures(old, new).verdict in VERDICTS
    assert VERDICTS == (
        "comparable",
        "ids_only",
        "partial",
        "incompatible",
        "invalid",
    )


def test_the_comparison_does_not_need_the_findings_side() -> None:
    import subprocess
    import sys

    code = (
        "import sys, sarand.structure.compare;"
        "bad = [m for m in sys.modules if m.startswith(('sarand.renderers', 'sarand.cli'))];"
        "print(bad)"
    )
    done = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert done.stdout.strip() == "[]"
