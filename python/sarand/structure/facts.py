"""Symbols and usage sites of one Python file (R14-A2, docs/R14A_PLAN.md sections 3, 5, 9).

Reads an already parsed `ast` tree (nothing is executed) and records, **without
resolving anything**:

- the symbols the file defines (class, function, method, property, variable, constant)
  with their qualified names, decorators, bases and flags;
- a binding table per scope (module, class, function, comprehension) that says which
  names are bound how: by a definition, an import, an assignment, a parameter, or
  something this module does not track;
- every usage site: a call, a reference to a name or an attribute chain, a decorator,
  a base class, and the dynamic forms that cannot be followed;
- what the entry-point and resolution stages need: `if __name__ == "__main__":`
  blocks, a static `__all__`, a module-level `__getattr__`, attribute assignments that
  may patch a module or class (`mod.f = g`, `setattr(mod, "f", g)`).

Names are looked up lexically, as Python does: a class body is not visible from the
methods inside it, a function's own assignments make a name local for the whole
function, `global` redirects an assignment to the module. Assignment expressions (`:=`) bind when
the walk reaches them; `del` of attributes, `exec` and `eval` are not tracked.

Which usage is *stored* and with what confidence is decided later (`resolve.py`).

نمادها و محل‌های استفاده‌ی یک فایل پایتون؛ بدون حل‌کردن چیزی و بدون اجرای کد.
"""

from __future__ import annotations

import ast
import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field, replace

from sarand.structure.fingerprint import fingerprint
from sarand.structure.model import (
    LANGUAGE_PYTHON,
    LIM_DYNAMIC,
    LIM_NODE_CAP,
    LIM_RECURSION,
    LIM_RESOURCE,
    REL_FLAG_ANNOTATION,
    REL_FLAG_CONDITIONAL,
    REL_FLAG_LAZY,
    REL_FLAG_TYPE_ONLY,
    REL_ORIG_ATTRIBUTE,
    REL_ORIG_BASE,
    REL_ORIG_CALL,
    REL_ORIG_DECORATOR,
    REL_ORIG_DYNAMIC,
    REL_ORIG_NAME,
    SYM_CLASS,
    SYM_CONSTANT,
    SYM_FLAG_CONDITIONAL,
    SYM_FLAG_DYNAMIC,
    SYM_FLAG_NESTED,
    SYM_FUNCTION,
    SYM_METHOD,
    SYM_PROPERTY,
    SYM_VARIABLE,
    ModuleEntity,
    SourceLocation,
    Symbol,
)
from sarand.structure.python_extract import (
    MAX_NODES_PER_FILE,
    evidence_of,
    split_lines,
)

# --- binding kinds -------------------------------------------------------------------
B_DEF = "def"  # a function or method definition (symbol)
B_CLASS = "class"  # a class definition (symbol)
B_VAR = "var"  # a module- or class-level assignment (symbol)
B_IMPORT = "import"  # `import a.b [as c]`
B_FROM = "from"  # `from m import x [as y]`
B_SELF = "self"  # the first parameter of a method (`self`, `cls`)
B_OTHER = "other"  # a parameter, loop variable, `with ... as`, `except ... as`, etc.
B_CONST_FALSE = "const_false"  # `TYPE_CHECKING = False`

# --- usage kinds ---------------------------------------------------------------------
U_CALL = "call"
U_REFERENCE = "reference"
U_DECORATOR = "decorator"
U_BASE = "base"
U_DYNAMIC = "dynamic"

# The root of a chain written `super().name`: not a name a program can bind.
# ریشه‌ی زنجیره‌ی `super().name`؛ نامی که برنامه نمی‌تواند مقید کند.
SUPER_ROOT = "<super>"

# Names written for a decorator that make a method a property / an accessor / an overload.
# Purely syntactic, documented in docs/STRUCTURE.md.
# نام‌هایی که متد را property، accessor یا overload می‌کنند؛ فقط نحوی.
_PROPERTY_DECORATORS = frozenset({"property", "cached_property"})
_ACCESSOR_ATTRIBUTES = frozenset({"setter", "getter", "deleter"})
_IMPLICIT_CLASSMETHODS = frozenset(
    {"__init_subclass__", "__class_getitem__", "__new__"}
)
_CONSTANT_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
_DYNAMIC_ATTRIBUTE_FUNCTIONS = frozenset({"getattr", "setattr", "delattr"})


@dataclass(frozen=True)
class Binding:
    """What a name is bound to in one scope.

    `symbol` is the symbol id for a definition or a variable. For an import, `module`
    is the dotted module (for `import a.b.c` without `as`, only the top name `a`: that
    is all it binds), `level` the number of leading dots of a `from` import and
    `member` the imported name. `alias` is the written chain of the right-hand side of
    a plain `Name = chain` assignment. `self_class` is the class symbol id of a
    method's first parameter. Equal bindings of one name are the same fact (two
    `import os` are not an ambiguity).
    """

    kind: str
    symbol: str = ""
    module: str = ""
    level: int = 0
    member: str = ""
    alias: tuple[str, ...] = ()
    self_class: str = ""


