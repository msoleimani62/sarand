"""Tests for the Shell analyzer."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from _helpers import write
from sarand.analyzers.registry import discover_analyzers, matching_analyzers
from sarand.analyzers.shell_analyzer import ShellAnalyzer
from sarand.discovery.project_detector import detect_project


def test_shell_analyzer_matches_on_top_level_sh_file() -> None:
    analyzer = ShellAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False

        write(root / "install.sh", "#!/bin/sh\necho hi\n")

        assert analyzer.matches(root) is True


def test_shell_analyzer_does_not_match_nested_sh_without_root_signal() -> None:
    analyzer = ShellAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "vendor" / "lib" / "helper.sh", "echo hi\n")

        assert analyzer.matches(root) is False


def test_shell_analyzer_does_not_match_unrelated_project() -> None:
    analyzer = ShellAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", "{}")

        assert analyzer.matches(root) is False


def test_shell_analyzer_entry_points() -> None:
    analyzer = ShellAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "install.sh", "echo hi\n")
        write(root / "unrelated.sh", "echo bye\n")

        assert analyzer.entry_points(root) == ["install.sh"]


def test_shell_analyzer_run_tests_is_none_without_bats_dir() -> None:
    analyzer = ShellAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "install.sh", "echo hi\n")

        result = asyncio.run(analyzer.run_tests(root))

    assert result is None


def test_shell_analyzer_run_tests_with_bats_suite_present() -> None:
    """When tests/*.bats exists, run_tests must actually attempt it --
    skipped cleanly if bats isn't installed, run otherwise (this
    machine may or may not have bats, so both outcomes are valid)."""

    analyzer = ShellAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "install.sh", "echo hi\n")
        write(root / "tests" / "install.bats", "")

        result = asyncio.run(analyzer.run_tests(root))

    assert result is not None
    assert result.kind == "bats"
    if result.skipped:
        assert "bats" in result.skip_reason.lower()


def test_shell_analyzer_run_quality_skips_cleanly_without_shellcheck() -> None:
    analyzer = ShellAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "install.sh", "echo hi\n")

        results = asyncio.run(analyzer.run_quality(root))

    assert len(results) == 1
    assert results[0].kind == "shellcheck"
    if results[0].skipped:
        assert "not found" in results[0].skip_reason.lower()


def test_shell_analyzer_run_security_is_always_empty() -> None:
    analyzer = ShellAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "install.sh", "echo hi\n")

        results = asyncio.run(analyzer.run_security(root))

    assert results == []


def test_shell_analyzer_in_discover_and_matching() -> None:
    analyzers = discover_analyzers()
    assert any(a.name == "Shell" for a in analyzers)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "install.sh", "echo hi\n")

        matched = matching_analyzers(root, analyzers)

    assert any(a.name == "Shell" for a in matched)


def test_shell_project_detection_uses_extension_fallback() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "install.sh", "echo hi\n")

        detection = detect_project(root)

    assert detection.primary_language == "Shell"
