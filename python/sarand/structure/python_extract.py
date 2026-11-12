"""Import extraction from one Python file with `ast` (R14-A, plan section 9).

Reads the file, parses it, and records every import statement and every call that
imports by name, with its location and the context it sits in (conditional, type
checking only, inside a function). It resolves nothing: that is `imports.py`.

The file is never executed. A file that does not parse yields a `failed` result with
the error location; a file that parses but hits a guard (recursion depth, node cap)
yields `partial` with the imports found so far. Nothing is silently dropped.

استخراج importها با ast؛ کد مخزن هرگز اجرا نمی‌شود.
"""

from __future__ import annotations

import ast
import hashlib
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
    LIM_SYNTAX_ERROR,
    LIM_UNSUPPORTED_SYNTAX,
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

_DYNAMIC_FUNCS = frozenset({"__import__"})
_IMPORTLIB_CALLS = frozenset({"import_module", "__import__"})


@dataclass(frozen=True)
class ImportRecord:
    """One import as written. `module` is the dotted name after the dots (empty for
    `from . import x`), `level` the number of leading dots, `names` the imported
    names of a `from` import (`*` for a star import), `literal` is false for a
    dynamic call whose argument is not a string constant."""

    original_type: str
    module: str
    level: int
    names: tuple[str, ...]
    flags: tuple[str, ...]
    location: SourceLocation
    evidence: str
    literal: bool = True


@dataclass(frozen=True)
class ExtractResult:
    sha256: str
    size: int
    provenance: Provenance
    imports: tuple[ImportRecord, ...] = ()
    error: SourceLocation | None = None
    extensions: dict[str, str | int | bool] = field(default_factory=dict)


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


def _is_type_checking(test: ast.expr) -> bool:
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    return False


def _catches_import_error(handler: ast.ExceptHandler) -> bool:
    names: list[ast.expr] = []
    if isinstance(handler.type, ast.Tuple):
        names = list(handler.type.elts)
    elif handler.type is not None:
        names = [handler.type]
    for item in names:
        label = item.id if isinstance(item, ast.Name) else getattr(item, "attr", "")
        if label in ("ImportError", "ModuleNotFoundError"):
            return True
    return False


