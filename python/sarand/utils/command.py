"""Safe external command execution helpers."""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import time
from collections.abc import Sequence
from pathlib import Path

from sarand.constants import DEFAULT_CMD_TIMEOUT, ERROR_PATTERNS, WARNING_PATTERNS
from sarand.models.results import CommandResult, Issue


def run_cmd(
    cmd: Sequence[str],
    cwd: Path,
    timeout: int = DEFAULT_CMD_TIMEOUT,
    *,
    env: dict[str, str] | None = None,
) -> tuple[int, str, float]:
    """Execute a command and capture combined stdout/stderr."""
    start = time.perf_counter()
    try:
        completed = subprocess.run(
            list(cmd),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env=env,
        )
        duration = time.perf_counter() - start
        return completed.returncode, completed.stdout or "", duration
    except subprocess.TimeoutExpired as exc:
        duration = time.perf_counter() - start
        output = exc.output
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        return 124, output or "Command timed out.", duration
    except FileNotFoundError:
        duration = time.perf_counter() - start
        return 127, f"Command not found: {cmd[0]}", duration
    except OSError as exc:
        duration = time.perf_counter() - start
        return 1, f"OS error while running command: {exc}", duration


def summarize_tail(output: str, lines: int = 80) -> str:
    """Return the last N non-empty lines of output."""
    data = output.strip().splitlines()
    if len(data) <= lines:
        return output.strip()
    return "\n".join(data[-lines:])


def scan_for_issues(source: str, output: str) -> tuple[list[Issue], list[Issue]]:
    """Extract warnings and errors from command output."""
    warnings: list[Issue] = []
    errors: list[Issue] = []
    for line in output.splitlines():
        lower = line.lower()
        stripped = line.strip()
        if not stripped:
            continue
        if any(pattern in lower for pattern in WARNING_PATTERNS):
            warnings.append(Issue(source=source, message=stripped, severity="warning"))
        if any(pattern in lower for pattern in ERROR_PATTERNS):
            errors.append(Issue(source=source, message=stripped, severity="error"))
    return warnings, errors


def make_command_result(
    kind: str,
    returncode: int,
    output: str,
    duration: float,
    *,
    skipped: bool = False,
    skip_reason: str = "",
) -> CommandResult:
    """Build a CommandResult from raw execution data."""
    warnings, errors = scan_for_issues(kind, output) if not skipped else ([], [])
    return CommandResult(
        kind=kind,
        returncode=returncode,
        summary=summarize_tail(output) if not skipped else skip_reason,
        raw_output=output if not skipped else "",
        warnings=warnings,
        errors=errors,
        duration_seconds=duration,
        skipped=skipped,
        skip_reason=skip_reason,
    )


async def _terminate_process(proc: asyncio.subprocess.Process) -> None:
    """Terminate a process group and wait for the process to exit."""
    if proc.returncode is not None:
        return

    if os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            await asyncio.wait_for(proc.wait(), timeout=2)
            return
        except (ProcessLookupError, asyncio.TimeoutError):
            pass

        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        proc.kill()

    await proc.wait()


async def run_cmd_async(
    cmd: Sequence[str],
    cwd: Path,
    timeout: int = DEFAULT_CMD_TIMEOUT,
    *,
    env: dict[str, str] | None = None,
) -> tuple[int, str, float]:
    """Execute a command asynchronously with timeout and cancellation cleanup."""
    start = time.perf_counter()
    proc: asyncio.subprocess.Process | None = None
    communicate_task: asyncio.Task[tuple[bytes, bytes]] | None = None

    try:
        if os.name == "posix":
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
                start_new_session=True,
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )

        communicate_task = asyncio.create_task(proc.communicate())

        try:
            stdout, _ = await asyncio.wait_for(
                asyncio.shield(communicate_task),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            await _terminate_process(proc)
            stdout, _ = await communicate_task
            output = stdout.decode("utf-8", errors="replace") if stdout else ""
            if not output:
                output = "Command timed out."
            return 124, output, time.perf_counter() - start
        except asyncio.CancelledError:
            await _terminate_process(proc)
            if communicate_task is not None:
                await communicate_task
            raise

        output = stdout.decode("utf-8", errors="replace") if stdout else ""
        return (
            proc.returncode if proc.returncode is not None else 1,
            output,
            time.perf_counter() - start,
        )
    except FileNotFoundError:
        return 127, f"Command not found: {cmd[0]}", time.perf_counter() - start
    except OSError as exc:
        if proc is not None:
            await _terminate_process(proc)
        if communicate_task is not None and not communicate_task.done():
            await communicate_task
        return 1, f"OS error while running command: {exc}", time.perf_counter() - start