@dataclass
class Scope:
    id: int
    kind: str  # "module", "class", "function", "comprehension"
    parent: int  # -1 for the module scope
    bindings: dict[str, list[Binding]] = field(default_factory=dict)
    stars: list[tuple[str, int]] = field(default_factory=list)  # (module, level)

    def add(self, name: str, binding: Binding) -> None:
        found = self.bindings.setdefault(name, [])
        if binding not in found:
            found.append(binding)


@dataclass(frozen=True)
class Usage:
    """One usage site. `chain` is the written dotted name (`("self", "run")`) and is
    empty when the thing is not a plain name chain (`f().g()`): such a site is counted
    but nothing is resolved for it. `scope` is the scope the names are looked up in and
    `source` the symbol id the usage belongs to (empty: module-level code)."""

    kind: str
    chain: tuple[str, ...]
    scope: int
    source: str
    location: SourceLocation
    evidence: str
    flags: tuple[str, ...]
    original_type: str
    note: str = ""


@dataclass(frozen=True)
class PatchTarget:
    """`chain.attr = value` or `setattr(chain, "attr", value)`: it may replace a
    module or class attribute at run time."""

    chain: tuple[str, ...]
    attr: str
    scope: int
    location: SourceLocation


@dataclass
class SymbolInfo:
    """A symbol with what the resolver needs: the scope it is defined in, the scope of
    its own body, and the written chains of its decorators and bases (`None` for an
    expression that is not a plain name chain)."""

    symbol: Symbol
    scope: int
    own_scope: int = -1
    decorator_chains: tuple[tuple[str, ...] | None, ...] = ()
    base_chains: tuple[tuple[str, ...] | None, ...] = ()
    accessor: bool = False
    overload: bool = False
    metaclass: bool = False
    # For a variable assigned the result of a call (`app = typer.Typer()`): the chain
    # of the called name. Used only to find framework application objects.
    # زنجیره‌ی نام فراخوانی‌شده در `x = f()`؛ فقط برای یافتن شیء برنامه‌ی فریم‌ورک.
    value_call: tuple[str, ...] | None = None


@dataclass
class MainBlock:
    location: SourceLocation
    evidence: str


@dataclass
class FileFacts:
    path: str
    module: str  # the module name, or "" when the file has none
    entity: ModuleEntity | None
    scopes: list[Scope]
    symbols: list[SymbolInfo]
    usages: list[Usage]
    patches: list[PatchTarget]
    main_blocks: list[MainBlock]
    dunder_all: tuple[str, ...] | None
    has_module_getattr: bool
    limits: set[str]
    dynamic: bool
    # Every top-level name written in the file; used only for sanity checks in tests.
    # همه‌ی نام‌های سطح بالا؛ فقط برای آزمون.
    sites_by_kind: dict[str, int] = field(default_factory=dict)

    @property
    def label(self) -> str:
        """The name other records use for this file: its module, else its path."""
        return self.module or self.path

    @property
    def root(self) -> str:
        return self.entity.root if self.entity is not None else ""


def symbol_id(kind: str, path: str, qualname: str, ordinal: int) -> str:
    """`sym:` + 12 hex digits over language, kind, path, qualified name and ordinal."""
    material = "\x1f".join([LANGUAGE_PYTHON, kind, path, qualname, str(ordinal)])
    return "sym:" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


def chain_of(node: ast.AST) -> tuple[str, ...] | None:
    """`a.b.c` as `("a", "b", "c")`; `None` when the root is not a plain name."""
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        parts.reverse()
        return tuple(parts)
    return None


def _decorator_chain(node: ast.expr) -> tuple[str, ...] | None:
    """The chain of a decorator: `@a.b` and `@a.b(...)` both give `("a", "b")`."""
    if isinstance(node, ast.Call):
        return chain_of(node.func)
    return chain_of(node)


def _base_chain(node: ast.expr) -> tuple[str, ...] | None:
    """The chain of a base class: `Base[int]` gives the chain of `Base`."""
    if isinstance(node, ast.Subscript):
        return chain_of(node.value)
    return chain_of(node)


def _parameter_nodes(args: ast.arguments) -> list[ast.arg]:
    found = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    if args.vararg:
        found.append(args.vararg)
    if args.kwarg:
        found.append(args.kwarg)
    return found


def _global_names(body: Iterable[ast.stmt]) -> tuple[set[str], set[str]]:
    """The names declared `global` and `nonlocal` in a function body, not looking into
    nested functions and classes (they have their own declarations)."""
    glob: set[str] = set()
    nonloc: set[str] = set()
    stack = list(body)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Global):
            glob.update(node.names)
        elif isinstance(node, ast.Nonlocal):
            nonloc.update(node.names)
        elif isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
        ):
            continue
        else:
            for value in ast.iter_child_nodes(node):
                if isinstance(value, ast.stmt):
                    stack.append(value)
                elif isinstance(value, (ast.ExceptHandler, ast.match_case)):
                    stack.extend(value.body)
    return glob, nonloc


def _static_all(value: ast.expr | None) -> tuple[str, ...] | None:
    """The names of a static `__all__` (a list or tuple of string constants)."""
    if not isinstance(value, (ast.List, ast.Tuple)):
        return None
    names: list[str] = []
    for item in value.elts:
        if not (isinstance(item, ast.Constant) and isinstance(item.value, str)):
            return None
        names.append(item.value)
    return tuple(names)


class _Stop(Exception):
    """Raised inside the walk when the node cap is reached."""


