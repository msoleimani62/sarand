"""The JSON form of the structural model (schema 1.7, key `structure`).

Plain dicts and lists in a fixed order, so two runs on the same repository state
give byte-identical JSON (R14-A, determinism requirement). The text of the model is
not changed here; this only chooses names and order.

شکل JSON مدل ساختاری؛ ترتیب ثابت تا دو اجرا بایت‌به‌بایت یکسان باشند.
"""

from __future__ import annotations

from typing import Any

from sarand.structure.model import (
    COMPLETENESS_VALUES,
    CONFIDENCE_LEVELS,
    TARGET_CLASSES,
    Cycle,
    Edge,
    FileEntity,
    SourceLocation,
    StructureData,
)


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
        "flags": list(edge.flags),
        "evidence": edge.evidence,
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
            "limitations": list(entity.provenance.limitations),
        },
    }
    if entity.error is not None:
        out["error"] = _location(entity.error)
    if entity.extensions:
        out["extensions"] = dict(sorted(entity.extensions.items()))
    return out


def _cycle(cycle: Cycle) -> dict[str, Any]:
    return {
        "modules": list(cycle.modules),
        "eager": cycle.eager,
        "edges": [_edge(e) for e in cycle.edges],
    }


def summary(data: StructureData) -> dict[str, Any]:
    """Counts that every renderer shows: files by completeness, modules, imports by
    target class and by confidence, and cycles. The one place these are counted."""
    files = {value: 0 for value in COMPLETENESS_VALUES}
    for entity in data.files:
        files[entity.provenance.completeness] += 1
    classes = {value: 0 for value in TARGET_CLASSES}
    confidence = {value: 0 for value in CONFIDENCE_LEVELS}
    for edge in data.edges:
        classes[edge.target_class] += 1
        confidence[edge.confidence] += 1
    packages = sum(1 for m in data.modules if m.is_package and not m.is_namespace)
    namespaces = sum(1 for m in data.modules if m.is_namespace)
    return {
        "files": len(data.files),
        "files_by_completeness": files,
        "modules": len(data.modules) - namespaces,
        "packages": packages,
        "namespace_packages": namespaces,
        "imports": len(data.edges),
        "imports_by_class": classes,
        "imports_by_confidence": confidence,
        "externals": len(data.externals),
        "cycles": len(data.cycles),
        "eager_cycles": sum(1 for c in data.cycles if c.eager),
    }


def structure_payload(data: StructureData) -> dict[str, Any]:
    """The `structure` object of the JSON report."""
    return {
        "schema": data.schema_version,
        "language": data.language,
        "meta": {key: data.meta[key] for key in sorted(data.meta)},
        "summary": summary(data),
        "files": [_file(f) for f in data.files],
        "modules": [
            {
                "name": m.name,
                "path": m.path,
                "is_package": m.is_package,
                "is_namespace": m.is_namespace,
                "root": m.root,
            }
            for m in data.modules
        ],
        "externals": [
            {
                "name": x.name,
                "target_class": x.target_class,
                "declared_in": list(x.declared_in),
            }
            for x in data.externals
        ],
        "edges": [_edge(e) for e in data.edges],
        "cycles": [_cycle(c) for c in data.cycles],
    }
