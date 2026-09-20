"""Tests for the PHP analyzer.

The contract covers marker-gated detection, entry-point discovery,
preferring a project-local vendor/bin/<tool> over a global binary,
clean handling of missing tools, project detection integration, and
registry integration.
"""

from __future__ import annotations

import asyncio
import shutil
import stat
import tempfile
from pathlib import Path

import pytest
from _helpers import write
from sarand.analyzers.php_analyzer import PhpAnalyzer
from sarand.analyzers.registry import discover_analyzers, matching_analyzers
from sarand.discovery.project_detector import detect_project


def _make_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def test_php_analyzer_matches_on_composer_json() -> None:
    analyzer = PhpAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False

        write(root / "composer.json", "{}")

        assert analyzer.matches(root) is True


def test_php_analyzer_does_not_match_unrelated_project() -> None:
    analyzer = PhpAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Gemfile", "")

        assert analyzer.matches(root) is False


def test_php_analyzer_entry_points() -> None:
    analyzer = PhpAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "composer.json", "{}")
        write(root / "public" / "index.php", "<?php")

        assert analyzer.entry_points(root) == ["public/index.php"]


def test_php_analyzer_prefers_local_vendor_binary_over_global(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sarand.analyzers.php_analyzer import _local_or_global_binary

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        local_phpunit = write(
            root / "vendor" / "bin" / "phpunit", "#!/bin/sh\nexit 0\n"
        )
        _make_executable(local_phpunit)

        # Simulate a *different* global phpunit also being on PATH, to
        # prove the local one wins even when a global one genuinely
        # exists too -- not just because no global one happened to be
        # installed in this sandbox.
        #
        # یک phpunit *global متفاوت* را هم روی PATH شبیه‌سازی می‌کنیم
        # تا ثابت شود نسخه‌ی محلی حتی وقتی یک نسخه‌ی global هم واقعاً
        # وجود دارد برنده می‌شود -- نه صرفاً چون در این سندباکس
        # تصادفاً هیچ نسخه‌ی globalای نصب نبوده است.
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/phpunit")

        found = _local_or_global_binary(root, "phpunit")

    assert found == str(local_phpunit)


def test_php_analyzer_run_tests_skips_cleanly_without_phpunit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Hermetic: pretend the tool is missing, otherwise the result depends on
    # what the machine running the tests happens to have installed (the
    # Ubuntu CI image ships PHPUnit).
    # ایزوله: وانمود می‌کنیم ابزار نصب نیست، وگرنه نتیجه به نصب‌بودن آن
    # روی ماشین اجراکننده بستگی پیدا می‌کند (image اوبونتوی CI خودش PHPUnit دارد).
    monkeypatch.setattr(shutil, "which", lambda name: None)
    analyzer = PhpAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "composer.json", "{}")

        result = asyncio.run(analyzer.run_tests(root))

    assert result is not None
    assert result.skipped is True
    assert "phpunit" in result.skip_reason.lower()


def test_php_analyzer_run_quality_skips_cleanly_without_phpstan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Hermetic: pretend the tool is missing, otherwise the result depends on
    # what the machine running the tests happens to have installed (the
    # Ubuntu CI image ships PHPUnit).
    # ایزوله: وانمود می‌کنیم ابزار نصب نیست، وگرنه نتیجه به نصب‌بودن آن
    # روی ماشین اجراکننده بستگی پیدا می‌کند (image اوبونتوی CI خودش PHPUnit دارد).
    monkeypatch.setattr(shutil, "which", lambda name: None)
    analyzer = PhpAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "composer.json", "{}")

        results = asyncio.run(analyzer.run_quality(root))

    assert results[0].skipped is True
    assert "phpstan" in results[0].skip_reason.lower()


def test_php_analyzer_run_security_skips_cleanly_without_composer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Hermetic: pretend the tool is missing, otherwise the result depends on
    # what the machine running the tests happens to have installed.
    # ایزوله: وانمود می‌کنیم ابزار نصب نیست، وگرنه نتیجه به نصب‌بودن آن
    # روی ماشینِ اجراکننده‌ی تست بستگی پیدا می‌کند.
    monkeypatch.setattr(shutil, "which", lambda name: None)
    analyzer = PhpAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "composer.json", "{}")

        results = asyncio.run(analyzer.run_security(root))

    assert results[0].skipped is True
    assert "composer" in results[0].skip_reason.lower()


def test_php_analyzer_in_discover_and_matching() -> None:
    analyzers = discover_analyzers()
    assert any(a.name == "PHP" for a in analyzers)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "composer.json", "{}")

        matched = matching_analyzers(root, analyzers)

    assert any(a.name == "PHP" for a in matched)


def test_php_project_detection_uses_composer_marker() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "composer.json", "{}")

        detection = detect_project(root)

    assert "PHP" in detection.languages
    assert detection.build_system == "composer"