class _FactsWalker:
    def __init__(
        self,
        path: str,
        module: str,
        entity: ModuleEntity | None,
        lines: list[str],
        tree: ast.Module,
    ) -> None:
        self.path = path
        self.module = module
        self.entity = entity
        self.lines = lines
        self.tree = tree
        self.scopes: list[Scope] = [Scope(0, "module", -1)]
        self.symbols: list[SymbolInfo] = []
        self.usages: list[Usage] = []
        self.patches: list[PatchTarget] = []
        self.main_blocks: list[MainBlock] = []
        self.sym_of: dict[int, SymbolInfo] = {}
        self.counters: dict[tuple[str, str], int] = {}
        self.nodes = 0
        self.dynamic = False
        self.limits: set[str] = set()
        self.context: list[str] = []
        self.owners: list[str] = [""]
        self.functions: list[SymbolInfo] = []
        self.dunder_all: tuple[str, ...] | None = None
        self._all_bindings = 0
        self.has_module_getattr = False
        self.sites: dict[str, int] = {}

    # --- small helpers -------------------------------------------------------------

    def location(self, node: ast.AST) -> SourceLocation:
        line = int(getattr(node, "lineno", 0) or 0)
        end_line = int(getattr(node, "end_lineno", None) or line)
        return SourceLocation(
            path=self.path,
            line=line,
            col=int(getattr(node, "col_offset", 0) or 0),
            end_line=end_line,
            end_col=int(getattr(node, "end_col_offset", 0) or 0),
        )

    def evidence(self, node: ast.AST) -> str:
        return evidence_of(self.lines, node)

    def tick(self) -> None:
        self.nodes += 1
        if self.nodes > MAX_NODES_PER_FILE:
            raise _Stop

    def new_scope(self, kind: str, parent: int) -> Scope:
        scope = Scope(len(self.scopes), kind, parent)
        self.scopes.append(scope)
        return scope

    def flags(self, *extra: str) -> tuple[str, ...]:
        found = set(extra)
        if "type_checking" in self.context:
            found.update({REL_FLAG_TYPE_ONLY, REL_FLAG_CONDITIONAL})
        if "conditional" in self.context:
            found.add(REL_FLAG_CONDITIONAL)
        if "function" in self.context:
            found.add(REL_FLAG_LAZY)
        if "annotation" in self.context:
            found.add(REL_FLAG_ANNOTATION)
        return tuple(sorted(found))

    def in_function(self, scope: Scope) -> bool:
        current = scope
        while current.parent >= 0:
            if current.kind == "function":
                return True
            current = self.scopes[current.parent]
        return False

    def module_scope(self) -> Scope:
        return self.scopes[0]

    def new_symbol(
        self,
        kind: str,
        name: str,
        qual_prefix: str,
        parent: str,
        scope: Scope,
        node: ast.AST,
        *,
        conditional: bool,
        decorators: tuple[str, ...] = (),
        bases: tuple[str, ...] = (),
        extensions: dict[str, str | int | bool] | None = None,
        dynamic: bool = False,
        content: tuple[ast.AST | None, ...] | None = None,
    ) -> SymbolInfo:
        qualname = f"{qual_prefix}{name}"
        key = (kind, qualname)
        ordinal = self.counters.get(key, 0)
        self.counters[key] = ordinal + 1
        flags: list[str] = []
        if self.in_function(scope):
            flags.append(SYM_FLAG_NESTED)
        if conditional:
            flags.append(SYM_FLAG_CONDITIONAL)
        if dynamic:
            flags.append(SYM_FLAG_DYNAMIC)
        symbol = Symbol(
            id=symbol_id(kind, self.path, qualname, ordinal),
            kind=kind,
            name=name,
            qualname=qualname,
            module=self.module,
            path=self.path,
            parent=parent,
            location=self.location(node),
            decorators=decorators,
            bases=bases,
            flags=tuple(flags),
            extensions=extensions or {},
            fingerprint=fingerprint(content if content is not None else (node,)),
        )
        info = SymbolInfo(symbol=symbol, scope=scope.id)
        self.symbols.append(info)
        self.sym_of[id(node)] = info
        return info

    # --- declaration pass: which names a scope binds -------------------------------

    def bind_other(self, scope: Scope, name: str, escaped: dict[str, set[str]]) -> None:
        """A binding this module does not follow. A `global` name binds in the module,
        a `nonlocal` name in the enclosing function."""
        if name in escaped.get("global", ()):
            self.module_scope().add(name, Binding(B_OTHER))
            return
        if name in escaped.get("nonlocal", ()):
            parent = self.scopes[scope.parent] if scope.parent >= 0 else scope
            parent.add(name, Binding(B_OTHER))
            return
        scope.add(name, Binding(B_OTHER))

    def bind_target(
        self, scope: Scope, target: ast.AST, escaped: dict[str, set[str]]
    ) -> None:
        if isinstance(target, ast.Name):
            self.bind_other(scope, target.id, escaped)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                self.bind_target(scope, item, escaped)
        elif isinstance(target, ast.Starred):
            self.bind_target(scope, target.value, escaped)

    def declare_block(
        self,
        statements: Iterable[ast.stmt],
        scope: Scope,
        conditional: bool,
        prefix: str,
        parent: str,
        escaped: dict[str, set[str]],
    ) -> None:
        for statement in statements:
            self.declare(statement, scope, conditional, prefix, parent, escaped)

    def declare(
        self,
        node: ast.stmt,
        scope: Scope,
        conditional: bool,
        prefix: str,
        parent: str,
        escaped: dict[str, set[str]],
    ) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self.declare_function(node, scope, conditional, prefix, parent, escaped)
        elif isinstance(node, ast.ClassDef):
            self.declare_class(node, scope, conditional, prefix, parent, escaped)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                self.declare_assignment(
                    target,
                    node.value,
                    scope,
                    conditional,
                    prefix,
                    parent,
                    escaped,
                    node,
                )
        elif isinstance(node, ast.AnnAssign):
            self.declare_assignment(
                node.target,
                node.value,
                scope,
                conditional,
                prefix,
                parent,
                escaped,
                node,
                annotated=True,
            )
        elif isinstance(node, ast.AugAssign):
            self.bind_target(scope, node.target, escaped)
            if (
                scope.kind == "module"
                and isinstance(node.target, ast.Name)
                and node.target.id == "__all__"
            ):
                self._all_bindings += 1
        elif isinstance(node, ast.Delete):
            for target in node.targets:
                self.bind_target(scope, target, escaped)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    scope.add(alias.asname, Binding(B_IMPORT, module=alias.name))
                else:
                    top = alias.name.split(".", 1)[0]
                    scope.add(top, Binding(B_IMPORT, module=top))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                if alias.name == "*":
                    scope.stars.append((module, node.level))
                    continue
                scope.add(
                    alias.asname or alias.name,
                    Binding(B_FROM, module=module, level=node.level, member=alias.name),
                )
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            self.bind_target(scope, node.target, escaped)
            self.declare_block(node.body, scope, True, prefix, parent, escaped)
            self.declare_block(node.orelse, scope, True, prefix, parent, escaped)
        elif isinstance(node, (ast.While, ast.If)):
            self.declare_block(node.body, scope, True, prefix, parent, escaped)
            self.declare_block(node.orelse, scope, True, prefix, parent, escaped)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    self.bind_target(scope, item.optional_vars, escaped)
            self.declare_block(node.body, scope, conditional, prefix, parent, escaped)
        elif isinstance(node, (ast.Try, ast.TryStar)):
            self.declare_block(node.body, scope, conditional, prefix, parent, escaped)
            for handler in node.handlers:
                if handler.name:
                    self.bind_other(scope, handler.name, escaped)
                self.declare_block(handler.body, scope, True, prefix, parent, escaped)
            self.declare_block(node.orelse, scope, True, prefix, parent, escaped)
            self.declare_block(
                node.finalbody, scope, conditional, prefix, parent, escaped
            )
        elif isinstance(node, ast.Match):
            for case in node.cases:
                for sub in ast.walk(case.pattern):
                    name = getattr(sub, "name", None) or getattr(sub, "rest", None)
                    if isinstance(
                        sub, (ast.MatchAs, ast.MatchStar, ast.MatchMapping)
                    ) and isinstance(name, str):
                        self.bind_other(scope, name, escaped)
                self.declare_block(case.body, scope, True, prefix, parent, escaped)

    def declare_assignment(
        self,
        target: ast.expr,
        value: ast.expr | None,
        scope: Scope,
        conditional: bool,
        prefix: str,
        parent: str,
        escaped: dict[str, set[str]],
        node: ast.stmt,
        *,
        annotated: bool = False,
    ) -> None:
        if not isinstance(target, ast.Name):
            self.bind_target(scope, target, escaped)
            return
        name = target.id
        if name in escaped.get("global", ()) or name in escaped.get("nonlocal", ()):
            self.bind_other(scope, name, escaped)
            return
        if scope.kind not in ("module", "class"):
            scope.add(name, Binding(B_OTHER))
            return
        if scope.kind == "module" and name == "__all__":
            self._all_bindings += 1
            self.dunder_all = _static_all(value)
        if (
            scope.kind == "module"
            and name == "TYPE_CHECKING"
            and isinstance(value, ast.Constant)
            and value.value is False
        ):
            scope.add(name, Binding(B_CONST_FALSE, member="TYPE_CHECKING"))
            return
        kind = SYM_CONSTANT if _CONSTANT_NAME.match(name) else SYM_VARIABLE
        alias = (
            _base_chain(value) if isinstance(value, (ast.Name, ast.Attribute)) else None
        )
        extensions: dict[str, str | int | bool] = {}
        if alias:
            extensions["alias_of"] = ".".join(alias)
        if annotated and value is None:
            extensions["declared_only"] = True
        info = self.new_symbol(
            kind,
            name,
            prefix,
            parent,
            scope,
            target,
            conditional=conditional,
            extensions=extensions,
            content=(
                node.annotation if isinstance(node, ast.AnnAssign) else None,
                value,
            ),
        )
        if isinstance(value, ast.Call):
            info.value_call = chain_of(value.func)
        if annotated and value is None:
            # `x: int` declares an attribute but binds nothing (a dataclass field).
            # `x: int` صفتی را اعلام می‌کند اما چیزی را مقید نمی‌کند.
            return
        scope.add(name, Binding(B_VAR, symbol=info.symbol.id, alias=alias or ()))

    def declare_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        scope: Scope,
        conditional: bool,
        prefix: str,
        parent: str,
        escaped: dict[str, set[str]],
    ) -> None:
        decorators = tuple(self.evidence(d) for d in node.decorator_list)
        accessor = False
        overload = False
        prop = False
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if isinstance(target, ast.Name):
                if target.id in _PROPERTY_DECORATORS:
                    prop = True
                if target.id == "overload":
                    overload = True
            elif isinstance(target, ast.Attribute):
                if target.attr in _PROPERTY_DECORATORS:
                    prop = True
                if target.attr == "overload":
                    overload = True
                if (
                    target.attr in _ACCESSOR_ATTRIBUTES
                    and isinstance(target.value, ast.Name)
                    and target.value.id == node.name
                ):
                    accessor = True
                    prop = True
        if scope.kind == "class":
            kind = SYM_PROPERTY if prop else SYM_METHOD
        else:
            kind = SYM_FUNCTION
        extensions: dict[str, str | int | bool] = {
            "is_async": isinstance(node, ast.AsyncFunctionDef),
            "has_star_args": node.args.vararg is not None
            or node.args.kwarg is not None,
        }
        if overload:
            extensions["overload"] = True
        dynamic = node.name in ("__getattr__", "__getattribute__")
        if dynamic:
            self.dynamic = True
            if scope.kind == "module":
                self.has_module_getattr = True
        info = self.new_symbol(
            kind,
            node.name,
            prefix,
            parent,
            scope,
            node,
            conditional=conditional,
            decorators=decorators,
            extensions=extensions,
            dynamic=dynamic,
        )
        info.accessor = accessor
        info.overload = overload
        info.decorator_chains = tuple(_decorator_chain(d) for d in node.decorator_list)
        if accessor or overload:
            return
        scope.add(node.name, Binding(B_DEF, symbol=info.symbol.id))

    def declare_class(
        self,
        node: ast.ClassDef,
        scope: Scope,
        conditional: bool,
        prefix: str,
        parent: str,
        escaped: dict[str, set[str]],
    ) -> None:
        decorators = tuple(self.evidence(d) for d in node.decorator_list)
        bases = tuple(self.evidence(b) for b in node.bases)
        metaclass = any(k.arg == "metaclass" for k in node.keywords)
        if metaclass:
            self.dynamic = True
        info = self.new_symbol(
            SYM_CLASS,
            node.name,
            prefix,
            parent,
            scope,
            node,
            conditional=conditional,
            decorators=decorators,
            bases=bases,
            extensions={"has_metaclass": metaclass},
            dynamic=metaclass,
        )
        info.metaclass = metaclass
        info.decorator_chains = tuple(_decorator_chain(d) for d in node.decorator_list)
        info.base_chains = tuple(_base_chain(b) for b in node.bases)
        scope.add(node.name, Binding(B_CLASS, symbol=info.symbol.id))

    # --- the walk: usage sites -----------------------------------------------------

    def run(self) -> None:
        module = self.module_scope()
        escaped: dict[str, set[str]] = {}
        self.declare_block(self.tree.body, module, False, "", "", escaped)
        if self._all_bindings != 1:
            self.dunder_all = None
        for statement in self.tree.body:
            self.statement(statement, module)

    def record(
        self,
        kind: str,
        chain: tuple[str, ...],
        scope: Scope,
        node: ast.AST,
        original_type: str,
        *,
        source: str | None = None,
        extra_flags: tuple[str, ...] = (),
        note: str = "",
    ) -> None:
        self.sites[kind] = self.sites.get(kind, 0) + 1
        self.usages.append(
            Usage(
                kind=kind,
                chain=chain,
                scope=scope.id,
                source=self.owners[-1] if source is None else source,
                location=self.location(node),
                evidence=self.evidence(node),
                flags=self.flags(*extra_flags),
                original_type=original_type,
                note=note,
            )
        )

    def block(
        self, statements: Iterable[ast.stmt], scope: Scope, marker: str | None
    ) -> None:
        if marker is not None:
            self.context.append(marker)
        for statement in statements:
            self.statement(statement, scope)
        if marker is not None:
            self.context.pop()

    def is_type_checking(self, test: ast.expr, scope: Scope) -> str:
        """`positive` for the typing sentinel, `negative` for its `not`, else `none`."""
        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            return (
                "negative"
                if self.is_type_checking(test.operand, scope) == "positive"
                else "none"
            )
        if isinstance(test, ast.Name):
            found = self.lookup_kind(test.id, scope)
            if found is not None and (
                found.kind == B_CONST_FALSE
                or (
                    found.kind == B_FROM
                    and found.member == "TYPE_CHECKING"
                    and found.module in ("typing", "typing_extensions")
                    and not found.level
                )
            ):
                return "positive"
        if (
            isinstance(test, ast.Attribute)
            and test.attr == "TYPE_CHECKING"
            and isinstance(test.value, ast.Name)
        ):
            found = self.lookup_kind(test.value.id, scope)
            if (
                found is not None
                and found.kind == B_IMPORT
                and found.module in ("typing", "typing_extensions")
            ):
                return "positive"
        return "none"

    def lookup_kind(self, name: str, scope: Scope) -> Binding | None:
        """The single binding of `name` visible from `scope`, or `None` when it is
        unbound or bound in more than one way (the same lexical rules as resolution)."""
        current: Scope | None = scope
        innermost = scope
        while current is not None:
            if current.kind != "class" or current is innermost:
                found = current.bindings.get(name)
                if found:
                    return found[0] if len(found) == 1 else None
            current = self.scopes[current.parent] if current.parent >= 0 else None
        return None

    def statement(self, node: ast.stmt, scope: Scope) -> None:
        self.tick()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self.function(node, scope)
        elif isinstance(node, ast.ClassDef):
            self.klass(node, scope)
        elif isinstance(node, ast.If):
            self.expression(node.test, scope)
            if scope.kind == "module" and self.is_main_test(node.test, scope):
                self.main_blocks.append(
                    MainBlock(self.location(node), self.evidence(node.test))
                )
            kind = self.is_type_checking(node.test, scope)
            self.block(
                node.body,
                scope,
                "type_checking" if kind == "positive" else "conditional",
            )
            self.block(
                node.orelse,
                scope,
                "type_checking" if kind == "negative" else "conditional",
            )
        elif isinstance(node, (ast.Try, ast.TryStar)):
            self.block(node.body, scope, None)
            for handler in node.handlers:
                if handler.type is not None:
                    self.expression(handler.type, scope)
                self.block(handler.body, scope, "conditional")
            self.block(node.orelse, scope, "conditional")
            self.block(node.finalbody, scope, None)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            self.expression(node.iter, scope)
            self.targets(node.target, scope)
            self.block(node.body, scope, "conditional")
            self.block(node.orelse, scope, "conditional")
        elif isinstance(node, ast.While):
            self.expression(node.test, scope)
            self.block(node.body, scope, "conditional")
            self.block(node.orelse, scope, "conditional")
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                self.expression(item.context_expr, scope)
                if item.optional_vars is not None:
                    self.targets(item.optional_vars, scope)
            self.block(node.body, scope, None)
        elif isinstance(node, ast.Match):
            self.expression(node.subject, scope)
            for case in node.cases:
                self.context.append("conditional")
                if case.guard is not None:
                    self.expression(case.guard, scope)
                self.block(case.body, scope, None)
                self.context.pop()
        elif isinstance(node, ast.Assign):
            self.expression(node.value, scope)
            for target in node.targets:
                self.targets(target, scope)
        elif isinstance(node, ast.AnnAssign):
            self.annotation(node.annotation, scope)
            if node.value is not None:
                self.expression(node.value, scope)
            self.targets(node.target, scope)
        elif isinstance(node, ast.AugAssign):
            self.expression(node.value, scope)
            self.targets(node.target, scope)
        elif isinstance(node, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal)):
            return
        else:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.stmt):
                    self.statement(child, scope)
                elif isinstance(child, ast.expr):
                    self.expression(child, scope)

    def is_main_test(self, test: ast.expr, scope: Scope) -> bool:
        """`__name__ == "__main__"` in either order, with `__name__` not rebound."""
        if not (
            isinstance(test, ast.Compare)
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Eq)
            and len(test.comparators) == 1
        ):
            return False
        sides = (test.left, test.comparators[0])
        names = [s for s in sides if isinstance(s, ast.Name) and s.id == "__name__"]
        consts = [
            s for s in sides if isinstance(s, ast.Constant) and s.value == "__main__"
        ]
        return (
            len(names) == 1
            and len(consts) == 1
            and "__name__" not in self.module_scope().bindings
        )

    def targets(self, target: ast.AST, scope: Scope) -> None:
        """Assignment targets: a name binds, an attribute may patch, a subscript loads."""
        if isinstance(target, ast.Attribute):
            chain = chain_of(target.value)
            if chain is not None:
                self.patches.append(
                    PatchTarget(chain, target.attr, scope.id, self.location(target))
                )
                self.record(
                    U_REFERENCE,
                    chain,
                    scope,
                    target.value,
                    REL_ORIG_NAME if len(chain) == 1 else REL_ORIG_ATTRIBUTE,
                )
            else:
                self.expression(target.value, scope)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                self.targets(item, scope)
        elif isinstance(target, ast.Starred):
            self.targets(target.value, scope)
        elif isinstance(target, ast.Subscript):
            self.expression(target.value, scope)
            self.expression(target.slice, scope)

    def annotation(self, node: ast.expr | None, scope: Scope) -> None:
        if node is None:
            return
        self.context.append("annotation")
        self.expression(node, scope)
        self.context.pop()

    # --- definitions -----------------------------------------------------------------

    def function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, scope: Scope
    ) -> None:
        info = self.sym_of[id(node)]
        symbol = info.symbol
        for decorator in node.decorator_list:
            chain = _decorator_chain(decorator)
            self.record(
                U_DECORATOR,
                chain or (),
                scope,
                decorator,
                REL_ORIG_DECORATOR,
                source=symbol.id,
            )
            if isinstance(decorator, ast.Call):
                self.arguments_of_call(decorator, scope)
        args = node.args
        for default in [*args.defaults, *args.kw_defaults]:
            if default is not None:
                self.expression(default, scope)
        for parameter in _parameter_nodes(args):
            if parameter.annotation is not None:
                self.owners.append(symbol.id)
                self.annotation(parameter.annotation, scope)
                self.owners.pop()
        if node.returns is not None:
            self.owners.append(symbol.id)
            self.annotation(node.returns, scope)
            self.owners.pop()
        own = self.new_scope("function", scope.id)
        info.own_scope = own.id
        escaped_global, escaped_nonlocal = _global_names(node.body)
        escaped = {"global": escaped_global, "nonlocal": escaped_nonlocal}
        names = _parameter_nodes(args)
        self_name = ""
        self_class = ""
        parent_info = self.class_info_of(scope)
        if parent_info is not None and not self.has_decorator(node, "staticmethod"):
            first = (*args.posonlyargs, *args.args)
            if first:
                self_name = first[0].arg
                self_class = parent_info.symbol.id
        for parameter in names:
            if parameter.arg == self_name and self_class:
                own.add(
                    parameter.arg,
                    Binding(
                        B_SELF,
                        self_class=self_class,
                        member="cls"
                        if self.has_decorator(node, "classmethod")
                        or node.name in _IMPLICIT_CLASSMETHODS
                        else "self",
                    ),
                )
            else:
                own.add(parameter.arg, Binding(B_OTHER))
        self.declare_block(
            node.body, own, False, f"{symbol.qualname}.<locals>.", symbol.id, escaped
        )
        self.owners.append(symbol.id)
        self.functions.append(info)
        self.context.append("function")
        for statement in node.body:
            self.statement(statement, own)
        self.context.pop()
        self.functions.pop()
        self.owners.pop()

    @staticmethod
    def has_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> bool:
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if isinstance(target, ast.Name) and target.id == name:
                return True
            if isinstance(target, ast.Attribute) and target.attr == name:
                return True
        return False

    def class_info_of(self, scope: Scope) -> SymbolInfo | None:
        """The class whose body is `scope`, when it is one."""
        if scope.kind != "class":
            return None
        for info in reversed(self.symbols):
            if info.own_scope == scope.id:
                return info
        return None

    def klass(self, node: ast.ClassDef, scope: Scope) -> None:
        info = self.sym_of[id(node)]
        symbol = info.symbol
        for decorator in node.decorator_list:
            chain = _decorator_chain(decorator)
            self.record(
                U_DECORATOR,
                chain or (),
                scope,
                decorator,
                REL_ORIG_DECORATOR,
                source=symbol.id,
            )
            if isinstance(decorator, ast.Call):
                self.arguments_of_call(decorator, scope)
        for base in node.bases:
            chain = _base_chain(base)
            self.record(
                U_BASE, chain or (), scope, base, REL_ORIG_BASE, source=symbol.id
            )
            if isinstance(base, ast.Subscript):
                self.expression(base.slice, scope)
            elif chain is None:
                self.expression(base, scope)
        for keyword in node.keywords:
            self.expression(keyword.value, scope)
        own = self.new_scope("class", scope.id)
        info.own_scope = own.id
        self.declare_block(node.body, own, False, f"{symbol.qualname}.", symbol.id, {})
        self.owners.append(symbol.id)
        for statement in node.body:
            self.statement(statement, own)
        self.owners.pop()

    # --- expressions -------------------------------------------------------------------

    def arguments_of_call(self, node: ast.Call, scope: Scope) -> None:
        for argument in node.args:
            self.expression(argument, scope)
        for keyword in node.keywords:
            self.expression(keyword.value, scope)

    def expression(self, node: ast.AST | None, scope: Scope) -> None:
        if node is None:
            return
        self.tick()
        if isinstance(node, ast.Call):
            self.call(node, scope)
        elif isinstance(node, (ast.Name, ast.Attribute)):
            chain = chain_of(node)
            if chain is not None and isinstance(
                getattr(node, "ctx", ast.Load()), ast.Load
            ):
                self.record(
                    U_REFERENCE,
                    chain,
                    scope,
                    node,
                    REL_ORIG_NAME if len(chain) == 1 else REL_ORIG_ATTRIBUTE,
                )
            elif isinstance(node, ast.Attribute):
                self.expression(node.value, scope)
        elif isinstance(node, ast.Subscript):
            self.expression(node.value, scope)
            self.expression(node.slice, scope)
        elif isinstance(node, ast.NamedExpr):
            # `:=` binds in the nearest function or module scope, when it is reached.
            # `:=` در نزدیک‌ترین scope تابع یا ماژول، هنگام رسیدن، مقید می‌کند.
            target = scope
            while target.kind == "comprehension" and target.parent >= 0:
                target = self.scopes[target.parent]
            if isinstance(node.target, ast.Name):
                target.add(node.target.id, Binding(B_OTHER))
            self.expression(node.value, scope)
        elif isinstance(node, ast.Lambda):
            self.lambda_(node, scope)
        elif isinstance(
            node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
        ):
            self.comprehension(node, scope)
        elif isinstance(node, ast.BoolOp):
            self.expression(node.values[0], scope)
            self.context.append("conditional")
            for value in node.values[1:]:
                self.expression(value, scope)
            self.context.pop()
        elif isinstance(node, ast.IfExp):
            self.expression(node.test, scope)
            self.context.append("conditional")
            self.expression(node.body, scope)
            self.expression(node.orelse, scope)
            self.context.pop()
        elif isinstance(node, (ast.Yield, ast.YieldFrom)):
            current = self.functions[-1] if self.functions else None
            if current is not None:
                self.mark_generator(current)
            for child in ast.iter_child_nodes(node):
                self.expression(child, scope)
        elif isinstance(node, ast.Constant):
            return
        else:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.expr):
                    self.expression(child, scope)
                elif isinstance(child, ast.keyword):
                    self.expression(child.value, scope)

    def mark_generator(self, info: SymbolInfo) -> None:
        symbol = info.symbol
        extensions = dict(symbol.extensions)
        extensions["is_generator"] = True
        info.symbol = replace(symbol, extensions=extensions)

    def call(self, node: ast.Call, scope: Scope) -> None:
        func = node.func
        chain = chain_of(func)
        if chain is not None and len(chain) == 1:
            name = chain[0]
            if name in _DYNAMIC_ATTRIBUTE_FUNCTIONS and self.is_builtin_name(
                name, scope
            ):
                self.dynamic_attribute(node, scope, name)
                self.arguments_of_call(node, scope)
                return
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Call)
            and isinstance(func.value.func, ast.Name)
            and func.value.func.id == "super"
            and self.is_builtin_name("super", scope)
        ):
            # `super().name(...)`: looked up in the bases of the enclosing class.
            # `super().name(...)`: در پایه‌های کلاس دربرگیرنده جست‌وجو می‌شود.
            self.record(U_CALL, (SUPER_ROOT, func.attr), scope, func, REL_ORIG_CALL)
            self.arguments_of_call(func.value, scope)
        elif chain is not None:
            self.record(U_CALL, chain, scope, func, REL_ORIG_CALL)
        else:
            self.record(U_CALL, (), scope, func, REL_ORIG_CALL)
            self.expression(func, scope)
        self.arguments_of_call(node, scope)

    def is_builtin_name(self, name: str, scope: Scope) -> bool:
        current: Scope | None = scope
        while current is not None:
            if (
                current.kind != "class" or current is scope
            ) and name in current.bindings:
                return False
            current = self.scopes[current.parent] if current.parent >= 0 else None
        return True

    def dynamic_attribute(self, node: ast.Call, scope: Scope, name: str) -> None:
        """`getattr`, `setattr`, `delattr`: a constant attribute name is one more thing
        the file does with the object (counted, not followed); a non-constant name is a
        dynamic construct (stored as `unknown`)."""
        attribute = node.args[1] if len(node.args) > 1 else None
        constant = isinstance(attribute, ast.Constant) and isinstance(
            attribute.value, str
        )
        if constant and name == "setattr" and node.args:
            chain = chain_of(node.args[0])
            if chain is not None and isinstance(attribute, ast.Constant):
                self.patches.append(
                    PatchTarget(
                        chain, str(attribute.value), scope.id, self.location(node)
                    )
                )
        if constant:
            self.sites["attribute_by_constant_name"] = (
                self.sites.get("attribute_by_constant_name", 0) + 1
            )
            return
        self.dynamic = True
        self.record(
            U_DYNAMIC,
            (name,),
            scope,
            node,
            REL_ORIG_DYNAMIC,
            note=f"{name}() with a name that is not a string constant",
        )

    def lambda_(self, node: ast.Lambda, scope: Scope) -> None:
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            if default is not None:
                self.expression(default, scope)
        own = self.new_scope("function", scope.id)
        for parameter in _parameter_nodes(node.args):
            own.add(parameter.arg, Binding(B_OTHER))
        self.context.append("function")
        self.expression(node.body, own)
        self.context.pop()

    def comprehension(
        self,
        node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp,
        scope: Scope,
    ) -> None:
        generators = node.generators
        if generators:
            self.expression(generators[0].iter, scope)
        own = self.new_scope("comprehension", scope.id)
        for generator in generators:
            self.bind_target(own, generator.target, {})
        self.context.append("conditional")
        for index, generator in enumerate(generators):
            if index:
                self.expression(generator.iter, own)
            for condition in generator.ifs:
                self.expression(condition, own)
        if isinstance(node, ast.DictComp):
            self.expression(node.key, own)
            self.expression(node.value, own)
        else:
            self.expression(node.elt, own)
        self.context.pop()


