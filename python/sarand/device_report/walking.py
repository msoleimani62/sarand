"""Portable filesystem walking, sizing, and hashing.

Every function here is pure Python stdlib (`os`, `pathlib`, `hashlib`)
deliberately instead of shelling out to `du`, `find`, `numfmt`, or
`sha256sum`. Those tools' flags differ across GNU coreutils, BSD/macOS,
BusyBox (Termux's default), and Toybox (stock Android) -- `du -sb` and
`find -printf` in particular are GNU-only and silently misbehave or
error out elsewhere. `os.walk`/`os.stat`/`hashlib` behave identically
on every platform Python itself supports, which is what actually makes
this cross-distro and cross-architecture rather than merely
cross-x86_64.

پیمایش، اندازه‌گیری و هش‌کردن پرتابل فایل‌سیستم.

هر تابع اینجا عمداً از stdlib خالص پایتون (`os`، `pathlib`، `hashlib`)
استفاده می‌کند به‌جای صدا زدن `du`، `find`، `numfmt`، یا `sha256sum`.
فلگ‌های این ابزارها بین GNU coreutils، BSD/macOS، BusyBox (پیش‌فرض
Termux)، و Toybox (اندروید خام) فرق می‌کند -- به‌خصوص `du -sb` و
`find -printf` مخصوص GNU هستند و جای دیگر بی‌صدا خراب می‌شوند یا خطا
می‌دهند. `os.walk`/`os.stat`/`hashlib` روی هر پلتفرمی که خودِ پایتون
پشتیبانی می‌کند یکسان رفتار می‌کنند -- همین چیزی است که این را واقعاً
cross-distro و cross-architecture می‌کند، نه فقط cross-x86_64.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from pathlib import Path

_HASH_CHUNK_SIZE = 1024 * 1024


def is_excluded(path: Path, exclude_paths: list[str]) -> bool:
    path_str = str(path)
    for excluded in exclude_paths:
        if path_str == excluded or path_str.startswith(excluded.rstrip("/") + "/"):
            return True
    return False


def walk_pruned(
    root: Path,
    *,
    exclude_paths: list[str] | None = None,
    max_depth: int = 0,
    same_filesystem: bool = True,
) -> Iterator[tuple[Path, list[str], list[str]]]:
    """os.walk over `root`, honoring excludes/max-depth/-xdev-equivalent.

    Mirrors what the original bash script built with `find ... -prune`
    and `-xdev`, but with pruning done directly on os.walk's own
    `dirnames` list (its documented mechanism for this) instead of
    shelling out. max_depth=0 means unlimited, same convention as the
    original script and as sarand's own --max-depth.
    """
    exclude_paths = exclude_paths or []
    root = root.resolve()
    try:
        root_dev = os.stat(root).st_dev
    except OSError:
        return

    for dirpath, dirnames, filenames in os.walk(
        root, topdown=True, onerror=lambda _e: None
    ):
        current = Path(dirpath)
        depth = len(current.relative_to(root).parts)

        if max_depth and depth >= max_depth:
            dirnames[:] = []
        else:
            keep = []
            for name in dirnames:
                child = current / name
                if is_excluded(child, exclude_paths):
                    continue
                if same_filesystem:
                    try:
                        if os.stat(child).st_dev != root_dev:
                            continue
                    except OSError:
                        continue
                keep.append(name)
            dirnames[:] = keep

        yield current, dirnames, filenames


def path_size_bytes(path: Path) -> int:
    """Recursive size of a file or directory tree, in bytes.

    Portable replacement for `du -sb`. A file's own size is counted via
    `os.path.getsize`; unreadable entries are skipped rather than
    aborting the whole sum (matching the original script's
    best-effort, never-fail intent).
    """
    try:
        if path.is_symlink():
            return 0
        if path.is_file():
            return path.stat().st_size
        if not path.is_dir():
            return 0
    except OSError:
        return 0

    total = 0
    for dirpath, _dirnames, filenames in os.walk(path, onerror=lambda _e: None):
        for name in filenames:
            fp = Path(dirpath) / name
            try:
                if fp.is_symlink():
                    continue
                total += fp.stat().st_size
            except OSError:
                continue
    return total


def sha256_file(path: Path) -> str | None:
    """SHA-256 of a file's contents, or None if it can't be read.

    Portable replacement for shelling out to `sha256sum`/`shasum`.
    """
    digest = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            while chunk := fh.read(_HASH_CHUNK_SIZE):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def iter_files(
    root: Path,
    *,
    exclude_paths: list[str] | None = None,
    max_depth: int = 0,
) -> Iterator[Path]:
    """Yield every regular file under root, respecting excludes/max-depth."""
    for dirpath, _dirnames, filenames in walk_pruned(
        root, exclude_paths=exclude_paths, max_depth=max_depth
    ):
        for name in filenames:
            fp = dirpath / name
            try:
                if fp.is_symlink() or not fp.is_file():
                    continue
            except OSError:
                continue
            yield fp


def find_dirs_named(
    root: Path,
    names: set[str],
    *,
    exclude_paths: list[str] | None = None,
    max_depth: int = 0,
) -> Iterator[Path]:
    """Yield directories under root matching any of `names`, pruning
    their own subtree once matched (mirrors `find -prune` on a matched
    directory -- e.g. never descends into a found `node_modules`).
    """
    for dirpath, dirnames, _filenames in walk_pruned(
        root, exclude_paths=exclude_paths, max_depth=max_depth
    ):
        matched = [name for name in dirnames if name in names]
        for name in matched:
            yield dirpath / name
        # Prune matched dirs so we don't recurse into them.
        dirnames[:] = [name for name in dirnames if name not in matched]
