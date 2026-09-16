"""Git repository analysis."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from sarand.models.results import GitSnapshot
from sarand.progress import status
from sarand.utils.command import run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("git")

# BUG FIX (user report: --full appears to hang for minutes on "Collecting
# Git information..."): the real cause turned out to be the *silent*
# analyzer pipeline right after this (see cli.py's run()), not this
# module -- but while investigating, two real weaknesses here were worth
# fixing anyway: every git subcommand ran sequentially (worst case
# additive: 8 calls x timeout each), and the per-call timeout was 60s,
# long enough that a single stuck command could look like exactly the
# multi-minute stall that was reported. Local git metadata commands
# (branch/status/log -20/diff --stat/tag/stash/ls-files) never
# legitimately need anywhere near 60s on a repo this size -- if one
# ever does, that's worth knowing quickly, not waiting a full minute
# for. Independent commands now run concurrently via asyncio.gather,
# so total wall time is bounded by the single slowest call, not their
# sum, and each call's duration is logged so a future slow run points
# at the exact command instead of "somewhere in git".
#
# اصلاح باگ (گزارش کاربر: --full به‌نظر چند دقیقه روی "Collecting Git
# information..." می‌ماند): علت واقعی خط‌لوله‌ی *بی‌صدای* آنالایزر
# درست بعد از این بود (به run() در cli.py نگاه کنید)، نه این ماژول --
# اما در حین بررسی، دو ضعف واقعی اینجا هم ارزش فیکس‌شدن داشتند: هر
# دستور git پشت‌سرهم اجرا می‌شد (بدترین حالت جمعی: ۸ فراخوانی × هرکدام
# یک timeout)، و timeout هر فراخوانی ۶۰ ثانیه بود، به‌قدر کافی طولانی
# که یک دستور گیرکرده دقیقاً شبیه همان توقف چنددقیقه‌ای گزارش‌شده
# به‌نظر برسد. دستورات متادیتای محلی گیت هیچ‌وقت واقعاً به چیزی نزدیک
# ۶۰ ثانیه روی ریپویی به این اندازه نیاز ندارند -- اگر یک‌بار نیاز
# داشت، بهتر است زود بفهمیم، نه یک دقیقه‌ی کامل منتظر بمانیم. دستورات
# مستقل حالا با asyncio.gather هم‌زمان اجرا می‌شوند، پس زمان کل با
# کندترین فراخوانی محدود می‌شود نه مجموعشان، و مدت هر فراخوانی لاگ
# می‌شود تا اجرای کند بعدی دقیقاً دستور مقصر را نشان دهد، نه «یه‌جایی
# توی گیت».
_GIT_CALL_TIMEOUT = 15


async def _git(root: Path, *args: str, timeout: int = _GIT_CALL_TIMEOUT) -> str:
    t0 = time.perf_counter()
    rc, out, _duration = await run_cmd_async(["git", *args], root, timeout=timeout)
    elapsed = time.perf_counter() - t0
    if elapsed > 3:
        logger.warning("git %s took %.1fs", " ".join(args), elapsed)
    else:
        logger.debug("git %s took %.2fs", " ".join(args), elapsed)
    if rc == 0:
        return out.strip()
    return "(unavailable)"


def _check_stale_lock(root: Path) -> None:
    """Warn (don't block) if a leftover .git/index.lock exists.

    A classic real-world cause of every git command hanging until
    timeout: a previous git process (an editor's git integration, a
    killed sarand run, anything) was interrupted and left the index
    lock behind. Every subsequent git command that touches the index
    blocks waiting for a lock that will never be released. Detecting
    this up front turns a mysterious multi-minute stall into an
    immediate, actionable warning.

    اگر یک .git/index.lock باقی‌مانده وجود دارد هشدار بده (بدون
    مسدودکردن). یک دلیل کلاسیک و واقعی برای گیرکردن هر دستور گیت تا
    timeout: یک فرآیند git قبلی (یکپارچگی گیت یک ادیتور، یک اجرای
    sarand که کشته شده، هرچیزی) قطع شده و lock ایندکس را باقی گذاشته.
    هر دستور git بعدی که به ایندکس دست می‌زند منتظر lockای می‌ماند که
    هیچ‌وقت آزاد نمی‌شود. تشخیص این از قبل، یک توقف مرموز چنددقیقه‌ای
    را به یک هشدار فوری و قابل‌اقدام تبدیل می‌کند.
    """
    lock_file = root / ".git" / "index.lock"
    if lock_file.exists():
        logger.warning(
            "Found %s -- a previous git process may have been interrupted. "
            "Every git command below may hang until it times out. If so, "
            "remove this file once you're sure no git process is running.",
            lock_file,
        )


async def collect_git_snapshot(root: Path) -> GitSnapshot:
    """Collect a comprehensive Git status snapshot."""
    status("Collecting Git information...")
    logger.info("Inspecting Git state at %s", root)

    rc, _, _ = await run_cmd_async(
        ["git", "rev-parse", "--is-inside-work-tree"], root, timeout=10
    )
    if rc != 0:
        logger.warning("Not a git repository")
        return GitSnapshot()

    _check_stale_lock(root)

    # Every call below is independent of the others (none depends on a
    # prior call's output), so they run concurrently instead of one
    # after another.
    #
    # هر فراخوانی پایین مستقل از بقیه است (هیچ‌کدام به خروجی فراخوانی
    # قبلی نیاز ندارد)، پس به‌جای پشت‌سرهم، هم‌زمان اجرا می‌شوند.
    (
        branch,
        commit,
        status_text,
        log,
        diff,
        tags,
        stashes,
        ab,
        untracked_raw,
    ) = await asyncio.gather(
        _git(root, "branch", "--show-current"),
        _git(root, "rev-parse", "--short", "HEAD"),
        _git(root, "status", "--short"),
        _git(root, "log", "--oneline", "-20"),
        _git(root, "diff", "--stat"),
        _git(root, "tag", "--list", "--sort=-creatordate"),
        _git(root, "stash", "list"),
        _git(root, "rev-list", "--left-right", "--count", "HEAD...@{upstream}"),
        _git(root, "ls-files", "--others", "--exclude-standard"),
    )

    dirty = bool(status_text and status_text != "(unavailable)")

    ahead = 0
    behind = 0
    if ab and ab != "(unavailable)":
        parts = ab.split()
        if len(parts) == 2:
            try:
                ahead = int(parts[0])
                behind = int(parts[1])
            except ValueError:
                pass

    untracked: list[str] = []
    if untracked_raw and untracked_raw != "(unavailable)":
        untracked = [line for line in untracked_raw.splitlines() if line.strip()]

    snapshot = GitSnapshot(
        branch=branch,
        commit=commit,
        status=status_text,
        log=log,
        diff=diff,
        dirty=dirty,
        ahead=ahead,
        behind=behind,
        tags=tags,
        stashes=stashes,
        untracked=untracked,
    )
    logger.debug("Git snapshot: branch=%s commit=%s dirty=%s", branch, commit, dirty)
    return snapshot
