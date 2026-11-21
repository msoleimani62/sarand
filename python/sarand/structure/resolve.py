"""Resolution of usage sites to repository symbols (R14-A2, docs/R14A_PLAN.md section 5).

A usage site (a call, a reference, a decorator, a base class) is resolved **only by name
binding inside the repository's own sources**: lexical scopes, import bindings, class
bodies and the bases of classes. There is no type inference: an attribute of a value
whose type is not known from the syntax is not resolved. Nothing is executed.

Confidence is assigned only by these rules, never by a score:

- **definite**: the name binds to exactly one repository entity by Python's own rules
  and nothing in the repository can rebind it: a name defined once in its module by
  `def` or `class`; `from m import f` where `m` defines `f` once (a chain of such
  re-exports too); `mod.f` through an `import`; `Cls.member` where the class named
  defines the member once.
- **probable**: one candidate but an assumption is needed: `self.method()` (a subclass
  may override it); a member found in a base class (the walk over the bases is
  depth-first, not the exact MRO); a name from `from m import *` when `m` has a static
  `__all__`; a function whose decorator is not in the table of transparent decorators;
  an alias (`Foo = Bar`); a module or class attribute that something assigns
  (`mod.f = g`, `setattr(mod, "f", g)`); a name that is both an attribute and a
  submodule; `super().m()`.
- **unknown**: the evidence cannot establish a target: `getattr` with a name that is
  not a constant; a star import whose source has no static `__all__`; a module-level
  `__getattr__`; two bindings of one name; an unresolved base class; a name that a
  module does not define at all.

The lowest level on the way wins. A site that does not resolve to the repository and
is not one of the specific unknown forms above is **counted by reason**, not stored
(`docs/STRUCTURE.md`, "What is stored"): the output states what was left out.

حل‌کردن محل‌های استفاده فقط با انقیاد نام در سورس خود مخزن؛ بدون استنتاج نوع.
"""

from __future__ import annotations

import builtins
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from sarand.structure.facts import (
    B_CLASS,
    B_CONST_FALSE,
    B_DEF,
    B_FROM,
    B_IMPORT,
    B_OTHER,
    B_SELF,
    B_VAR,
    SUPER_ROOT,
    U_BASE,
    U_CALL,
    U_DYNAMIC,
    Binding,
    FileFacts,
    Scope,
    SymbolInfo,
    Usage,
)
from sarand.structure.imports import ModuleIndex, declared_match, pick_module
from sarand.structure.imports import relative_base as _relative_base
from sarand.structure.model import (
    CONF_DEFINITE,
    CONF_PROBABLE,
    CONF_UNKNOWN,
    ENDPOINT_DYNAMIC,
    ENDPOINT_MODULE,
    ENDPOINT_SYMBOL,
    ENDPOINT_UNRESOLVED,
    REL_CALLS,
    REL_INHERITS,
    REL_REFERENCES,
    SYM_CLASS,
    SYM_CONSTANT,
    SYM_VARIABLE,
    TARGET_EXTERNAL_DECLARED,
    TARGET_EXTERNAL_UNMATCHED,
    TARGET_STDLIB,
    Relation,
    relation_sort_key,
)

MAX_REEXPORT_DEPTH = 8

# Names every module has without defining them (`__file__`, `__doc__`, ...): treated
# like builtins.
# نام‌هایی که هر ماژول بدون تعریف دارد.
_MODULE_GLOBALS = frozenset(
    {
        "__file__",
        "__name__",
        "__doc__",
        "__package__",
        "__spec__",
        "__loader__",
        "__path__",
        "__builtins__",
        "__cached__",
        "__dict__",
    }
)
_BUILTIN_NAMES = frozenset(dir(builtins)) | _MODULE_GLOBALS
_RANK = {CONF_DEFINITE: 0, CONF_PROBABLE: 1, CONF_UNKNOWN: 2}

# Decorators that keep a call going to the function body (or return the class itself):
# a function decorated only with these resolves as definite. Anything else (a web
# framework route, a click command, a user-written wrapper) may replace the function,
# so the resolution is probable. Dotted names after import resolution, plus the
# builtins that need no import.
# دکوراتورهایی که فراخوانی را به بدنه‌ی تابع می‌رسانند؛ بقیه یعنی probable.
TRANSPARENT_DECORATORS = frozenset(
    {
        "staticmethod",
        "classmethod",
        "property",
        "abc.abstractmethod",
        "abc.abstractproperty",
        "atexit.register",
        "contextlib.asynccontextmanager",
        "contextlib.contextmanager",
        "dataclasses.dataclass",
        "enum.unique",
        "functools.cache",
        "functools.cached_property",
        "functools.lru_cache",
        "functools.total_ordering",
        "functools.wraps",
        "typing.final",
        "typing.overload",
        "typing.override",
        "typing.runtime_checkable",
        "typing_extensions.final",
        "typing_extensions.overload",
        "typing_extensions.override",
        "typing_extensions.runtime_checkable",
    }
)

