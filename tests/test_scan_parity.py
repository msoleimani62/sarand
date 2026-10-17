"""Parity between the two scan engines (AGENTS.md 5.69).

The compiled Rust core and the pure-Python fallback must report the same files
for the same tree. Two bugs broke that: the Rust walker matched the ignore list
against *every component of the absolute path* (a project living under `build/`
lost all its files), and the Python fallback dropped every directory whose name
starts with `.git` (including `.github/`). The fallback also stored `rel_path`
with the platform separator, unlike Rust.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sarand import rust_bridge
from sarand.constants import HASH_MAX_BYTES, IGNORE_DIRS, MAX_HASH_FILES

_EXPECTED = {
    ".github/workflows/ci.yml",
    "README.md",
    "dist",  # a FILE named like an ignored directory is kept
    "src/a.py",
}


def _make_project(root: Path) -> None:
    files = [
        ".github/workflows/ci.yml",
        "README.md",
        "dist",
        "src/a.py",
        "src/build/gen.py",  # inside an ignored directory: pruned
        "node_modules/pkg/index.js",  # ignored directory: pruned
    ]
    for rel in files:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x = 1\n", encoding="utf-8")


def _fallback_paths(root: Path) -> set[str]:
    records = rust_bridge._pure_python_scan(
        root, IGNORE_DIRS, HASH_MAX_BYTES, MAX_HASH_FILES
    )
    return {record["rel_path"] for record in records}


def test_fallback_keeps_dot_github_and_prunes_only_ignored_directories(
    tmp_path: Path,
) -> None:
    _make_project(tmp_path)
    assert _fallback_paths(tmp_path) == _EXPECTED


def test_fallback_uses_posix_relative_paths(tmp_path: Path) -> None:
    _make_project(tmp_path)
    assert all("\\" not in path for path in _fallback_paths(tmp_path))


def test_fallback_scans_a_project_that_lives_under_an_ignored_name(
    tmp_path: Path,
) -> None:
    root = tmp_path / "build" / "proj"
    _make_project(root)
    assert _fallback_paths(root) == _EXPECTED


def test_rust_core_and_fallback_return_the_same_files(tmp_path: Path) -> None:
    if not rust_bridge.RUST_CORE_AVAILABLE:
        pytest.skip("compiled Rust core is not available in this environment")
    for base in (tmp_path / "plain", tmp_path / "build" / "dist" / "proj"):
        _make_project(base)
        rust = {record["rel_path"] for record in rust_bridge.scan_project(base)}
        assert rust == _fallback_paths(base) == _EXPECTED, base
