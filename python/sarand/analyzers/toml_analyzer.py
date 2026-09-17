"""TOML analyzer: taplo, gated on a top-level *.toml file.

A format analyzer, not a language analyzer: no run_tests, and no
run_security (no broadly standard TOML vulnerability-audit tool) --
same honest-empty shape as YamlAnalyzer/JsonAnalyzer/CssAnalyzer.
Matches independently of whatever other analyzer also claims the same
file for a different purpose (e.g. RustAnalyzer already runs against
Cargo.toml) -- same complementary-match precedent as YamlAnalyzer.

آنالایزر TOML: taplo، فقط وقتی یک فایل *.toml سطح-ریشه وجود داشته باشد.

یک آنالایزر فرمت است، نه زبان: بدون run_tests، و بدون run_security
(بدون ابزار audit آسیب‌پذیریِ به‌طور گسترده استاندارد برای TOML) -- همان
شکل خالیِ صادقانه‌ی YamlAnalyzer/JsonAnalyzer/CssAnalyzer. مستقل از هر
آنالایزر دیگری که همان فایل را برای هدف دیگری claim می‌کند تطابق پیدا
می‌کند (مثلاً RustAnalyzer از قبل روی Cargo.toml اجرا می‌شود) -- همان
سابقه‌ی تطابقِ مکملِ YamlAnalyzer.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.toml")

_ENTRY_POINTS = ("Cargo.toml", "pyproject.toml")


def _top_level_toml_files(root: Path) -> list[Path]:
    try:
        return sorted(
            p for p in root.iterdir() if p.is_file() and p.suffix.lower() == ".toml"
        )
    except OSError:
        return []


class TomlAnalyzer:
    name = "TOML"

    def matches(self, root: Path) -> bool:
        return bool(_top_level_toml_files(root))

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).is_file()]

    async def run_tests(self, root: Path) -> CommandResult | None:
        return None

    async def run_quality(self, root: Path) -> list[CommandResult]:
        files = _top_level_toml_files(root)
        taplo = shutil.which("taplo")
        if taplo is None:
            return [
                make_command_result(
                    "taplo lint",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="taplo not found in PATH",
                )
            ]
        rc, out, dur = await run_cmd_async(
            [taplo, "lint", *(str(p.name) for p in files)], root, LONG_CMD_TIMEOUT
        )
        return [make_command_result("taplo lint", rc, out, dur)]

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
