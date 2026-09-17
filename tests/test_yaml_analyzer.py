"""Tests for the YAML analyzer."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from _helpers import write
from sarand.analyzers.registry import discover_analyzers, matching_analyzers
from sarand.analyzers.yaml_analyzer import YamlAnalyzer


def test_yaml_analyzer_matches_on_top_level_yaml_file() -> None:
    analyzer = YamlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False

        write(root / "docker-compose.yml", "services: {}\n")

        assert analyzer.matches(root) is True


def test_yaml_analyzer_does_not_match_nested_yaml_without_root_signal() -> None:
    analyzer = YamlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "vendor" / "lib" / "config.yaml", "a: 1\n")

        assert analyzer.matches(root) is False


def test_yaml_analyzer_matches_alongside_other_language_markers() -> None:
    """A pubspec.yaml (Dart's marker) is still a top-level YAML file --
    YamlAnalyzer complements DartAnalyzer rather than deferring to it."""

    analyzer = YamlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pubspec.yaml", "name: app\n")

        assert analyzer.matches(root) is True


def test_yaml_analyzer_entry_points() -> None:
    analyzer = YamlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "docker-compose.yml", "services: {}\n")

        assert analyzer.entry_points(root) == ["docker-compose.yml"]


def test_yaml_analyzer_run_tests_is_always_none() -> None:
    analyzer = YamlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "docker-compose.yml", "services: {}\n")

        result = asyncio.run(analyzer.run_tests(root))

    assert result is None


def test_yaml_analyzer_run_quality_skips_cleanly_without_yamllint() -> None:
    analyzer = YamlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "docker-compose.yml", "services: {}\n")

        results = asyncio.run(analyzer.run_quality(root))

    assert len(results) == 1
    assert results[0].kind == "yamllint"
    if results[0].skipped:
        assert "not found" in results[0].skip_reason.lower()


def test_yaml_analyzer_run_security_is_always_empty() -> None:
    analyzer = YamlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "docker-compose.yml", "services: {}\n")

        results = asyncio.run(analyzer.run_security(root))

    assert results == []


def test_yaml_analyzer_in_discover_and_matching() -> None:
    analyzers = discover_analyzers()
    assert any(a.name == "YAML" for a in analyzers)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "docker-compose.yml", "services: {}\n")

        matched = matching_analyzers(root, analyzers)

    assert any(a.name == "YAML" for a in matched)
