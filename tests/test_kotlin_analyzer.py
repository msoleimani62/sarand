"""Tests for the Kotlin analyzer."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from _helpers import write
from sarand.analyzers.kotlin_analyzer import KotlinAnalyzer
from sarand.analyzers.registry import discover_analyzers, matching_analyzers


def test_kotlin_analyzer_matches_on_build_gradle_kts() -> None:
    analyzer = KotlinAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False

        write(root / "build.gradle.kts", "")

        assert analyzer.matches(root) is True


def test_kotlin_analyzer_matches_on_kotlin_plugin_in_build_gradle() -> None:
    analyzer = KotlinAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(
            root / "build.gradle",
            "apply plugin: 'org.jetbrains.kotlin.jvm'\n",
        )

        assert analyzer.matches(root) is True


def test_kotlin_analyzer_does_not_match_plain_java_gradle() -> None:
    analyzer = KotlinAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "build.gradle", "apply plugin: 'java'\n")

        assert analyzer.matches(root) is False


def test_kotlin_analyzer_entry_points() -> None:
    analyzer = KotlinAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "build.gradle.kts", "")
        (root / "src" / "main" / "kotlin").mkdir(parents=True)

        assert analyzer.entry_points(root) == ["src/main/kotlin"]


def test_kotlin_analyzer_run_tests_is_always_none() -> None:
    # Test execution is JavaAnalyzer's job -- see the module docstring.
    analyzer = KotlinAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "build.gradle.kts", "")

        result = asyncio.run(analyzer.run_tests(root))

    assert result is None


def test_kotlin_analyzer_run_quality_skips_cleanly_without_tools() -> None:
    analyzer = KotlinAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "build.gradle.kts", "")

        results = asyncio.run(analyzer.run_quality(root))

    assert {r.kind for r in results} == {"ktlint", "detekt"}
    for result in results:
        if result.skipped:
            assert "not found" in result.skip_reason.lower()


def test_kotlin_analyzer_run_security_is_always_empty() -> None:
    analyzer = KotlinAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "build.gradle.kts", "")

        results = asyncio.run(analyzer.run_security(root))

    assert results == []


def test_kotlin_analyzer_in_discover_and_matching() -> None:
    analyzers = discover_analyzers()
    assert any(a.name == "Kotlin" for a in analyzers)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "build.gradle.kts", "")

        matched = matching_analyzers(root, analyzers)

    assert any(a.name == "Kotlin" for a in matched)


def test_kotlin_and_java_analyzers_both_match_a_kotlin_gradle_project() -> None:
    analyzers = discover_analyzers()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "build.gradle.kts", "")

        matched = {a.name for a in matching_analyzers(root, analyzers)}

    assert "Kotlin" in matched
    assert "Java/Kotlin" in matched
