"""Versioned structural fingerprint of a Python definition (R14-A3, plan section 8).

`fp1` answers one question: *has the content of this definition changed?* It is a
SHA-256 over a canonical walk of the definition's syntax tree, truncated to 12 hex
digits and prefixed with the algorithm version (`fp1:`).

What the fingerprint ignores (so it is stable across harmless edits):

- positions (line, column), whitespace, parentheses, quote style, trailing commas,
  comments, `u` string prefixes, type comments;
- the docstring of a function, method or class (the first statement when it is a
  plain string expression);
- the expression context (`Load`/`Store`), which the position in the tree implies.

What it includes (so a real change changes it): every statement and expression of the
definition, including nested definitions, decorators, default values, annotations and
the values of literals.

Limits, stated here and in `docs/STRUCTURE.md`:

- The syntax tree of Python differs between interpreter versions, so a fingerprint is
  comparable only between two outputs that carry the same `fingerprint_basis`
  (`fp1/python-3.12`). Matching refuses to compare fingerprints across bases.
- A fingerprint is not a security hash of the source and is never used alone: it
  proposes a *probable* match, never an exact one.
- The walk is iterative, so a deeply nested definition cannot fail with a recursion
  error. Any change of the algorithm bumps `FINGERPRINT_VERSION`.

بصمت ساختاری نسخه‌دار یک تعریف پایتون؛ مستقل از فاصله‌گذاری، شماره‌ی خط، کامنت و docstring.
"""

from __future__ import annotations

import ast
import hashlib
import platform
import re
from collections.abc import Callable, Iterable

FINGERPRINT_VERSION = "fp1"
FINGERPRINT_DIGITS = 12
FINGERPRINT_PATTERN = re.compile(
    rf"^{FINGERPRINT_VERSION}:[0-9a-f]{{{FINGERPRINT_DIGITS}}}$"
)

# Fields that carry no definition content (see the module docstring).
# فیلدهایی که محتوای تعریف را تغییر نمی‌دهند.
_SKIPPED_FIELDS = frozenset({"ctx", "kind", "type_comment"})
_DOCSTRING_OWNERS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

_SEP = "\x1f"


def fingerprint_basis(version: str | None = None) -> str:
    """The comparison basis: the algorithm version and the interpreter's minor version
    (the syntax tree is only comparable inside one of them)."""
    text = version if version is not None else platform.python_version()
    parts = text.split(".")
    minor = ".".join(parts[:2])
    return f"{FINGERPRINT_VERSION}/python-{minor}"


def is_docstring(statement: ast.stmt) -> bool:
    """A statement that is only a string literal (a docstring when it comes first)."""
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


def fingerprint(parts: Iterable[ast.AST | None]) -> str:
    """The `fp1:` fingerprint of the given syntax nodes, in order (`None` is a marker).

    A function or class is fingerprinted from its definition node; a variable from its
    annotation and value (two parts), so another target of the same statement does
    not change it.
    """
    digest = hashlib.sha256()
    for part in parts:
        if part is None:
            digest.update(b"\x01")
        else:
            digest.update(b"\x00")
            _feed(digest.update, part)
    return f"{FINGERPRINT_VERSION}:{digest.hexdigest()[:FINGERPRINT_DIGITS]}"


_OPEN = b"\x02"
_CLOSE = b"\x03"
_LIST_OPEN = b"\x04"
_LIST_CLOSE = b"\x05"
_FLUSH_AT = 8192

# Per node type: the (field name token, field name) pairs that count, computed once.
# برای هر نوع گره، فیلدهای مؤثر یک بار محاسبه می‌شود.
_PLANS: dict[type, tuple[tuple[str, bytes], ...]] = {}


def _plan(node_type: type) -> tuple[tuple[str, bytes], ...]:
    plan = _PLANS.get(node_type)
    if plan is None:
        fields = getattr(node_type, "_fields", ())
        plan = tuple(
            (name, (_SEP + name + _SEP).encode("ascii"))
            for name in fields
            if name not in _SKIPPED_FIELDS
        )
        _PLANS[node_type] = plan
    return plan


def _scalar(value: object) -> bytes:
    return f"{type(value).__name__}:{value!r}".encode("utf-8", "backslashreplace")


def _feed(update: Callable[[bytes], object], root: ast.AST) -> None:
    """Hash `root` with an explicit stack (no recursion). The stack holds syntax
    nodes, lists, and `bytes` tokens that are written as they are; every scalar is
    turned into a token when it is pushed, so a literal can never pass for a
    delimiter."""
    pending: list[bytes] = []
    stack: list[object] = [root]
    while stack:
        item = stack.pop()
        if isinstance(item, bytes):
            pending.append(item)
        elif isinstance(item, ast.AST):
            node_type = type(item)
            pending.append(_OPEN)
            pending.append(node_type.__name__.encode("ascii"))
            stack.append(_CLOSE)
            for name, token in reversed(_plan(node_type)):
                value = getattr(item, name, None)
                if value is None:
                    continue
                if isinstance(value, list):
                    if not value:
                        continue
                    if (
                        name == "body"
                        and isinstance(item, _DOCSTRING_OWNERS)
                        and is_docstring(value[0])
                    ):
                        value = value[1:]
                        if not value:
                            continue
                    stack.append(value)
                elif isinstance(value, ast.AST):
                    stack.append(value)
                else:
                    stack.append(_scalar(value))
                stack.append(token)
        elif isinstance(item, list):
            pending.append(_LIST_OPEN)
            stack.append(_LIST_CLOSE)
            for element in reversed(item):
                if isinstance(element, (ast.AST, list)):
                    stack.append(element)
                else:
                    stack.append(_scalar(element))
        else:  # pragma: no cover - every scalar was turned into a token
            pending.append(_scalar(item))
        if len(pending) >= _FLUSH_AT:
            update(b"".join(pending))
            pending.clear()
    update(b"".join(pending))
