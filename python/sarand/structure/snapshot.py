"""Structure snapshots: the reference a structural comparison reads (R14-D1, slice S1).

A snapshot is the `structure` object of a report in a small envelope that records
what is needed to interpret it later: the snapshot format, the structure schema, the
fingerprint basis, the settings that change what a snapshot contains (the paths
excluded as secrets, the file size limit) and a SHA-256 digest of all of that. It has
no time and no machine name, so the same project and the same code always give the
same bytes.

This module only builds and reads the envelope in memory. Writing a file, replacing a
reference and the command line belong to slice S2; nothing here touches the disk.

A comparison may also use a JSON report that has a `structure` key as its reference
(`source` is then `report`). `read_reference` never raises on bad input: it returns a
`Reference` whose `problem_kind` says `invalid` (the data is not a usable snapshot) or
`incompatible` (it is well formed but written by a version this code does not know),
so that a comparison can say so instead of comparing nothing and calling it unchanged.

عکس لحظه‌ای ساختار: پوشه‌ی کوچک دور خروجی `structure` با نسخه، بصمت، تنظیمات و digest؛
بدون زمان و بدون نوشتن روی دیسک.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

SNAPSHOT_KIND = "sarand-structure-snapshot"
SNAPSHOT_FORMAT = 1
# The structure schemas the comparison knows how to read. A new schema is
# `incompatible` until this tuple and the comparison are updated together (a test ties
# it to the schema that the builder writes today).
# نسخه‌های schema که مقایسه می‌شناسد؛ نسخه‌ی تازه تا به‌روزرسانی هر دو ناسازگار است.
SUPPORTED_SCHEMAS: tuple[int, ...] = (4,)
SUPPORTED_LANGUAGES: tuple[str, ...] = ("python",)

PROBLEM_INVALID = "invalid"
PROBLEM_INCOMPATIBLE = "incompatible"

SOURCE_SNAPSHOT = "snapshot"
SOURCE_REPORT = "report"

_LISTS = (
    "files",
    "modules",
    "externals",
    "edges",
    "cycles",
    "symbols",
    "relations",
    "entry_points",
)
# The keys of every item that the comparison reads.
# کلیدهایی از هر عنصر که مقایسه می‌خواند.
_ITEM_KEYS: dict[str, tuple[str, ...]] = {
    "files": ("path", "sha256", "provenance"),
    "modules": ("name", "path", "root"),
    "externals": ("name", "target_class"),
    "edges": (
        "kind",
        "source",
        "requested",
        "target",
        "target_class",
        "confidence",
        "resolution_method",
    ),
    "cycles": ("modules", "eager"),
    "symbols": ("id", "kind", "path", "qualname"),
    "relations": (
        "kind",
        "source",
        "source_kind",
        "target",
        "target_kind",
        "confidence",
        "resolution_method",
        "count",
    ),
    "entry_points": ("type", "name", "target"),
}


class _Problem(ValueError):
    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class Reference:
    """One side of a comparison: a usable structure, or the reason it is not."""

    structure: Mapping[str, Any] = field(default_factory=dict)
    source: str = ""
    excluded_secret_files: tuple[str, ...] = ()
    max_file_size: int | None = None
    problem_kind: str = ""
    problem: str = ""

    @property
    def usable(self) -> bool:
        return not self.problem_kind


def canonical_json(value: Any) -> str:
    """The one JSON form used for digests: sorted keys, no spaces, ASCII only."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest_of(body: Mapping[str, Any]) -> str:
    """`sha256:<hex>` of the envelope without its `digest` key."""
    plain = {k: v for k, v in body.items() if k != "digest"}
    return "sha256:" + hashlib.sha256(canonical_json(plain).encode("ascii")).hexdigest()


def make_snapshot(
    structure: Mapping[str, Any],
    *,
    excluded_secret_files: Iterable[str] = (),
    max_file_size: int | None = None,
) -> dict[str, Any]:
    """The envelope of a `structure` payload. Raises `ValueError` when the payload is
    not a usable structure (the same checks as reading one)."""
    plain: dict[str, Any] = json.loads(canonical_json(structure))
    _check_structure(plain)
    basis = _basis(plain)
    body: dict[str, Any] = {
        "kind": SNAPSHOT_KIND,
        "snapshot_format": SNAPSHOT_FORMAT,
        "structure_schema": plain["schema"],
        "language": plain["language"],
        "fingerprint_basis": basis,
        "settings": {
            "excluded_secret_files": sorted({str(p) for p in excluded_secret_files}),
            "max_file_size": max_file_size,
        },
        "structure": plain,
    }
    body["digest"] = digest_of(body)
    return body


