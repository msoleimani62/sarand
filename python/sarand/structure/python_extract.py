"""Import extraction from one Python file with `ast` (R14-A, plan section 9).

Reads the file, parses it, and records every import statement and every call that
imports by name, with its location, a bounded copy of its statement as evidence, and
the context it sits in. It resolves nothing: that is `imports.py`. The file is never
executed.

Names are bound **by scope**, not by spelling. A small binding table per scope (module,
class, function, comprehension) records only the few names this module cares about:
`TYPE_CHECKING`, the `importlib` and `typing`/`builtins` modules (under any alias),
`importlib.import_module`, `__import__` and the `ImportError` family. A name that is
rebound to anything else, or bound two different ways in one scope, is *ambiguous* and
is never recognised. Assignment expressions (`:=`) and the names a `from x import *`
brings in are not tracked.

Context of an import (flags):

- `conditional`: it may not run when its scope runs: the branches of `if`, a `try` body
  that an `ImportError` handler guards, every `except` handler, `try ... else`, the body
  of `for`/`while` and their `else`, `match` cases, the right side of `and`/`or`, the
  branches of a conditional expression, comprehension bodies. `finally` and `with`
  are not conditional.
- `type_only`: under `if TYPE_CHECKING:` (the `typing`/`typing_extensions` sentinel, or
  the module-level `TYPE_CHECKING = False` idiom); also `conditional`.
- `lazy`: inside a function or lambda body (it runs when the function is called).

A file that does not parse is `failed` with the error location; a file that hits a guard
(recursion depth, node cap, memory) is `partial` and keeps every import found before
the guard (a recursion failure loses only the statement it happened in). Nothing is
silently dropped. Only the failures named in `extract_imports` are handled; any other
exception is a bug and propagates.

استخراج importها با ast، با جدول انقیاد وابسته به scope؛ کد مخزن هرگز اجرا نمی‌شود.
"""

from __future__ import annotations

import ast
import hashlib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from sarand.structure.model import (
    COMPLETENESS_FAILED,
    COMPLETENESS_FULL,
    COMPLETENESS_PARTIAL,
    FLAG_CONDITIONAL,
    FLAG_LAZY,
    FLAG_RELATIVE,
    FLAG_STAR,
    FLAG_TYPE_ONLY,
    LIM_DYNAMIC,
    LIM_ENCODING,
    LIM_NODE_CAP,
    LIM_RECURSION,
    LIM_RESOURCE,
    LIM_SYNTAX_ERROR,
    ORIGINAL_DYNAMIC_CALL,
    ORIGINAL_FROM_IMPORT,
    ORIGINAL_IMPORT,
    PARSER_PYTHON_AST,
    Provenance,
    SourceLocation,
)

# A guard against pathological input: more nodes than this stops the walk.
# محافظ در برابر ورودی بیش‌ازحد بزرگ.
MAX_NODES_PER_FILE = 1_000_000

# The evidence of an import is its source lines joined by single spaces, cut here.
# شاهد import: خطوط دستور با فاصله‌ی تکی، با سقف طول.
MAX_EVIDENCE_CHARS = 240

# --- canonical names the binding table can hold ------------------------------------
_OTHER = ""  # bound to something unsupported, or bound in conflicting ways
_TYPE_CHECKING = "typing.TYPE_CHECKING"
_MOD_IMPORTLIB = "module:importlib"
_MOD_TYPING = "module:typing"
_MOD_BUILTINS = "module:builtins"
_IMPORT_MODULE = "importlib.import_module"
_IMPORTLIB_IMPORT = "importlib.__import__"
_BUILTIN_IMPORT = "builtins.__import__"
_IMPORT_ERROR = "builtins.ImportError"
_MODULE_NOT_FOUND = "builtins.ModuleNotFoundError"
_EXCEPTION = "builtins.Exception"
_BASE_EXCEPTION = "builtins.BaseException"
_CATCHES_IMPORT_ERROR = frozenset(
    {_IMPORT_ERROR, _MODULE_NOT_FOUND, _EXCEPTION, _BASE_EXCEPTION}
)

