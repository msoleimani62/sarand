"""Source roots and module names (R14-A, docs/R14A_PLAN.md section 2).

A dotted module name starts at a *source root*. The root of a file is, in order:

1. a root declared in the project's `pyproject.toml` (maturin `python-source`,
   setuptools `package-dir` and `packages.find.where`) that contains the file;
2. otherwise the nearest ancestor directory that is not a regular package (has no
   `__init__.py`), which is where Python's import machinery starts for it.

A declared root matters for namespace packages (a layout without `__init__.py`);
the second rule handles ordinary packages. No installed metadata is read.

ریشه‌ی ماژول: ریشه‌ی اعلام‌شده در pyproject یا نزدیک‌ترین پوشه‌ی بدون __init__.py.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterable
from pathlib import PurePosixPath

_MANIFEST = "pyproject.toml"


def _as_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    return []


def declared_roots(manifest_dir: str, text: str) -> list[str]:
    """Source roots declared by one `pyproject.toml` (repo-relative POSIX paths).

    Unreadable or unrelated TOML gives an empty list; a manifest never breaks a run.
    """
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError):
        return []
    tool = data.get("tool")
    if not isinstance(tool, dict):
        return []
    found: list[str] = []
    maturin = tool.get("maturin")
    if isinstance(maturin, dict):
        found.extend(_as_list(maturin.get("python-source")))
    setuptools = tool.get("setuptools")
    if isinstance(setuptools, dict):
        package_dir = setuptools.get("package-dir")
        if isinstance(package_dir, dict) and isinstance(package_dir.get(""), str):
            found.append(package_dir[""])
        packages = setuptools.get("packages")
        find = packages.get("find") if isinstance(packages, dict) else None
        if isinstance(find, dict):
            found.extend(_as_list(find.get("where")))
    roots: list[str] = []
    for item in found:
        joined = (
            PurePosixPath(manifest_dir) / item if manifest_dir else PurePosixPath(item)
        )
        text_path = joined.as_posix().strip("/")
        roots.append("" if text_path in ("", ".") else text_path)
    return sorted(set(roots))


def _under(path: str, root: str) -> bool:
    return root == "" or path == root or path.startswith(root + "/")


def file_root(path: str, declared: Iterable[str], package_dirs: frozenset[str]) -> str:
    """The source root of `path`. `package_dirs` is the set of directories that hold
    an `__init__.py` (regular packages)."""
    best = ""
    found = False
    for root in declared:
        if _under(path, root) and (not found or len(root) > len(best)):
            best, found = root, True
    if found:
        return best
    directory = PurePosixPath(path).parent
    while str(directory) not in ("", ".") and directory.as_posix() in package_dirs:
        directory = directory.parent
    text = directory.as_posix()
    return "" if text in ("", ".") else text


def module_name(path: str, root: str) -> tuple[str, bool]:
    """The dotted module name of `path` under `root`, and whether the file is a
    package's `__init__.py`. An empty name means the file is not importable by
    name (for example `__main__` of nothing, or a path with a non-identifier part)."""
    relative = path[len(root) + 1 :] if root else path
    parts = relative.split("/")
    if not parts or not parts[-1].endswith(".py"):
        return "", False
    stem = parts[-1][:-3]
    is_package = stem == "__init__"
    pieces = parts[:-1] if is_package else [*parts[:-1], stem]
    if not pieces or not all(p.isidentifier() for p in pieces):
        return "", is_package
    return ".".join(pieces), is_package


def manifest_name() -> str:
    return _MANIFEST
