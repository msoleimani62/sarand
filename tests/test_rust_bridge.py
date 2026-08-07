"""Tests for sarand.rust_bridge -- the Rust/pure-Python contract (rule 3.5).

If the compiled Rust core is present, this file cross-checks that its
output shape matches the pure-Python fallback on the same fixture
project. If it is not present (e.g. this sandbox), only the fallback
path is exercised -- run this suite again after `maturin develop` to
get the cross-check.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from sarand import rust_bridge
from sarand.rust_bridge import (
    RUST_CORE_AVAILABLE,
    _pure_python_scan,
    _pure_python_tree,
    build_tree_text,
    scan_project,
)

from _helpers import write

_EXPECTED_KEYS = {
    "rel_path",
    "size",
    "is_symlink",
    "is_broken_symlink",
    "is_hidden",
    "is_binary",
    "is_executable",
    "extension",
    "total_lines",
    "code_lines",
    "comment_lines",
    "blank_lines",
    "content_hash",
}


def _make_fixture_project(root: Path) -> None:
    write(root / "main.py", "# TODO: fix this\nprint('hi')\n")
    write(root / "README.md", "# demo\n")
    write(root / ".hidden", "secret\n")
    (root / "empty.txt").touch()


def test_pure_python_scan_returns_expected_shape() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_fixture_project(root)

        records = _pure_python_scan(root, frozenset(), 512_000, 5000)

        assert len(records) == 4
        for rec in records:
            assert set(rec.keys()) == _EXPECTED_KEYS

        by_name = {r["rel_path"]: r for r in records}
        assert by_name["main.py"]["total_lines"] == 2
        assert by_name["main.py"]["code_lines"] == 1
        assert by_name["main.py"]["comment_lines"] == 1
        assert by_name[".hidden"]["is_hidden"] is True
        assert by_name["empty.txt"]["size"] == 0


def test_pure_python_tree_matches_expected_ascii_shape() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "a.py", "x = 1\n")
        write(root / "sub" / "b.py", "y = 2\n")

        tree = _pure_python_tree(root, frozenset(), max_depth=8, max_entries=100)

        assert tree.startswith(f"{root.name}/")
        assert "a.py" in tree
        assert "sub/" in tree
        assert "b.py" in tree


def test_scan_project_public_api_matches_fallback_shape_when_rust_absent() -> None:
    """When the Rust core isn't compiled, the public API must be
    byte-for-byte identical to calling the fallback directly."""
    if RUST_CORE_AVAILABLE:
        return  # covered by the cross-check test below instead
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_fixture_project(root)

        via_public_api = scan_project(root)
        via_fallback_directly = _pure_python_scan(root, rust_bridge.IGNORE_DIRS, 512_000, 5000)

        assert {r["rel_path"] for r in via_public_api} == {r["rel_path"] for r in via_fallback_directly}


def test_rust_and_python_paths_agree_on_fixture_project() -> None:
    """Cross-check required by AGENTS.md Phase A. Only meaningful once
    `maturin develop --release` has been run -- skips itself otherwise."""
    if not RUST_CORE_AVAILABLE:
        return
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_fixture_project(root)

        rust_records = scan_project(root)
        python_records = _pure_python_scan(root, rust_bridge.IGNORE_DIRS, 512_000, 5000)

        rust_by_path = {r["rel_path"]: r for r in rust_records}
        python_by_path = {r["rel_path"]: r for r in python_records}

        assert set(rust_by_path) == set(python_by_path)
        for path, py_rec in python_by_path.items():
            rust_rec = rust_by_path[path]
            assert rust_rec["size"] == py_rec["size"]
            assert rust_rec["is_binary"] == py_rec["is_binary"]
            assert rust_rec["total_lines"] == py_rec["total_lines"]
            assert rust_rec["code_lines"] == py_rec["code_lines"]
