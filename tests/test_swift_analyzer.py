"""Tests for the Swift analyzer.

Covers marker-gated detection (Package.swift or a top-level
.xcworkspace/.xcodeproj), entry-point discovery, clean handling of a
missing swift/xcodebuild binary on both code paths, always-empty
run_security, project detection integration, and registry
integration. The xcodebuild scheme-discovery path itself needs a real
xcodebuild binary (macOS + Xcode only) and is intentionally not
exercised here -- CI/sandbox machines don't have one, and the "not
found" skip path already proves run_tests degrades cleanly without it.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

import pytest
from _helpers import write
from sarand.analyzers.registry import discover_analyzers, matching_analyzers
from sarand.analyzers.swift_analyzer import SwiftAnalyzer
from sarand.discovery.project_detector import detect_project


def test_swift_analyzer_matches_on_package_swift() -> None:
    analyzer = SwiftAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False

        write(root / "Package.swift", "")

        assert analyzer.matches(root) is True


def test_swift_analyzer_matches_on_xcodeproj_without_package_swift() -> None:
    analyzer = SwiftAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "App.xcodeproj").mkdir()

        assert analyzer.matches(root) is True


def test_swift_analyzer_does_not_match_unrelated_project() -> None:
    analyzer = SwiftAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", "{}")

        assert analyzer.matches(root) is False


def test_swift_analyzer_entry_points() -> None:
    analyzer = SwiftAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Package.swift", "")
        write(root / "main.swift", "")

        assert analyzer.entry_points(root) == ["main.swift"]


def test_swift_analyzer_run_tests_skips_cleanly_without_swift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Hermetic: pretend the tool is missing, otherwise the result depends on
    # what the machine running the tests happens to have installed.
    # ایزوله: وانمود می‌کنیم ابزار نصب نیست، وگرنه نتیجه به نصب‌بودن آن
    # روی ماشینِ اجراکننده‌ی تست بستگی پیدا می‌کند.
    monkeypatch.setattr(shutil, "which", lambda name: None)
    analyzer = SwiftAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Package.swift", "")

        result = asyncio.run(analyzer.run_tests(root))

    assert result is not None
    assert result.skipped is True
    assert "swift" in result.skip_reason.lower()


def test_swift_analyzer_run_tests_skips_cleanly_without_xcodebuild() -> None:
    """Xcode-only project (no Package.swift): must degrade cleanly when
    xcodebuild itself isn't present, which is the normal case off
    macOS."""

    analyzer = SwiftAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "App.xcworkspace").mkdir()

        result = asyncio.run(analyzer.run_tests(root))

    assert result is not None
    assert result.skipped is True
    assert "xcodebuild" in result.skip_reason.lower()


def test_swift_analyzer_run_quality_skips_cleanly_without_swift_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_which(name: str) -> str | None:
        if name == "swift-format":
            return None
        return f"/usr/bin/{name}"

    monkeypatch.setattr(shutil, "which", fake_which)
    analyzer = SwiftAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Package.swift", "")

        results = asyncio.run(analyzer.run_quality(root))

    fmt_result = next(r for r in results if r.kind == "swift-format lint")
    assert fmt_result.skipped is True
    assert "not found" in fmt_result.skip_reason.lower()


def test_swift_analyzer_run_quality_skips_swiftlint_without_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_which(name: str) -> str | None:
        if name == "swiftlint":
            return None
        return f"/usr/bin/{name}"

    monkeypatch.setattr(shutil, "which", fake_which)
    analyzer = SwiftAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Package.swift", "")

        results = asyncio.run(analyzer.run_quality(root))

    lint_result = next(r for r in results if r.kind == "swiftlint")
    assert lint_result.skipped is True
    assert "not installed" in lint_result.skip_reason


def test_swift_analyzer_run_quality_runs_swiftlint_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sarand.analyzers.swift_analyzer as swift_analyzer_module

    captured_cmds: list[list[str]] = []

    async def fake_run_cmd_async(cmd, cwd, timeout):
        captured_cmds.append(cmd)
        return 0, "ok", 0.1

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(swift_analyzer_module, "run_cmd_async", fake_run_cmd_async)
    analyzer = SwiftAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Package.swift", "")

        results = asyncio.run(analyzer.run_quality(root))

    lint_result = next(r for r in results if r.kind == "swiftlint")
    assert lint_result.skipped is False
    assert ["swiftlint", "lint", "--quiet"] in captured_cmds


def test_swift_analyzer_run_security_is_always_empty() -> None:
    analyzer = SwiftAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Package.swift", "")

        results = asyncio.run(analyzer.run_security(root))

        assert results == []


def test_swift_analyzer_in_discover_and_matching() -> None:
    analyzers = discover_analyzers()
    assert any(a.name == "Swift" for a in analyzers)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Package.swift", "")

        matched = matching_analyzers(root, analyzers)

    assert any(a.name == "Swift" for a in matched)


def test_swift_project_detection_uses_package_swift_marker() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Package.swift", "")

        detection = detect_project(root)

    assert "Swift" in detection.languages
    assert detection.build_system == "swift package manager"
