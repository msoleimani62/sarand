"""The structural model (R14-A, docs/R14A_PLAN.md sections 1 and 2).

Frozen dataclasses only, no logic. Every entity that has a place in a file carries a
`SourceLocation`; every file carries a `Provenance` that says which parser read it,
how completely, and what it could not understand. Language-specific facts go in the
`extensions` mapping of an entity, never in a generic field.

مدل ساختاری: فقط داده؛ هر موجودیت مکان منبع و منشأ تجزیه را نگه می‌دارد.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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
LIM_TOO_LARGE = "too_large"
LIM_NODE_CAP = "node_cap"
LIM_ENCODING = "encoding_error"
LIM_UNSUPPORTED_SYNTAX = "unsupported_syntax_for_interpreter"
LIM_DYNAMIC = "dynamic_construct_seen"
LIM_UNREADABLE = "unreadable"

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

# --- edge kinds and original statement types ---------------------------------------
EDGE_IMPORTS = "imports"
ORIGINAL_IMPORT = "import"
ORIGINAL_FROM_IMPORT = "from_import"
ORIGINAL_DYNAMIC_CALL = "dynamic_call"


@dataclass(frozen=True)
class SourceLocation:
    """Where something is: repo-relative POSIX path and a 1-based line, 0-based
    column (as `ast` reports them)."""

    path: str
    line: int
    col: int
    end_line: int
    end_col: int


@dataclass(frozen=True)
class Provenance:
    """Which parser produced an entity, how completely, and what it could not read.

    `rules` names the grammar the file needed when that could be told (for example a
    syntax error under this interpreter). `limitations` holds codes from the closed
    list above, sorted.
    """

    parser: str
    parser_version: str
    rules: str
    completeness: str
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class FileEntity:
    """One source file known to the structure, parsed or not. A file that could not
    be read is kept (never dropped silently) with its completeness and reason."""

    path: str
    language: str
    size: int
    sha256: str
    module: str
    provenance: Provenance
    error: SourceLocation | None = None
    extensions: dict[str, str | int | bool] = field(default_factory=dict)


@dataclass(frozen=True)
class ModuleEntity:
    """A Python module of the repository, named from its source root."""

    name: str
    path: str
    is_package: bool
    is_namespace: bool
    root: str


@dataclass(frozen=True)
class ExternalRef:
    """A top-level name that is not a repository module: standard library, matched
    to a manifest declaration, or neither (unmatched)."""

    name: str
    target_class: str
    declared_in: tuple[str, ...] = ()


@dataclass(frozen=True)
class Edge:
    """One import relationship with the evidence for it.

    `source` is the importing module; `requested` the name as written (resolved for a
    relative import); `target` the module or top-level name it resolved to (empty
    when nothing could be resolved). `evidence` is the statement text and `location`
    where it is. `resolution_method` says which rule produced the target.
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


@dataclass(frozen=True)
class Cycle:
    """A set of internal modules that import each other (a strongly connected
    component, or a module that imports itself). `eager` is true when the cycle
    survives after removing type-only and lazy (in-function) imports, that is when
    it can bite at import time."""

    modules: tuple[str, ...]
    eager: bool
    edges: tuple[Edge, ...]


@dataclass(frozen=True)
class StructureData:
    """The whole structural model of one project (`--structure`)."""

    schema_version: int
    language: str
    meta: dict[str, str | int | bool | list[str]]
    files: tuple[FileEntity, ...]
    modules: tuple[ModuleEntity, ...]
    externals: tuple[ExternalRef, ...]
    edges: tuple[Edge, ...]
    cycles: tuple[Cycle, ...]
