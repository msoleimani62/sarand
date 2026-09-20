"""Tests for core/sbom.py."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

import pytest
from sarand.core.sbom import run_syft


def test_run_syft_skips_cleanly_without_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)

    with tempfile.TemporaryDirectory() as tmp:
        result = asyncio.run(run_syft(Path(tmp)))

    assert result.kind == "syft (SBOM)"
    assert result.skipped is True
    assert "not installed" in result.skip_reason


def test_run_syft_runs_with_expected_command_when_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sarand.core.sbom as sbom_module

    captured_cmds: list[list[str]] = []

    async def fake_run_cmd_async(cmd, cwd, timeout):
        captured_cmds.append(cmd)
        return 0, "NAME  VERSION  TYPE\nrequests  2.31.0  python", 0.1

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(sbom_module, "run_cmd_async", fake_run_cmd_async)

    with tempfile.TemporaryDirectory() as tmp:
        result = asyncio.run(run_syft(Path(tmp)))

    assert result.skipped is False
    assert captured_cmds == [["syft", "dir:.", "-o", "table", "--quiet"]]
