"""Build the structural model of a project (R14-A, docs/R14A_PLAN.md).

`build_structure` takes the files the report is allowed to read, finds the source
roots, names the modules, reads every Python file with `ast` (never executing it),
resolves the imports and finds the cycles. It is deterministic: files are processed
in sorted path order and every collection is sorted before it is returned.

Two environment inputs are named and recorded in `meta`, never hidden: the
interpreter version (the `ast` grammar and the standard-library name list depend on
it) and the standard-library names themselves.

Path contract: `included` and `skipped` hold **relative** paths, inside the project,
without `..`; an absolute path or a parent traversal raises `ValueError` (the CLI
never produces one). Unknown data stays unknown: a file that cannot be read has
`size=None`, an empty hash and the limitation `unreadable`, never a made-up size.

ساخت مدل ساختاری پروژه؛ قطعی، بدون اجرای کد، و ورودی‌های محیطی در meta ثبت می‌شوند.
"""

from __future__ import annotations

import platform
import sys
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path, PurePosixPath

from sarand.core.components import declared_dependencies
from sarand.structure.cycles import find_cycles
from sarand.structure.entry_points import find_entry_points
from sarand.structure.facts import FileFacts, extract_facts
from sarand.structure.fingerprint import fingerprint_basis
from sarand.structure.imports import ModuleIndex, normalise_distribution, resolve_record
from sarand.structure.model import (
    COMPLETENESS_FAILED,
    COMPLETENESS_PARTIAL,
    COMPLETENESS_SKIPPED_SIZE,
    LANGUAGE_PYTHON,
    LIM_NODE_CAP,
    LIM_RECURSION,
    LIM_RESOURCE,
    LIM_TOO_LARGE,
    LIM_UNREADABLE,
    PARSER_PYTHON_AST,
    SCHEMA_VERSION,
    TARGET_EXTERNAL_DECLARED,
    TARGET_EXTERNAL_UNMATCHED,
    TARGET_STDLIB,
    Edge,
    ExternalRef,
    ExternalUsage,
    FileEntity,
    ModuleEntity,
    Provenance,
    StructureData,
    edge_sort_key,
)
from sarand.structure.python_extract import extract_imports
from sarand.structure.resolve import Resolver
from sarand.structure.roots import (
    DeclaredRoot,
    declared_roots,
    file_root,
    manifest_name,
    module_name,
)

_PYTHON_MANIFESTS = frozenset({"pyproject.toml", "requirements.txt"})


