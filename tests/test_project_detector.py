"""Tests for sarand.discovery.project_detector."""

from __future__ import annotations

import tempfile
from pathlib import Path

from _helpers import write
from sarand.discovery.project_detector import detect_project


def test_detects_python_via_pyproject() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pyproject.toml", "[project]\nname='x'\n")
        write(root / "main.py", "print('hi')\n")

        result = detect_project(root)

        assert result.primary_language == "Python"
        assert "Python" in result.languages
        assert result.markers_found == ["pyproject.toml"]
        assert result.build_system == "pip/poetry/uv"
        assert result.is_recognized
        assert "main.py" in result.entry_points


def test_detects_rust_via_cargo_toml() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Cargo.toml", "[package]\nname='x'\n")
        write(root / "src" / "main.rs", "fn main() {}\n")

        result = detect_project(root)

        assert result.primary_language == "Rust"
        assert result.build_system == "cargo"
        assert "src/main.rs" in result.entry_points


def test_detects_multiple_languages_in_polyglot_repo() -> None:
    """A Rust core + Node frontend repo must report both, not just one."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Cargo.toml", "[package]\nname='x'\n")
        write(root / "package.json", '{"name": "x"}')

        result = detect_project(root)

        assert set(result.languages) == {"Rust", "Node.js"}
        assert len(result.markers_found) == 2


def test_falls_back_to_extension_guess_with_no_markers() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for i in range(5):
            write(root / f"file_{i}.go", "package main\n")
        write(root / "readme.txt", "no markers here")

        result = detect_project(root)

        assert result.primary_language == "Go"
        assert result.markers_found == []
        assert not result.is_recognized  # no real marker, just a guess
        assert result.build_system == "none detected"


def test_empty_directory_has_no_detection() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = detect_project(Path(tmp))
        assert result.primary_language == "Unknown"
        assert result.languages == []
        assert not result.is_recognized


def test_never_hardcodes_a_specific_project_name() -> None:
    """Regression test for the original bxt bug: detection must depend
    only on the directory's *contents*, never its name or path."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "bimarz"  # deliberately using the old hardcoded name
        write(root / "package.json", '{"name": "x"}')

        result = detect_project(root)

        # Detected because of package.json, not because the folder is
        # literally named "bimarz" -- an empty folder with that same
        # name must NOT be detected as anything.
        assert result.primary_language == "Node.js"

        empty_root = Path(tmp) / "bimarz-empty"
        empty_root.mkdir()
        empty_result = detect_project(empty_root)
        assert empty_result.primary_language == "Unknown"
