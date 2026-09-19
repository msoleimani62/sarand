"""Tests for the Shell analyzer."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

import pytest
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


def test_shell_analyzer_run_quality_skips_cleanly_without_shellcheck(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_which(name: str) -> str | None:
        if name == "shellcheck":
            return None
        return f"/usr/bin/{name}"

    monkeypatch.setattr(shutil, "which", fake_which)
    analyzer = ShellAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "install.sh", "echo hi\n")

        results = asyncio.run(analyzer.run_quality(root))

    shellcheck_result = next(r for r in results if r.kind == "shellcheck")
    assert shellcheck_result.skipped is True
    assert "not found" in shellcheck_result.skip_reason.lower()


def test_shell_analyzer_run_quality_skips_shfmt_without_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_which(name: str) -> str | None:
        if name == "shfmt":
            return None
        return f"/usr/bin/{name}"

    monkeypatch.setattr(shutil, "which", fake_which)
    analyzer = ShellAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "install.sh", "echo hi\n")

        results = asyncio.run(analyzer.run_quality(root))

    shfmt_result = next(r for r in results if r.kind == "shfmt -d")
    assert shfmt_result.skipped is True
    assert "not installed" in shfmt_result.skip_reason


def test_shell_analyzer_run_quality_runs_shfmt_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sarand.analyzers.shell_analyzer as shell_analyzer_module

    captured_cmds: list[list[str]] = []

    async def fake_run_cmd_async(cmd, cwd, timeout):
        captured_cmds.append(cmd)
        return 0, "ok", 0.1

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(shell_analyzer_module, "run_cmd_async", fake_run_cmd_async)
    analyzer = ShellAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "install.sh", "echo hi\n")

        results = asyncio.run(analyzer.run_quality(root))

    shfmt_result = next(r for r in results if r.kind == "shfmt -d")
    assert shfmt_result.skipped is False
    shfmt_cmd = next(c for c in captured_cmds if c[0] == "shfmt")
    assert shfmt_cmd[1] == "-d"
    assert "install.sh" in shfmt_cmd


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
