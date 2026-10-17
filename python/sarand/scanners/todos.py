"""Source code scanner for TODO / FIXME / BUG / HACK markers."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from fnmatch import fnmatchcase
from pathlib import Path

from sarand.constants import (
    TODO_EXCLUDE_DIRS,
    TODO_EXCLUDE_SUFFIXES,
    TODO_PATTERNS,
)
from sarand.models.results import TodoItem
from sarand.progress import status, track
from sarand.rust_bridge import FileRecord, scan_project
from sarand.utils.logging import get_logger

logger = get_logger("todos")

_TODO_RE = re.compile(
    r"\b(" + "|".join(re.escape(p) for p in TODO_PATTERNS) + r")\b", re.IGNORECASE
)


def is_todo_excluded(path: str, extra_globs: Sequence[str] = ()) -> bool:
    """True when a marker in `path` is not a task: default places or a glob.

    Defaults: any directory segment named like TODO_EXCLUDE_DIRS (golden,
    fixtures, snapshots), and prose files (Markdown, reStructuredText).
    `extra_globs` are `fnmatch` patterns on the POSIX-style path.

    مارکر در این مسیر «کار» نیست: مکان‌های پیش‌فرض یا یک glob.
    """
    posix = path.replace("\\", "/")
    parts = posix.split("/")
    if any(segment.lower() in TODO_EXCLUDE_DIRS for segment in parts[:-1]):
        return True
    if parts[-1].lower().endswith(TODO_EXCLUDE_SUFFIXES):
        return True
    return any(fnmatchcase(posix, pattern) for pattern in extra_globs)


def filter_todos(
    items: Iterable[TodoItem], extra_globs: Sequence[str] = ()
) -> tuple[list[TodoItem], int]:
    """Drop excluded markers; return the kept ones and how many were dropped."""
    kept: list[TodoItem] = []
    suppressed = 0
    for item in items:
        if is_todo_excluded(item.path, extra_globs):
            suppressed += 1
        else:
            kept.append(item)
    return kept, suppressed


def scan_todos(
    root: Path,
    *,
    records: list[FileRecord] | None = None,
    max_items: int = 1000,
    only: set[str] | None = None,
) -> list[TodoItem]:
    """Scan non-binary source files for TODO-style markers.

    Args:
        only: If given, restrict the scan to these relative paths (as
            strings). Used by the incremental cache (--cache, Phase E)
            to skip re-scanning files whose content hasn't changed
            since the last run. ``None`` means "scan everything," the
            same behavior as before this parameter existed.
    """
    status("Scanning for TODO / FIXME markers...")
    if records is None:
        records = scan_project(root)

    candidates = [
        rec["rel_path"]
        for rec in records
        if not rec["is_binary"] and not rec["is_symlink"]
    ]
    if only is not None:
        candidates = [c for c in candidates if c in only]

    items: list[TodoItem] = []
    if not candidates:
        # Nothing to scan (e.g. every file was a --cache hit). Skip the
        # progress bar entirely -- rich renders a `total=0` bar stuck at
        # "0% -:--:--" forever, which looks hung even though nothing is
        # actually wrong.
        # چیزی برای اسکن نیست (مثلاً همه‌ی فایل‌ها cache hit بودن). نوار
        # پیشرفت را کامل رد می‌کنیم -- rich یک نوار با total=0 را برای
        # همیشه روی «0% -:--:--» گیر می‌دهد که با وجود درست بودن همه‌چیز،
        # هنگ‌کرده به‌نظر می‌رسد.
        logger.info("Found 0 TODO-style markers (nothing to scan)")
        return items

    for rel in track(candidates, description="Scanning TODOs", total=len(candidates)):
        if len(items) >= max_items:
            break
        path = root / rel
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                for lineno, line in enumerate(fh, start=1):
                    match = _TODO_RE.search(line)
                    if match:
                        content = line.strip()
                        if len(content) > 200:
                            content = content[:197] + "..."
                        items.append(
                            TodoItem(
                                path=rel,
                                line_number=lineno,
                                kind=match.group(1).upper(),
                                content=content,
                            )
                        )
                        if len(items) >= max_items:
                            break
        except OSError:
            continue

    logger.info("Found %d TODO-style markers", len(items))
    return items
