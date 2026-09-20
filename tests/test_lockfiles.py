"""Tests for core/lockfiles.py."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest
from _helpers import write
from sarand.core.lockfiles import run_lockfile_check


def _run(root: Path):
    return asyncio.run(run_lockfile_check(root))


def test_skips_when_no_manifest_with_a_lockfile_convention() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = _run(Path(tmp))

    assert result.kind == "lockfile check"
    assert result.skipped is True
    assert "no dependency manifest" in result.skip_reason


def test_rust_manifest_without_lockfile_is_a_problem() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Cargo.toml", '[package]\nname = "x"\n')

        result = _run(root)

    assert result.passed is False
    assert "problem: Cargo.toml (Rust) has no lockfile" in result.raw_output
    # Must not trip sarand's own compile-error scanners.
    # نباید اسکنرهای خطای کامپایلِ خودِ sarand را فعال کند.
    assert "error:" not in result.raw_output.lower()
    assert "failed" not in result.raw_output.lower()


def test_rust_manifest_with_lockfile_passes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Cargo.toml", '[package]\nname = "x"\n')
        write(root / "Cargo.lock", "# lock\n")

        result = _run(root)

    assert result.passed is True
    assert "ok: Cargo.toml (Rust) -> Cargo.lock" in result.raw_output


def test_node_manifest_without_dependencies_has_nothing_to_lock() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", json.dumps({"name": "x", "scripts": {}}))

        result = _run(root)

    assert result.skipped is True


def test_node_manifest_with_dependencies_requires_a_lockfile() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", json.dumps({"dependencies": {"left-pad": "1"}}))

        missing = _run(root)
        write(root / "yarn.lock", "")
        present = _run(root)

    assert missing.passed is False
    assert present.passed is True


def test_two_node_lockfiles_is_a_warning_not_a_failure() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", json.dumps({"dependencies": {"left-pad": "1"}}))
        write(root / "package-lock.json", "{}")
        write(root / "yarn.lock", "")

        result = _run(root)

    assert result.passed is True
    assert "warning: more than one lockfile for Node.js" in result.raw_output


def test_go_and_php_gates_require_real_dependencies() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "go.mod", "module x\n\ngo 1.22\n")
        write(root / "composer.json", json.dumps({"require": {"php": ">=8.1"}}))

        result = _run(root)

    assert result.skipped is True


def test_go_requires_without_go_sum_is_a_problem() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "go.mod", "module x\n\nrequire example.com/a v1.0.0\n")

        result = _run(root)

    assert result.passed is False
    assert "go.sum" in result.raw_output


def test_python_only_counts_with_a_lock_producing_tool_marker() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pyproject.toml", '[project]\nname = "x"\n')
        plain = _run(root)
        write(root / "pyproject.toml", '[project]\nname = "x"\n\n[tool.uv]\n')
        with_uv = _run(root)

    assert plain.skipped is True
    assert with_uv.passed is False
    assert "uv.lock" in with_uv.raw_output


@pytest.mark.parametrize(
    ("git_rc", "expect_pass"),
    [(0, False), (1, True), (128, True)],
)
def test_git_ignored_lockfile_is_a_problem_but_unknown_is_not(
    monkeypatch: pytest.MonkeyPatch, git_rc: int, expect_pass: bool
) -> None:
    import sarand.core.lockfiles as lockfiles_module

    captured: list[list[str]] = []

    async def fake_run_cmd_async(cmd, cwd, timeout):
        captured.append(cmd)
        return git_rc, "", 0.0

    monkeypatch.setattr(lockfiles_module, "run_cmd_async", fake_run_cmd_async)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".git").mkdir()
        write(root / "Cargo.toml", '[package]\nname = "x"\n')
        write(root / "Cargo.lock", "# lock\n")

        result = _run(root)

    assert captured == [["git", "check-ignore", "-q", "--", "Cargo.lock"]]
    assert result.passed is expect_pass
    if not expect_pass:
        assert "git-ignored" in result.raw_output


def test_git_is_not_consulted_without_a_git_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sarand.core.lockfiles as lockfiles_module

    async def must_not_run(cmd, cwd, timeout):
        raise AssertionError("git must not be called without a .git directory")

    monkeypatch.setattr(lockfiles_module, "run_cmd_async", must_not_run)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Cargo.toml", '[package]\nname = "x"\n')
        write(root / "Cargo.lock", "# lock\n")

        result = _run(root)

    assert result.passed is True