_TRACKED_MODULES = {
    "importlib": _MOD_IMPORTLIB,
    "typing": _MOD_TYPING,
    "typing_extensions": _MOD_TYPING,
    "builtins": _MOD_BUILTINS,
}
_FROM_MEMBERS = {
    ("typing", "TYPE_CHECKING"): _TYPE_CHECKING,
    ("typing_extensions", "TYPE_CHECKING"): _TYPE_CHECKING,
    ("importlib", "import_module"): _IMPORT_MODULE,
    ("importlib", "__import__"): _IMPORTLIB_IMPORT,
    ("builtins", "__import__"): _BUILTIN_IMPORT,
    ("builtins", "ImportError"): _IMPORT_ERROR,
    ("builtins", "ModuleNotFoundError"): _MODULE_NOT_FOUND,
    ("builtins", "Exception"): _EXCEPTION,
    ("builtins", "BaseException"): _BASE_EXCEPTION,
}
_BUILTIN_NAMES = {
    "__import__": _BUILTIN_IMPORT,
    "ImportError": _IMPORT_ERROR,
    "ModuleNotFoundError": _MODULE_NOT_FOUND,
    "Exception": _EXCEPTION,
    "BaseException": _BASE_EXCEPTION,
}


@dataclass(frozen=True)
class ImportRecord:
    """One import as written. `module` is the dotted name after the dots (empty for
    `from . import x`), `level` the number of leading dots, `names` the imported
    names of a `from` import (`*` for a star import).

    For a call that imports by name: `literal` is false when the module name is not a
    string constant; `package` is the `package=` argument of `importlib.import_module`
    (`package_literal` false when it is not a string constant); `relative_anchor_known`
    is false for `__import__(..., level=n)` whose `globals` argument is not the plain
    `globals()` call, so the package the level refers to is not known."""

    original_type: str
    module: str
    level: int
    names: tuple[str, ...]
    flags: tuple[str, ...]
    location: SourceLocation
    evidence: str
    literal: bool = True
    package: str | None = None
    package_literal: bool = True
    relative_anchor_known: bool = True


@dataclass(frozen=True)
class ExtractResult:
    sha256: str
    size: int
    provenance: Provenance
    imports: tuple[ImportRecord, ...] = ()
    error: SourceLocation | None = None
    extensions: dict[str, str | int | bool] = field(default_factory=dict)
    # The parsed tree, kept only so the caller can read symbols from the same parse
    # without parsing twice; it is not part of the result's identity.
    # درخت تجزیه‌شده؛ برای جلوگیری از تجزیه‌ی دوباره، بخشی از هویت نتیجه نیست.
    tree: ast.Module | None = field(default=None, repr=False, compare=False)


def _provenance(
    version: str,
    completeness: str,
    limitations: set[str],
    rules: str = "",
) -> Provenance:
    return Provenance(
        parser=PARSER_PYTHON_AST,
        parser_version=version,
        rules=rules,
        completeness=completeness,
        limitations=tuple(sorted(limitations)),
    )


def split_lines(source: str) -> list[str]:
    """Lines numbered the way the Python tokenizer numbers them: `\\n`, `\\r\\n` and
    `\\r` end a line (`str.splitlines` would also split on form feeds and others)."""
    return re.split(r"\r\n|\r|\n", source)


def byte_column(lines: Sequence[str], line: int, char_offset: int | None) -> int:
    """A 1-based **character** offset on `line` (what a `SyntaxError` reports) as the
    0-based UTF-8 **byte** offset the rest of the model uses."""
    if not char_offset or char_offset < 1 or not 1 <= line <= len(lines):
        return 0
    return len(lines[line - 1][: char_offset - 1].encode("utf-8", "replace"))


