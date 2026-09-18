"""Tests for the Zig analyzer.

The contract covers marker-gated detection, entry-point discovery,
clean handling of a missing zig binary, always-empty run_security,
project detection integration, and registry integration.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

import pytest
from _helpers import write
from sarand.analyzers.registry import discover_analyzers, matching_analyzers
from sarand.analyzers.zig_analyzer import ZigAnalyzer
from sarand.discovery.project_detector import detect_project


def test_zig_analyzer_matches_on_build_zig() -> None:
    analyzer = ZigAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False

        write(root / "build.zig", "")

        assert analyzer.matches(root) is True


def test_zig_analyzer_does_not_match_unrelated_project() -> None:
    analyzer = ZigAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", "{}")

        assert analyzer.matches(root) is False


def test_zig_analyzer_entry_points() -> None:
    analyzer = ZigAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "build.zig", "")
        write(root / "src" / "main.zig", "")

        assert analyzer.entry_points(root) == ["src/main.zig", "build.zig"]


def test_zig_analyzer_run_tests_skips_cleanly_without_zig(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # BUG FIX: same shape as the Dart fix -- relied on the real machine
    # not having `zig` installed. On a machine that does (this
    # maintainer's), it ran a real `zig build test` against an empty
    # build.zig and got a real compile error instead of exercising the
    # skip path the test claims to cover. Monkeypatch `shutil.which`
    # to actually simulate the binary's absence.
    #
    # اصلاح باگ: همان شکل فیکس Dart -- به این متکی بود که ماشین واقعی
    # `zig` نصب نداشته باشد. روی دستگاهی که دارد (دستگاه خود
    # نگه‌دارنده)، یک `zig build test` واقعی روی build.zig خالی اجرا
    # کرد و یک خطای کامپایل واقعی گرفت، به‌جای تمرین مسیر skip که ادعای
    # تست است. `shutil.which` را monkeypatch می‌کنیم تا غیاب باینری را
    # واقعاً شبیه‌سازی کند.
    monkeypatch.setattr(shutil, "which", lambda name: None)
    analyzer = ZigAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "build.zig", "")

        result = asyncio.run(analyzer.run_tests(root))

    assert result is not None
    assert result.skipped is True
    assert "zig" in result.skip_reason.lower()


def test_zig_analyzer_run_quality_skips_cleanly_without_zig() -> None:
    analyzer = ZigAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "build.zig", "")

        results = asyncio.run(analyzer.run_quality(root))

        assert len(results) == 1
        assert results[0].kind == "zig fmt --check"

        if results[0].skipped:
            assert "not found" in results[0].skip_reason.lower()


def test_zig_analyzer_run_security_is_always_empty() -> None:
    analyzer = ZigAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "build.zig", "")

        results = asyncio.run(analyzer.run_security(root))

        assert results == []


def test_zig_analyzer_in_discover_and_matching() -> None:
    analyzers = discover_analyzers()
    assert any(a.name == "Zig" for a in analyzers)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "build.zig", "")

        matched = matching_analyzers(root, analyzers)

    assert any(a.name == "Zig" for a in matched)


def test_zig_project_detection_uses_build_zig_marker() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "build.zig", "")

        detection = detect_project(root)

    assert "Zig" in detection.languages
    assert detection.build_system == "zig"
