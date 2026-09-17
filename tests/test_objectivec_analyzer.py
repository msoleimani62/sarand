"""Tests for the Objective-C analyzer.

The contract covers marker-gated detection (Podfile / top-level .m
file / Xcode project), entry-point discovery, clean handling of
missing external tools, extension-fallback project detection, and
registry integration.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from _helpers import write
from sarand.analyzers.objectivec_analyzer import ObjectiveCAnalyzer
from sarand.analyzers.registry import discover_analyzers, matching_analyzers
from sarand.discovery.project_detector import detect_project


def test_objectivec_analyzer_matches_on_podfile() -> None:
    analyzer = ObjectiveCAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False

        write(root / "Podfile", "platform :ios, '13.0'\n")

        assert analyzer.matches(root) is True


def test_objectivec_analyzer_matches_on_top_level_m_file() -> None:
    analyzer = ObjectiveCAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "main.m", "int main(void) { return 0; }\n")

        assert analyzer.matches(root) is True


def test_objectivec_analyzer_matches_on_xcodeproj() -> None:
    analyzer = ObjectiveCAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        (root / "App.xcodeproj").mkdir()

        assert analyzer.matches(root) is True


def test_objectivec_analyzer_does_not_match_nested_m_without_root_signal() -> None:
    analyzer = ObjectiveCAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "vendor" / "lib" / "thing.m", "\n")

        assert analyzer.matches(root) is False


def test_objectivec_analyzer_does_not_match_unrelated_project() -> None:
    analyzer = ObjectiveCAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "main.py", "print('hi')\n")

        assert analyzer.matches(root) is False


def test_objectivec_analyzer_entry_points() -> None:
    analyzer = ObjectiveCAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "main.m", "int main(void) { return 0; }\n")

        found = analyzer.entry_points(root)

        assert found == ["main.m"]


def test_objectivec_analyzer_run_tests_is_none_without_xcode_project() -> None:
    analyzer = ObjectiveCAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "main.m", "int main(void) { return 0; }\n")

        result = asyncio.run(analyzer.run_tests(root))

        assert result is None


def test_objectivec_analyzer_run_quality_is_noop_without_clang_format_config() -> None:
    analyzer = ObjectiveCAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "main.m", "int main(void) { return 0; }\n")

        results = asyncio.run(analyzer.run_quality(root))

        assert results == []


def test_objectivec_analyzer_run_security_is_always_empty() -> None:
    analyzer = ObjectiveCAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "main.m", "int main(void) { return 0; }\n")

        results = asyncio.run(analyzer.run_security(root))

        assert results == []


def test_objectivec_analyzer_in_discover_and_matching() -> None:
    pool = discover_analyzers()
    names = {analyzer.name for analyzer in pool}

    assert "Objective-C" in names

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "main.m", "int main(void) { return 0; }\n")

        active = matching_analyzers(root, pool)

        assert any(analyzer.name == "Objective-C" for analyzer in active)


def test_objectivec_analyzer_does_not_match_empty_tree() -> None:
    analyzer = ObjectiveCAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False


def test_objectivec_project_detection_uses_extension_fallback() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "main.m", "int main(void) { return 0; }\n")

        detection = detect_project(root)

        assert detection.primary_language == "Objective-C"
