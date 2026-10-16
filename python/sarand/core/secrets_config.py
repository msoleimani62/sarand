"""Per-project secret-scan settings, read from `.sarand.toml`.

The only setting is the fixture allowlist: a project that deliberately keeps
fake credentials in its own tests (sarand does, in `tests/test_secrets.py`)
says so explicitly, and findings in exactly those files stop counting against
the health score. Nothing is guessed from the path any more (AGENTS.md 5.67).

    [secrets]
    fixture_paths = ["tests/test_secrets.py"]

Semantics:

- Globs are matched with `fnmatch` against the POSIX-style project-relative
  path; case-sensitive; `*` also crosses `/`.
- The default is an empty list: every finding counts.
- Allow-listed files are still never embedded in a report and their findings
  are still listed -- only the health score changes.
- A glob that would match every file (only `*` and `/` characters) is
  rejected: it would silently switch the security penalty off.
- Like the `[licenses]` table, anything wrong (an unknown key, a bad type,
  invalid TOML) is an error, never silently ignored.

تنظیمات اسکن secret برای هر پروژه، از `.sarand.toml`. تنها تنظیم، فهرست
مجاز fixtureهاست: پروژه‌ای که عمداً اعتبارنامه‌ی جعلی در تست‌های خودش دارد
(sarand در `tests/test_secrets.py` دارد) صراحتاً اعلام می‌کند و یافته‌های
دقیقاً همان فایل‌ها دیگر روی امتیاز سلامت اثر نمی‌گذارند. دیگر چیزی از مسیر
حدس زده نمی‌شود. پیش‌فرض فهرست خالی است: هر یافته شمرده می‌شود. فایل‌های
مجاز همچنان هرگز در گزارش embed نمی‌شوند و یافته‌هایشان همچنان فهرست
می‌شود. globی که همه‌ی فایل‌ها را بپوشاند رد می‌شود. هر چیز نادرست خطاست،
نه نادیده‌گرفتن بی‌صدا.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sarand.core.license_policy import POLICY_FILENAME

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10: same parser, packaged separately
    import tomli as tomllib

_SECRETS_KEYS = {"fixture_paths"}


class SecretsConfigError(ValueError):
    """The `[secrets]` table of `.sarand.toml` is invalid."""


def _matches_everything(pattern: str) -> bool:
    return all(ch in "*/" for ch in pattern)


def parse_fixture_paths(text: str) -> tuple[str, ...]:
    """Parse the file's text. Empty tuple when there is no `[secrets]` table."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise SecretsConfigError(f"invalid TOML: {exc}") from exc
    table = data.get("secrets")
    if table is None:
        return ()
    if not isinstance(table, dict):
        raise SecretsConfigError("`secrets` must be a table")
    unknown_keys = set(table) - _SECRETS_KEYS
    if unknown_keys:
        raise SecretsConfigError(
            f"[secrets] unknown key(s): {', '.join(sorted(unknown_keys))} "
            f"(expected: {', '.join(sorted(_SECRETS_KEYS))})"
        )
    raw = table.get("fixture_paths", [])
    if not isinstance(raw, list):
        raise SecretsConfigError("[secrets] fixture_paths must be a list of strings")
    patterns: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise SecretsConfigError(
                "[secrets] fixture_paths must be a list of non-empty strings"
            )
        pattern = item.strip().replace("\\", "/")
        if _matches_everything(pattern):
            raise SecretsConfigError(
                f"[secrets] fixture_paths entry {item!r} would match every file"
            )
        patterns.append(pattern)
    return tuple(patterns)


def load_fixture_paths(root: Path) -> tuple[str, ...]:
    """The project's fixture allowlist (empty when there is no file/section).

    Raises SecretsConfigError when the file exists but is invalid.
    """
    path = root / POLICY_FILENAME
    if not path.is_file():
        return ()
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SecretsConfigError(f"cannot read {POLICY_FILENAME}: {exc}") from exc
    try:
        return parse_fixture_paths(text)
    except SecretsConfigError as exc:
        raise SecretsConfigError(f"{POLICY_FILENAME}: {exc}") from exc