def evidence_of(lines: Sequence[str], node: ast.AST) -> str:
    """The node's own text: from its start column to its end column (a trailing
    comment is not part of it), lines joined by single spaces, bounded by
    `MAX_EVIDENCE_CHARS`. Columns are UTF-8 byte offsets, as `ast` gives them.

    متن خود گره: از ستون شروع تا ستون پایان، خطوط با فاصله‌ی تکی، با سقف طول."""
    start = int(getattr(node, "lineno", 0) or 0)
    end = int(getattr(node, "end_lineno", None) or start)
    if not 1 <= start <= len(lines):
        return ""
    end = min(end, len(lines))
    col = int(getattr(node, "col_offset", 0) or 0)
    end_col = getattr(node, "end_col_offset", None)
    raw = [line.encode("utf-8") for line in lines[start - 1 : end]]
    if end_col is not None:
        raw[-1] = raw[-1][: int(end_col)]
    raw[0] = raw[0][col:]
    parts = [p.decode("utf-8", "replace").strip() for p in raw]
    text = " ".join(p for p in parts if p)
    if len(text) <= MAX_EVIDENCE_CHARS:
        return text
    return text[: MAX_EVIDENCE_CHARS - 3] + "..."


# --- scope tables ---------------------------------------------------------------------


def _bind(table: dict[str, str], name: str, canonical: str) -> None:
    if name in table and table[name] != canonical:
        table[name] = _OTHER
    else:
        table[name] = canonical


def _bind_target(table: dict[str, str], target: ast.AST) -> None:
    if isinstance(target, ast.Name):
        _bind(table, target.id, _OTHER)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for item in target.elts:
            _bind_target(table, item)
    elif isinstance(target, ast.Starred):
        _bind_target(table, target.value)


def _assignment_canonical(
    target: ast.expr, value: ast.expr | None, table: dict[str, str]
) -> str:
    """What a plain `Name = value` binds, for the idioms the table understands:
    `TYPE_CHECKING = False` and an alias of an unshadowed `ImportError`-family name."""
    if not isinstance(target, ast.Name) or value is None:
        return _OTHER
    if (
        target.id == "TYPE_CHECKING"
        and isinstance(value, ast.Constant)
        and value.value is False
    ):
        return _TYPE_CHECKING
    if (
        isinstance(value, ast.Name)
        and value.id in _BUILTIN_NAMES
        and value.id not in table
    ):
        return _BUILTIN_NAMES[value.id]
    return _OTHER


def _pattern_names(pattern: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(pattern):
        name = getattr(node, "name", None) or getattr(node, "rest", None)
        if isinstance(node, (ast.MatchAs, ast.MatchStar, ast.MatchMapping)) and name:
            found.append(name)
    return found


def _collect_statement(
    node: ast.stmt, table: dict[str, str], escaped: set[str]
) -> None:
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.asname:
                module = (
                    _TRACKED_MODULES.get(alias.name) if "." not in alias.name else None
                )
                _bind(table, alias.asname, module or _OTHER)
            else:
                top = alias.name.split(".", 1)[0]
                _bind(table, top, _TRACKED_MODULES.get(top, _OTHER))
    elif isinstance(node, ast.ImportFrom):
        for alias in node.names:
            if alias.name == "*":
                continue
            canonical = (
                _FROM_MEMBERS.get((node.module or "", alias.name))
                if not node.level
                else None
            )
            _bind(table, alias.asname or alias.name, canonical or _OTHER)
    elif isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                _bind(
                    table, target.id, _assignment_canonical(target, node.value, table)
                )
            else:
                _bind_target(table, target)
    elif isinstance(node, ast.AnnAssign):
        if isinstance(node.target, ast.Name):
            _bind(
                table,
                node.target.id,
                _assignment_canonical(node.target, node.value, table),
            )
        else:
            _bind_target(table, node.target)
    elif isinstance(node, ast.AugAssign):
        _bind_target(table, node.target)
    elif isinstance(node, (ast.For, ast.AsyncFor)):
        _bind_target(table, node.target)
        _collect(node.body, table, escaped)
        _collect(node.orelse, table, escaped)
    elif isinstance(node, (ast.While, ast.If)):
        _collect(node.body, table, escaped)
        _collect(node.orelse, table, escaped)
    elif isinstance(node, (ast.With, ast.AsyncWith)):
        for item in node.items:
            if item.optional_vars is not None:
                _bind_target(table, item.optional_vars)
        _collect(node.body, table, escaped)
    elif isinstance(node, (ast.Try, ast.TryStar)):
        _collect(node.body, table, escaped)
        for handler in node.handlers:
            if handler.name:
                _bind(table, handler.name, _OTHER)
            _collect(handler.body, table, escaped)
        _collect(node.orelse, table, escaped)
        _collect(node.finalbody, table, escaped)
    elif isinstance(node, ast.Match):
        for case in node.cases:
            for name in _pattern_names(case.pattern):
                _bind(table, name, _OTHER)
            _collect(case.body, table, escaped)
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        _bind(table, node.name, _OTHER)
    elif isinstance(node, (ast.Global, ast.Nonlocal)):
        escaped.update(node.names)


def _collect(
    body: Iterable[ast.stmt], table: dict[str, str], escaped: set[str]
) -> None:
    for node in body:
        _collect_statement(node, table, escaped)


def _parameter_names(args: ast.arguments) -> list[str]:
    names = [a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)]
    if args.vararg:
        names.append(args.vararg.arg)
    if args.kwarg:
        names.append(args.kwarg.arg)
    return names


