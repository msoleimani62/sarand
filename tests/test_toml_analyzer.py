"""Tests for the TOML analyzer."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from _helpers import write
from sarand.analyzers.registry import discover_analyzers, matching_analyzers
from sarand.analyzers.toml_analyzer import TomlAnalyzer


def test_toml_analyzer_matches_on_top_level_toml_file() -> None:
    analyzer = TomlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False

        write(root / "Cargo.toml", '[package]\nname = "app"\n')

        assert analyzer.matches(root) is True


def test_toml_analyzer_does_not_match_nested_toml_without_root_signal() -> None:
    analyzer = TomlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "vendor" / "lib" / "config.toml", "a = 1\n")

        assert analyzer.matches(root) is False


def test_toml_analyzer_matches_alongside_other_language_markers() -> None:
    """Cargo.toml (Rust's marker) is still a top-level TOML file --
    TomlAnalyzer complements RustAnalyzer rather than deferring to it."""

    analyzer = TomlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Cargo.toml", '[package]\nname = "app"\n')

        assert analyzer.matches(root) is True


def test_toml_analyzer_entry_points() -> None:
    analyzer = TomlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Cargo.toml", "")

        assert analyzer.entry_points(root) == ["Cargo.toml"]


def test_toml_analyzer_run_tests_is_always_none() -> None:
    analyzer = TomlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Cargo.toml", "")

        result = asyncio.run(analyzer.run_tests(root))

    assert result is None


def test_toml_analyzer_run_quality_skips_cleanly_without_taplo() -> None:
    analyzer = TomlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Cargo.toml", "")

        results = asyncio.run(analyzer.run_quality(root))

    assert len(results) == 1
    assert results[0].kind == "taplo lint"
    if results[0].skipped:
        assert "not found" in results[0].skip_reason.lower()


def test_toml_analyzer_run_security_is_always_empty() -> None:
    analyzer = TomlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Cargo.toml", "")

        results = asyncio.run(analyzer.run_security(root))

    assert results == []


def test_toml_analyzer_in_discover_and_matching() -> None:
    analyzers = discover_analyzers()
    assert any(a.name == "TOML" for a in analyzers)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Cargo.toml", "")

        matched = matching_analyzers(root, analyzers)

    assert any(a.name == "TOML" for a in matched)
