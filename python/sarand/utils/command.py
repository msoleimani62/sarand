"""Safe external command execution helpers."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import signal

# sarand exists to run external tools; every call below passes a fixed argv
# list (never a shell string), so bandit B404/B603 is accepted by design.
# وظیفه‌ی sarand اجرای ابزارهای خارجی است؛ هر فراخوانیِ زیر یک لیست argv
# ثابت می‌گیرد (هرگز رشته‌ی shell)، پس B404/B603 در bandit عمداً پذیرفته شده.
import subprocess  # nosec B404
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from sarand.constants import (
    DEFAULT_CMD_TIMEOUT,
    ERROR_LINE_PATTERNS,
    INCONCLUSIVE_KIND_MARKERS,
    INCONCLUSIVE_SIGNATURES,
    MAX_COMMAND_OUTPUT_BYTES,
    WARNING_LINE_PATTERNS,
)
from sarand.models.results import CommandResult, Issue


def _resolve_argv(cmd: Sequence[str]) -> list[str]:
    """Return `cmd` as a list, with a Windows-resolved first element.

    On Windows `CreateProcess` only appends `.exe`, so tools that ship as
    `npm.cmd`, `gradle.bat`, `mvn.cmd`, `composer.bat` ... are "not found"
    when started by bare name even though `shutil.which` (which honors
    PATHEXT) finds them -- and every analyzer gates on `shutil.which`, so
    the check would be reported as a failure instead of running. Resolving
    the first element through `shutil.which` first fixes that. On every
    other OS the command is passed through untouched.

    روی Windows تابع `CreateProcess` فقط `.exe` اضافه می‌کند، پس ابزارهایی
    که به‌صورت `npm.cmd`، `gradle.bat`، `mvn.cmd`، `composer.bat` ... نصب
    می‌شوند با نام ساده «پیدا نمی‌شوند» در حالی که `shutil.which` (که
    PATHEXT را رعایت می‌کند) پیدایشان می‌کند -- و هر آنالایزر روی
    `shutil.which` گیت شده، پس چک به‌جای اجرا شدن به‌عنوان شکست گزارش
    می‌شد. حل‌کردن عنصر اول با `shutil.which` این را درست می‌کند. روی بقیه‌ی
    سیستم‌عامل‌ها فرمان دست‌نخورده می‌ماند.
    """
    argv = list(cmd)
    if os.name != "nt" or not argv:
        return argv
    resolved = shutil.which(argv[0])
    if resolved:
        argv[0] = resolved
    return argv


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
        completed = subprocess.run(  # nosec B603
            _resolve_argv(cmd),
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


# Lines that look like diagnostics to a substring match but are not:
#  - bandit prints the source line around every finding as
#    "<lineno>\t<code>", quoting this project's own test strings verbatim;
#  - bandit's internal log lines ("[tester]\tWARNING\tnosec encountered
#    ... no failed test ...") describe bandit itself, not the scanned code;
#  - cargo/pytest summaries say "0 failed" on success.
# سطرهایی که برای تطبیق substring شبیه diagnostic‌اند ولی نیستند:
#  - bandit سورس دور هر finding را به شکل "<شماره‌خط>\t<کد>" چاپ می‌کند و
#    رشته‌های تستِ خودِ همین پروژه را عیناً نقل می‌کند؛
#  - خطوط log داخلیِ bandit ("[tester]\tWARNING\tnosec encountered ...")
#    درباره‌ی خودِ bandit‌اند، نه کدِ اسکن‌شده؛
#  - خلاصه‌ی cargo/pytest در حالت موفق «0 failed» می‌نویسد.
_BANDIT_CONTEXT_LINE = re.compile(r"^\d+\t")
_TOOL_LOG_LINE = re.compile(r"^\[[a-z_]+\]\t(?!ERROR)", re.IGNORECASE)
# Compiled once. The error patterns only match a NON-ZERO failure count
# (`[1-9]\d* failed`), so "0 failed" needs no special case any more.
# یک‌بار compile می‌شوند. الگوی خطا فقط تعداد غیرصفر را می‌گیرد، پس
# «0 failed» دیگر حالت خاص نمی‌خواهد.
_WARNING_RES = tuple(re.compile(p) for p in WARNING_LINE_PATTERNS)
_ERROR_RES = tuple(re.compile(p) for p in ERROR_LINE_PATTERNS)
_INCONCLUSIVE_RES = tuple(
    (re.compile(p), reason) for p, reason in INCONCLUSIVE_SIGNATURES
)


def scan_for_issues(source: str, output: str) -> tuple[list[Issue], list[Issue]]:
    """Extract warnings and errors from command output.

    Lines are classified by their shape (constants.WARNING_LINE_PATTERNS /
    ERROR_LINE_PATTERNS), never by a bare substring. Whether the *command*
    failed is not known here; `make_command_result` drops the errors of a
    command that exited 0.

    خطوط بر اساس شکل‌شان دسته‌بندی می‌شوند، نه substring خالی. اینکه خودِ
    دستور شکست خورده یا نه اینجا معلوم نیست؛ `make_command_result` خطاهای
    دستوری که با کد ۰ تمام شده را حذف می‌کند.
    """
    warnings: list[Issue] = []
    errors: list[Issue] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _BANDIT_CONTEXT_LINE.match(line) or _TOOL_LOG_LINE.match(line):
            continue
        if any(rx.search(line) for rx in _WARNING_RES):
            warnings.append(Issue(source=source, message=stripped, severity="warning"))
        if any(rx.search(line) for rx in _ERROR_RES):
            errors.append(Issue(source=source, message=stripped, severity="error"))
    return warnings, errors


def detect_inconclusive(kind: str, returncode: int, output: str) -> str:
    """Why an audit-style check that exited 0 did not really finish, or "".

    Only audit-style kinds (`cargo audit`, `pip-audit`, `npm audit`,
    `govulncheck`, ...) and only exit code 0 are considered: a failing exit
    is never downgraded to "inconclusive".

    دلیل اینکه یک چک از نوع audit با کد خروج ۰ واقعاً تمام نشده، یا "". فقط
    نوع‌های audit و فقط کد ۰؛ شکست هرگز به «نامشخص» تنزل داده نمی‌شود.
    """
    if returncode != 0:
        return ""
    lowered_kind = kind.lower()
    if not any(marker in lowered_kind for marker in INCONCLUSIVE_KIND_MARKERS):
        return ""
    for rx, reason in _INCONCLUSIVE_RES:
        if rx.search(output):
            return reason
    return ""


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
    warnings: list[Issue] = []
    errors: list[Issue] = []
    inconclusive_reason = ""
    if not skipped:
        warnings, errors = scan_for_issues(kind, output)
        if returncode == 0:
            # A command that exited 0 reports no errors: an "error:" line in
            # a passing tool's output is a quotation or a log line, not a
            # failure (AGENTS.md 5.68).
            # دستوری که با کد ۰ تمام شده خطایی گزارش نمی‌کند: خط «error:» در
            # خروجی ابزار موفق نقل‌قول یا log است، نه شکست.
            errors = []
        inconclusive_reason = detect_inconclusive(kind, returncode, output)
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
        inconclusive_reason=inconclusive_reason,
    )


async def _terminate_process(proc: asyncio.subprocess.Process) -> None:
    """Terminate a process group and wait for the process to exit."""
    if proc.returncode is not None:
        return

    # `sys.platform` (not `os.name`) on purpose: mypy narrows on it, so the
    # POSIX-only `os.killpg` / `signal.SIGKILL` are not type-checked on
    # Windows, where they do not exist.
    # عمداً `sys.platform` (نه `os.name`): mypy روی آن narrow می‌کند، پس
    # `os.killpg` / `signal.SIGKILL` مخصوص POSIX روی Windows، که وجود
    # ندارند، type-check نمی‌شوند.
    if sys.platform != "win32":
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            await asyncio.wait_for(proc.wait(), timeout=2)
            return
        except (TimeoutError, ProcessLookupError):
            pass

        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        proc.kill()

    await proc.wait()


# --- Limits on external commands (AGENTS.md 5.73) ---------------------------------
# Every analyzer subprocess goes through `run_cmd_async`, so the two limits live here:
# how many run at once, and how much of each one's output is kept.
# دو سقف روی دستورهای بیرونی: چند تا هم‌زمان اجرا شوند و چقدر از خروجی هرکدام نگه
# داشته شود. هر زیرفرایند analyzer از `run_cmd_async` می‌گذرد، پس هر دو اینجا هستند.

_READ_CHUNK = 65536
_max_commands: int | None = None  # None: not limited (the library default)
_limiter: tuple[asyncio.AbstractEventLoop, int, asyncio.Semaphore] | None = None


def set_max_concurrent_commands(limit: int | None) -> None:
    """At most `limit` external commands run at once from now on (None: no limit)."""
    global _max_commands, _limiter
    _max_commands = limit
    _limiter = None


def _command_slots() -> asyncio.Semaphore | None:
    """The semaphore for the running event loop, rebuilt when the loop or limit changes."""
    global _limiter
    if _max_commands is None:
        return None
    loop = asyncio.get_running_loop()
    if _limiter is None or _limiter[0] is not loop or _limiter[1] != _max_commands:
        _limiter = (loop, _max_commands, asyncio.Semaphore(_max_commands))
    return _limiter[2]


async def _drain(proc: asyncio.subprocess.Process, cap: int) -> bytes:
    """Read the merged output to its end and wait for the process, keeping at most `cap`
    bytes: the first half and the last half of the budget, with a marker in between.

    The pipe is read to the very end even past the cap, so the child never blocks on
    a full pipe. The tail is trimmed only when it has doubled, which keeps the work per
    chunk constant and the peak memory near 1.5 times `cap`.

    خروجی را تا پایان می‌خواند ولی حداکثر `cap` بایت نگه می‌دارد (نیمه‌ی اول و نیمه‌ی
    آخر بودجه، با یک نشانه در وسط). لوله تا آخر خوانده می‌شود تا child روی لوله‌ی پر
    گیر نکند.
    """
    stream = proc.stdout
    if stream is None:
        await proc.wait()
        return b""
    head_cap = cap // 2
    tail_cap = cap - head_cap
    head = bytearray()
    tail = bytearray()
    total = 0
    while True:
        chunk = await stream.read(_READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if len(head) < head_cap:
            room = head_cap - len(head)
            head += chunk[:room]
            chunk = chunk[room:]
        if chunk:
            tail += chunk
            if len(tail) > 2 * tail_cap:
                del tail[: len(tail) - tail_cap]
    await proc.wait()
    if len(tail) > tail_cap:
        del tail[: len(tail) - tail_cap]
    omitted = total - len(head) - len(tail)
    if omitted <= 0:
        return bytes(head + tail)
    marker = f"\n[sarand: {omitted} bytes omitted from the middle of this output]\n"
    return bytes(head) + marker.encode() + bytes(tail)


async def run_cmd_async(
    cmd: Sequence[str],
    cwd: Path,
    timeout: int = DEFAULT_CMD_TIMEOUT,
    *,
    env: dict[str, str] | None = None,
    max_output_bytes: int = MAX_COMMAND_OUTPUT_BYTES,
) -> tuple[int, str, float]:
    """Execute a command asynchronously with timeout and cancellation cleanup.

    At most `set_max_concurrent_commands` of these run at once; the timeout starts
    when the command gets its slot, not while it waits for one.
    """
    slots = _command_slots()
    if slots is None:
        return await _run_cmd(
            cmd, cwd, timeout, env=env, max_output_bytes=max_output_bytes
        )
    async with slots:
        return await _run_cmd(
            cmd, cwd, timeout, env=env, max_output_bytes=max_output_bytes
        )


async def _run_cmd(
    cmd: Sequence[str],
    cwd: Path,
    timeout: int,
    *,
    env: dict[str, str] | None,
    max_output_bytes: int,
) -> tuple[int, str, float]:
    """The unlimited body of `run_cmd_async` (see there)."""
    start = time.perf_counter()
    proc: asyncio.subprocess.Process | None = None
    communicate_task: asyncio.Task[bytes] | None = None
    argv = _resolve_argv(cmd)

    try:
        if os.name == "posix":
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
                start_new_session=True,
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )

        communicate_task = asyncio.create_task(_drain(proc, max_output_bytes))

        try:
            stdout = await asyncio.wait_for(
                asyncio.shield(communicate_task),
                timeout=timeout,
            )
        except TimeoutError:
            await _terminate_process(proc)
            stdout = await communicate_task
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
