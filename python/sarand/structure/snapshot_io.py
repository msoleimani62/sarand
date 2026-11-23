"""Reading and writing structure snapshot files (R14-D1, slice S2).

`snapshot.py` builds and checks the envelope in memory; this module is the only place
that touches the disk for it. Three rules:

- **A reference is never destroyed by accident.** Writing to a path that already holds
  a file is refused unless the caller asks to replace it. A replacement keeps the
  previous generation next to it as `<name>.prev`, so the older reference can be
  restored by renaming it back.
- **A write is all or nothing.** The snapshot is staged in a temporary file in the same
  directory, flushed to disk, read back and verified (it must parse as a usable
  snapshot with the digest that was meant), and only then renamed into place. A failure
  at any step leaves the destination as it was.
- **Reading never raises.** A missing, unreadable, too large or malformed file becomes a
  `Reference` that says why it cannot be used, like any other unusable reference.

عکس لحظه‌ای ساختار روی دیسک: مرجع هرگز تصادفی از بین نمی‌رود، نوشتن یا کامل است یا هیچ،
و خواندن هرگز exception نمی‌دهد.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sarand.structure.snapshot import (
    PROBLEM_INVALID,
    Reference,
    read_reference,
    snapshot_text,
)

# A real snapshot is a few MB (about 12 MB for 5,000 symbols); this stops a wrong file
# (a log, a disk image) from being read whole.
# snapshot واقعی چند مگابایت است؛ این سقف جلوی خواندنِ کاملِ فایل اشتباه را می‌گیرد.
MAX_SNAPSHOT_BYTES = 256 * 1024 * 1024
PREVIOUS_SUFFIX = ".prev"


class SnapshotTargetError(ValueError):
    """The path cannot be written as a snapshot (the message says why)."""


@dataclass(frozen=True)
class SnapshotWrite:
    """What a write did."""

    path: Path
    digest: str
    previous: Path | None  # the kept previous generation, if the file was replaced


def previous_path(path: Path) -> Path:
    """Where the previous generation of `path` is kept."""
    return path.with_name(path.name + PREVIOUS_SUFFIX)


def read_reference_file(path: Path) -> Reference:
    """The reference in a file: a snapshot or a JSON report. Never raises."""
    try:
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            return _invalid(f"{path} is not a regular file")
        if info.st_size > MAX_SNAPSHOT_BYTES:
            return _invalid(f"{path} is larger than {MAX_SNAPSHOT_BYTES} bytes")
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _invalid(f"{path} does not exist")
    except OSError as exc:
        return _invalid(f"{path} cannot be read: {exc.strerror or exc}")
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        return _invalid(f"{path} is not valid JSON: {exc}")
    return read_reference(data)


def _invalid(message: str) -> Reference:
    return Reference(problem_kind=PROBLEM_INVALID, problem=message)


def check_snapshot_target(path: Path, *, replace: bool) -> None:
    """Raise `SnapshotTargetError` unless `path` may be written now.

    Called before a scan starts, so a refusal costs nothing, and again by
    `write_snapshot`. A symbolic link is refused (it could point anywhere), a missing
    parent directory is not created, and an existing file needs `replace`.
    """
    parent = path.parent
    if not parent.is_dir():
        raise SnapshotTargetError(f"the directory {parent} does not exist")
    if path.is_symlink():
        raise SnapshotTargetError(f"{path} is a symbolic link")
    if path.is_dir():
        raise SnapshotTargetError(f"{path} is a directory")
    if previous_path(path).is_symlink():
        raise SnapshotTargetError(f"{previous_path(path)} is a symbolic link")
    if path.exists() and not replace:
        raise SnapshotTargetError(
            f"{path} already exists; pass --replace-structure-snapshot to replace it "
            f"(the old file is kept as {previous_path(path).name})"
        )


def write_snapshot(
    path: Path, snapshot: Mapping[str, Any], *, replace: bool = False
) -> SnapshotWrite:
    """Write `snapshot` to `path`; all or nothing, and never over a file unasked."""
    check_snapshot_target(path, replace=replace)
    text = snapshot_text(snapshot)
    existed = path.exists()
    mode = _file_mode(path)
    staged = _stage(path.parent, f".{path.name}.", text, mode)
    kept: Path | None = None
    try:
        _verify(staged, str(snapshot.get("digest", "")))
        if existed:
            kept = previous_path(path)
            _copy_atomically(path, kept, mode)
        os.replace(staged, path)
        _fsync_directory(path.parent)
    finally:
        staged.unlink(missing_ok=True)
    return SnapshotWrite(
        path=path, digest=str(snapshot.get("digest", "")), previous=kept
    )


# ------------------------------------------------------------------- helpers


def _file_mode(previous: Path) -> int:
    """The permission bits of a new snapshot: the old file's, else the umask default
    (a temporary file alone would be private, 0600).
    مجوز snapshot تازه: همان فایل قبلی، وگرنه پیش‌فرض umask (فایل موقت تنها خصوصی است).
    """
    try:
        return stat.S_IMODE(previous.stat().st_mode)
    except OSError:
        current = os.umask(0)
        os.umask(current)
        return 0o666 & ~current


def _stage(directory: Path, prefix: str, text: str, mode: int) -> Path:
    """Write `text` to a new temporary file in `directory`, flushed to disk."""
    fd, name = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=directory)
    staged = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != "nt":
            staged.chmod(mode)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    return staged


def _verify(staged: Path, expected_digest: str) -> None:
    """The staged file must read back as a usable snapshot with the expected digest."""
    try:
        data = json.loads(staged.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError) as exc:
        raise OSError(f"the snapshot did not read back: {exc}") from exc
    reference = read_reference(data)
    if not reference.usable:
        raise OSError(f"the snapshot did not read back correctly: {reference.problem}")
    if data.get("digest") != expected_digest:
        raise OSError("the snapshot read back with another digest than the one written")


def _copy_atomically(source: Path, target: Path, mode: int) -> None:
    """Copy `source` to `target` through a temporary file, so `target` is never partial."""
    fd, name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    os.close(fd)
    temporary = Path(name)
    try:
        shutil.copyfile(source, temporary)
        if os.name != "nt":
            temporary.chmod(mode)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    """Flush the directory entry so the rename survives a crash (not possible on Windows).
    ورودی دایرکتوری را هم می‌نویسد تا جایگزینی از کرش جان به در ببرد (در Windows ممکن نیست).
    """
    if os.name == "nt":
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