# Why a site was counted and not stored. A closed list (docs/STRUCTURE.md).
# چرا یک محل شمرده شد و ذخیره نشد؛ فهرست بسته.
R_BUILTIN = "builtin"
R_OPAQUE = "expression_without_a_name"
R_LOCAL = "local_binding"
R_UNBOUND = "unbound_name"
R_INSTANCE_ATTRIBUTE = "instance_attribute"
R_ATTRIBUTE_OF_VALUE = "attribute_of_value"
R_CALL_OF_VARIABLE = "call_of_variable"
R_NOT_ANALYSED = "module_not_analysed"
R_AMBIGUOUS_OTHER = "ambiguous_binding_without_repository_candidate"
R_DEPTH = "reexport_depth"
R_SELF = "self_reference"
R_BASE_NOT_CLASS = "base_not_a_class"
R_CONSTANT_NAME = "attribute_by_constant_name"
R_CALL_OF_MODULE = "call_of_module"
UNTRACKED_REASONS: tuple[str, ...] = (
    R_AMBIGUOUS_OTHER,
    R_ATTRIBUTE_OF_VALUE,
    R_BASE_NOT_CLASS,
    R_BUILTIN,
    R_CALL_OF_MODULE,
    R_CALL_OF_VARIABLE,
    R_CONSTANT_NAME,
    R_DEPTH,
    R_INSTANCE_ATTRIBUTE,
    R_LOCAL,
    R_NOT_ANALYSED,
    R_OPAQUE,
    R_SELF,
    R_UNBOUND,
)


def weaker(a: str, b: str) -> str:
    """The lower of two confidence levels."""
    return a if _RANK[a] >= _RANK[b] else b


@dataclass(frozen=True)
class Value:
    """What a name (or a chain) resolved to.

    kind: `symbol` (target is a symbol id), `module` (a module name), `external`
    (target is the dotted name, `target_class` its class), `self` (the first parameter
    of a method; target is the class id), `unresolved` (an unknown with a note), or
    `none` (nothing to store; `reason` says why).
    """

    kind: str
    target: str = ""
    confidence: str = CONF_DEFINITE
    method: str = ""
    note: str = ""
    target_class: str = ""
    reason: str = ""
    super_call: bool = False


def _none(reason: str) -> Value:
    return Value("none", reason=reason)


def _unresolved(method: str, note: str) -> Value:
    return Value("unresolved", confidence=CONF_UNKNOWN, method=method, note=note)


@dataclass
class ExternalUse:
    calls: int = 0
    inherits: int = 0
    references: int = 0
    target_class: str = ""


@dataclass
class ResolveResult:
    relations: list[Relation]
    sites: dict[str, object]
    external_use: dict[str, ExternalUse]


@dataclass
class _Tables:
    by_path: dict[str, FileFacts] = field(default_factory=dict)
    symbols: dict[str, SymbolInfo] = field(default_factory=dict)
    file_of: dict[str, FileFacts] = field(default_factory=dict)
    members: dict[str, dict[str, list[str]]] = field(default_factory=dict)


