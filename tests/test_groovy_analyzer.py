"""Tests for the Groovy analyzer.

The contract covers complementary marker-gated detection (Gradle +
actual Groovy source), entry-point discovery, clean handling of
missing external tools, and registry integration. No project-detection
test here -- same as KotlinAnalyzer, a bare build.gradle(.kts) marker
already resolves to the generic "Java/Kotlin" primary language in
PROJECT_MARKERS, so there is nothing Groovy-specific to assert there.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from _helpers import write
from sarand.analyzers.groovy_analyzer import GroovyAnalyzer
from sarand.analyzers.registry import discover_analyzers, matching_analyzers


def test_groovy_analyzer_matches_on_gradle_plus_groovy_source() -> None:
    analyzer = GroovyAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "build.gradle", "apply plugin: 'groovy'\n")

        assert analyzer.matches(root) is False

        write(root / "src" / "main" / "groovy" / "App.groovy", "class App {}\n")

        assert analyzer.matches(root) is True


def test_groovy_analyzer_matches_on_gradle_kts_plus_top_level_groovy() -> None:
    analyzer = GroovyAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "build.gradle.kts", "plugins { groovy }\n")
        write(root / "script.groovy", "println 'hi'\n")

        assert analyzer.matches(root) is True


def test_groovy_analyzer_does_not_match_gradle_without_groovy_source() -> None:
    """A plain Kotlin/Java Gradle project must not falsely match."""

    analyzer = GroovyAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "build.gradle.kts", 'plugins { id("java") }\n')

        assert analyzer.matches(root) is False


def test_groovy_analyzer_does_not_match_groovy_source_without_gradle() -> None:
    """Groovy source with no Gradle marker at all must not match --
    Java/JavaAnalyzer owns build/test execution, so this analyzer
    needs the Gradle signal too."""

    analyzer = GroovyAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "script.groovy", "println 'hi'\n")

        assert analyzer.matches(root) is False


def test_groovy_analyzer_entry_points() -> None:
    analyzer = GroovyAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "build.gradle", "apply plugin: 'groovy'\n")
        write(root / "src" / "main" / "groovy" / "App.groovy", "class App {}\n")

        found = analyzer.entry_points(root)

        assert found == ["src/main/groovy"]


def test_groovy_analyzer_run_tests_is_always_none() -> None:
    """Delegated to JavaAnalyzer's gradle/gradlew test, same as Kotlin."""

    analyzer = GroovyAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "build.gradle", "apply plugin: 'groovy'\n")
        write(root / "src" / "main" / "groovy" / "App.groovy", "class App {}\n")

        result = asyncio.run(analyzer.run_tests(root))

        assert result is None


def test_groovy_analyzer_run_quality_skips_cleanly_without_codenarc() -> None:
    analyzer = GroovyAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "build.gradle", "apply plugin: 'groovy'\n")
        write(root / "src" / "main" / "groovy" / "App.groovy", "class App {}\n")

        results = asyncio.run(analyzer.run_quality(root))

        assert len(results) == 1
        assert results[0].kind == "codenarc"

        if results[0].skipped:
            assert "not found" in results[0].skip_reason.lower()


def test_groovy_analyzer_run_security_is_always_empty() -> None:
    analyzer = GroovyAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "build.gradle", "apply plugin: 'groovy'\n")
        write(root / "src" / "main" / "groovy" / "App.groovy", "class App {}\n")

        results = asyncio.run(analyzer.run_security(root))

        assert results == []


def test_groovy_analyzer_in_discover_and_matching() -> None:
    pool = discover_analyzers()
    names = {analyzer.name for analyzer in pool}

    assert "Groovy" in names

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "build.gradle", "apply plugin: 'groovy'\n")
        write(root / "src" / "main" / "groovy" / "App.groovy", "class App {}\n")

        active = matching_analyzers(root, pool)

        assert any(analyzer.name == "Groovy" for analyzer in active)


def test_groovy_and_java_analyzers_both_match_a_groovy_gradle_project() -> None:
    from sarand.analyzers.java_analyzer import JavaAnalyzer

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "build.gradle", "apply plugin: 'groovy'\n")
        write(root / "src" / "main" / "groovy" / "App.groovy", "class App {}\n")

        assert JavaAnalyzer().matches(root) is True
        assert GroovyAnalyzer().matches(root) is True
