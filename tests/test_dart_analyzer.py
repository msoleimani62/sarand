"""Tests for the Dart/Flutter analyzer.

The contract covers marker-gated detection, entry-point discovery,
correctly distinguishing a plain Dart project from a Flutter one
(same pubspec.yaml marker, different required tool), clean handling
of missing tools, the always-empty run_security (no standard
vulnerability-audit tool exists for this ecosystem yet), project
detection integration, and registry integration.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from _helpers import write
from sarand.analyzers.dart_analyzer import DartAnalyzer, _is_flutter_project
from sarand.analyzers.registry import discover_analyzers, matching_analyzers
from sarand.discovery.project_detector import detect_project


def test_dart_analyzer_matches_on_pubspec_yaml() -> None:
    analyzer = DartAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False

        write(root / "pubspec.yaml", "name: test\n")

        assert analyzer.matches(root) is True


def test_dart_analyzer_does_not_match_unrelated_project() -> None:
    analyzer = DartAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", "{}")

        assert analyzer.matches(root) is False


def test_dart_analyzer_entry_points() -> None:
    analyzer = DartAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pubspec.yaml", "name: test\n")
        write(root / "lib" / "main.dart", "void main() {}\n")

        assert analyzer.entry_points(root) == ["lib/main.dart"]


def test_is_flutter_project_true_for_flutter_dependency() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(
            root / "pubspec.yaml",
            "name: test\ndependencies:\n  flutter:\n    sdk: flutter\n",
        )

        assert _is_flutter_project(root) is True


def test_is_flutter_project_false_for_plain_dart_package() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pubspec.yaml", "name: test\ndependencies:\n  http: ^1.0.0\n")

        assert _is_flutter_project(root) is False


def test_is_flutter_project_false_without_pubspec() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert _is_flutter_project(Path(tmp)) is False


def test_dart_analyzer_run_tests_skips_cleanly_without_dart_or_flutter() -> None:
    analyzer = DartAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pubspec.yaml", "name: test\n")

        result = asyncio.run(analyzer.run_tests(root))

    assert result is not None
    assert result.skipped is True
    assert "flutter" in result.skip_reason.lower()
    assert "dart" in result.skip_reason.lower()


def test_dart_analyzer_run_quality_skips_cleanly_without_dart_or_flutter() -> None:
    analyzer = DartAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pubspec.yaml", "name: test\n")

        results = asyncio.run(analyzer.run_quality(root))

    assert results[0].skipped is True


def test_dart_analyzer_run_security_is_always_empty() -> None:
    # No broadly standard vulnerability-audit tool exists for
    # Dart/Flutter yet -- an empty list is the honest answer, not a
    # skipped placeholder (same precedent as LuaAnalyzer).
    analyzer = DartAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pubspec.yaml", "name: test\n")

        results = asyncio.run(analyzer.run_security(root))

    assert results == []


def test_dart_analyzer_in_discover_and_matching() -> None:
    analyzers = discover_analyzers()
    assert any(a.name == "Dart" for a in analyzers)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pubspec.yaml", "name: test\n")

        matched = matching_analyzers(root, analyzers)

    assert any(a.name == "Dart" for a in matched)


def test_dart_project_detection_uses_pubspec_marker() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pubspec.yaml", "name: test\n")

        detection = detect_project(root)

    assert "Dart/Flutter" in detection.languages
    assert detection.build_system == "pub"
