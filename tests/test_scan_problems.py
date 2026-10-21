"""A path the scan cannot read is reported, not dropped (AGENTS.md 5.74).

Before, a directory without permission (or a file that vanished mid-scan) simply
vanished from every count of the report, in the Rust core (`filter_map(|e| e.ok())`)
and in the Python fallback (`except OSError: continue`) alike.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sarand import rust_bridge
from sarand.constants import HASH_MAX_BYTES, IGNORE_DIRS, MAX_HASH_FILES
from sarand.models.results import EnvironmentInfo, GitSnapshot, ProjectStats, ReportData
from sarand.renderers import json_renderer, markdown
from sarand.rust_bridge import ScanProblems, scan_project_report


def _can_read_anything() -> bool:
    geteuid = getattr(os, "geteuid", None)
    return os.name == "nt" or (geteuid is not None and geteuid() == 0)


def _locked_project(root: Path) -> Path:
    (root / "open.py").write_text("x = 1\n", encoding="utf-8")
    locked = root / "locked"
    locked.mkdir()
    (locked / "secret.py").write_text("y = 2\n", encoding="utf-8")
    locked.chmod(0)
    return locked


def _unlock(path: Path) -> None:
    path.chmod(stat.S_IRWXU)


def test_scan_problems_counts_everything_and_keeps_the_first_few() -> None:
    problems = ScanProblems()
    for index in range(12):
        problems.add(f"problem {index}")
    assert problems.skipped == 12
    assert problems.samples == [f"problem {index}" for index in range(5)]


def test_a_clean_tree_reports_no_problems() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "a.py").write_text("x = 1\n", encoding="utf-8")
        records, problems = scan_project_report(root)
    assert [record["rel_path"] for record in records] == ["a.py"]
    assert problems.skipped == 0
    assert problems.samples == []


def test_the_python_fallback_reports_an_unreadable_directory() -> None:
    if _can_read_anything():
        pytest.skip("this account can read a directory with mode 000")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        locked = _locked_project(root)
        try:
            problems = ScanProblems()
            records = rust_bridge._pure_python_scan(
                root, IGNORE_DIRS, HASH_MAX_BYTES, MAX_HASH_FILES, problems=problems
            )
        finally:
            _unlock(locked)
    assert [record["rel_path"] for record in records] == ["open.py"]
    assert problems.skipped >= 1
    assert any("locked" in sample for sample in problems.samples)
    assert all(str(root) not in sample for sample in problems.samples)


def test_the_compiled_core_reports_an_unreadable_directory_too() -> None:
    if not rust_bridge.RUST_CORE_AVAILABLE:
        pytest.skip("compiled Rust core is not available in this environment")
    if _can_read_anything():
        pytest.skip("this account can read a directory with mode 000")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        locked = _locked_project(root)
        try:
            records, problems = scan_project_report(root)
        finally:
            _unlock(locked)
    assert [record["rel_path"] for record in records] == ["open.py"]
    assert problems.skipped >= 1
    assert any("locked" in sample for sample in problems.samples)
    assert all(str(root) not in sample for sample in problems.samples)


def test_an_older_compiled_core_without_the_report_function_still_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A stale `_core*.so` next to newer Python code must not crash the scan.
    calls: list[str] = []

    def old_scan_project(*args: object) -> list[dict[str, object]]:
        calls.append("scan_project")
        return [{"rel_path": "kept.py"}]

    monkeypatch.setattr(rust_bridge, "RUST_CORE_AVAILABLE", True)
    monkeypatch.setattr(
        rust_bridge, "_core", SimpleNamespace(scan_project=old_scan_project)
    )
    records, problems = scan_project_report(Path("."))
    assert calls == ["scan_project"]
    assert [record["rel_path"] for record in records] == ["kept.py"]
    assert problems.skipped == 0


def _report(skipped: int, samples: list[str]) -> ReportData:
    return ReportData(
        project_root=Path("fixture-project"),
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        environment=EnvironmentInfo(),
        git=GitSnapshot(),
        stats=ProjectStats(),
        scan_skipped=skipped,
        scan_skipped_samples=samples,
    )


def test_the_report_names_what_could_not_be_scanned() -> None:
    output = markdown.render(
        _report(3, ["locked: Permission denied", "gone.py: No such file"]),
        include_source=False,
    )
    assert "**Scan warning:** 3 path(s) could not be read" in output
    assert "`locked: Permission denied`" in output
    clean = markdown.render(_report(0, []), include_source=False)
    assert "Scan warning" not in clean


def test_the_json_keys_appear_only_when_something_was_skipped() -> None:
    some = json.loads(
        json_renderer.render(_report(2, ["a: denied"]), include_source=False)
    )
    assert some["scan_skipped"] == 2
    assert some["scan_skipped_samples"] == ["a: denied"]
    none = json.loads(json_renderer.render(_report(0, []), include_source=False))
    assert "scan_skipped" not in none
    assert "scan_skipped_samples" not in none
