"""Tests for Android/Kotlin detection and the dedicated AndroidAnalyzer."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

from _helpers import write
from sarand.analyzers.android_analyzer import AndroidAnalyzer
from sarand.analyzers.java_analyzer import JavaAnalyzer
from sarand.analyzers.registry import discover_analyzers, matching_analyzers
from sarand.discovery.android import is_android_project
from sarand.discovery.project_detector import detect_project


def _make_single_module_android_project(root: Path) -> None:
    write(root / "settings.gradle.kts", 'include(":app")\n')
    write(root / "build.gradle.kts", "// root build file\n")
    write(
        root / "app" / "build.gradle.kts", 'plugins { id("com.android.application") }\n'
    )
    write(
        root / "app" / "src" / "main" / "AndroidManifest.xml", "<manifest></manifest>\n"
    )
    write(
        root / "app" / "src" / "main" / "kotlin" / "MainActivity.kt",
        "class MainActivity\n",
    )


def test_is_android_project_detects_manifest_in_standard_module_layout() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_single_module_android_project(root)
        assert is_android_project(root) is True


def test_is_android_project_detects_agp_plugin_without_manifest_yet() -> None:
    """A freshly scaffolded module might have the plugin declared before
    any manifest exists -- the plugin reference alone must be enough."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "build.gradle", "apply plugin: 'com.android.library'\n")
        assert is_android_project(root) is True


def test_is_android_project_false_for_plain_java_gradle() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "build.gradle", "apply plugin: 'java'\n")
        assert is_android_project(root) is False


def test_java_analyzer_defers_to_android_on_android_projects() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_single_module_android_project(root)

        assert JavaAnalyzer().matches(root) is False
        assert AndroidAnalyzer().matches(root) is True


def test_java_and_android_analyzers_are_mutually_exclusive_on_matching() -> None:
    """Never both match the same project -- that would mean two
    conflicting sets of test/lint commands running."""
    pool = discover_analyzers()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_single_module_android_project(root)

        active_names = {a.name for a in matching_analyzers(root, pool)}
        assert "Android/Kotlin" in active_names
        assert "Java/Kotlin" not in active_names


def test_discover_project_relabels_generic_java_kotlin_as_android() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_single_module_android_project(root)

        detection = detect_project(root)

        assert detection.primary_language == "Android/Kotlin"
        assert detection.project_type == "mobile application"


def test_android_analyzer_entry_points_found() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_single_module_android_project(root)

        entry_points = AndroidAnalyzer().entry_points(root)

        assert "app/src/main/AndroidManifest.xml" in entry_points


def test_android_analyzer_run_tests_skips_cleanly_without_gradle() -> None:
    analyzer = AndroidAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_single_module_android_project(root)
        # No ./gradlew wrapper written for this fixture, and this
        # sandbox has no system-wide `gradle` either -- exercises the
        # real "neither available" skip path.

        result = asyncio.run(analyzer.run_tests(root))

        assert result is not None
        assert result.kind == "gradle testDebugUnitTest"
        if shutil.which("gradle") is None:
            assert result.skipped
            assert "gradlew" in result.skip_reason


def test_android_analyzer_prefers_gradlew_wrapper_when_present() -> None:
    analyzer = AndroidAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_single_module_android_project(root)
        wrapper = write(root / "gradlew", "#!/bin/sh\necho fake\n")
        wrapper.chmod(0o755)

        binary, found = analyzer._gradle_invocation(root)

        assert found is True
        assert binary == str(root / "gradlew")


def test_android_analyzer_quality_and_security_skip_cleanly_without_gradle() -> None:
    analyzer = AndroidAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_single_module_android_project(root)

        quality = asyncio.run(analyzer.run_quality(root))
        security = asyncio.run(analyzer.run_security(root))

        if shutil.which("gradle") is None:
            assert len(quality) == 1 and quality[0].skipped
            assert len(security) == 1 and security[0].skipped


def test_registry_includes_android_analyzer() -> None:
    names = {a.name for a in discover_analyzers()}
    assert "Android/Kotlin" in names
