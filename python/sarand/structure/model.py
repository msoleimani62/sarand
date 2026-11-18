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
  `structure.schema` field of the JSON payload (an integer, 2 today: 1 was imports
  only, 2 adds symbols, relations and entry points);
- the outer **report** schema (`schema_version`, `"1.8"`) is versioned by
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

SCHEMA_VERSION = 2
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


# --- symbols (R14-A2) --------------------------------------------------------------
SYM_CLASS = "class"
SYM_FUNCTION = "function"
SYM_METHOD = "method"
SYM_VARIABLE = "variable"
SYM_CONSTANT = "constant"
SYM_PROPERTY = "property"
SYMBOL_KINDS: tuple[str, ...] = (
    SYM_CLASS,
    SYM_FUNCTION,
    SYM_METHOD,
    SYM_VARIABLE,
    SYM_CONSTANT,
    SYM_PROPERTY,
)
SYM_FLAG_NESTED = "nested"
SYM_FLAG_CONDITIONAL = "conditional"
SYM_FLAG_DYNAMIC = "dynamic"
SYMBOL_FLAGS: tuple[str, ...] = (
    SYM_FLAG_NESTED,
    SYM_FLAG_CONDITIONAL,
    SYM_FLAG_DYNAMIC,
)

# --- relations between symbols (R14-A2) ---------------------------------------------
REL_CALLS = "calls"
REL_INHERITS = "inherits"
REL_REFERENCES = "references"
RELATION_KINDS: tuple[str, ...] = (REL_CALLS, REL_INHERITS, REL_REFERENCES)

REL_ORIG_CALL = "call"
REL_ORIG_NAME = "name"
REL_ORIG_ATTRIBUTE = "attribute"
REL_ORIG_DECORATOR = "decorator"
REL_ORIG_BASE = "base"
REL_ORIG_DYNAMIC = "dynamic_attribute"
RELATION_ORIGINAL_TYPES: tuple[str, ...] = (
    REL_ORIG_CALL,
    REL_ORIG_NAME,
    REL_ORIG_ATTRIBUTE,
    REL_ORIG_DECORATOR,
    REL_ORIG_BASE,
    REL_ORIG_DYNAMIC,
)

# What a relation's source or target is.
# منبع یا هدف رابطه چیست.
ENDPOINT_SYMBOL = "symbol"
ENDPOINT_MODULE = "module"
ENDPOINT_UNRESOLVED = "unresolved"
ENDPOINT_DYNAMIC = "dynamic"
SOURCE_KINDS: tuple[str, ...] = (ENDPOINT_SYMBOL, ENDPOINT_MODULE)
TARGET_KINDS: tuple[str, ...] = (
    ENDPOINT_SYMBOL,
    ENDPOINT_MODULE,
    ENDPOINT_UNRESOLVED,
    ENDPOINT_DYNAMIC,
)

REL_FLAG_CONDITIONAL = "conditional"
REL_FLAG_TYPE_ONLY = "type_only"
REL_FLAG_LAZY = "lazy"
REL_FLAG_ANNOTATION = "annotation"
RELATION_FLAGS: tuple[str, ...] = (
    REL_FLAG_CONDITIONAL,
    REL_FLAG_TYPE_ONLY,
    REL_FLAG_LAZY,
    REL_FLAG_ANNOTATION,
)

