"""Git repository analysis."""

from __future__ import annotations

from pathlib import Path

from sarand.models.results import GitSnapshot
from sarand.progress import status
from sarand.utils.command import run_cmd
from sarand.utils.logging import get_logger

logger = get_logger("git")


def _git(root: Path, *args: str, timeout: int = 60) -> str:
    rc, out, _ = run_cmd(["git", *args], cwd=root, timeout=timeout)
    if rc == 0:
        return out.strip()
    return "(unavailable)"


def collect_git_snapshot(root: Path) -> GitSnapshot:
    """Collect a comprehensive Git status snapshot."""
    status("Collecting Git information...")
    logger.info("Inspecting Git state at %s", root)

    rc, _, _ = run_cmd(
        ["git", "rev-parse", "--is-inside-work-tree"], cwd=root, timeout=10
    )
    if rc != 0:
        logger.warning("Not a git repository")
        return GitSnapshot()

    branch = _git(root, "branch", "--show-current")
    commit = _git(root, "rev-parse", "--short", "HEAD")
    status_text = _git(root, "status", "--short")
    log = _git(root, "log", "--oneline", "-20")
    diff = _git(root, "diff", "--stat")
    tags = _git(root, "tag", "--list", "--sort=-creatordate")
    stashes = _git(root, "stash", "list")

    dirty = bool(status_text and status_text != "(unavailable)")

    ahead = 0
    behind = 0
    ab = _git(root, "rev-list", "--left-right", "--count", "HEAD...@{upstream}")
    if ab and ab != "(unavailable)":
        parts = ab.split()
        if len(parts) == 2:
            try:
                ahead = int(parts[0])
                behind = int(parts[1])
            except ValueError:
                pass

    untracked_raw = _git(root, "ls-files", "--others", "--exclude-standard")
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
