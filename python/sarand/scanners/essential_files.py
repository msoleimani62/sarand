"""Select "essential" (source/config) files from the shared scan records.

Reuses the single scan pass already done for stats -- no second
filesystem walk needed, unlike the old bxt implementation which did
one os.walk per concern (tree, stats, essential files).
"""

from __future__ import annotations

from pathlib import Path

from sarand.constants import ESSENTIAL_EXTENSIONS, MAX_FILE_SIZE
from sarand.progress import status
from sarand.rust_bridge import FileRecord, scan_project
from sarand.utils.logging import get_logger

logger = get_logger("essential_files")


def collect_essential_files(
    root: Path,
    *,
    records: list[FileRecord] | None = None,
    max_file_size: int = MAX_FILE_SIZE,
) -> tuple[list[Path], list[tuple[Path, int]]]:
    """Return (included relative paths, skipped-too-large (path, size))."""
    status("Collecting essential project files...")
    if records is None:
        records = scan_project(root)

    included: list[Path] = []
    skipped: list[tuple[Path, int]] = []

    for rec in records:
        if rec["is_symlink"] or rec["extension"] not in ESSENTIAL_EXTENSIONS:
            continue
        rel = Path(rec["rel_path"])
        if rec["size"] > max_file_size:
            skipped.append((rel, rec["size"]))
        else:
            included.append(rel)

    included.sort()
    skipped.sort(key=lambda x: x[0])
    logger.info("Included %d files, skipped %d large files", len(included), len(skipped))
    return included, skipped