def extract_facts(
    path: str,
    data: bytes,
    tree: ast.Module,
    module: str,
    entity: ModuleEntity | None,
) -> FileFacts:
    """Read the symbols and usage sites of an already parsed file.

    Guards are the ones of the import extraction: the node cap and the interpreter's
    recursion and memory limits stop the walk, keep what was read, and are reported in
    `limits` (the caller turns that into `partial`)."""
    source = data.decode("utf-8-sig", errors="replace")
    walker = _FactsWalker(path, module, entity, split_lines(source), tree)
    try:
        walker.run()
    except _Stop:
        walker.limits.add(LIM_NODE_CAP)
    except RecursionError:
        walker.limits.add(LIM_RECURSION)
    except MemoryError:
        walker.limits.add(LIM_RESOURCE)
    if walker.dynamic:
        walker.limits.add(LIM_DYNAMIC)
    return FileFacts(
        path=path,
        module=module,
        entity=entity,
        scopes=walker.scopes,
        symbols=walker.symbols,
        usages=walker.usages,
        patches=walker.patches,
        main_blocks=walker.main_blocks,
        dunder_all=walker.dunder_all,
        has_module_getattr=walker.has_module_getattr,
        limits=walker.limits,
        dynamic=walker.dynamic,
        sites_by_kind=dict(walker.sites),
    )
