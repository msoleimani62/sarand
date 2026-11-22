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
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

from pathspec import GitIgnoreSpec

from sarand.constants import (
    HASH_MAX_BYTES,
    IGNORE_DIRS,
    MAX_HASH_FILES,
    MAX_TREE_DEPTH,
    MAX_TREE_ENTRIES,
)
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
        raw = _core.scan_project(
            str(root), list(ignore_dirs), hash_max_bytes, max_hash_files
        )
        return raw  # already list[dict] with matching keys

    return _pure_python_scan(root, ignore_dirs, hash_max_bytes, max_hash_files)


# How many reasons are kept (the count is always exact): a million unreadable
# files must not become a million strings.
# چند دلیل نگه داشته می‌شود (شمارش همیشه دقیق است).
MAX_PROBLEM_SAMPLES = 5


@dataclass
class ScanProblems:
    """Paths the scan could not read (permission denied, vanished, ...).

    Before AGENTS.md 5.74 these were dropped silently, so every count in the report
    could be short with no sign of it. `samples` never holds an absolute path.

    مسیرهایی که اسکن نتوانست بخواند؛ قبلاً بی‌صدا حذف می‌شدند.
    """

    skipped: int = 0
    samples: list[str] = field(default_factory=list)

    def add(self, message: str) -> None:
        self.skipped += 1
        if len(self.samples) < MAX_PROBLEM_SAMPLES:
            self.samples.append(message)


def scan_project_report(
    root: Path,
    *,
    ignore_dirs: frozenset[str] = IGNORE_DIRS,
    hash_max_bytes: int = HASH_MAX_BYTES,
    max_hash_files: int = MAX_HASH_FILES,
) -> tuple[list[FileRecord], ScanProblems]:
    """Like `scan_project`, plus what could not be read.

    A compiled core built before this function existed (a stale `_core*.so` next to
    newer Python) has no `scan_project_report`; it is used through the old function
    and reports no problems rather than crashing.
    """
    if RUST_CORE_AVAILABLE:
        report = getattr(_core, "scan_project_report", None)
        if report is not None:
            records, skipped, samples = report(
                str(root), list(ignore_dirs), hash_max_bytes, max_hash_files
            )
            return records, ScanProblems(skipped=skipped, samples=list(samples))
        return (
            scan_project(
                root,
                ignore_dirs=ignore_dirs,
                hash_max_bytes=hash_max_bytes,
                max_hash_files=max_hash_files,
            ),
            ScanProblems(),
        )

    problems = ScanProblems()
    records = _pure_python_scan(
        root, ignore_dirs, hash_max_bytes, max_hash_files, problems=problems
    )
    return records, problems


def _describe_walk_error(root: Path, error: OSError) -> str:
    """`relative/path: reason`, never the absolute path."""
    where = (
        safe_relative(Path(str(error.filename)), root).as_posix()
        if error.filename
        else "?"
    )
    return f"{where}: {error.strerror or error}"


def _git_directory(root: Path) -> tuple[Path, Path] | None:
    for parent in (root, *root.parents):
        marker = parent / ".git"
        if marker.is_dir():
            return marker, parent
        if marker.is_file():
            try:
                first_line = marker.read_text(encoding="utf-8").strip()
            except OSError:
                return None
            if not first_line.startswith("gitdir:"):
                return None
            target = Path(first_line.partition(":")[2].strip())
            git_dir = (
                (parent / target).resolve() if not target.is_absolute() else target
            )
            common_dir_file = git_dir / "commondir"
            if common_dir_file.is_file():
                try:
                    common_value = common_dir_file.read_text(encoding="utf-8").strip()
                except OSError:
                    return None
                common_dir = Path(common_value)
                git_dir = (
                    (git_dir / common_dir).resolve()
                    if not common_dir.is_absolute()
                    else common_dir
                )
            return git_dir, parent
    return None


def _read_ignore_spec(
    directory: Path, filename: str, problems: ScanProblems | None
) -> GitIgnoreSpec | None:
    path = directory / filename
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return None
    except OSError as error:
        if problems is not None:
            problems.add(_describe_walk_error(directory, error))
        return None
    if not lines:
        return None
    try:
        return GitIgnoreSpec.from_lines(lines)
    except ValueError as error:
        if problems is not None:
            problems.add(f"{filename}: invalid ignore pattern: {error}")
        return None


def _is_ignored_by_rules(
    path: Path,
    is_directory: bool,
    rules: list[tuple[Path, GitIgnoreSpec]],
) -> bool:
    ignored = False
    for base, spec in rules:
        try:
            relative = path.relative_to(base).as_posix()
        except ValueError:
            continue
        if is_directory:
            relative += "/"
        result = spec.check_file(relative)
        if result.include is not None:
            ignored = result.include
    return ignored


