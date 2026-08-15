"""Aggregate ProjectStats from the flat scan record list.

Business rules here (what counts as "temporary", "cache-like", which
extensions matter) are pure Python on purpose -- they change often and
should never require recompiling the Rust core.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from sarand.models.results import ProjectStats
from sarand.progress import status
from sarand.rust_bridge import FileRecord, scan_project
from sarand.utils.logging import get_logger

logger = get_logger("stats")

_CACHE_DIR_MARKERS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "target",
    "node_modules",
}


def collect_project_stats(
    root: Path, records: list[FileRecord] | None = None
) -> ProjectStats:
    """Aggregate ProjectStats from a scan record list.

    Args:
        root: Project root (used only for logging).
        records: Pre-computed records from ``rust_bridge.scan_project``.
            If omitted, a scan is performed here (useful for callers
            that only need stats, not the full record list).
    """
    status("Collecting project statistics...")
    if records is None:
        records = scan_project(root)

    stats = ProjectStats()
    dir_sizes: dict[str, int] = defaultdict(int)
    file_sizes: list[tuple[str, int]] = []
    hashes: dict[str, list[str]] = defaultdict(list)
    ext_counts: dict[str, int] = defaultdict(int)

    for rec in records:
        stats.total_files += 1

        if rec["is_hidden"]:
            stats.hidden_files += 1

        if rec["is_symlink"]:
            if rec["is_broken_symlink"]:
                stats.broken_symlinks.append(rec["rel_path"])
            continue

        rel = rec["rel_path"]
        lower_name = rel.lower()
        if lower_name.endswith((".tmp", ".temp", ".swp", "~")):
            stats.temporary_files.append(rel)
        if any(marker in rel.split("/") for marker in _CACHE_DIR_MARKERS):
            stats.unused_cache_files.append(rel)
        if rec["size"] == 0:
            stats.empty_files.append(rel)
        if rec["is_executable"]:
            stats.executable_scripts.append(rel)

        ext = rec["extension"]
        if ext:
            ext_counts[ext] += 1

        if rec["is_binary"]:
            stats.binary_files += 1
        else:
            stats.total_loc += rec["total_lines"]
            stats.code_lines += rec["code_lines"]
            stats.comment_lines += rec["comment_lines"]
            stats.blank_lines += rec["blank_lines"]

        file_sizes.append((rel, rec["size"]))
        parent = str(Path(rel).parent) if "/" in rel else "."
        dir_sizes[parent] += rec["size"]

        if rec["content_hash"]:
            hashes[rec["content_hash"]].append(rel)

    file_sizes.sort(key=lambda x: x[1], reverse=True)
    stats.largest_files = file_sizes[:20]

    sorted_dirs = sorted(dir_sizes.items(), key=lambda x: x[1], reverse=True)
    stats.largest_directories = sorted_dirs[:15]

    for digest, paths in hashes.items():
        if len(paths) > 1:
            stats.duplicate_files.append((digest[:12], paths))

    stats.files_by_extension = dict(
        sorted(ext_counts.items(), key=lambda kv: kv[1], reverse=True)
    )

    logger.info(
        "Stats: %d files, %d LOC, extensions=%s",
        stats.total_files,
        stats.total_loc,
        list(stats.files_by_extension.items())[:5],
    )
    return stats
