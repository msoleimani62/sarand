"""The JSON form of the structural model (the `structure` key of the report).

Two schema versions are involved and are different things:

- the **outer report** schema (`schema_version`, `"1.10"` at the time of writing) is
  versioned in `renderers/json_renderer.py` and `docs/JSON_SCHEMA.md`;
- the **structure model** schema is `SCHEMA_VERSION` of `structure/model.py` (an
  integer, 4) and appears here as `structure.schema`.

Output is canonical: every collection is sorted here by an explicit key (so two equal
models serialize to the same bytes whatever order their producers used), mappings are
key-sorted recursively, and sequences in `meta` are sorted. Sequences inside
`extensions` keep the order they were given (their order is not defined by this
module). Serialization never changes the model.

شکل JSON مدل ساختاری؛ دو نسخه‌ی شمای جدا (گزارش بیرونی و مدل ساختار) و خروجی کانونی.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sarand.structure.model import (
    COMPLETENESS_VALUES,
    CONFIDENCE_LEVELS,
    ENTRY_POINT_TYPES,
    RELATION_KINDS,
    SYMBOL_KINDS,
    TARGET_CLASSES,
    Cycle,
    Edge,
    EntryPoint,
    FileEntity,
    Relation,
    SourceLocation,
    StructureData,
    Symbol,
    edge_sort_key,
    relation_sort_key,
)


def canonical(value: Any, *, sort_sequences: bool = False) -> Any:
    """A plain-JSON copy of `value`: mappings as key-sorted dicts (recursively),
    sequences as lists (sorted when `sort_sequences`), scalars unchanged."""
    if isinstance(value, Mapping):
        return {
            str(key): canonical(value[key], sort_sequences=sort_sequences)
            for key in sorted(value, key=str)
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [canonical(v, sort_sequences=sort_sequences) for v in value]
        if sort_sequences:
            items.sort(key=repr)
        return items
    return value


def _location(loc: SourceLocation | None) -> dict[str, Any] | None:
    if loc is None:
        return None
    return {
        "path": loc.path,
        "line": loc.line,
        "col": loc.col,
        "end_line": loc.end_line,
        "end_col": loc.end_col,
    }


def _edge(edge: Edge) -> dict[str, Any]:
    return {
        "kind": edge.kind,
        "source": edge.source,
        "requested": edge.requested,
        "target": edge.target,
        "target_class": edge.target_class,
        "confidence": edge.confidence,
        "resolution_method": edge.resolution_method,
        "original_type": edge.original_type,
        "flags": sorted(edge.flags),
        "evidence": edge.evidence,
        "note": edge.note,
        "location": _location(edge.location),
    }


def _file(entity: FileEntity) -> dict[str, Any]:
    out: dict[str, Any] = {
        "path": entity.path,
        "language": entity.language,
        "module": entity.module,
        "size": entity.size,
        "sha256": entity.sha256,
        "provenance": {
            "parser": entity.provenance.parser,
            "parser_version": entity.provenance.parser_version,
            "rules": entity.provenance.rules,
            "completeness": entity.provenance.completeness,
            "limitations": sorted(entity.provenance.limitations),
        },
    }
    if entity.error is not None:
        out["error"] = _location(entity.error)
    if entity.extensions:
        out["extensions"] = canonical(entity.extensions)
    return out


def _cycle(cycle: Cycle) -> dict[str, Any]:
    return {
        "modules": sorted(cycle.modules),
        "eager": cycle.eager,
        "edges": [_edge(e) for e in sorted(cycle.edges, key=edge_sort_key)],
    }


def _symbol(symbol: Symbol) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": symbol.id,
        "kind": symbol.kind,
        "name": symbol.name,
        "qualname": symbol.qualname,
        "module": symbol.module,
        "path": symbol.path,
        "parent": symbol.parent,
        "location": _location(symbol.location),
        "flags": sorted(symbol.flags),
        "fingerprint": symbol.fingerprint,
    }
    if symbol.decorators:
        out["decorators"] = list(symbol.decorators)
    if symbol.bases:
        out["bases"] = list(symbol.bases)
    if symbol.extensions:
        out["extensions"] = canonical(symbol.extensions)
    return out


def _relation(relation: Relation) -> dict[str, Any]:
    return {
        "kind": relation.kind,
        "source": relation.source,
        "source_kind": relation.source_kind,
        "target": relation.target,
        "target_kind": relation.target_kind,
        "target_name": relation.target_name,
        "confidence": relation.confidence,
        "resolution_method": relation.resolution_method,
        "original_type": relation.original_type,
        "count": relation.count,
        "flags": sorted(relation.flags),
        "evidence": relation.evidence,
        "note": relation.note,
        "location": _location(relation.location),
    }


def _entry_point(entry: EntryPoint) -> dict[str, Any]:
    return {
        "type": entry.type,
        "name": entry.name,
        "target": entry.target,
        "resolved": entry.resolved,
        "confidence": entry.confidence,
        "method": entry.method,
        "evidence": entry.evidence,
        "note": entry.note,
        "location": _location(entry.location),
    }


def summary(data: StructureData) -> dict[str, Any]:
    """Counts that every renderer shows: files by completeness, modules, imports by
    target class and by confidence, and cycles. The one place these are counted. The
    model validates its vocabularies on construction, so every key is known."""
    files = {value: 0 for value in COMPLETENESS_VALUES}
    for entity in data.files:
        files[entity.provenance.completeness] += 1
    classes = {value: 0 for value in TARGET_CLASSES}
    confidence = {value: 0 for value in CONFIDENCE_LEVELS}
    for edge in data.edges:
        classes[edge.target_class] += 1
        confidence[edge.confidence] += 1
    symbols = {value: 0 for value in SYMBOL_KINDS}
    for symbol in data.symbols:
        symbols[symbol.kind] += 1
    relations = {value: 0 for value in RELATION_KINDS}
    relation_confidence = {value: 0 for value in CONFIDENCE_LEVELS}
    for relation in data.relations:
        relations[relation.kind] += 1
        relation_confidence[relation.confidence] += 1
    entries = {value: 0 for value in ENTRY_POINT_TYPES}
    for entry in data.entry_points:
        entries[entry.type] += 1
    packages = sum(1 for m in data.modules if m.is_package and not m.is_namespace)
    namespace_names = {m.name for m in data.modules if m.is_namespace}
    modules = len({m.name for m in data.modules if not m.is_namespace})
    return {
        "files": len(data.files),
        "files_by_completeness": files,
        "modules": modules,
        "packages": packages,
        "namespace_packages": len(namespace_names),
        "imports": len(data.edges),
        "imports_by_class": classes,
        "imports_by_confidence": confidence,
        "externals": len(data.externals),
        "cycles": len(data.cycles),
        "eager_cycles": sum(1 for c in data.cycles if c.eager),
        "symbols": len(data.symbols),
        "symbols_by_kind": symbols,
        "relations": len(data.relations),
        "relations_by_kind": relations,
        "relations_by_confidence": relation_confidence,
        "entry_points": len(data.entry_points),
        "entry_points_by_type": entries,
    }


def structure_payload(data: StructureData) -> dict[str, Any]:
    """The `structure` object of the JSON report (canonical, see the module docstring)."""
    return {
        "schema": data.schema_version,
        "language": data.language,
        "meta": canonical(data.meta, sort_sequences=True),
        "summary": summary(data),
        "files": [_file(f) for f in sorted(data.files, key=lambda f: f.path)],
        "modules": [
            {
                "name": m.name,
                "path": m.path,
                "is_package": m.is_package,
                "is_namespace": m.is_namespace,
                "root": m.root,
            }
            for m in sorted(data.modules, key=lambda m: (m.name, m.root, m.path))
        ],
        "externals": [
            {
                "name": x.name,
                "target_class": x.target_class,
                "declared_in": sorted(x.declared_in),
            }
            for x in sorted(data.externals, key=lambda x: (x.name, x.target_class))
        ],
        "edges": [_edge(e) for e in sorted(data.edges, key=edge_sort_key)],
        "cycles": [_cycle(c) for c in sorted(data.cycles, key=lambda c: c.modules)],
        "symbols": [
            _symbol(x)
            for x in sorted(
                data.symbols,
                key=lambda x: (
                    x.path,
                    x.location.line,
                    x.location.col,
                    x.qualname,
                    x.id,
                ),
            )
        ],
        "relations": [
            _relation(r) for r in sorted(data.relations, key=relation_sort_key)
        ],
        "entry_points": [
            _entry_point(e)
            for e in sorted(
                data.entry_points,
                key=lambda e: (
                    e.type,
                    e.name,
                    e.target,
                    e.location.path,
                    e.location.line,
                    e.location.col,
                    e.method,
                ),
            )
        ],
        "external_use": [
            {
                "name": u.name,
                "target_class": u.target_class,
                "calls": u.calls,
                "inherits": u.inherits,
                "references": u.references,
            }
            for u in sorted(data.external_use, key=lambda u: u.name)
        ],
        "sites": canonical(data.sites),
    }
