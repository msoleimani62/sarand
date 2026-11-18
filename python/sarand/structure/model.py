"""The structural model (R14-A, docs/R14A_PLAN.md sections 1 and 2).

Frozen dataclasses that **validate themselves on construction**: a value outside the
closed vocabularies below, a malformed path or a negative coordinate raises
`ModelError` with a message that names the field and the allowed values, so invalid
data cannot travel into a summary or a renderer.

Immutability is deep: mappings are stored as read-only `MappingProxyType` objects
(keys sorted) and every sequence is a tuple, so a model object cannot be changed
after construction, including the nested `meta` and `extensions` values.

Two schema versions exist and must not be confused:

- `SCHEMA_VERSION` here is the version of the **structure model** and of the
  `structure.schema` field of the JSON payload (an integer, 1 today);
- the outer **report** schema (`schema_version`, `"1.7"`) is versioned by
  `renderers/json_renderer.py` and `docs/JSON_SCHEMA.md`.

Coordinates (`SourceLocation`): `line` is 1-based (0 means unknown), `col` and
`end_col` are 0-based **UTF-8 byte offsets** in the line, exactly as the `ast`
module reports them (0 for `end_col` means unknown). Offsets that a parser reports
in characters (a `SyntaxError`) are converted to bytes before they enter the model.

مدل ساختاری؛ اعتبارسنجی هنگام ساخت، تغییرناپذیری عمیق، و دو نسخه‌ی شمای جدا
(مدل ساختار و گزارش بیرونی).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

SCHEMA_VERSION = 1
LANGUAGE_PYTHON = "python"
PARSER_PYTHON_AST = "python-ast"

# --- how completely a file was read -----------------------------------------------
COMPLETENESS_FULL = "full"
COMPLETENESS_PARTIAL = "partial"
COMPLETENESS_FAILED = "failed"
COMPLETENESS_SKIPPED_SIZE = "skipped_size"
COMPLETENESS_VALUES: tuple[str, ...] = (
    COMPLETENESS_FULL,
    COMPLETENESS_PARTIAL,
    COMPLETENESS_FAILED,
    COMPLETENESS_SKIPPED_SIZE,
)

# --- limitation codes (a closed list; see docs/STRUCTURE.md) -----------------------
LIM_SYNTAX_ERROR = "syntax_error"
LIM_RECURSION = "recursion_limit"
LIM_RESOURCE = "resource_limit"
LIM_TOO_LARGE = "too_large"
LIM_NODE_CAP = "node_cap"
LIM_ENCODING = "encoding_error"
LIM_UNSUPPORTED_SYNTAX = "unsupported_syntax_for_interpreter"
LIM_DYNAMIC = "dynamic_construct_seen"
LIM_UNREADABLE = "unreadable"
LIMITATION_CODES: tuple[str, ...] = (
    LIM_SYNTAX_ERROR,
    LIM_RECURSION,
    LIM_RESOURCE,
    LIM_TOO_LARGE,
    LIM_NODE_CAP,
    LIM_ENCODING,
    LIM_UNSUPPORTED_SYNTAX,
    LIM_DYNAMIC,
    LIM_UNREADABLE,
)

# --- what an import resolved to ----------------------------------------------------
TARGET_INTERNAL = "internal"
TARGET_STDLIB = "stdlib"
TARGET_EXTERNAL_DECLARED = "external_declared"
TARGET_EXTERNAL_UNMATCHED = "external_unmatched"
TARGET_INTERNAL_UNRESOLVED = "internal_unresolved"
TARGET_DYNAMIC = "dynamic"
TARGET_CLASSES: tuple[str, ...] = (
    TARGET_INTERNAL,
    TARGET_STDLIB,
    TARGET_EXTERNAL_DECLARED,
    TARGET_EXTERNAL_UNMATCHED,
    TARGET_INTERNAL_UNRESOLVED,
    TARGET_DYNAMIC,
)
EXTERNAL_CLASSES: tuple[str, ...] = (
    TARGET_STDLIB,
    TARGET_EXTERNAL_DECLARED,
    TARGET_EXTERNAL_UNMATCHED,
)

# --- confidence (operational definitions in docs/STRUCTURE.md) ---------------------
CONF_DEFINITE = "definite"
CONF_PROBABLE = "probable"
CONF_UNKNOWN = "unknown"
CONFIDENCE_LEVELS: tuple[str, ...] = (CONF_DEFINITE, CONF_PROBABLE, CONF_UNKNOWN)

# --- flags on an import edge (conditionality does not lower confidence) -------------
FLAG_CONDITIONAL = "conditional"
FLAG_TYPE_ONLY = "type_only"
FLAG_RELATIVE = "relative"
FLAG_STAR = "star"
FLAG_LAZY = "lazy"
EDGE_FLAGS: tuple[str, ...] = (
    FLAG_CONDITIONAL,
    FLAG_TYPE_ONLY,
    FLAG_RELATIVE,
    FLAG_STAR,
    FLAG_LAZY,
)

# --- edge kinds and original statement types ---------------------------------------
EDGE_IMPORTS = "imports"
EDGE_KINDS: tuple[str, ...] = (EDGE_IMPORTS,)
ORIGINAL_IMPORT = "import"
ORIGINAL_FROM_IMPORT = "from_import"
ORIGINAL_DYNAMIC_CALL = "dynamic_call"
ORIGINAL_TYPES: tuple[str, ...] = (
    ORIGINAL_IMPORT,
    ORIGINAL_FROM_IMPORT,
    ORIGINAL_DYNAMIC_CALL,
)

ScalarValue = str | int | bool
MetaValue = str | int | bool | tuple[str, ...]


class ModelError(ValueError):
    """A structural entity was built with a value outside its contract."""


def _choice(owner: str, name: str, value: object, allowed: Iterable[str]) -> None:
    options = tuple(allowed)
    if not isinstance(value, str) or value not in options:
        raise ModelError(f"{owner}.{name} must be one of {options}, got {value!r}")


def _relative_posix(owner: str, name: str, value: object, *, allow_empty: bool) -> None:
    """A repo-relative POSIX path: no leading slash, no backslash, no `..`."""
    if not isinstance(value, str):
        raise ModelError(f"{owner}.{name} must be a string, got {value!r}")
    if value == "":
        if allow_empty:
            return
        raise ModelError(f"{owner}.{name} must not be empty")
    parts = value.split("/")
    if value.startswith("/") or "\\" in value or ".." in parts or "" in parts:
        raise ModelError(
            f"{owner}.{name} must be a relative POSIX path without '..', got {value!r}"
        )


def _non_negative(owner: str, name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ModelError(
            f"{owner}.{name} must be a non-negative integer, got {value!r}"
        )


def _sorted_unique(
    owner: str, name: str, values: Iterable[str], allowed: Iterable[str] | None
) -> tuple[str, ...]:
    items = tuple(values)
    if allowed is not None:
        known = tuple(allowed)
        for item in items:
            if item not in known:
                raise ModelError(f"{owner}.{name} has {item!r}, allowed: {known}")
    return tuple(sorted(set(items)))


def freeze(value: Any) -> Any:
    """Deep, read-only copy: mappings become key-sorted `MappingProxyType`, lists,
    sets and tuples become tuples. Scalars are returned as they are."""
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(k): freeze(value[k]) for k in sorted(value, key=str)}
        )
    if isinstance(value, (list, tuple)):
        return tuple(freeze(v) for v in value)
    if isinstance(value, (set, frozenset)):
        return tuple(freeze(v) for v in sorted(value, key=repr))
    return value


@dataclass(frozen=True)
class SourceLocation:
    """Where something is: repo-relative POSIX path, a 1-based line (0 = unknown) and
    0-based UTF-8 byte offsets of the start and end column (`end_col` 0 = unknown)."""

    path: str
    line: int
    col: int
    end_line: int
    end_col: int

    def __post_init__(self) -> None:
        _relative_posix("SourceLocation", "path", self.path, allow_empty=False)
        for name in ("line", "col", "end_line", "end_col"):
            _non_negative("SourceLocation", name, getattr(self, name))


@dataclass(frozen=True)
class Provenance:
    """Which parser produced an entity, how completely, and what it could not read.

    `rules` names the grammar the file needed when that could be told (for example a
    syntax error that points at newer syntax). `limitations` holds codes from
    `LIMITATION_CODES`, sorted and unique.
    """

    parser: str
    parser_version: str
    rules: str
    completeness: str
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.parser:
            raise ModelError("Provenance.parser must not be empty")
        _choice("Provenance", "completeness", self.completeness, COMPLETENESS_VALUES)
        object.__setattr__(
            self,
            "limitations",
            _sorted_unique(
                "Provenance", "limitations", self.limitations, LIMITATION_CODES
            ),
        )


@dataclass(frozen=True)
class FileEntity:
    """One source file known to the structure, parsed or not. A file that could not
    be read is kept (never dropped silently) with its completeness and reason.

    `size` is `None` when it is **unknown** (the file could not be read); it is never
    a made-up 0. `sha256` is empty when the content was not read."""

    path: str
    language: str
    size: int | None
    sha256: str
    module: str
    provenance: Provenance
    error: SourceLocation | None = None
    extensions: Mapping[str, ScalarValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _relative_posix("FileEntity", "path", self.path, allow_empty=False)
        if not self.language:
            raise ModelError("FileEntity.language must not be empty")
        if self.size is not None:
            _non_negative("FileEntity", "size", self.size)
        if self.sha256 and (
            len(self.sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.sha256)
        ):
            raise ModelError(
                f"FileEntity.sha256 must be 64 lowercase hex digits, got {self.sha256!r}"
            )
        object.__setattr__(self, "extensions", freeze(dict(self.extensions)))


@dataclass(frozen=True)
class ModuleEntity:
    """A Python module of the repository, named from its source root. A namespace
    package portion has no file (`path` is empty) and `is_namespace` is true."""

    name: str
    path: str
    is_package: bool
    is_namespace: bool
    root: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ModelError("ModuleEntity.name must not be empty")
        _relative_posix("ModuleEntity", "root", self.root, allow_empty=True)
        if self.is_namespace:
            if self.path != "" or not self.is_package:
                raise ModelError(
                    "a namespace package portion has no file and is a package"
                )
        else:
            _relative_posix("ModuleEntity", "path", self.path, allow_empty=False)


@dataclass(frozen=True)
class ExternalRef:
    """A top-level name that is not a repository module: standard library, matched
    to a manifest declaration, or neither (unmatched)."""

    name: str
    target_class: str
    declared_in: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name:
            raise ModelError("ExternalRef.name must not be empty")
        _choice("ExternalRef", "target_class", self.target_class, EXTERNAL_CLASSES)
        object.__setattr__(self, "declared_in", tuple(sorted(set(self.declared_in))))
        if self.declared_in and self.target_class != TARGET_EXTERNAL_DECLARED:
            raise ModelError("only an external_declared reference has declared_in")


@dataclass(frozen=True)
class Edge:
    """One import relationship with the evidence for it.

    `source` is the importing module (or the file path when the file has no module
    name); `requested` the name as written (resolved for a relative import); `target`
    the module or top-level name it resolved to (empty when nothing could be
    resolved: only for `internal_unresolved` and `dynamic`). `evidence` is the
    statement text (its lines joined by single spaces, at most 240 characters, `...`
    marks a cut) and `location` where it is. `resolution_method` says which rule
    produced the target and `note` (empty when there is nothing to add) says in words
    why an edge is unresolved or dynamic; it is sarand's own text, never source text.
    """

    kind: str
    source: str
    requested: str
    target: str
    target_class: str
    confidence: str
    resolution_method: str
    evidence: str
    location: SourceLocation
    original_type: str
    flags: tuple[str, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        _choice("Edge", "kind", self.kind, EDGE_KINDS)
        _choice("Edge", "target_class", self.target_class, TARGET_CLASSES)
        _choice("Edge", "confidence", self.confidence, CONFIDENCE_LEVELS)
        _choice("Edge", "original_type", self.original_type, ORIGINAL_TYPES)
        if not self.source:
            raise ModelError("Edge.source must not be empty")
        if not self.resolution_method:
            raise ModelError("Edge.resolution_method must not be empty")
        if not self.target and self.target_class not in (
            TARGET_INTERNAL_UNRESOLVED,
            TARGET_DYNAMIC,
        ):
            raise ModelError(f"Edge.target must not be empty for {self.target_class}")
        object.__setattr__(
            self, "flags", _sorted_unique("Edge", "flags", self.flags, EDGE_FLAGS)
        )


@dataclass(frozen=True)
class Cycle:
    """A set of internal modules that import each other (a strongly connected
    component, or a module that imports itself).

    `edges` holds **every** definite or probable import edge whose two ends are both
    in the cycle, lazy and type-only ones included, each with its own flags; it is
    not a minimal set of edges that closes one loop. `eager` is true when the cycle
    survives after removing type-only and lazy (in-function) imports, that is when it
    can bite at import time."""

    modules: tuple[str, ...]
    eager: bool
    edges: tuple[Edge, ...]

    def __post_init__(self) -> None:
        if not self.modules:
            raise ModelError("Cycle.modules must not be empty")
        object.__setattr__(self, "modules", tuple(sorted(set(self.modules))))
        object.__setattr__(self, "edges", tuple(sorted(self.edges, key=edge_sort_key)))


@dataclass(frozen=True)
class StructureData:
    """The whole structural model of one project (`--structure`).

    `schema_version` is the version of this model (see the module docstring), not of
    the outer report."""

    schema_version: int
    language: str
    meta: Mapping[str, MetaValue]
    files: tuple[FileEntity, ...]
    modules: tuple[ModuleEntity, ...]
    externals: tuple[ExternalRef, ...]
    edges: tuple[Edge, ...]
    cycles: tuple[Cycle, ...]

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version < 1:
            raise ModelError(
                f"StructureData.schema_version must be >= 1, got {self.schema_version!r}"
            )
        if not self.language:
            raise ModelError("StructureData.language must not be empty")
        object.__setattr__(self, "meta", freeze(dict(self.meta)))


def edge_sort_key(edge: Edge) -> tuple[Any, ...]:
    """The one total order of edges: where they are, then what they say. Used by the
    builder, the cycle finder and the serializer, so equal models serialize equally."""
    loc = edge.location
    return (
        edge.source,
        loc.path,
        loc.line,
        loc.col,
        loc.end_line,
        loc.end_col,
        edge.requested,
        edge.target,
        edge.original_type,
        edge.target_class,
        edge.confidence,
        edge.resolution_method,
        edge.flags,
        edge.evidence,
        edge.note,
    )
