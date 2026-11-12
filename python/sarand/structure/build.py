"""Build the structural model of a project (R14-A, docs/R14A_PLAN.md).

`build_structure` takes the files the report is allowed to read, finds the source
roots, names the modules, reads every Python file with `ast` (never executing it),
resolves the imports and finds the cycles. It is deterministic: files are processed
in sorted path order and every collection is sorted before it is returned.

Two environment inputs are named and recorded in `meta`, never hidden: the
interpreter version (the `ast` grammar and the standard-library name list depend on
it) and the standard-library names themselves.

ساخت مدل ساختاری پروژه؛ قطعی، بدون اجرای کد، و ورودی‌های محیطی در meta ثبت می‌شوند.
"""

from __future__ import annotations

import platform
import sys
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path, PurePosixPath

from sarand.core.components import declared_dependencies
from sarand.structure.cycles import find_cycles
from sarand.structure.imports import ModuleIndex, normalise_distribution, resolve_record
from sarand.structure.model import (
    COMPLETENESS_FAILED,
    COMPLETENESS_SKIPPED_SIZE,
    LANGUAGE_PYTHON,
    LIM_TOO_LARGE,
    LIM_UNREADABLE,
    PARSER_PYTHON_AST,
    SCHEMA_VERSION,
    TARGET_EXTERNAL_DECLARED,
    TARGET_EXTERNAL_UNMATCHED,
    TARGET_STDLIB,
    Edge,
    ExternalRef,
    FileEntity,
    ModuleEntity,
    Provenance,
    StructureData,
)
from sarand.structure.python_extract import extract_imports
from sarand.structure.roots import declared_roots, file_root, manifest_name, module_name

_PYTHON_MANIFESTS = frozenset({"pyproject.toml", "requirements.txt"})


def _posix(path: Path) -> str:
    return PurePosixPath(*path.parts).as_posix()


def _read(root: Path, rel: str) -> bytes | None:
    try:
        return (root / rel).read_bytes()
    except OSError:
        return None


def _declarations(root: Path, files: Iterable[str]) -> dict[str, tuple[str, ...]]:
    """Declared Python dependencies keyed by normalised name, each with the
    manifests that declare it (`dir/manifest`). Reuses the one manifest reader of
    core/components.py, so this module cannot disagree with Quick Context."""
    by_dir: dict[str, set[str]] = {}
    for rel in files:
        parent, _, name = rel.rpartition("/")
        by_dir.setdefault(parent, set()).add(name)
    found: dict[str, set[str]] = {}
    for directory in sorted(by_dir):
        names = by_dir[directory]
        if not names & _PYTHON_MANIFESTS:
            continue
        for dep in declared_dependencies(
            root / directory if directory else root, names
        ):
            if dep.manifest not in _PYTHON_MANIFESTS:
                continue
            label = f"{directory}/{dep.manifest}" if directory else dep.manifest
            found.setdefault(normalise_distribution(dep.name), set()).add(label)
    return {name: tuple(sorted(labels)) for name, labels in sorted(found.items())}


