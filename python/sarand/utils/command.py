"""Safe external command execution helpers."""

from __future__ import annotations

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
            timeout=timeout,
            check=False,
            env=env,
        )
        duration = time.perf_counter() - start
        return completed.returncode, completed.stdout or "", duration
    except subprocess.TimeoutExpired:
        duration = time.perf_counter() - start
        return 124, "Command timed out.", duration
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
        if any(p in lower for p in WARNING_PATTERNS):
            warnings.append(Issue(source=source, message=stripped, severity="warning"))
        if any(p in lower for p in ERROR_PATTERNS):
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


async def run_cmd_async(
    cmd: Sequence[str],
    cwd: Path,
    timeout: int = DEFAULT_CMD_TIMEOUT,
) -> tuple[int, str, float]:
    """Async variant of run_cmd, used to run independent checks concurrently.

    This is what lets sarand run ``cargo test``, ``pytest``, ``go test``
    and ``npm test`` in parallel instead of one after another -- they
    share nothing and were only ever sequential in bxt because nobody
    had written the async version yet.

    این همان چیزی است که اجازه می‌دهد ``cargo test``، ``pytest``،
    ``go test`` و ``npm test`` هم‌زمان اجرا شوند، نه یکی پس از دیگری --
    هیچ اشتراکی ندارند و در bxt فقط به این دلیل سریال بودند که کسی
    نسخه‌ی async را ننوشته بود.
    """
    import asyncio

    start = time.perf_counter()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return 124, "Command timed out.", time.perf_counter() - start
        output = stdout.decode("utf-8", errors="replace") if stdout else ""
        return proc.returncode or 0, output, time.perf_counter() - start
    except FileNotFoundError:
        return 127, f"Command not found: {cmd[0]}", time.perf_counter() - start
    except OSError as exc:
        return 1, f"OS error while running command: {exc}", time.perf_counter() - start