class Resolver:
    """Resolves the usage sites of every analysed file against the whole repository."""

    def __init__(self, facts: Sequence[FileFacts], index: ModuleIndex) -> None:
        self.index = index
        self.t = _Tables()
        for item in facts:
            self.t.by_path[item.path] = item
            for info in item.symbols:
                self.t.symbols[info.symbol.id] = info
                self.t.file_of[info.symbol.id] = item
                if info.symbol.parent:
                    self.t.members.setdefault(info.symbol.parent, {}).setdefault(
                        info.symbol.name, []
                    ).append(info.symbol.id)
        self.patched: set[tuple[str, str]] = set()
        self._chain_cache: dict[tuple[str, int, tuple[str, ...]], Value] = {}
        self._transparent: dict[str, bool] = {}
        self._bases: dict[str, tuple[list[str], bool, bool]] = {}
        self._collect_patches(facts)

    # --- modules -------------------------------------------------------------------

    def module_facts(
        self, name: str, importer_root: str, *, only_root: bool = False
    ) -> tuple[FileFacts | None, str, bool]:
        """(facts of the module `name`, how it was picked, exists). `exists` is true
        for a module with no analysed file (a namespace package, a file that failed to
        parse), where `facts` is `None`."""
        entity, how = pick_module(
            self.index.by_name.get(name, []), importer_root, only_root=only_root
        )
        if entity is not None:
            return self.t.by_path.get(entity.path), how, True
        if name in self.index.prefixes and how != "ambiguous":
            return None, "namespace", True
        return None, how, False

    def classify_external(self, top: str) -> str:
        if top in self.index.stdlib:
            return TARGET_STDLIB
        # The same rule as the import edge (imports.declared_match): the distribution of
        # the same name, or one that the table of distributions.py says ships `top`.
        if declared_match(self.index, top) is not None:
            return TARGET_EXTERNAL_DECLARED
        return TARGET_EXTERNAL_UNMATCHED

    def _external(self, dotted: str, method: str) -> Value:
        top = dotted.split(".", 1)[0]
        return Value(
            "external",
            target=dotted,
            method=method,
            target_class=self.classify_external(top),
        )

    def _internal_top(self, top: str) -> bool:
        return top in self.index.by_name or top in self.index.prefixes

    # --- bindings ------------------------------------------------------------------

    @staticmethod
    def find_binding(
        facts: FileFacts, scope_id: int, name: str
    ) -> tuple[list[Binding], Scope] | None:
        scopes = facts.scopes
        innermost = scopes[scope_id]
        current = innermost
        while True:
            if current.kind != "class" or current is innermost:
                found = current.bindings.get(name)
                if found:
                    return found, current
            if current.parent < 0:
                return None
            current = scopes[current.parent]

    def value_of_binding(
        self, binding: Binding, facts: FileFacts, scope: Scope, depth: int
    ) -> Value:
        if depth > MAX_REEXPORT_DEPTH:
            return _none(R_DEPTH)
        kind = binding.kind
        if kind in (B_DEF, B_CLASS):
            return self._symbol_value(binding.symbol, facts, scope)
        if kind == B_VAR:
            if binding.alias:
                inner = self.resolve_chain(
                    facts, scope.id, binding.alias, depth + 1, skip=binding.symbol
                )
                if inner.kind in ("symbol", "module", "external"):
                    return _replace(
                        inner,
                        confidence=weaker(inner.confidence, CONF_PROBABLE),
                        method="alias",
                    )
                return inner
            return self._symbol_value(binding.symbol, facts, scope)
        if kind == B_IMPORT:
            return self._module_value(binding.module, facts, "import")
        if kind == B_FROM:
            return self._from_value(binding, facts, depth)
        if kind == B_SELF:
            return Value(
                "self", target=binding.self_class, note=binding.member, method="self"
            )
        if kind in (B_OTHER, B_CONST_FALSE):
            return _none(R_LOCAL)
        return _none(R_LOCAL)

    def _symbol_value(self, symbol_id: str, facts: FileFacts, scope: Scope) -> Value:
        info = self.t.symbols.get(symbol_id)
        if info is None:
            return _none(R_UNBOUND)
        confidence = CONF_DEFINITE
        method = "definition"
        note = ""
        if not self.transparent(info):
            confidence, method = CONF_PROBABLE, "decorated"
            note = "a decorator may replace the definition"
        if scope.kind == "module" and (facts.label, info.symbol.name) in self.patched:
            confidence, method = CONF_PROBABLE, "patched"
            note = "the name is assigned somewhere else in the repository"
        return Value(
            "symbol", target=symbol_id, confidence=confidence, method=method, note=note
        )

    def _module_value(self, name: str, importer: FileFacts, method: str) -> Value:
        top = name.split(".", 1)[0]
        if not self._internal_top(top):
            return self._external(name, method)
        _found, how, exists = self.module_facts(name, importer.root)
        if not exists:
            return _unresolved(
                "import-target-missing", f"{name} not found in the repository"
            )
        confidence = CONF_DEFINITE if how in ("unique", "namespace") else CONF_PROBABLE
        return Value("module", target=name, confidence=confidence, method=method)

    def _from_value(self, binding: Binding, facts: FileFacts, depth: int) -> Value:
        if binding.level:
            base = _relative_base(facts.entity, binding.level)
            if base is None:
                return _unresolved("relative-no-parent-package", "no parent package")
            full = f"{base}.{binding.module}" if binding.module else base
            only_root = True
        else:
            full, only_root = binding.module, False
        top = full.split(".", 1)[0]
        if not binding.level and not self._internal_top(top):
            return self._external(f"{full}.{binding.member}", "from-import")
        found, how, exists = self.module_facts(full, facts.root, only_root=only_root)
        if not exists:
            return _unresolved(
                "import-target-missing", f"{full} not found in the repository"
            )
        value = self.member_of_module(full, found, binding.member, facts, depth + 1)
        if value.kind == "module":
            return value
        if how not in ("unique", "namespace"):
            return _replace(value, confidence=weaker(value.confidence, CONF_PROBABLE))
        return value

    # --- module members --------------------------------------------------------------

    def member_of_module(
        self,
        module: str,
        mfacts: FileFacts | None,
        name: str,
        importer: FileFacts,
        depth: int,
    ) -> Value:
        if depth > MAX_REEXPORT_DEPTH:
            return _none(R_DEPTH)
        sub = f"{module}.{name}"
        _sub_facts, sub_how, sub_exists = self.module_facts(sub, importer.root)
        if mfacts is None:
            if sub_exists:
                return Value(
                    "module",
                    target=sub,
                    confidence=CONF_DEFINITE
                    if sub_how in ("unique", "namespace")
                    else CONF_PROBABLE,
                    method="submodule",
                )
            return _none(R_NOT_ANALYSED)
        module_scope = mfacts.scopes[0]
        bindings = module_scope.bindings.get(name)
        if bindings:
            if len(bindings) > 1:
                return self._ambiguous(bindings, mfacts, module_scope, depth)
            value = self.value_of_binding(bindings[0], mfacts, module_scope, depth + 1)
            if sub_exists and value.kind in ("symbol", "external", "module"):
                value = _replace(
                    value, confidence=weaker(value.confidence, CONF_PROBABLE)
                )
            return value
        if sub_exists:
            return Value(
                "module",
                target=sub,
                confidence=CONF_DEFINITE
                if sub_how in ("unique", "namespace")
                else CONF_PROBABLE,
                method="submodule",
            )
        if name in _MODULE_GLOBALS:
            return _none(R_BUILTIN)
        if mfacts.has_module_getattr:
            return _unresolved(
                "module-getattr", f"{module} defines a module-level __getattr__"
            )
        starred = self._star_value(mfacts, name, depth)
        if starred is not None:
            return starred
        return _unresolved("member-missing", f"{module} does not define {name}")

    def _star_value(self, facts: FileFacts, name: str, depth: int) -> Value | None:
        """What `from m import *` statements of a module say about `name`: a probable
        symbol when exactly one source with a static `__all__` lists it, an unknown when
        a source has no static `__all__` or two sources list it, `None` when the star
        imports do not explain the name."""
        stars = facts.scopes[0].stars
        if not stars:
            return None
        candidates: list[Value] = []
        unknown_source = False
        for module, level in stars:
            if level:
                base = _relative_base(facts.entity, level)
                full = (f"{base}.{module}" if module else base) if base else None
            else:
                full = module
            if not full:
                unknown_source = True
                continue
            if not level and not self._internal_top(full.split(".", 1)[0]):
                unknown_source = True
                continue
            sfacts, _how, exists = self.module_facts(
                full, facts.root, only_root=bool(level)
            )
            if sfacts is None or not exists:
                unknown_source = True
                continue
            if sfacts.dunder_all is None:
                unknown_source = True
                continue
            if name in sfacts.dunder_all:
                inner = self.member_of_module(full, sfacts, name, facts, depth + 1)
                candidates.append(inner)
        if len(candidates) == 1 and not unknown_source:
            inner = candidates[0]
            if inner.kind in ("symbol", "module", "external"):
                return _replace(
                    inner,
                    confidence=weaker(inner.confidence, CONF_PROBABLE),
                    method="star-import-all",
                )
            return inner
        if len(candidates) > 1:
            return _unresolved(
                "star-import-two-candidates",
                f"{name} comes from more than one star import",
            )
        if unknown_source:
            return _unresolved(
                "star-import-without-static-all",
                f"{name} may come from a star import whose source has no static __all__",
            )
        return None

    def _ambiguous(
        self, bindings: list[Binding], facts: FileFacts, scope: Scope, depth: int
    ) -> Value:
        values = [self.value_of_binding(b, facts, scope, depth + 1) for b in bindings]
        if any(v.kind in ("symbol", "module") for v in values):
            return _unresolved(
                "ambiguous-binding", f"the name is bound {len(bindings)} different ways"
            )
        return _none(R_AMBIGUOUS_OTHER)

    # --- classes ---------------------------------------------------------------------

    def transparent(self, info: SymbolInfo) -> bool:
        """True when every decorator of the definition is in the table of transparent
        decorators (after import resolution)."""
        cached = self._transparent.get(info.symbol.id)
        if cached is not None:
            return cached
        facts = self.t.file_of[info.symbol.id]
        result = True
        for chain in info.decorator_chains:
            if chain is None:
                result = False
                break
            name = self._canonical_name(facts, info.scope, chain)
            if name not in TRANSPARENT_DECORATORS:
                result = False
                break
        self._transparent[info.symbol.id] = result
        return result

    def _canonical_name(
        self, facts: FileFacts, scope_id: int, chain: tuple[str, ...]
    ) -> str:
        """The dotted name a chain refers to when it ends outside the repository, the
        builtin's own name for an unshadowed builtin, or an empty string."""
        found = self.find_binding(facts, scope_id, chain[0])
        if found is None:
            return (
                ".".join(chain)
                if chain[0] in _BUILTIN_NAMES and len(chain) == 1
                else ""
            )
        value = self.resolve_chain(facts, scope_id, chain, 0)
        return value.target if value.kind == "external" else ""

    def decorator_names(self, info: SymbolInfo) -> list[str]:
        """The external dotted names of a definition's decorators ('' for the rest)."""
        facts = self.t.file_of[info.symbol.id]
        return [
            "" if chain is None else self._canonical_name(facts, info.scope, chain)
            for chain in info.decorator_chains
        ]

    def class_bases(self, class_id: str) -> tuple[list[str], bool, bool]:
        """(repository base class ids in order, has an external base, has an unresolved
        base). A base that is not a plain name, or that does not resolve, is
        unresolved; a base resolved outside the repository is external."""
        cached = self._bases.get(class_id)
        if cached is not None:
            return cached
        self._bases[class_id] = ([], False, False)  # cycle guard
        info = self.t.symbols[class_id]
        facts = self.t.file_of[class_id]
        ids: list[str] = []
        external = unresolved = False
        for chain in info.base_chains:
            if chain is None:
                unresolved = True
                continue
            value = self.resolve_chain(facts, info.scope, chain, 0)
            if (
                value.kind == "symbol"
                and self.t.symbols[value.target].symbol.kind == SYM_CLASS
            ):
                ids.append(value.target)
            elif value.kind == "external" or (
                value.kind == "none" and value.reason == R_BUILTIN
            ):
                external = True
            else:
                unresolved = True
        result = (ids, external, unresolved)
        self._bases[class_id] = result
        return result

    def class_member(
        self,
        class_id: str,
        name: str,
        *,
        via_instance: bool,
        skip_own: bool = False,
    ) -> Value:
        """Look `name` up in a class and then, depth first, in its repository bases."""
        visited: set[str] = set()
        order: list[str] = []
        unresolved_base = False

        def walk(current: str, first: bool) -> None:
            nonlocal unresolved_base
            if current in visited:
                return
            visited.add(current)
            if not (first and skip_own):
                order.append(current)
            ids, _external, unresolved = self.class_bases(current)
            unresolved_base = unresolved_base or unresolved
            for base in ids:
                walk(base, False)

        walk(class_id, True)
        for current in order:
            found = self._own_member(current, name)
            if found is None:
                continue
            if found.kind != "symbol":
                return found
            inherited = current != class_id
            if via_instance or inherited or skip_own:
                confidence = weaker(found.confidence, CONF_PROBABLE)
                method = (
                    "super-call"
                    if skip_own
                    else "inherited-member"
                    if inherited
                    else "self-member"
                )
                return _replace(found, confidence=confidence, method=method)
            return found
        for current in order:
            hook = self._own_member(current, "__getattr__")
            if hook is not None and hook.kind == "symbol":
                return _unresolved("getattr-hook", "the class defines __getattr__")
        if unresolved_base:
            return _unresolved("unresolved-base", "a base class could not be resolved")
        return _none(R_INSTANCE_ATTRIBUTE)

    def _own_member(self, class_id: str, name: str) -> Value | None:
        info = self.t.symbols[class_id]
        facts = self.t.file_of[class_id]
        if info.own_scope < 0:
            return None
        scope = facts.scopes[info.own_scope]
        bindings = scope.bindings.get(name)
        if bindings:
            if len(bindings) > 1:
                return self._ambiguous(bindings, facts, scope, 0)
            binding = bindings[0]
            if binding.kind in (B_DEF, B_CLASS, B_VAR):
                value = self._symbol_value(binding.symbol, facts, scope)
                if (class_id, name) in self.patched:
                    value = _replace(value, confidence=CONF_PROBABLE, method="patched")
                return value
            return _none(R_LOCAL)
        for child in self.t.members.get(class_id, {}).get(name, ()):
            child_info = self.t.symbols[child]
            if child_info.symbol.extensions.get("declared_only"):
                return Value(
                    "symbol",
                    target=child,
                    confidence=CONF_PROBABLE,
                    method="declared-attribute",
                )
        return None

    # --- chains ------------------------------------------------------------------------

    def resolve_chain(
        self,
        facts: FileFacts,
        scope_id: int,
        chain: tuple[str, ...],
        depth: int = 0,
        *,
        skip: str = "",
        enclosing: str = "",
    ) -> Value:
        """Resolve a written chain (`a.b.c`) seen from a scope. `enclosing` is the
        symbol the site belongs to (needed for `super()`)."""
        if not chain:
            return _none(R_OPAQUE)
        key = (facts.path, scope_id, chain)
        cacheable = depth == 0 and not enclosing and not skip
        if cacheable and key in self._chain_cache:
            return self._chain_cache[key]
        value = self._resolve_chain(facts, scope_id, chain, depth, skip, enclosing)
        if cacheable:
            self._chain_cache[key] = value
        return value

    def _resolve_chain(
        self,
        facts: FileFacts,
        scope_id: int,
        chain: tuple[str, ...],
        depth: int,
        skip: str,
        enclosing: str,
    ) -> Value:
        root, rest = chain[0], chain[1:]
        if root == SUPER_ROOT:
            return self._super_member(enclosing, rest)
        found = self.find_binding(facts, scope_id, root)
        if found is None:
            if root in _BUILTIN_NAMES:
                return _none(R_BUILTIN)
            starred = self._star_value(facts, root, depth)
            if starred is not None:
                return self.follow_attributes(starred, rest, facts)
            return _none(R_UNBOUND)
        bindings, owner = found
        if skip:
            bindings = [b for b in bindings if b.symbol != skip]
            if not bindings:
                return _none(R_LOCAL)
        if len(bindings) > 1:
            return self._ambiguous(bindings, facts, owner, depth)
        value = self.value_of_binding(bindings[0], facts, owner, depth)
        return self.follow_attributes(value, rest, facts)

    def _super_member(self, enclosing: str, rest: tuple[str, ...]) -> Value:
        info = self.t.symbols.get(enclosing)
        if info is None or len(rest) != 1 or not info.symbol.parent:
            return _none(R_ATTRIBUTE_OF_VALUE)
        parent = self.t.symbols.get(info.symbol.parent)
        if parent is None or parent.symbol.kind != SYM_CLASS:
            return _none(R_ATTRIBUTE_OF_VALUE)
        return self.class_member(
            parent.symbol.id, rest[0], via_instance=True, skip_own=True
        )

    def follow_attributes(
        self, value: Value, rest: tuple[str, ...], facts: FileFacts
    ) -> Value:
        """Follow the attributes of a chain from a resolved root."""
        current = value
        for position, attr in enumerate(rest):
            if current.kind == "module":
                mfacts, _how, _exists = self.module_facts(current.target, facts.root)
                nxt = self.member_of_module(current.target, mfacts, attr, facts, 1)
                current = (
                    _replace(nxt, confidence=weaker(current.confidence, nxt.confidence))
                    if nxt.kind in ("symbol", "module", "external")
                    else nxt
                )
            elif current.kind == "external":
                current = _replace(current, target=f"{current.target}.{attr}")
            elif current.kind == "self":
                if position != 0:
                    return _none(R_ATTRIBUTE_OF_VALUE)
                nxt = self.class_member(current.target, attr, via_instance=True)
                if nxt.kind == "symbol":
                    nxt = _replace(
                        nxt, confidence=weaker(nxt.confidence, CONF_PROBABLE)
                    )
                current = nxt
            elif current.kind == "symbol":
                info = self.t.symbols[current.target]
                if info.symbol.kind != SYM_CLASS:
                    return _none(R_ATTRIBUTE_OF_VALUE)
                nxt = self.class_member(current.target, attr, via_instance=False)
                if nxt.kind == "symbol":
                    nxt = _replace(
                        nxt, confidence=weaker(nxt.confidence, current.confidence)
                    )
                current = nxt
            else:
                return current
        if current.kind == "self":
            if current.note == "cls":
                return Value(
                    "symbol",
                    target=current.target,
                    confidence=CONF_PROBABLE,
                    method="cls-constructor",
                    note="cls may be a subclass",
                )
            return _none(R_SELF)
        return current

    # --- patches ---------------------------------------------------------------------

    def _collect_patches(self, facts: Sequence[FileFacts]) -> None:
        for item in facts:
            for patch in item.patches:
                value = self.resolve_chain(item, patch.scope, patch.chain)
                if value.kind == "module":
                    self.patched.add((value.target, patch.attr))
                elif value.kind == "symbol":
                    info = self.t.symbols[value.target]
                    if info.symbol.kind == SYM_CLASS:
                        self.patched.add((value.target, patch.attr))
        # The chains resolved before every patch was known: forget them.
        # زنجیره‌ها پیش از شناخت همه‌ی patchها حل شده بودند؛ فراموش می‌شوند.
        self._chain_cache.clear()
        self._transparent.clear()
        self._bases.clear()

    # --- sites -------------------------------------------------------------------------

    def target_name(self, symbol_id: str) -> str:
        info = self.t.symbols[symbol_id].symbol
        return f"{info.module or info.path}:{info.qualname}"

    def resolve_all(
        self,
        facts: Sequence[FileFacts],
        untracked: list[tuple[str, str, str]] | None = None,
    ) -> ResolveResult:
        """Resolve every usage site; store what the policy says, count the rest.

        `untracked`, when given, receives `(reason, location, evidence)` for every
        site that was counted and not stored (used by the evaluation, off by default)."""
        merged: dict[tuple[object, ...], Relation] = {}
        external_use: dict[str, ExternalUse] = {}
        sites: dict[str, int] = {
            "total": 0,
            "builtin": 0,
            "internal": 0,
            "external_stdlib": 0,
            "external_declared": 0,
            "external_unmatched": 0,
            "unresolved": 0,
            "dynamic": 0,
            "untracked": 0,
        }
        reasons: dict[str, int] = {}

        def count_untracked(reason: str, usage: Usage | None, count: int = 1) -> None:
            sites["untracked"] += count
            reasons[reason] = reasons.get(reason, 0) + count
            if untracked is not None and usage is not None:
                loc = usage.location
                untracked.append(
                    (reason, f"{loc.path}:{loc.line}:{loc.col}", usage.evidence)
                )

        for item in sorted(facts, key=lambda f: f.path):
            constant_names = item.sites_by_kind.get(R_CONSTANT_NAME, 0)
            if constant_names:
                sites["total"] += constant_names
                count_untracked(R_CONSTANT_NAME, None, constant_names)
            ordered = sorted(
                item.usages,
                key=lambda u: (u.location.line, u.location.col, u.kind, u.chain),
            )
            for usage in ordered:
                sites["total"] += 1
                self._one(item, usage, merged, external_use, sites, count_untracked)
        final: dict[str, object] = dict(sites)
        final["untracked_by_reason"] = {k: reasons[k] for k in sorted(reasons)}
        relations = sorted(merged.values(), key=relation_sort_key)
        return ResolveResult(relations, final, external_use)

    def _one(
        self,
        item: FileFacts,
        usage: Usage,
        merged: dict[tuple[object, ...], Relation],
        external_use: dict[str, ExternalUse],
        sites: dict[str, int],
        count_untracked: Callable[[str, Usage | None, int], None],
    ) -> None:
        source = usage.source or item.label
        source_kind = ENDPOINT_SYMBOL if usage.source else ENDPOINT_MODULE
        if usage.kind == U_DYNAMIC:
            sites["dynamic"] += 1
            self._store(
                merged,
                Relation(
                    kind=REL_CALLS,
                    source=source,
                    source_kind=source_kind,
                    target="",
                    target_kind=ENDPOINT_DYNAMIC,
                    target_name=usage.chain[0] if usage.chain else "",
                    confidence=CONF_UNKNOWN,
                    resolution_method="dynamic-attribute",
                    original_type=usage.original_type,
                    location=usage.location,
                    evidence=usage.evidence,
                    flags=usage.flags,
                    note=usage.note,
                ),
            )
            return
        if not usage.chain:
            count_untracked(R_OPAQUE, usage, 1)
            return
        value = self.resolve_chain(
            item, usage.scope, usage.chain, 0, enclosing=usage.source
        )
        kind = {U_CALL: REL_CALLS, U_BASE: REL_INHERITS}.get(usage.kind, REL_REFERENCES)
        if value.kind == "none":
            if value.reason == R_BUILTIN:
                sites["builtin"] += 1
                return
            if usage.kind != U_CALL and value.reason in (R_LOCAL, R_SELF):
                # Reading a local variable is not a usage site of anything.
                # خواندن یک متغیر محلی محل استفاده از چیزی به‌شمار نمی‌آید.
                sites["total"] -= 1
                return
            count_untracked(value.reason, usage, 1)
            return
        if value.kind == "self":
            if usage.kind == U_CALL:
                count_untracked(R_SELF, usage, 1)
            else:
                sites["total"] -= 1
            return
        if value.kind == "external":
            key = {
                TARGET_STDLIB: "external_stdlib",
                TARGET_EXTERNAL_DECLARED: "external_declared",
                TARGET_EXTERNAL_UNMATCHED: "external_unmatched",
            }[value.target_class]
            sites[key] += 1
            use = external_use.setdefault(
                value.target, ExternalUse(target_class=value.target_class)
            )
            if kind == REL_CALLS:
                use.calls += 1
            elif kind == REL_INHERITS:
                use.inherits += 1
            else:
                use.references += 1
            return
        if value.kind == "module":
            if usage.kind == U_CALL:
                count_untracked(R_CALL_OF_MODULE, usage, 1)
            else:
                # A bare module name is an import fact, not a usage site.
                # نام خالی یک ماژول واقعیت import است، نه محل استفاده.
                sites["total"] -= 1
            return
        if value.kind == "unresolved":
            sites["unresolved"] += 1
            self._store(
                merged,
                Relation(
                    kind=kind,
                    source=source,
                    source_kind=source_kind,
                    target="",
                    target_kind=ENDPOINT_UNRESOLVED,
                    target_name=".".join(usage.chain),
                    confidence=CONF_UNKNOWN,
                    resolution_method=value.method,
                    original_type=usage.original_type,
                    location=usage.location,
                    evidence=usage.evidence,
                    flags=usage.flags,
                    note=value.note,
                ),
            )
            return
        # A symbol of the repository.
        target = self.t.symbols[value.target].symbol
        if usage.kind == U_CALL and target.kind in (SYM_VARIABLE, SYM_CONSTANT):
            count_untracked(R_CALL_OF_VARIABLE, usage, 1)
            return
        if usage.kind == U_BASE and target.kind != SYM_CLASS:
            count_untracked(R_BASE_NOT_CLASS, usage, 1)
            return
        sites["internal"] += 1
        self._store(
            merged,
            Relation(
                kind=kind,
                source=source,
                source_kind=source_kind,
                target=target.id,
                target_kind=ENDPOINT_SYMBOL,
                target_name=self.target_name(target.id),
                confidence=value.confidence,
                resolution_method=value.method,
                original_type=usage.original_type,
                location=usage.location,
                evidence=usage.evidence,
                flags=usage.flags,
                note=value.note,
            ),
        )

    @staticmethod
    def _store(merged: dict[tuple[object, ...], Relation], relation: Relation) -> None:
        key = (
            relation.kind,
            relation.source,
            relation.source_kind,
            relation.target,
            relation.target_kind,
            relation.target_name,
            relation.confidence,
            relation.resolution_method,
            relation.original_type,
            relation.flags,
            relation.note,
        )
        existing = merged.get(key)
        if existing is None:
            merged[key] = relation
            return
        merged[key] = Relation(
            kind=existing.kind,
            source=existing.source,
            source_kind=existing.source_kind,
            target=existing.target,
            target_kind=existing.target_kind,
            target_name=existing.target_name,
            confidence=existing.confidence,
            resolution_method=existing.resolution_method,
            original_type=existing.original_type,
            location=existing.location,
            evidence=existing.evidence,
            count=existing.count + 1,
            flags=existing.flags,
            note=existing.note,
        )


def _replace(value: Value, **changes: object) -> Value:
    data = {
        "kind": value.kind,
        "target": value.target,
        "confidence": value.confidence,
        "method": value.method,
        "note": value.note,
        "target_class": value.target_class,
        "reason": value.reason,
        "super_call": value.super_call,
    }
    data.update(changes)
    return Value(**data)  # type: ignore[arg-type]