# --- entry points (R14-A2) ----------------------------------------------------------
EP_MAIN_BLOCK = "main_block"
EP_PACKAGE_MAIN = "package_main"
EP_CONSOLE_SCRIPT = "console_script"
EP_ENTRY_POINT_GROUP = "entry_point_group"
EP_TEST_ROOT = "test_root"
EP_FRAMEWORK_APP = "framework_app"
ENTRY_POINT_TYPES: tuple[str, ...] = (
    EP_MAIN_BLOCK,
    EP_PACKAGE_MAIN,
    EP_CONSOLE_SCRIPT,
    EP_ENTRY_POINT_GROUP,
    EP_TEST_ROOT,
    EP_FRAMEWORK_APP,
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
class Symbol:
    """A named definition of the repository: a class, function, method, property,
    variable or constant. `id` is `sym:` plus 12 hex digits of a SHA-256 over the
    language, kind, repo-relative path, qualified name and a `#n` disambiguator for
    a duplicate (a conditional redefinition): none of them is a line number, so the
    id survives formatting and unrelated edits.

    `qualname` follows Python's own convention (`Outer.method`, `outer.<locals>.inner`).
    `parent` is the id of the enclosing class or function, empty at module level (this
    is where the plan's `defines` relationship lives; it is not stored twice).
    `decorators` and `bases` are the written texts of those expressions, in source
    order (not sorted: order is meaning). `module` is empty when the file has no module
    name. `extensions` holds language facts (`is_async`, `is_generator`,
    `has_star_args`, `has_metaclass`, `alias_of`, ...).
    """

    id: str
    kind: str
    name: str
    qualname: str
    module: str
    path: str
    parent: str
    location: SourceLocation
    decorators: tuple[str, ...] = ()
    bases: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()
    extensions: Mapping[str, ScalarValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.startswith("sym:") or len(self.id) != 16:
            raise ModelError(
                f"Symbol.id must be 'sym:' + 12 hex digits, got {self.id!r}"
            )
        _choice("Symbol", "kind", self.kind, SYMBOL_KINDS)
        if not self.name or not self.qualname:
            raise ModelError("Symbol.name and Symbol.qualname must not be empty")
        _relative_posix("Symbol", "path", self.path, allow_empty=False)
        object.__setattr__(
            self, "flags", _sorted_unique("Symbol", "flags", self.flags, SYMBOL_FLAGS)
        )
        object.__setattr__(self, "decorators", tuple(self.decorators))
        object.__setattr__(self, "bases", tuple(self.bases))
        object.__setattr__(self, "extensions", freeze(dict(self.extensions)))


@dataclass(frozen=True)
class Relation:
    """One relationship between two things of the repository, with the evidence.

    `source` is a symbol id (`source_kind` symbol) or a module name (`source_kind`
    module: code at module level). `target` is a symbol id, a module name, or empty
    for `unresolved` and `dynamic`; `target_name` is the name as best known (the
    qualified name of the symbol, the module, or the text that could not be
    resolved). `resolution_method` names the rule that produced the target and `note`
    (sarand's own text) says why a target is unresolved or dynamic.

    Equal relations (same kind, source, target, confidence, method, original type and
    flags) are **merged**: `count` is how many sites said it, `location` and
    `evidence` are those of the first site in source order.
    """

    kind: str
    source: str
    source_kind: str
    target: str
    target_kind: str
    target_name: str
    confidence: str
    resolution_method: str
    original_type: str
    location: SourceLocation
    evidence: str
    count: int = 1
    flags: tuple[str, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        _choice("Relation", "kind", self.kind, RELATION_KINDS)
        _choice("Relation", "source_kind", self.source_kind, SOURCE_KINDS)
        _choice("Relation", "target_kind", self.target_kind, TARGET_KINDS)
        _choice("Relation", "confidence", self.confidence, CONFIDENCE_LEVELS)
        _choice(
            "Relation", "original_type", self.original_type, RELATION_ORIGINAL_TYPES
        )
        if not self.source:
            raise ModelError("Relation.source must not be empty")
        if not self.resolution_method:
            raise ModelError("Relation.resolution_method must not be empty")
        if not self.target and self.target_kind in (ENDPOINT_SYMBOL, ENDPOINT_MODULE):
            raise ModelError(
                f"Relation.target must not be empty for {self.target_kind}"
            )
        if self.target and self.target_kind in (ENDPOINT_UNRESOLVED, ENDPOINT_DYNAMIC):
            raise ModelError(f"Relation.target must be empty for {self.target_kind}")
        _non_negative("Relation", "count", self.count)
        if self.count < 1:
            raise ModelError("Relation.count must be at least 1")
        object.__setattr__(
            self,
            "flags",
            _sorted_unique("Relation", "flags", self.flags, RELATION_FLAGS),
        )


@dataclass(frozen=True)
class EntryPoint:
    """A place execution can start, with the rule that found it and its confidence.

    `type` is one of `ENTRY_POINT_TYPES`; `name` the script, group entry or test path
    (empty for a main block); `target` what was declared (`pkg.mod:func`, a module or
    a path); `resolved` the symbol id or module name it resolved to, empty when it did
    not resolve (then the confidence is `unknown` and `note` says why). `location` is
    where it is written (a manifest line is not tracked: it is the manifest's path with
    line 0).
    """

    type: str
    name: str
    target: str
    resolved: str
    confidence: str
    method: str
    evidence: str
    location: SourceLocation
    note: str = ""

    def __post_init__(self) -> None:
        _choice("EntryPoint", "type", self.type, ENTRY_POINT_TYPES)
        _choice("EntryPoint", "confidence", self.confidence, CONFIDENCE_LEVELS)
        if not self.method:
            raise ModelError("EntryPoint.method must not be empty")


@dataclass(frozen=True)
class ExternalUsage:
    """How the repository's code uses one thing from outside it (`subprocess.run`,
    `click.command`): counts of calls, subclassings and other references. Such uses are
    counted here, not stored one by one (docs/STRUCTURE.md, "What is stored")."""

    name: str
    target_class: str
    calls: int = 0
    inherits: int = 0
    references: int = 0

    def __post_init__(self) -> None:
        if not self.name:
            raise ModelError("ExternalUsage.name must not be empty")
        _choice("ExternalUsage", "target_class", self.target_class, EXTERNAL_CLASSES)
        for name in ("calls", "inherits", "references"):
            _non_negative("ExternalUsage", name, getattr(self, name))


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
    symbols: tuple[Symbol, ...] = ()
    relations: tuple[Relation, ...] = ()
    entry_points: tuple[EntryPoint, ...] = ()
    external_use: tuple[ExternalUsage, ...] = ()
    # Counts of every usage site by outcome, kept so that what was not stored is
    # still accounted for (docs/STRUCTURE.md, "What is stored").
    # شمارش همه‌ی محل‌های استفاده بر حسب نتیجه؛ آنچه ذخیره نشده هم حسابش هست.
    sites: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version < 1:
            raise ModelError(
                f"StructureData.schema_version must be >= 1, got {self.schema_version!r}"
            )
        if not self.language:
            raise ModelError("StructureData.language must not be empty")
        object.__setattr__(self, "meta", freeze(dict(self.meta)))
        object.__setattr__(self, "sites", freeze(dict(self.sites)))


def relation_sort_key(relation: Relation) -> tuple[Any, ...]:
    """The one total order of relations (source, place, then what they say)."""
    loc = relation.location
    return (
        relation.source,
        loc.path,
        loc.line,
        loc.col,
        relation.kind,
        relation.target,
        relation.target_name,
        relation.target_kind,
        relation.confidence,
        relation.resolution_method,
        relation.original_type,
        relation.flags,
        relation.note,
    )


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
