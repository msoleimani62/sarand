"""Tests for core/gitleaks.py."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

import pytest
from sarand.core.gitleaks import run_gitleaks


def test_run_gitleaks_skips_cleanly_without_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)

    with tempfile.TemporaryDirectory() as tmp:
        result = asyncio.run(run_gitleaks(Path(tmp)))

    assert result.kind == "gitleaks"
    assert result.skipped is True
    assert "not installed" in result.skip_reason


def test_run_gitleaks_adds_no_git_flag_without_a_git_repo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sarand.core.gitleaks as gitleaks_module

    captured_cmds: list[list[str]] = []

    async def fake_run_cmd_async(cmd, cwd, timeout):
        captured_cmds.append(cmd)
        return 0, "no leaks found", 0.1

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(gitleaks_module, "run_cmd_async", fake_run_cmd_async)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # deliberately no .git directory
        result = asyncio.run(run_gitleaks(root))

    assert result.skipped is False
    assert "--no-git" in captured_cmds[0]
    assert "--redact" in captured_cmds[0]


def test_run_gitleaks_omits_no_git_flag_with_a_real_git_repo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sarand.core.gitleaks as gitleaks_module

    captured_cmds: list[list[str]] = []

    async def fake_run_cmd_async(cmd, cwd, timeout):
        captured_cmds.append(cmd)
        return 0, "no leaks found", 0.1

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(gitleaks_module, "run_cmd_async", fake_run_cmd_async)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".git").mkdir()
        result = asyncio.run(run_gitleaks(root))

    assert result.skipped is False
    assert "--no-git" not in captured_cmds[0]


def test_run_gitleaks_output_is_actionable_and_always_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--verbose shows findings, --no-color keeps ANSI codes out of the
    report, and --verbose must never be built without --redact (it would
    print the real secret value into the embedded report)."""
    import sarand.core.gitleaks as gitleaks_module

    captured_cmds: list[list[str]] = []

    async def fake_run_cmd_async(cmd, cwd, timeout):
        captured_cmds.append(cmd)
        return 0, "", 0.1

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(gitleaks_module, "run_cmd_async", fake_run_cmd_async)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        asyncio.run(run_gitleaks(root))
        (root / ".git").mkdir()
        asyncio.run(run_gitleaks(root))

    assert len(captured_cmds) == 2
    for cmd in captured_cmds:
        assert "--verbose" in cmd
        assert "--no-color" in cmd
        assert "--redact" in cmd
