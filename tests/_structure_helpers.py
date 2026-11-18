"""Shared helpers of the structure tests (R14-A1): build a tree, build a structure.

The standard-library name list is injected so no result depends on the interpreter
that runs the tests.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from sarand.structure import build_structure
from sarand.structure.model import Edge, StructureData

STDLIB = frozenset(
    {
        "os",
        "sys",
        "json",
        "re",
        "typing",
        "importlib",
        "collections",
        "types",
        "builtins",
    }
)


def write_tree(root: Path, files: Mapping[str, str | bytes]) -> list[Path]:
    paths: list[Path] = []
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
        paths.append(Path(rel))
    return paths


def build(tmp_path: Path, files: Mapping[str, str | bytes]) -> StructureData:
    return build_structure(tmp_path, write_tree(tmp_path, files), stdlib=STDLIB)


def edges_of(data: StructureData, source: str) -> list[Edge]:
    return [e for e in data.edges if e.source == source]


def edge_to(data: StructureData, source: str, requested: str) -> Edge:
    found = [e for e in data.edges if e.source == source and e.requested == requested]
    assert len(found) == 1, (
        source,
        requested,
        [(e.source, e.requested) for e in data.edges],
    )
    return found[0]