def build_structure(
    root: Path,
    included: Sequence[Path],
    skipped: Sequence[tuple[Path, int]] = (),
    *,
    stdlib: frozenset[str] | None = None,
    reader: Callable[[Path, str], bytes | None] = _read,
) -> StructureData:
    """Build the structure of the project under `root`.

    `included` is every file of the project the report may read (relative paths, any
    extension: manifests are needed too); `skipped` the files over the size limit as
    (path, size). `stdlib` and `reader` can be replaced in tests.
    """
    interpreter = platform.python_version()
    stdlib_names = stdlib if stdlib is not None else frozenset(sys.stdlib_module_names)
    included_posix = sorted({_posix(p) for p in included})
    skipped_map = {_posix(p): size for p, size in skipped}
    py_paths = sorted(
        {p for p in included_posix if p.endswith(".py")}
        | {p for p in skipped_map if p.endswith(".py")}
    )

    declared: list[str] = []
    for rel in included_posix:
        if rel.rsplit("/", 1)[-1] == manifest_name():
            text_bytes = reader(root, rel)
            if text_bytes is None:
                continue
            parent = rel.rpartition("/")[0]
            declared.extend(
                declared_roots(parent, text_bytes.decode("utf-8", errors="replace"))
            )
    declared_sorted = sorted(set(declared))
    package_dirs = frozenset(
        p.rpartition("/")[0] for p in py_paths if p.rsplit("/", 1)[-1] == "__init__.py"
    )

    by_path: dict[str, ModuleEntity] = {}
    entities: list[ModuleEntity] = []
    for rel in py_paths:
        source_root = file_root(rel, declared_sorted, package_dirs)
        name, is_package = module_name(rel, source_root)
        if not name:
            continue
        entity = ModuleEntity(
            name=name,
            path=rel,
            is_package=is_package,
            is_namespace=False,
            root=source_root,
        )
        entities.append(entity)
        by_path[rel] = entity
    by_name: dict[str, list[ModuleEntity]] = {}
    for entity in entities:
        by_name.setdefault(entity.name, []).append(entity)
    # Implicit namespace packages: a dotted prefix with no file of its own.
    # بسته‌ی namespace ضمنی: پیشوندی که فایل خودش را ندارد.
    prefix_roots: dict[str, str] = {}
    for entity in entities:
        parts = entity.name.split(".")
        for size in range(1, len(parts)):
            prefix_roots.setdefault(".".join(parts[:size]), entity.root)
    namespace_entities = [
        ModuleEntity(name=n, path="", is_package=True, is_namespace=True, root=r)
        for n, r in sorted(prefix_roots.items())
        if n not in by_name
    ]
    index = ModuleIndex(
        by_name=by_name,
        prefixes=frozenset(prefix_roots),
        stdlib=stdlib_names,
        declared=_declarations(root, included_posix),
    )

    files: list[FileEntity] = []
    edges: list[Edge] = []
    for rel in py_paths:
        importer = by_path.get(rel)
        label = importer.name if importer is not None else ""
        if rel in skipped_map and rel not in included_posix:
            files.append(
                FileEntity(
                    path=rel,
                    language=LANGUAGE_PYTHON,
                    size=skipped_map[rel],
                    sha256="",
                    module=label,
                    provenance=Provenance(
                        PARSER_PYTHON_AST,
                        interpreter,
                        "",
                        COMPLETENESS_SKIPPED_SIZE,
                        (LIM_TOO_LARGE,),
                    ),
                )
            )
            continue
        data = reader(root, rel)
        if data is None:
            files.append(
                FileEntity(
                    path=rel,
                    language=LANGUAGE_PYTHON,
                    size=0,
                    sha256="",
                    module=label,
                    provenance=Provenance(
                        PARSER_PYTHON_AST,
                        interpreter,
                        "",
                        COMPLETENESS_FAILED,
                        (LIM_UNREADABLE,),
                    ),
                )
            )
            continue
        result = extract_imports(rel, data, interpreter)
        files.append(
            FileEntity(
                path=rel,
                language=LANGUAGE_PYTHON,
                size=result.size,
                sha256=result.sha256,
                module=label,
                provenance=result.provenance,
                error=result.error,
                extensions=dict(result.extensions),
            )
        )
        source = label or rel
        for record in result.imports:
            edges.extend(resolve_record(record, importer, source, index))

    edges.sort(
        key=lambda e: (
            e.source,
            e.location.line,
            e.location.col,
            e.requested,
            e.target,
            e.original_type,
        )
    )
    externals = _externals(edges, index)
    cycles = find_cycles(edges)
    all_modules = sorted(
        [*entities, *namespace_entities], key=lambda m: (m.name, m.root, m.path)
    )
    meta: dict[str, str | int | bool | list[str]] = {
        "interpreter": interpreter,
        "stdlib_source": "sys.stdlib_module_names" if stdlib is None else "injected",
        "stdlib_count": len(stdlib_names),
        "source_roots": sorted({m.root for m in entities}),
        "declared_roots": declared_sorted,
        "parser": PARSER_PYTHON_AST,
    }
    return StructureData(
        schema_version=SCHEMA_VERSION,
        language=LANGUAGE_PYTHON,
        meta=meta,
        files=tuple(files),
        modules=tuple(all_modules),
        externals=externals,
        edges=tuple(edges),
        cycles=cycles,
    )


def _externals(edges: Sequence[Edge], index: ModuleIndex) -> tuple[ExternalRef, ...]:
    """The distinct external top-level names the edges point at."""
    seen: dict[str, ExternalRef] = {}
    for edge in edges:
        if edge.target_class not in (
            TARGET_STDLIB,
            TARGET_EXTERNAL_DECLARED,
            TARGET_EXTERNAL_UNMATCHED,
        ):
            continue
        if edge.target in seen:
            continue
        declared_in: tuple[str, ...] = ()
        if edge.target_class == TARGET_EXTERNAL_DECLARED:
            declared_in = index.declared.get(normalise_distribution(edge.target), ())
        seen[edge.target] = ExternalRef(
            edge.target, edge.target_class, tuple(declared_in)
        )
    return tuple(seen[name] for name in sorted(seen))
