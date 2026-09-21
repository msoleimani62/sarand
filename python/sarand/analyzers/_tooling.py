"""Small helpers shared by the analyzers that just drive one or two tools.

Every one of them follows the same contract (AGENTS.md §4.3): the analyzer
only runs after `matches(root)` is True, never crashes because a tool
binary is missing (it returns a *skipped* `CommandResult`), and never
executes project code itself.

توابع کوچک مشترک بین آنالایزرهایی که فقط یک یا دو ابزار را اجرا می‌کنند.
همه‌شان یک قرارداد را دنبال می‌کنند (AGENTS.md §4.3): آنالایزر فقط بعد از
`matches(root)` درست اجرا می‌شود، هرگز به‌خاطر نبودن باینری ابزار crash
نمی‌کند (یک `CommandResult` از نوع *skipped* برمی‌گرداند) و خودش هرگز کد
پروژه را اجرا نمی‌کند.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Sequence
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async


def skipped(kind: str, reason: str) -> CommandResult:
    return make_command_result(kind, 127, "", 0.0, skipped=True, skip_reason=reason)


async def run_tool(root: Path, kind: str, argv: Sequence[str]) -> CommandResult:
    """Run `argv` in `root`, or return a skipped result if its binary is missing."""
    binary = argv[0]
    if shutil.which(binary) is None:
        return skipped(kind, f"{binary} not installed")
    return_code, output, duration = await run_cmd_async(
        list(argv), root, LONG_CMD_TIMEOUT
    )
    return make_command_result(kind, return_code, output, duration)


def top_level_files(root: Path, wanted: Callable[[str], bool]) -> list[str]:
    """Names of the regular files directly under `root` that `wanted` accepts,
    in a stable order."""
    try:
        return sorted(
            entry.name
            for entry in root.iterdir()
            if entry.is_file() and wanted(entry.name)
        )
    except OSError:
        return []


def read_text_safely(path: Path) -> str:
    """UTF-8 text of `path`, or "" if unreadable (never raises)."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def existing(root: Path, candidates: Sequence[str]) -> list[str]:
    """The candidates (posix paths) that exist under `root`, files or dirs."""
    found: list[str] = []
    for candidate in candidates:
        try:
            if (root / candidate).exists():
                found.append(candidate)
        except OSError:
            continue
    return found