def _target_names(target: ast.AST) -> list[str]:
    table: dict[str, str] = {}
    _bind_target(table, target)
    return list(table)


@dataclass
class _Scope:
    kind: str  # "module", "class", "function", "comprehension"
    names: dict[str, str]


class _Walker:
    """A recursive walk that tracks scopes and the context of each import."""

    def __init__(self, path: str, source: str, tree: ast.Module) -> None:
        self.path = path
        self.source_lines = split_lines(source)
        self.records: list[ImportRecord] = []
        self.nodes = 0
        self.capped = False
        self.dynamic = False
        self.recursion_hit = False
        # context stack entries: "conditional", "type_checking", "function".
        # پشته‌ی زمینه: شرطی بودن، type-checking و داخل تابع بودن.
        self.context: list[str] = []
        table: dict[str, str] = {}
        escaped: set[str] = set()
        try:
            _collect(tree.body, table, escaped)
        except RecursionError:
            self.recursion_hit = True
        # A name declared `global` anywhere is assigned from a function we do not
        # follow: it is ambiguous at module level.
        # نامی که در جایی global اعلام شده در سطح ماژول مبهم است.
        for node in ast.walk(tree):
            if isinstance(node, ast.Global):
                for name in node.names:
                    table[name] = _OTHER
        self.scopes: list[_Scope] = [_Scope("module", table)]

    # --- scopes ---------------------------------------------------------------------

    def lookup(self, name: str) -> str | None:
        """The canonical thing `name` is bound to here, or `None` when it is bound to
        something unsupported. An unbound builtin name resolves to the builtin."""
        innermost = self.scopes[-1]
        for scope in reversed(self.scopes):
            if scope.kind == "class" and scope is not innermost:
                continue
            if name in scope.names:
                return scope.names[name] or None
        return _BUILTIN_NAMES.get(name)

    def unshadowed(self, name: str) -> bool:
        innermost = self.scopes[-1]
        return not any(
            name in scope.names
            for scope in self.scopes
            if not (scope.kind == "class" and scope is not innermost)
        )

    def reset(self) -> None:
        del self.scopes[1:]
        self.context.clear()

    # --- locations --------------------------------------------------------------------

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
        """The statement's own text (see `evidence_of`)."""
        return evidence_of(self.source_lines, node)

    def flags(self, extra: tuple[str, ...] = ()) -> tuple[str, ...]:
        found = set(extra)
        if "type_checking" in self.context:
            found.update({FLAG_TYPE_ONLY, FLAG_CONDITIONAL})
        if "conditional" in self.context:
            found.add(FLAG_CONDITIONAL)
        if "function" in self.context:
            found.add(FLAG_LAZY)
        return tuple(sorted(found))

    # --- recognising the supported forms ---------------------------------------------

    def _type_checking_kind(self, test: ast.expr) -> str:
        """`positive` for the sentinel, `negative` for `not` of it, else `none`."""
        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            return (
                "negative"
                if self._type_checking_kind(test.operand) == "positive"
                else "none"
            )
        if isinstance(test, ast.Name):
            return "positive" if self.lookup(test.id) == _TYPE_CHECKING else "none"
        if (
            isinstance(test, ast.Attribute)
            and test.attr == "TYPE_CHECKING"
            and isinstance(test.value, ast.Name)
            and self.lookup(test.value.id) == _MOD_TYPING
        ):
            return "positive"
        return "none"

    def _catches_import_error(self, expr: ast.expr | None) -> bool:
        if expr is None:  # a bare `except:` catches it
            return True
        if isinstance(expr, ast.Tuple):
            return any(self._catches_import_error(item) for item in expr.elts)
        if isinstance(expr, ast.Name):
            return self.lookup(expr.id) in _CATCHES_IMPORT_ERROR
        if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
            return (
                self.lookup(expr.value.id) == _MOD_BUILTINS
                and _BUILTIN_NAMES.get(expr.attr) in _CATCHES_IMPORT_ERROR
            )
        return False

    def _import_call_kind(self, func: ast.expr) -> str:
        """`dunder_import`, `import_module` or empty."""
        if isinstance(func, ast.Name):
            canonical = self.lookup(func.id)
            if canonical in (_BUILTIN_IMPORT, _IMPORTLIB_IMPORT):
                return "dunder_import"
            if canonical == _IMPORT_MODULE:
                return "import_module"
        elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            module = self.lookup(func.value.id)
            if module == _MOD_IMPORTLIB and func.attr == "import_module":
                return "import_module"
            if module == _MOD_IMPORTLIB and func.attr == "__import__":
                return "dunder_import"
            if module == _MOD_BUILTINS and func.attr == "__import__":
                return "dunder_import"
        return ""

    # --- the walk ---------------------------------------------------------------------

    def visit(self, node: ast.AST) -> None:
        self.nodes += 1
        if self.nodes > MAX_NODES_PER_FILE:
            self.capped = True
            return
        if isinstance(node, ast.Import):
            for alias in node.names:
                self.records.append(
                    ImportRecord(
                        ORIGINAL_IMPORT,
                        alias.name,
                        0,
                        (),
                        self.flags(),
                        self.location(node),
                        self.evidence(node),
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            names = tuple(a.name for a in node.names)
            extra = [FLAG_RELATIVE] if node.level else []
            if "*" in names:
                extra.append(FLAG_STAR)
            self.records.append(
                ImportRecord(
                    ORIGINAL_FROM_IMPORT,
                    node.module or "",
                    node.level,
                    names,
                    self.flags(tuple(extra)),
                    self.location(node),
                    self.evidence(node),
                )
            )
        elif isinstance(node, ast.Call):
            self.call(node)
        self.descend(node)

    @staticmethod
    def _argument(call: ast.Call, index: int, keyword: str) -> ast.expr | None:
        if len(call.args) > index and not isinstance(call.args[index], ast.Starred):
            return call.args[index]
        for item in call.keywords:
            if item.arg == keyword:
                return item.value
        return None

    def call(self, node: ast.Call) -> None:
        func = node.func
        if (
            isinstance(func, ast.Name)
            and func.id in ("exec", "eval")
            and self.unshadowed(func.id)
        ):
            self.dynamic = True
            return
        kind = self._import_call_kind(func)
        if not kind:
            return
        self.dynamic = True
        opaque = any(isinstance(a, ast.Starred) for a in node.args) or any(
            k.arg is None for k in node.keywords
        )
        name_arg = None if opaque else self._argument(node, 0, "name")
        literal = (
            isinstance(name_arg, ast.Constant)
            and isinstance(name_arg.value, str)
            and bool(name_arg.value)
        )
        module = (
            name_arg.value if isinstance(name_arg, ast.Constant) and literal else ""
        )
        level = 0
        anchor_known = True
        package: str | None = None
        package_literal = True
        if kind == "dunder_import":
            level_arg = self._argument(node, 4, "level")
            if level_arg is not None:
                if (
                    isinstance(level_arg, ast.Constant)
                    and isinstance(level_arg.value, int)
                    and not isinstance(level_arg.value, bool)
                    and level_arg.value >= 0
                ):
                    level = level_arg.value
                else:
                    literal = False
            if level > 0:
                globals_arg = self._argument(node, 1, "globals")
                plain = (
                    isinstance(globals_arg, ast.Call)
                    and isinstance(globals_arg.func, ast.Name)
                    and globals_arg.func.id == "globals"
                    and self.unshadowed("globals")
                    and not globals_arg.args
                    and not globals_arg.keywords
                )
                anchor_known = bool(plain)
        else:
            package_arg = None if opaque else self._argument(node, 1, "package")
            if package_arg is not None:
                if isinstance(package_arg, ast.Constant) and isinstance(
                    package_arg.value, str
                ):
                    package = package_arg.value
                elif (
                    isinstance(package_arg, ast.Constant) and package_arg.value is None
                ):
                    package = None
                else:
                    package_literal = False
        self.records.append(
            ImportRecord(
                ORIGINAL_DYNAMIC_CALL,
                str(module),
                level,
                (),
                self.flags(),
                self.location(node),
                self.evidence(node),
                literal=bool(literal),
                package=package,
                package_literal=package_literal,
                relative_anchor_known=anchor_known,
            )
        )

    def push(self, kind: str, names: dict[str, str], marker: str | None = None) -> None:
        self.scopes.append(_Scope(kind, names))
        if marker is not None:
            self.context.append(marker)

    def pop(self, marked: bool) -> None:
        self.scopes.pop()
        if marked:
            self.context.pop()

    def block(self, statements: Iterable[ast.AST], marker: str | None) -> None:
        if marker is not None:
            self.context.append(marker)
        for statement in statements:
            if self.capped:
                break
            self.visit(statement)
        if marker is not None:
            self.context.pop()

    def descend(self, node: ast.AST) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Decorators, defaults and annotations run when the function is defined;
            # the body runs when it is called (lazy).
            # دکوراتور، مقدار پیش‌فرض و annotation هنگام تعریف اجرا می‌شوند، بدنه هنگام فراخوانی.
            for decorator in node.decorator_list:
                self.visit(decorator)
            self.visit(node.args)
            if node.returns is not None:
                self.visit(node.returns)
            for parameter in getattr(node, "type_params", ()):
                self.visit(parameter)
            table: dict[str, str] = {}
            escaped: set[str] = set()
            _collect(node.body, table, escaped)
            for name in _parameter_names(node.args):
                _bind(table, name, _OTHER)
            for name in escaped:
                table.pop(name, None)
            self.push("function", table, "function")
            self.block(node.body, None)
            self.pop(True)
        elif isinstance(node, ast.Lambda):
            self.visit(node.args)
            table = {}
            for name in _parameter_names(node.args):
                _bind(table, name, _OTHER)
            self.push("function", table, "function")
            self.visit(node.body)
            self.pop(True)
        elif isinstance(node, ast.ClassDef):
            for decorator in node.decorator_list:
                self.visit(decorator)
            for base in node.bases:
                self.visit(base)
            for keyword in node.keywords:
                self.visit(keyword.value)
            for parameter in getattr(node, "type_params", ()):
                self.visit(parameter)
            table = {}
            _collect(node.body, table, set())
            self.push("class", table)
            self.block(node.body, None)
            self.pop(False)
        elif isinstance(
            node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
        ):
            self.comprehension(node)
        elif isinstance(node, ast.If):
            self.visit(node.test)
            kind = self._type_checking_kind(node.test)
            self.block(
                node.body, "type_checking" if kind == "positive" else "conditional"
            )
            self.block(
                node.orelse, "type_checking" if kind == "negative" else "conditional"
            )
        elif isinstance(node, (ast.Try, ast.TryStar)):
            guarded = any(
                self._catches_import_error(handler.type) for handler in node.handlers
            )
            self.block(node.body, "conditional" if guarded else None)
            for handler in node.handlers:
                if handler.type is not None:
                    self.visit(handler.type)
                self.block(handler.body, "conditional")
            self.block(node.orelse, "conditional")
            self.block(node.finalbody, None)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            self.visit(node.iter)
            self.block(node.body, "conditional")
            self.block(node.orelse, "conditional")
        elif isinstance(node, ast.While):
            self.visit(node.test)
            self.block(node.body, "conditional")
            self.block(node.orelse, "conditional")
        elif isinstance(node, ast.Match):
            self.visit(node.subject)
            for case in node.cases:
                self.context.append("conditional")
                if case.guard is not None:
                    self.visit(case.guard)
                self.block(case.body, None)
                self.context.pop()
        elif isinstance(node, ast.BoolOp):
            self.visit(node.values[0])
            self.block(node.values[1:], "conditional")
        elif isinstance(node, ast.IfExp):
            self.visit(node.test)
            self.block([node.body, node.orelse], "conditional")
        else:
            self.children(node)

    def comprehension(
        self, node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp
    ) -> None:
        """The first iterable is evaluated in the enclosing scope, the rest in the
        comprehension's own scope; its element runs once per item (conditional)."""
        generators = node.generators
        if generators:
            self.visit(generators[0].iter)
        table: dict[str, str] = {}
        for generator in generators:
            for name in _target_names(generator.target):
                _bind(table, name, _OTHER)
        self.push("comprehension", table, "conditional")
        for index, generator in enumerate(generators):
            if index:
                self.visit(generator.iter)
            for condition in generator.ifs:
                self.visit(condition)
        if isinstance(node, ast.DictComp):
            self.visit(node.key)
            if node.value is not None:
                self.visit(node.value)
        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            self.visit(node.elt)
        self.pop(True)

    def children(self, node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if self.capped:
                return
            self.visit(child)


def extract_imports(path: str, data: bytes, interpreter_version: str) -> ExtractResult:
    """Parse `data` (the bytes of `path`) and return its imports and provenance.

    Failures that come from the input are handled and become a limitation code: not
    UTF-8 (`encoding_error`), a syntax error (`syntax_error`, with the location), an
    interpreter recursion or memory failure while parsing or walking (`recursion_limit`
    or `resource_limit`), and the node cap (`node_cap`). Any other exception is a bug
    in sarand and is not caught.
    """
    digest = hashlib.sha256(data).hexdigest()
    size = len(data)
    try:
        source = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return ExtractResult(
            digest,
            size,
            _provenance(interpreter_version, COMPLETENESS_FAILED, {LIM_ENCODING}),
        )
    lines = split_lines(source)
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        line = int(exc.lineno or 0)
        end_line = int(exc.end_lineno or line)
        where = SourceLocation(
            path,
            line,
            byte_column(lines, line, exc.offset),
            end_line,
            byte_column(lines, end_line, exc.end_offset),
        )
        return ExtractResult(
            digest,
            size,
            _provenance(interpreter_version, COMPLETENESS_FAILED, {LIM_SYNTAX_ERROR}),
            error=where,
        )
    except RecursionError:
        return ExtractResult(
            digest,
            size,
            _provenance(interpreter_version, COMPLETENESS_FAILED, {LIM_RECURSION}),
        )
    except (MemoryError, ValueError):
        return ExtractResult(
            digest,
            size,
            _provenance(interpreter_version, COMPLETENESS_FAILED, {LIM_RESOURCE}),
        )
    walker = _Walker(path, source, tree)
    limits: set[str] = set()
    completeness = COMPLETENESS_FULL
    if walker.recursion_hit:
        limits.add(LIM_RECURSION)
        completeness = COMPLETENESS_PARTIAL
    for statement in tree.body:
        if walker.capped:
            break
        try:
            walker.visit(statement)
        except RecursionError:
            # Only this statement is lost; the next one is read normally.
            # فقط همین دستور از دست می‌رود؛ دستور بعدی عادی خوانده می‌شود.
            limits.add(LIM_RECURSION)
            completeness = COMPLETENESS_PARTIAL
            walker.reset()
        except MemoryError:
            limits.add(LIM_RESOURCE)
            completeness = COMPLETENESS_PARTIAL
            walker.reset()
            break
    if walker.capped:
        limits.add(LIM_NODE_CAP)
        completeness = COMPLETENESS_PARTIAL
    if walker.dynamic:
        limits.add(LIM_DYNAMIC)
    ordered = sorted(
        walker.records,
        key=lambda r: (
            r.location.line,
            r.location.col,
            r.module,
            r.names,
            r.original_type,
        ),
    )
    return ExtractResult(
        digest,
        size,
        _provenance(interpreter_version, completeness, limits),
        imports=tuple(ordered),
        tree=tree,
    )
