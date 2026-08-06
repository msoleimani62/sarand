"""Bridge to the compiled Rust core (``sarand._core``), with a pure-Python
fallback that produces the exact same data shape.

This is the single point of truth for "is the fast path available".
Everything downstream (scanners/stats.py, scanners/tree.py, ...) calls
these two functions and never touches ``sarand._core`` or ``os.walk``
directly -- which is what makes the Rust core optional rather than
required: on a platform where `maturin develop` fails to compile
(e.g. an exotic Termux/aarch64 toolchain), sarand keeps working, just
slower.

این تنها نقطه‌ی تصمیم‌گیری «آیا مسیر سریع در دسترس است» است. هرچیزی
پایین‌دست (scanners/stats.py، scanners/tree.py، ...) فقط همین دو تابع
را صدا می‌زند و هرگز مستقیم به ``sarand._core`` یا ``os.walk`` دست
نمی‌زند -- دقیقاً همین چیزی است که هسته‌ی Rust را «اختیاری» می‌کند نه
«الزامی»: در پلتفرمی که کامپایل `maturin develop` شکست بخورد (مثلاً
یک زنجیره‌ابزار عجیب Termux/aarch64)، sarand همچنان کار می‌کند، فقط
کندتر.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, TypedDict

from sarand.constants import HASH_MAX_BYTES, IGNORE_DIRS, MAX_HASH_FILES, MAX_TREE_DEPTH, MAX_TREE_ENTRIES
from sarand.utils.fs import is_binary, safe_relative

try:
    from sarand import _core  # type: ignore[attr-defined]

    RUST_CORE_AVAILABLE = True
except ImportError:
    _core = None  # type: ignore[assignment]
    RUST_CORE_AVAILABLE = False


class FileRecord(TypedDict):
    rel_path: str
    size: int
    is_symlink: bool
    is_broken_symlink: bool
    is_hidden: bool
    is_binary: bool
    is_executable: bool
    extension: str
    total_lines: int
    code_lines: int
    comment_lines: int
    blank_lines: int
    content_hash: str | None


def scan_project(
    root: Path,
    *,
    ignore_dirs: frozenset[str] = IGNORE_DIRS,
    hash_max_bytes: int = HASH_MAX_BYTES,
    max_hash_files: int = MAX_HASH_FILES,
) -> list[FileRecord]:
    """Walk ``root`` once and return a flat per-file record list.

    Tries the compiled Rust core first; falls back to an equivalent
    pure-Python walk (same field names, same semantics) if the
    extension module was never built for this platform.
    """
    if RUST_CORE_AVAILABLE:
        raw = _core.scan_project(str(root), list(ignore_dirs), hash_max_bytes, max_hash_files)
        return raw  # already list[dict] with matching keys

    return _pure_python_scan(root, ignore_dirs, hash_max_bytes, max_hash_files)


def build_tree_text(
    root: Path,
    *,
    ignore_dirs: frozenset[str] = IGNORE_DIRS,
    max_depth: int = MAX_TREE_DEPTH,
    max_entries: int = MAX_TREE_ENTRIES,
) -> str:
    """Build the ASCII project tree, Rust-accelerated when available."""
    if RUST_CORE_AVAILABLE:
        return _core.build_tree_text(str(root), list(ignore_dirs), max_depth, max_entries)
    return _pure_python_tree(root, ignore_dirs, max_depth, max_entries)


# ---------------------------------------------------------------------
# Pure-Python fallbacks (identical semantics to the Rust implementation)
# نسخه‌های fallback خالص‌پایتونی (با معناشناسی یکسان با پیاده‌سازی Rust)
# ---------------------------------------------------------------------


def _count_lines(path: Path) -> tuple[int, int, int, int]:
    total = code = comment = blank = 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                total += 1
                stripped = line.strip()
                if not stripped:
                    blank += 1
                elif stripped.startswith("#") or stripped.startswith("//"):
                    comment += 1
                else:
                    code += 1
    except OSError:
        pass
    return total, code, comment, blank


def _pure_python_scan(
    root: Path,
    ignore_dirs: frozenset[str],
    hash_max_bytes: int,
    max_hash_files: int,
) -> list[FileRecord]:
    import hashlib

    records: list[FileRecord] = []
    hashed = 0

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs and not d.startswith(".git")]
        for name in filenames:
            path = Path(dirpath) / name
            rel = str(safe_relative(path, root))

            if path.is_symlink():
                broken = not path.exists()
                records.append(
                    FileRecord(
                        rel_path=rel,
                        size=0,
                        is_symlink=True,
                        is_broken_symlink=broken,
                        is_hidden=name.startswith("."),
                        is_binary=False,
                        is_executable=False,
                        extension="",
                        total_lines=0,
                        code_lines=0,
                        comment_lines=0,
                        blank_lines=0,
                        content_hash=None,
                    )
                )
                continue

            try:
                st = path.stat()
            except OSError:
                continue

            binary = is_binary(path)
            if binary:
                total = code = comment = blank = 0
            else:
                total, code, comment, blank = _count_lines(path)

            content_hash = None
            if not binary and 0 < st.st_size <= hash_max_bytes and hashed < max_hash_files:
                try:
                    content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
                    hashed += 1
                except OSError:
                    pass

            records.append(
                FileRecord(
                    rel_path=rel,
                    size=st.st_size,
                    is_symlink=False,
                    is_broken_symlink=False,
                    is_hidden=name.startswith("."),
                    is_binary=binary,
                    is_executable=os.access(path, os.X_OK),
                    extension=path.suffix.lower(),
                    total_lines=total,
                    code_lines=code,
                    comment_lines=comment,
                    blank_lines=blank,
                    content_hash=content_hash,
                )
            )

    return records


def _pure_python_tree(root: Path, ignore_dirs: frozenset[str], max_depth: int, max_entries: int) -> str:
    lines: list[str] = [f"{root.name}/"]

    def walk(directory: Path, prefix: str, depth: int) -> None:
        if depth >= max_depth:
            return
        try:
            entries = sorted(
                (item for item in directory.iterdir() if item.name not in ignore_dirs),
                key=lambda item: (item.is_file(), item.name.lower()),
            )
        except OSError:
            return

        hidden = max(0, len(entries) - max_entries)
        entries = entries[:max_entries]

        for index, entry in enumerate(entries):
            last = index == len(entries) - 1 and hidden == 0
            connector = "└── " if last else "├── "
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{prefix}{connector}{entry.name}{suffix}")
            if entry.is_dir():
                extension = "    " if last else "│   "
                walk(entry, prefix + extension, depth + 1)

        if hidden:
            lines.append(f"{prefix}└── ... ({hidden} more entries hidden)")

    walk(root, "", 0)
    return "\n".join(lines)