def _ancestor_ignore_rules(
    root: Path, problems: ScanProblems | None
) -> tuple[list[tuple[Path, GitIgnoreSpec]], list[tuple[Path, GitIgnoreSpec]]]:
    git_rules: list[tuple[Path, GitIgnoreSpec]] = []
    ignore_rules: list[tuple[Path, GitIgnoreSpec]] = []
    git_metadata = _git_directory(root)
    if git_metadata is not None:
        git_dir, repository_root = git_metadata
        exclude = _read_ignore_spec(git_dir / "info", "exclude", problems)
        if exclude is not None:
            git_rules.append((repository_root, exclude))

    for directory in reversed(root.parents):
        spec = _read_ignore_spec(directory, ".gitignore", problems)
        if spec is not None:
            git_rules.append((directory, spec))
    for directory in reversed(root.parents):
        spec = _read_ignore_spec(directory, ".ignore", problems)
        if spec is not None:
            ignore_rules.append((directory, spec))
    return git_rules, ignore_rules


def build_tree_text(
    root: Path,
    *,
    ignore_dirs: frozenset[str] = IGNORE_DIRS,
    max_depth: int = MAX_TREE_DEPTH,
    max_entries: int = MAX_TREE_ENTRIES,
) -> str:
    """Build the ASCII project tree, Rust-accelerated when available."""
    if RUST_CORE_AVAILABLE:
        return _core.build_tree_text(
            str(root), list(ignore_dirs), max_depth, max_entries
        )
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
                elif stripped.startswith(("#", "//")):
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
    problems: ScanProblems | None = None,
) -> list[FileRecord]:
    import hashlib

    records: list[FileRecord] = []
    root = root.resolve()
    inherited_git_rules, inherited_ignore_rules = _ancestor_ignore_rules(root, problems)
    rules_by_directory: dict[
        Path,
        tuple[list[tuple[Path, GitIgnoreSpec]], list[tuple[Path, GitIgnoreSpec]]],
    ] = {}

    def on_error(error: OSError) -> None:
        if problems is not None:
            problems.add(_describe_walk_error(root, error))

    for dirpath, dirnames, filenames in os.walk(root, topdown=True, onerror=on_error):
        directory = Path(dirpath)
        if directory == root:
            git_rules = list(inherited_git_rules)
            ignore_rules = list(inherited_ignore_rules)
        else:
            parent_rules = rules_by_directory.get(
                directory.parent, (inherited_git_rules, inherited_ignore_rules)
            )
            git_rules = list(parent_rules[0])
            ignore_rules = list(parent_rules[1])

        git_spec = _read_ignore_spec(directory, ".gitignore", problems)
        if git_spec is not None:
            git_rules.append((directory, git_spec))
        ignore_spec = _read_ignore_spec(directory, ".ignore", problems)
        if ignore_spec is not None:
            ignore_rules.append((directory, ignore_spec))
        rules_by_directory[directory] = (git_rules, ignore_rules)
        rules = [*git_rules, *ignore_rules]

        dirnames.sort()
        filenames.sort()
        retained_directories: list[str] = []
        for name in dirnames:
            child = directory / name
            if name in ignore_dirs or _is_ignored_by_rules(child, True, rules):
                continue
            retained_directories.append(name)
        dirnames[:] = retained_directories

        for name in filenames:
            path = directory / name
            if _is_ignored_by_rules(path, False, rules):
                continue
            rel = safe_relative(path, root).as_posix()

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
            except OSError as error:
                if problems is not None:
                    problems.add(f"{rel}: {error.strerror or error}")
                continue

            binary = is_binary(path)
            if binary:
                total = code = comment = blank = 0
            else:
                total, code, comment, blank = _count_lines(path)

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
                    content_hash=None,
                )
            )

    records.sort(key=lambda record: record["rel_path"])
    hashed = 0
    for record in records:
        if (
            hashed >= max_hash_files
            or record["is_symlink"]
            or record["is_binary"]
            or not 0 < record["size"] <= hash_max_bytes
        ):
            continue
        path = root / record["rel_path"]
        hashed += 1
        try:
            record["content_hash"] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as error:
            if problems is not None:
                problems.add(f"{record['rel_path']}: {error.strerror or error}")
    return records


def _pure_python_tree(
    root: Path, ignore_dirs: frozenset[str], max_depth: int, max_entries: int
) -> str:
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
