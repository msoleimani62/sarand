"""Per-project TODO-scan settings, read from `.sarand.toml`.

    [todo]
    exclude_globs = ["tests/test_health.py", "vendor/*"]

The TODO scanner already skips a few places by default (see
`TODO_EXCLUDE_DIRS` / `TODO_EXCLUDE_SUFFIXES` in constants.py: golden and
fixture directories, Markdown/reStructuredText prose). This table adds
project-specific globs on top. Matching is `fnmatch` on the POSIX-style
project-relative path (case-sensitive; `*` also crosses `/`). Nothing is
hidden silently: the report states how many markers were suppressed.

As with `[licenses]` and `[secrets]`, anything wrong (an unknown key, a bad
type, invalid TOML, a glob that would match every file) is an error; the CLI
turns it into a warning and falls back to the defaults only.

تنظیمات اسکن TODO برای هر پروژه، از `.sarand.toml`. اسکنر TODO به‌طور
پیش‌فرض چند جا را رد می‌کند (پوشه‌های golden و fixture، متن Markdown/rst)؛
این جدول الگوهای اختصاصی پروژه را اضافه می‌کند. هیچ‌چیز بی‌صدا پنهان
نمی‌شود: گزارش می‌گوید چند marker حذف شده است. هر اشتباه خطاست و CLI آن را
به هشدار تبدیل می‌کند و فقط پیش‌فرض‌ها را به کار می‌برد.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from sarand.core.license_policy import POLICY_FILENAME

_TODO_KEYS = {"exclude_globs"}


class TodoConfigError(ValueError):
    """The `[todo]` table of `.sarand.toml` is invalid."""


def _matches_everything(pattern: str) -> bool:
    return all(ch in "*/" for ch in pattern)


def parse_exclude_globs(text: str) -> tuple[str, ...]:
    """Parse the file's text. Empty tuple when there is no `[todo]` table."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise TodoConfigError(f"invalid TOML: {exc}") from exc
    table = data.get("todo")
    if table is None:
        return ()
    if not isinstance(table, dict):
        raise TodoConfigError("`todo` must be a table")
    unknown_keys = set(table) - _TODO_KEYS
    if unknown_keys:
        raise TodoConfigError(
            f"[todo] unknown key(s): {', '.join(sorted(unknown_keys))} "
            f"(expected: {', '.join(sorted(_TODO_KEYS))})"
        )
    raw = table.get("exclude_globs", [])
    if not isinstance(raw, list):
        raise TodoConfigError("[todo] exclude_globs must be a list of strings")
    patterns: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise TodoConfigError(
                "[todo] exclude_globs must be a list of non-empty strings"
            )
        pattern = item.strip().replace("\\", "/")
        if _matches_everything(pattern):
            raise TodoConfigError(
                f"[todo] exclude_globs entry {item!r} would match every file"
            )
        patterns.append(pattern)
    return tuple(patterns)


def load_exclude_globs(root: Path) -> tuple[str, ...]:
    """The project's extra TODO exclusions (empty when there is no file/section).

    Raises TodoConfigError when the file exists but is invalid.
    """
    path = root / POLICY_FILENAME
    if not path.is_file():
        return ()
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise TodoConfigError(f"cannot read {POLICY_FILENAME}: {exc}") from exc
    try:
        return parse_exclude_globs(text)
    except TodoConfigError as exc:
        raise TodoConfigError(f"{POLICY_FILENAME}: {exc}") from exc
