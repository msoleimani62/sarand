"""Source roots and module names (R14-A, docs/R14A_PLAN.md section 2).

A dotted module name starts at a *source root*. The root of a file is, in order:

1. a root declared in the project's `pyproject.toml` that contains the file (maturin
   `python-source`; setuptools `package-dir` and `packages.find.where`); the longest
   declared directory wins;
2. otherwise the nearest ancestor directory that is not a regular package (has no
   `__init__.py`), which is where Python's import machinery starts for it.

A declared root can carry a **package prefix**: the setuptools mapping
`package-dir = {"mypkg" = "lib/other"}` says the directory `lib/other` *is* the
package `mypkg`, so `lib/other/a.py` is the module `mypkg.a`. The empty key
(`{"" = "src"}`) means no prefix.

A declared root must be a relative path inside the repository: an absolute path, a
backslash, or a `..` that leaves the repository is rejected and reported (never
silently used or dropped). No installed metadata is read.

ریشه‌ی ماژول و پیشوند بسته؛ ریشه‌ی نامعتبر رد و گزارش می‌شود.
"""

from __future__ import annotations

import posixpath
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath

_MANIFEST = "pyproject.toml"


@dataclass(frozen=True)
class DeclaredRoot:
    """A source root declared in a manifest: a repo-relative directory (`""` is the
    repository root) and the package name that directory stands for (`""` = none)."""

    path: str
    prefix: str = ""


def manifest_name() -> str:
    return _MANIFEST


def normalise_root(manifest_dir: str, value: str) -> str | None:
    """A declared root as a repo-relative POSIX path, or `None` when it is not one.

    `manifest_dir` is the directory of the manifest (the value is relative to it).
    Rejected: empty-looking absolute forms, a backslash, a Windows drive, and any
    path that leaves the repository after normalisation."""
    text = value.strip()
    if (
        not text
        or text.startswith("/")
        or "\\" in text
        or (len(text) > 1 and text[1] == ":")
    ):
        return None
    joined = posixpath.normpath(posixpath.join(manifest_dir or ".", text))
    if joined == ".":
        return ""
    if joined == ".." or joined.startswith(("../", "/")):
        return None
    return joined


def _as_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    return []


def _valid_prefix(prefix: str) -> bool:
    return prefix == "" or all(part.isidentifier() for part in prefix.split("."))


def declared_roots(
    manifest_dir: str, text: str
) -> tuple[list[DeclaredRoot], list[str]]:
    """Source roots declared by one `pyproject.toml`, and the declarations that were
    rejected (as written). Unreadable or unrelated TOML gives two empty lists; a
    manifest never breaks a run."""
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError):
        return [], []
    tool = data.get("tool")
    if not isinstance(tool, dict):
        return [], []
    wanted: list[tuple[str, str]] = []  # (raw path, prefix)
    maturin = tool.get("maturin")
    if isinstance(maturin, dict):
        wanted.extend((raw, "") for raw in _as_list(maturin.get("python-source")))
    setuptools = tool.get("setuptools")
    if isinstance(setuptools, dict):
        package_dir = setuptools.get("package-dir")
        if isinstance(package_dir, dict):
            for key, raw in package_dir.items():
                if isinstance(key, str) and isinstance(raw, str):
                    wanted.append((raw, key))
        packages = setuptools.get("packages")
        find = packages.get("find") if isinstance(packages, dict) else None
        if isinstance(find, dict):
            wanted.extend((raw, "") for raw in _as_list(find.get("where")))
    roots: set[DeclaredRoot] = set()
    rejected: set[str] = set()
    for raw, prefix in wanted:
        path = normalise_root(manifest_dir, raw)
        if path is None or not _valid_prefix(prefix):
            rejected.add(raw if prefix == "" else f"{prefix} = {raw}")
            continue
        roots.add(DeclaredRoot(path, prefix))
    return sorted(roots, key=lambda r: (r.path, r.prefix)), sorted(rejected)


def _under(path: str, root: str) -> bool:
    return root == "" or path == root or path.startswith(root + "/")


def file_root(
    path: str, declared: Iterable[DeclaredRoot], package_dirs: frozenset[str]
) -> tuple[str, str]:
    """The source root of `path` and the package prefix that goes with it.
    `package_dirs` is the set of directories that hold an `__init__.py`."""
    best: DeclaredRoot | None = None
    for root in declared:
        if _under(path, root.path) and (
            best is None
            or (len(root.path), len(root.prefix)) > (len(best.path), len(best.prefix))
        ):
            best = root
    if best is not None:
        return best.path, best.prefix
    directory = PurePosixPath(path).parent
    while str(directory) not in ("", ".") and directory.as_posix() in package_dirs:
        directory = directory.parent
    text = directory.as_posix()
    return ("" if text in ("", ".") else text), ""


def module_name(path: str, root: str, prefix: str = "") -> tuple[str, bool]:
    """The dotted module name of `path` under `root` (with `prefix` in front when the
    root stands for a package), and whether the file is a package's `__init__.py`.

    An empty name means the file is not importable by name: it is not inside `root`,
    a path part is not an identifier, or it is the `__init__.py` of a root that has no
    package name (a root-level `__init__.py` has no name to import it by)."""
    if not _under(path, root):
        return "", False
    relative = path[len(root) + 1 :] if root else path
    parts = relative.split("/")
    if not parts or not parts[-1].endswith(".py"):
        return "", False
    stem = parts[-1][:-3]
    is_package = stem == "__init__"
    pieces = parts[:-1] if is_package else [*parts[:-1], stem]
    if not all(p.isidentifier() for p in pieces):
        return "", is_package
    if prefix:
        pieces = [*prefix.split("."), *pieces]
    if not pieces:
        return "", is_package
    return ".".join(pieces), is_package
