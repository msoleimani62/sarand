"""Select "essential" (source/config) files from the shared scan records.

Reuses the single scan pass already done for stats -- no second
filesystem walk needed, unlike the old bxt implementation which did
one os.walk per concern (tree, stats, essential files).
"""

from __future__ import annotations

from pathlib import Path

from sarand.constants import ESSENTIAL_EXTENSIONS, MAX_FILE_SIZE
from sarand.core.secrets import looks_like_secret_filename
from sarand.progress import status
from sarand.rust_bridge import FileRecord, scan_project
from sarand.utils.logging import get_logger

logger = get_logger("essential_files")


def collect_essential_files(
    root: Path,
    *,
    records: list[FileRecord] | None = None,
    max_file_size: int = MAX_FILE_SIZE,
) -> tuple[list[Path], list[tuple[Path, int]], list[Path]]:
    """Return (included, skipped-too-large (path, size), excluded-as-secret).

    The excluded-as-secret list (AGENTS.md §4.10) is filtered out
    unconditionally -- there is no flag to disable this, by design: it's
    a safety rule, not an optional feature.
    """
    status("Collecting essential project files...")
    if records is None:
        records = scan_project(root)

    included: list[Path] = []
    skipped: list[tuple[Path, int]] = []
    excluded_secrets: list[Path] = []

    for rec in records:
        if rec["is_symlink"] or rec["extension"] not in ESSENTIAL_EXTENSIONS:
            continue
        rel = Path(rec["rel_path"])

        if looks_like_secret_filename(rel.name):
            excluded_secrets.append(rel)
            continue

        if rec["size"] > max_file_size:
            skipped.append((rel, rec["size"]))
        else:
            included.append(rel)

    included.sort()
    skipped.sort(key=lambda x: x[0])
    excluded_secrets.sort()
    if excluded_secrets:
        logger.warning("Excluded %d credential-shaped file(s) from the report", len(excluded_secrets))
    logger.info("Included %d files, skipped %d large files", len(included), len(skipped))
    return included, skipped, excluded_secrets