class _Walker:
    """A recursive walk that tracks the context of each import."""

    def __init__(self, path: str, source: str) -> None:
        self.path = path
        self.source_lines = source.splitlines()
        self.records: list[ImportRecord] = []
        self.nodes = 0
        self.capped = False
        self.dynamic = False
        self.from_importlib: set[str] = set()
        # context stack: "if", "try", "function", "type_checking".
        # پشته‌ی زمینه: شرطی بودن، type-checking و داخل تابع بودن.
        self.context: list[str] = []

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
        line = getattr(node, "lineno", 0)
        if 1 <= line <= len(self.source_lines):
            return self.source_lines[line - 1].strip()[:200]
        return ""

    def flags(self, extra: tuple[str, ...] = ()) -> tuple[str, ...]:
        found = set(extra)
        if "type_checking" in self.context:
            found.update({FLAG_TYPE_ONLY, FLAG_CONDITIONAL})
        if any(c in ("if", "try") for c in self.context):
            found.add(FLAG_CONDITIONAL)
        if "function" in self.context:
            found.add(FLAG_LAZY)
        return tuple(sorted(found))

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
            if node.module == "importlib":
                self.from_importlib.update(
                    (a.asname or a.name)
                    for a in node.names
                    if a.name in _IMPORTLIB_CALLS
                )
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

    def call(self, node: ast.Call) -> None:
        func = node.func
        target = ""
        if isinstance(func, ast.Name):
            if func.id in _DYNAMIC_FUNCS or func.id in self.from_importlib:
                target = func.id
            elif func.id in ("exec", "eval"):
                self.dynamic = True
        elif (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "importlib"
            and func.attr in _IMPORTLIB_CALLS
        ):
            target = func.attr
        if not target:
            return
        self.dynamic = True
        argument = node.args[0] if node.args else None
        literal = isinstance(argument, ast.Constant) and isinstance(argument.value, str)
        name = argument.value if isinstance(argument, ast.Constant) else ""
        level = 0
        if len(node.args) >= 4 and isinstance(node.args[3], ast.Constant):
            level = (
                int(node.args[3].value) if isinstance(node.args[3].value, int) else 0
            )
        self.records.append(
            ImportRecord(
                ORIGINAL_DYNAMIC_CALL,
                str(name) if literal else "",
                level if target == "__import__" else 0,
                (),
                self.flags(),
                self.location(node),
                self.evidence(node),
                literal=bool(literal),
            )
        )

    def descend(self, node: ast.AST) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Decorators and defaults run when the function is defined, the body
            # when it is called (lazy).
            # دکوراتور و مقدار پیش‌فرض هنگام تعریف اجرا می‌شوند، بدنه هنگام فراخوانی.
            for decorator in node.decorator_list:
                self.visit(decorator)
            self.visit(node.args)
            self.context.append("function")
            for statement in node.body:
                if self.capped:
                    break
                self.visit(statement)
            self.context.pop()
        elif isinstance(node, ast.Lambda):
            self.visit(node.args)
            self.context.append("function")
            self.visit(node.body)
            self.context.pop()
        elif isinstance(node, ast.If):
            self.visit(node.test)
            marker = "type_checking" if _is_type_checking(node.test) else "if"
            self.context.append(marker)
            for child in node.body:
                self.visit(child)
            self.context.pop()
            self.context.append("if")
            for child in node.orelse:
                self.visit(child)
            self.context.pop()
        elif isinstance(node, ast.Try) or type(node).__name__ == "TryStar":
            # Only a `try` that catches ImportError makes an import optional.
            # فقط try ای که ImportError را می‌گیرد import را اختیاری می‌کند.
            handlers = getattr(node, "handlers", [])
            guarded = any(_catches_import_error(h) for h in handlers)
            if guarded:
                self.context.append("try")
            self.children(node)
            if guarded:
                self.context.pop()
        else:
            self.children(node)

    def children(self, node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if self.capped:
                return
            self.visit(child)


def _rules_for_error(error: SyntaxError) -> str:
    message = (error.msg or "").lower()
    if any(word in message for word in ("match", "type alias", "f-string", "except*")):
        return "newer grammar than this interpreter"
    return ""


def extract_imports(path: str, data: bytes, interpreter_version: str) -> ExtractResult:
    """Parse `data` (the bytes of `path`) and return its imports and provenance.

    Never raises for bad input: every failure becomes a provenance with a limitation
    code, so a broken file is visible in the output instead of disappearing.
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
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        rules = _rules_for_error(exc)
        syntax_limits = {LIM_SYNTAX_ERROR}
        if rules:
            syntax_limits.add(LIM_UNSUPPORTED_SYNTAX)
        where = SourceLocation(
            path,
            exc.lineno or 0,
            (exc.offset or 1) - 1,
            exc.end_lineno or exc.lineno or 0,
            0,
        )
        return ExtractResult(
            digest,
            size,
            _provenance(interpreter_version, COMPLETENESS_FAILED, syntax_limits, rules),
            error=where,
        )
    except (RecursionError, MemoryError, ValueError):
        return ExtractResult(
            digest,
            size,
            _provenance(interpreter_version, COMPLETENESS_FAILED, {LIM_RECURSION}),
        )
    walker = _Walker(path, source)
    limits: set[str] = set()
    completeness = COMPLETENESS_FULL
    try:
        walker.visit(tree)
    except RecursionError:
        limits.add(LIM_RECURSION)
        completeness = COMPLETENESS_PARTIAL
    if walker.capped:
        limits.add(LIM_NODE_CAP)
        completeness = COMPLETENESS_PARTIAL
    if walker.dynamic:
        limits.add(LIM_DYNAMIC)
    ordered = sorted(
        walker.records,
        key=lambda r: (r.location.line, r.location.col, r.module, r.names),
    )
    return ExtractResult(
        digest,
        size,
        _provenance(interpreter_version, completeness, limits),
        imports=tuple(ordered),
    )