def _posix(path: Path) -> str:
    """A project-relative path as POSIX text; anything else is a caller bug."""
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(
            f"structure paths must be relative and inside the project, got {path}"
        )
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
    untracked: list[tuple[str, str, str]] | None = None,
) -> StructureData:
    """Build the structure of the project under `root`.

    `included` is every file of the project the report may read (relative paths, any
    extension: manifests are needed too); `skipped` the files over the size limit as
    (path, size). `stdlib` and `reader` can be replaced in tests. `untracked`, when a
    list is given, receives one `(reason, location, evidence)` for every usage site that
    was counted and not stored (used by the evaluation; not part of the output).
    """
    interpreter = platform.python_version()
    stdlib_names = stdlib if stdlib is not None else frozenset(sys.stdlib_module_names)
    included_posix = sorted({_posix(p) for p in included})
    skipped_map = {_posix(p): size for p, size in skipped}
    py_paths = sorted(
        {p for p in included_posix if p.endswith(".py")}
        | {p for p in skipped_map if p.endswith(".py")}
    )

    declared: set[DeclaredRoot] = set()
    rejected: set[str] = set()
    for rel in included_posix:
        if rel.rsplit("/", 1)[-1] == manifest_name():
            text_bytes = reader(root, rel)
            if text_bytes is None:
                continue
            parent = rel.rpartition("/")[0]
            found, refused = declared_roots(
                parent, text_bytes.decode("utf-8", errors="replace")
            )
            declared.update(found)
            rejected.update(refused)
    declared_sorted = sorted(declared, key=lambda r: (r.path, r.prefix))
    package_dirs = frozenset(
        p.rpartition("/")[0] for p in py_paths if p.rsplit("/", 1)[-1] == "__init__.py"
    )

    by_path: dict[str, ModuleEntity] = {}
    entities: list[ModuleEntity] = []
    for rel in py_paths:
        source_root, package_prefix = file_root(rel, declared_sorted, package_dirs)
        name, is_package = module_name(rel, source_root, package_prefix)
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
    # A namespace package can have a portion in several roots (PEP 420): keep every
    # root, one entity per (name, root).
    # بسته‌ی namespace می‌تواند در چند ریشه سهم داشته باشد؛ همه‌ی ریشه‌ها نگه داشته می‌شوند.
    prefix_roots: dict[str, set[str]] = {}
    for entity in entities:
        parts = entity.name.split(".")
        for size in range(1, len(parts)):
            prefix_roots.setdefault(".".join(parts[:size]), set()).add(entity.root)
    namespace_entities = [
        ModuleEntity(name=n, path="", is_package=True, is_namespace=True, root=r)
        for n, roots_of in sorted(prefix_roots.items())
        for r in sorted(roots_of)
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
    all_facts: list[FileFacts] = []
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
                    size=None,
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
        provenance = result.provenance
        extensions = dict(result.extensions)
        if result.tree is not None:
            facts = extract_facts(rel, data, result.tree, label, importer)
            all_facts.append(facts)
            provenance = _merge_provenance(provenance, facts.limits)
            if facts.dunder_all is not None:
                extensions["dunder_all"] = ",".join(facts.dunder_all)
            if facts.has_module_getattr:
                extensions["has_module_getattr"] = True
        files.append(
            FileEntity(
                path=rel,
                language=LANGUAGE_PYTHON,
                size=result.size,
                sha256=result.sha256,
                module=label,
                provenance=provenance,
                error=result.error,
                extensions=extensions,
            )
        )
        source = label or rel
        for record in result.imports:
            edges.extend(resolve_record(record, importer, source, index))

    edges.sort(key=edge_sort_key)
    externals = _externals(edges, index)
    cycles = find_cycles(edges)
    resolver = Resolver(all_facts, index)
    resolved = resolver.resolve_all(all_facts, untracked)
    manifests = [
        (rel, text.decode("utf-8", errors="replace"))
        for rel in included_posix
        if rel.rsplit("/", 1)[-1] == manifest_name()
        and (text := reader(root, rel)) is not None
    ]
    entry_points = find_entry_points(manifests, included_posix, all_facts, resolver)
    symbols = sorted(
        (info.symbol for facts in all_facts for info in facts.symbols),
        key=lambda s: (s.path, s.location.line, s.location.col, s.qualname, s.id),
    )
    external_use = tuple(
        ExternalUsage(
            name=name,
            target_class=use.target_class,
            calls=use.calls,
            inherits=use.inherits,
            references=use.references,
        )
        for name, use in sorted(resolved.external_use.items())
    )
    all_modules = sorted(
        [*entities, *namespace_entities], key=lambda m: (m.name, m.root, m.path)
    )
    meta: dict[str, str | int | bool | tuple[str, ...]] = {
        "interpreter": interpreter,
        "stdlib_source": "sys.stdlib_module_names" if stdlib is None else "injected",
        "stdlib_count": len(stdlib_names),
        "source_roots": tuple(sorted({m.root for m in entities})),
        "declared_roots": tuple(
            f"{r.prefix}={r.path}" if r.prefix else r.path for r in declared_sorted
        ),
        "rejected_roots": tuple(sorted(rejected)),
        "parser": PARSER_PYTHON_AST,
        "fingerprint_basis": fingerprint_basis(interpreter),
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
        symbols=tuple(symbols),
        relations=tuple(resolved.relations),
        entry_points=entry_points,
        external_use=external_use,
        sites=resolved.sites,
    )


def _merge_provenance(base: Provenance, extra: set[str]) -> Provenance:
    """The file's provenance after the symbol pass: the limits it hit are added, and a
    guard that cut the walk short (recursion, node cap, memory) makes it `partial`."""
    if not extra:
        return base
    completeness = base.completeness
    if extra & {LIM_RECURSION, LIM_NODE_CAP, LIM_RESOURCE} and completeness == "full":
        completeness = COMPLETENESS_PARTIAL
    return Provenance(
        base.parser,
        base.parser_version,
        base.rules,
        completeness,
        tuple(sorted({*base.limitations, *extra})),
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
