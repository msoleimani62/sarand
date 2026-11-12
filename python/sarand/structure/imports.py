"""Import resolution (R14-A, docs/R14A_PLAN.md section 2).

Turns the import records of one file into `Edge`s with a target class, a confidence
and the rule that produced the target. It reads only repository file names and the
manifests' declarations: nothing installed, nothing executed.

Confidence (docs/STRUCTURE.md): **definite** when the name binds to exactly one
repository module by Python's own rules; **probable** when one candidate exists but
an assumption was needed (own root preferred over another root, a repository module
shadowing a standard-library name, a literal `importlib` argument, a package matched
only by elimination); **unknown** when the evidence cannot name a target (a dynamic
argument, an ambiguous name, a missing submodule).

Parent-package initialisation (`import a.b.c` runs `a/__init__.py` first) is not
modelled as an edge: it would make every package and its submodules a cycle.

حل‌کردن importها؛ اعتماد فقط از قواعد مستند می‌آید و init والد یال ساخته نمی‌شود.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sarand.structure.model import (
    CONF_DEFINITE,
    CONF_PROBABLE,
    CONF_UNKNOWN,
    EDGE_IMPORTS,
    FLAG_STAR,
    ORIGINAL_DYNAMIC_CALL,
    ORIGINAL_FROM_IMPORT,
    TARGET_DYNAMIC,
    TARGET_EXTERNAL_DECLARED,
    TARGET_EXTERNAL_UNMATCHED,
    TARGET_INTERNAL,
    TARGET_INTERNAL_UNRESOLVED,
    TARGET_STDLIB,
    Edge,
    ModuleEntity,
)
from sarand.structure.python_extract import ImportRecord


@dataclass
class ModuleIndex:
    """What the resolver may consult: the repository's modules (a name can exist in
    several roots), the standard-library names, and the declared dependencies keyed
    by their normalised name."""

    by_name: dict[str, list[ModuleEntity]] = field(default_factory=dict)
    prefixes: frozenset[str] = frozenset()
    stdlib: frozenset[str] = frozenset()
    declared: dict[str, tuple[str, ...]] = field(default_factory=dict)


def normalise_distribution(name: str) -> str:
    """The PEP 503 style name used to compare an import name with a declaration."""
    out: list[str] = []
    previous_dash = False
    for char in name.lower():
        if char in "-_.":
            if not previous_dash:
                out.append("-")
            previous_dash = True
        else:
            out.append(char)
            previous_dash = False
    return "".join(out)


def _pick(
    candidates: list[ModuleEntity], root: str, *, only_root: bool
) -> tuple[ModuleEntity | None, str]:
    """Choose one candidate. Returns (entity, how); how is `unique`, `own_root`,
    `ambiguous` or `none`."""
    if only_root:
        candidates = [c for c in candidates if c.root == root]
    if not candidates:
        return None, "none"
    if len(candidates) == 1:
        return candidates[0], "unique"
    own = [c for c in candidates if c.root == root]
    if len(own) == 1:
        return own[0], "own_root"
    return None, "ambiguous"


def _edge(
    source: str,
    record: ImportRecord,
    requested: str,
    target: str,
    target_class: str,
    confidence: str,
    method: str,
    original_type: str | None = None,
    note: str = "",
) -> Edge:
    evidence = record.evidence if not note else f"{record.evidence}  # {note}"
    return Edge(
        kind=EDGE_IMPORTS,
        source=source,
        requested=requested,
        target=target,
        target_class=target_class,
        confidence=confidence,
        resolution_method=method,
        evidence=evidence,
        location=record.location,
        original_type=original_type or record.original_type,
        flags=record.flags,
    )


def _resolve_absolute(
    name: str,
    importer_root: str,
    index: ModuleIndex,
    source: str,
    record: ImportRecord,
    original_type: str | None = None,
    *,
    literal_dynamic: bool = False,
) -> Edge:
    top = name.split(".", 1)[0]
    internal_top = top in index.by_name or top in index.prefixes
    shadows = internal_top and top in index.stdlib
    softer = CONF_PROBABLE if (literal_dynamic or shadows) else CONF_DEFINITE
    if internal_top:
        found, how = _pick(index.by_name.get(name, []), importer_root, only_root=False)
        if found is not None:
            method = "absolute-module"
            confidence = softer
            if how == "own_root":
                method, confidence = "own-root-preferred", CONF_PROBABLE
            if shadows:
                method = "internal-shadows-stdlib"
            if literal_dynamic:
                method = "importlib-literal"
            return _edge(
                source,
                record,
                name,
                found.name,
                TARGET_INTERNAL,
                confidence,
                method,
                original_type,
            )
        if how == "ambiguous":
            return _edge(
                source,
                record,
                name,
                "",
                TARGET_INTERNAL_UNRESOLVED,
                CONF_UNKNOWN,
                "ambiguous-module",
                original_type,
                "several repository modules match",
            )
        if name in index.prefixes:
            return _edge(
                source,
                record,
                name,
                name,
                TARGET_INTERNAL,
                softer,
                "namespace-package",
                original_type,
            )
        return _edge(
            source,
            record,
            name,
            "",
            TARGET_INTERNAL_UNRESOLVED,
            CONF_UNKNOWN,
            "missing-submodule",
            original_type,
            f"{top} is a repository package but {name} was not found",
        )
    if top in index.stdlib:
        return _edge(
            source,
            record,
            name,
            top,
            TARGET_STDLIB,
            CONF_PROBABLE if literal_dynamic else CONF_DEFINITE,
            "importlib-literal" if literal_dynamic else "stdlib-name",
            original_type,
        )
    declared = index.declared.get(normalise_distribution(top))
    if declared is not None:
        return _edge(
            source,
            record,
            name,
            top,
            TARGET_EXTERNAL_DECLARED,
            CONF_PROBABLE if literal_dynamic else CONF_DEFINITE,
            "importlib-literal" if literal_dynamic else "declared-dependency",
            original_type,
        )
    return _edge(
        source,
        record,
        name,
        top,
        TARGET_EXTERNAL_UNMATCHED,
        CONF_PROBABLE,
        "external-by-elimination",
        original_type,
        "not a repository module, not standard library, no matching declaration",
    )


def _relative_base(importer: ModuleEntity | None, level: int) -> str | None:
    """The package a relative import starts from, or None when it cannot exist
    (no known parent package, or more dots than packages)."""
    if importer is None or not importer.name:
        return None
    parts = importer.name.split(".")
    if not importer.is_package:
        parts = parts[:-1]
    drop = level - 1
    if drop > len(parts) or not parts:
        return None
    return ".".join(parts[: len(parts) - drop])


def resolve_record(
    record: ImportRecord,
    importer: ModuleEntity | None,
    source: str,
    index: ModuleIndex,
) -> list[Edge]:
    """All edges produced by one import record (a `from` import may produce several)."""
    importer_root = importer.root if importer is not None else ""
    if record.original_type == ORIGINAL_DYNAMIC_CALL:
        if not record.literal or not record.module:
            return [
                _edge(
                    source,
                    record,
                    "",
                    "",
                    TARGET_DYNAMIC,
                    CONF_UNKNOWN,
                    "non-literal-argument",
                    None,
                    "the module name is computed at run time",
                )
            ]
        if record.level:
            return [
                _edge(
                    source,
                    record,
                    record.module,
                    "",
                    TARGET_INTERNAL_UNRESOLVED,
                    CONF_UNKNOWN,
                    "dynamic-relative-import",
                    None,
                    "relative dynamic import is not resolved",
                )
            ]
        return [
            _resolve_absolute(
                record.module,
                importer_root,
                index,
                source,
                record,
                literal_dynamic=True,
            )
        ]
    if record.level == 0:
        edges = [_resolve_absolute(record.module, importer_root, index, source, record)]
        if record.original_type == ORIGINAL_FROM_IMPORT:
            extra = _submodule_edges(
                record.module, record, importer_root, index, source
            )
            if extra and _only_submodules(record, extra):
                edges = []
            edges.extend(extra)
        return edges
    base = _relative_base(importer, record.level)
    if base is None:
        return [
            _edge(
                source,
                record,
                "." * record.level + record.module,
                "",
                TARGET_INTERNAL_UNRESOLVED,
                CONF_UNKNOWN,
                "relative-no-parent-package",
                None,
                "no parent package at this level",
            )
        ]
    full = f"{base}.{record.module}" if record.module else base
    found, _how = _pick(index.by_name.get(full, []), importer_root, only_root=True)
    if found is not None:
        edges = [
            _edge(
                source,
                record,
                full,
                found.name,
                TARGET_INTERNAL,
                CONF_DEFINITE,
                "relative-module",
                None,
            )
        ]
    elif full in index.prefixes:
        edges = [
            _edge(
                source,
                record,
                full,
                full,
                TARGET_INTERNAL,
                CONF_DEFINITE,
                "namespace-package",
                None,
            )
        ]
    else:
        edges = [
            _edge(
                source,
                record,
                full,
                "",
                TARGET_INTERNAL_UNRESOLVED,
                CONF_UNKNOWN,
                "relative-target-missing",
                None,
                f"{full} not found in this source root",
            )
        ]
    if record.original_type == ORIGINAL_FROM_IMPORT:
        extra = _submodule_edges(
            full, record, importer_root, index, source, relative=True
        )
        if extra and _only_submodules(record, extra):
            edges = []
        edges.extend(extra)
    return edges


def _only_submodules(record: ImportRecord, extra: list[Edge]) -> bool:
    """True when every imported name of a `from` import is a repository submodule.

    Then the statement depends on those submodules, not on the package's own
    `__init__` content, so no edge to the package is made (the package is only
    initialised as a side effect, which is not modelled).
    فقط وقتی همه‌ی نام‌ها زیرماژول‌اند؛ آنگاه به محتوای __init__ وابسته نیست.
    """
    if FLAG_STAR in record.flags:
        return False
    return len(extra) == len([n for n in record.names if n != "*"])


def _submodule_edges(
    package: str,
    record: ImportRecord,
    importer_root: str,
    index: ModuleIndex,
    source: str,
    *,
    relative: bool = False,
) -> list[Edge]:
    """`from pkg import name` also imports `pkg.name` when that is a repository
    module. Only names that are submodules produce an extra edge; a name that is a
    symbol is the symbol graph's concern (R14-A2)."""
    edges: list[Edge] = []
    for name in record.names:
        if name == "*" or not package:
            continue
        dotted = f"{package}.{name}"
        found, how = _pick(
            index.by_name.get(dotted, []), importer_root, only_root=relative
        )
        if found is None:
            continue
        confidence = CONF_DEFINITE if how == "unique" else CONF_PROBABLE
        method = "from-import-submodule" if how == "unique" else "own-root-preferred"
        edges.append(
            _edge(
                source,
                record,
                dotted,
                found.name,
                TARGET_INTERNAL,
                confidence,
                method,
                None,
            )
        )
    return edges
