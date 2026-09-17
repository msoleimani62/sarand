"""Tests for the JSON analyzer."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from _helpers import write
from sarand.analyzers.json_analyzer import JsonAnalyzer
from sarand.analyzers.registry import discover_analyzers, matching_analyzers


def test_json_analyzer_matches_on_top_level_json_file() -> None:
    analyzer = JsonAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False

        write(root / "config.json", "{}\n")

        assert analyzer.matches(root) is True


def test_json_analyzer_does_not_match_nested_json_without_root_signal() -> None:
    analyzer = JsonAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "vendor" / "lib" / "data.json", "{}\n")

        assert analyzer.matches(root) is False


def test_json_analyzer_entry_points() -> None:
    analyzer = JsonAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", '{"name": "app"}\n')

        assert analyzer.entry_points(root) == ["package.json"]


def test_json_analyzer_run_tests_is_always_none() -> None:
    analyzer = JsonAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "config.json", "{}\n")

        result = asyncio.run(analyzer.run_tests(root))

    assert result is None


def test_json_analyzer_run_quality_stdlib_fallback_passes_on_valid_json() -> None:
    """Without jsonlint installed, run_quality still validates syntax
    via the stdlib -- it must not just skip."""

    analyzer = JsonAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "config.json", '{"a": 1}\n')

        results = asyncio.run(analyzer.run_quality(root))

    assert len(results) == 1
    if not results[0].skipped and results[0].kind == "json syntax check":
        assert results[0].returncode == 0


def test_json_analyzer_run_quality_stdlib_fallback_catches_invalid_json() -> None:
    analyzer = JsonAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "broken.json", "{not valid json,,,\n")

        results = asyncio.run(analyzer.run_quality(root))

    assert len(results) == 1
    if results[0].kind == "json syntax check":
        assert results[0].returncode != 0
        assert "broken.json" in results[0].raw_output


def test_json_analyzer_run_security_is_always_empty() -> None:
    analyzer = JsonAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "config.json", "{}\n")

        results = asyncio.run(analyzer.run_security(root))

    assert results == []


def test_json_analyzer_in_discover_and_matching() -> None:
    analyzers = discover_analyzers()
    assert any(a.name == "JSON" for a in analyzers)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "config.json", "{}\n")

        matched = matching_analyzers(root, analyzers)

    assert any(a.name == "JSON" for a in matched)
