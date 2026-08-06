"""Project tree rendering (thin wrapper over rust_bridge)."""

from __future__ import annotations

from pathlib import Path

from sarand.constants import IGNORE_DIRS, MAX_TREE_DEPTH, MAX_TREE_ENTRIES
from sarand.progress import status
from sarand.rust_bridge import build_tree_text as _build_tree_text
from sarand.utils.logging import get_logger

logger = get_logger("tree")


def build_tree(root: Path, *, max_depth: int = MAX_TREE_DEPTH, max_entries: int = MAX_TREE_ENTRIES) -> str:
    status("Building project tree...")
    logger.info("Building tree (depth=%d, entries=%d)", max_depth, max_entries)
    return _build_tree_text(root, ignore_dirs=IGNORE_DIRS, max_depth=max_depth, max_entries=max_entries)
