"""What a source-code marker means (R13-E).

The TODO scanner finds every occurrence of a marker keyword (TODO, FIXME, BUG,
HACK, SAFETY, XXX) on a line of text. That is *discovery*, and it is deliberately
wide: it also finds the word inside prose, a docstring, a variable name or a
fixture string. Whether an occurrence is technical debt is a separate question,
answered here, one category per occurrence:

- `actionable`: TODO or FIXME written as a task (`TODO: fix x`, `FIXME(ana): x`,
  `TODO - x`). Only these count toward the code-health score and the
  `TODO-CLUSTER` risk.
- `historical`: BUG. It usually records a defect that was already fixed ("BUG
  FIX: ...", a regression note) or a known limitation; it is never counted as
  debt on its own. Write a task as TODO or FIXME.
- `safety`: SAFETY. A justification of an invariant (Rust's `// SAFETY:`) or a
  note about safety; it stays visible for review and is not debt.
- `development`: HACK or XXX. A development note (a workaround, a place that
  needs attention); shown, not scored.
- `mention`: TODO or FIXME that is not written as a task: the word in prose
  (`the TODO scanner`), in a name (`todo.kind`), in a list (`TODO/FIXME`), or a
  placeholder (`TODO: ...`).

The classification reads the text of the line from the marker onward. It cannot
know whether the line is a comment or a string: a task written inside a test's
string literal still looks like a task. A project silences such files with
`[todo] exclude_globs` in `.sarand.toml`.

Pure and deterministic.

معنای مارکر در کد (R13-E). کشف مارکر عمداً گسترده است؛ اینکه یک مورد «بدهی فنی»
است یا نه جداگانه و اینجا تعیین می‌شود. فقط TODO/FIXME نوشته‌شده به‌شکل کار در امتیاز
و ریسک می‌آید.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from sarand.models.results import TodoItem

CATEGORY_ACTIONABLE = "actionable"
CATEGORY_HISTORICAL = "historical"
CATEGORY_SAFETY = "safety"
CATEGORY_DEVELOPMENT = "development"
CATEGORY_MENTION = "mention"

# Fixed order: the order of the summary and of the report column.
# ترتیب ثابت: ترتیب خلاصه و ستون گزارش.
CATEGORIES: tuple[str, ...] = (
    CATEGORY_ACTIONABLE,
    CATEGORY_HISTORICAL,
    CATEGORY_SAFETY,
    CATEGORY_DEVELOPMENT,
    CATEGORY_MENTION,
)

_KIND_CATEGORY = {
    "BUG": CATEGORY_HISTORICAL,
    "SAFETY": CATEGORY_SAFETY,
    "HACK": CATEGORY_DEVELOPMENT,
    "XXX": CATEGORY_DEVELOPMENT,
}

# A task: the keyword, an optional owner `(name)`, then `:` or a spaced dash, then
# text that starts like a sentence (a letter, digit, quote, backtick or bracket).
# `TODO-style`, `TODO-CLUSTER`, `TODO/FIXME` and `TODO: ...` are not tasks.
# کار: کلیدواژه، owner اختیاری، سپس `:` یا خط‌تیره‌ی فاصله‌دار، سپس متنی که مثل
# جمله شروع می‌شود. `TODO-style` و `TODO: ...` کار نیستند.
_TASK = re.compile(
    r"^(?:TODO|FIXME)\b(?:\([^)\n]*\))?(?:[ \t]*:[ \t]*|[ \t]+[-\u2013\u2014][ \t]+)"
    r"(?=[\w`\"'(\[])",
    re.IGNORECASE,
)
_KEYWORD = re.compile(r"\b(?:TODO|FIXME)\b", re.IGNORECASE)


def classify_marker_text(kind: str, tail: str) -> str:
    """The category of one marker; `tail` is the line text from the keyword on."""
    fixed = _KIND_CATEGORY.get(kind.upper())
    if fixed is not None:
        return fixed
    return CATEGORY_ACTIONABLE if _TASK.match(tail) else CATEGORY_MENTION


def marker_category(item: TodoItem) -> str:
    """The category of a found marker.

    The scanner sets `category` from the whole line. An item built without one
    (an older cache entry, a test) is classified from its `content`, at its first
    keyword of that kind.
    """
    if item.category:
        return item.category
    kind = (item.kind or "").upper()
    if kind in _KIND_CATEGORY:
        return _KIND_CATEGORY[kind]
    match = re.search(rf"\b{re.escape(kind)}\b", item.content or "", re.IGNORECASE)
    tail = (item.content or "")[match.start() :] if match else (item.content or "")
    return classify_marker_text(kind, tail)


def is_actionable(item: TodoItem) -> bool:
    """True for a TODO / FIXME written as a task: the only debt marker."""
    return marker_category(item) == CATEGORY_ACTIONABLE


def category_counts(items: Iterable[TodoItem]) -> dict[str, int]:
    """How many markers are in each category (every category present, in order)."""
    counted = Counter(marker_category(i) for i in items)
    return {category: counted.get(category, 0) for category in CATEGORIES}