def snapshot_text(snapshot: Mapping[str, Any]) -> str:
    """The text a snapshot file holds: stable, readable, ends with a newline."""
    return json.dumps(snapshot, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def read_reference(data: Any) -> Reference:
    """A `Reference` from parsed JSON: a snapshot, or a report with a `structure` key."""
    try:
        return _read(data)
    except _Problem as problem:
        return Reference(problem_kind=problem.kind, problem=str(problem))


def _read(data: Any) -> Reference:
    if not isinstance(data, Mapping):
        raise _Problem(PROBLEM_INVALID, "the reference is not a JSON object")
    if data.get("kind") == SNAPSHOT_KIND:
        return _read_snapshot(data)
    if "structure" in data:
        excluded = data.get("excluded_secret_files", [])
        if not isinstance(excluded, list) or not all(
            isinstance(p, str) for p in excluded
        ):
            raise _Problem(
                PROBLEM_INVALID, "excluded_secret_files is not a list of paths"
            )
        structure = _check_structure(data["structure"])
        return Reference(
            structure=structure,
            source=SOURCE_REPORT,
            excluded_secret_files=tuple(sorted(set(excluded))),
            max_file_size=None,
        )
    if "schema_version" in data:
        raise _Problem(
            PROBLEM_INVALID,
            "the report has no `structure` key: it was made without --structure",
        )
    raise _Problem(PROBLEM_INVALID, "the reference is neither a snapshot nor a report")


def _read_snapshot(data: Mapping[str, Any]) -> Reference:
    version = data.get("snapshot_format")
    if isinstance(version, bool) or not isinstance(version, int):
        raise _Problem(PROBLEM_INVALID, "snapshot_format is missing or not an integer")
    if version != SNAPSHOT_FORMAT:
        raise _Problem(
            PROBLEM_INCOMPATIBLE,
            f"snapshot format {version} is not the format {SNAPSHOT_FORMAT} that this "
            "version reads",
        )
    if data.get("digest") != digest_of(data):
        raise _Problem(
            PROBLEM_INVALID, "the integrity digest does not match the content"
        )
    settings = data.get("settings")
    if not isinstance(settings, Mapping):
        raise _Problem(PROBLEM_INVALID, "settings is missing")
    excluded = settings.get("excluded_secret_files")
    if not isinstance(excluded, list) or not all(isinstance(p, str) for p in excluded):
        raise _Problem(PROBLEM_INVALID, "settings.excluded_secret_files is not a list")
    limit = settings.get("max_file_size")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int)):
        raise _Problem(PROBLEM_INVALID, "settings.max_file_size is not an integer")
    structure = _check_structure(data.get("structure"))
    if data.get("structure_schema") != structure["schema"]:
        raise _Problem(PROBLEM_INVALID, "structure_schema differs from the structure")
    if data.get("language") != structure["language"]:
        raise _Problem(PROBLEM_INVALID, "language differs from the structure")
    if data.get("fingerprint_basis") != _basis(structure):
        raise _Problem(PROBLEM_INVALID, "fingerprint_basis differs from the structure")
    return Reference(
        structure=structure,
        source=SOURCE_SNAPSHOT,
        excluded_secret_files=tuple(sorted(set(excluded))),
        max_file_size=limit,
    )


def _basis(structure: Mapping[str, Any]) -> str:
    meta = structure.get("meta")
    return str(meta.get("fingerprint_basis", "")) if isinstance(meta, Mapping) else ""


def _check_structure(structure: Any) -> Mapping[str, Any]:
    """The `structure` payload itself; raise `_Problem` unless this code can read it."""
    if not isinstance(structure, Mapping):
        raise _Problem(PROBLEM_INVALID, "structure is not an object")
    schema = structure.get("schema")
    if isinstance(schema, bool) or not isinstance(schema, int):
        raise _Problem(PROBLEM_INVALID, "structure.schema is missing or not an integer")
    language = structure.get("language")
    if not isinstance(language, str):
        raise _Problem(PROBLEM_INVALID, "structure.language is missing")
    if schema not in SUPPORTED_SCHEMAS:
        raise _Problem(
            PROBLEM_INCOMPATIBLE,
            f"structure schema {schema} is not one this version compares "
            f"(it compares {', '.join(str(s) for s in SUPPORTED_SCHEMAS)})",
        )
    if language not in SUPPORTED_LANGUAGES:
        raise _Problem(PROBLEM_INCOMPATIBLE, f"language {language!r} is not compared")
    if not isinstance(structure.get("meta"), Mapping):
        raise _Problem(PROBLEM_INVALID, "structure.meta is missing")
    for name in _LISTS:
        items = structure.get(name)
        if not isinstance(items, list):
            raise _Problem(
                PROBLEM_INVALID, f"structure.{name} is missing or not a list"
            )
        for index, item in enumerate(items):
            if not isinstance(item, Mapping):
                raise _Problem(
                    PROBLEM_INVALID, f"structure.{name}[{index}] is not an object"
                )
            for key in _ITEM_KEYS[name]:
                if key not in item:
                    raise _Problem(
                        PROBLEM_INVALID, f"structure.{name}[{index}] has no `{key}`"
                    )
    for index, item in enumerate(structure["files"]):
        provenance = item["provenance"]
        if not isinstance(provenance, Mapping) or "completeness" not in provenance:
            raise _Problem(
                PROBLEM_INVALID,
                f"structure.files[{index}].provenance has no completeness",
            )
    for index, item in enumerate(structure["cycles"]):
        if not isinstance(item["modules"], list):
            raise _Problem(
                PROBLEM_INVALID, f"structure.cycles[{index}].modules is not a list"
            )
    return structure
