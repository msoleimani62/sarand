"""Shell analyzer: shellcheck + bats, gated on a top-level *.sh/*.bash
file.

Detection mirrors CssAnalyzer/LuaAnalyzer's shallow, top-level-only
check -- a shell script three directories deep inside a Node.js
project's node_modules (or any vendored dependency) must not turn that
whole project into a "Shell project."

آنالایزر Shell: shellcheck + bats، فقط وقتی یک فایل *.sh/*.bash
سطح-ریشه وجود داشته باشد.

تشخیص همان بررسیِ کم‌عمق و فقط-سطح-ریشه‌ی CssAnalyzer/LuaAnalyzer را
تکرار می‌کند -- یک اسکریپت شل سه پوشه پایین‌تر داخل node_modules یک
پروژه‌ی Node.js (یا هر وابستگیِ vendor‌شده) نباید کل آن پروژه را به
یک «پروژه‌ی Shell» تبدیل کند.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.shell")

_ENTRY_POINTS = ("install.sh", "run.sh", "main.sh", "build.sh")
_SHELL_EXTENSIONS = (".sh", ".bash")


def _top_level_shell_scripts(root: Path) -> list[Path]:
    try:
        return sorted(
            p
            for p in root.iterdir()
            if p.is_file() and p.suffix.lower() in _SHELL_EXTENSIONS
        )
    except OSError:
        return []


class ShellAnalyzer:
    name = "Shell"

    def matches(self, root: Path) -> bool:
        return bool(_top_level_shell_scripts(root))

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).is_file()]

    async def run_tests(self, root: Path) -> CommandResult | None:
        tests_dir = root / "tests"
        if not tests_dir.is_dir() or not any(tests_dir.glob("*.bats")):
            return None
        if shutil.which("bats") is None:
            return make_command_result(
                "bats",
                127,
                "",
                0.0,
                skipped=True,
                skip_reason="bats not found in PATH",
            )
        logger.info("Running bats tests/")
        rc, out, dur = await run_cmd_async(["bats", "tests"], root, LONG_CMD_TIMEOUT)
        return make_command_result("bats", rc, out, dur)

    async def run_quality(self, root: Path) -> list[CommandResult]:
        scripts = _top_level_shell_scripts(root)
        if shutil.which("shellcheck") is None:
            return [
                make_command_result(
                    "shellcheck",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="shellcheck not found in PATH",
                )
            ]
        rc, out, dur = await run_cmd_async(
            ["shellcheck", *(str(p.name) for p in scripts)], root, LONG_CMD_TIMEOUT
        )
        return [make_command_result("shellcheck", rc, out, dur)]

    async def run_security(self, root: Path) -> list[CommandResult]:
        # No standard shell-script vulnerability-audit tool exists as
        # of this writing -- honest empty, same precedent as other
        # ecosystems without one (Dart/Lua/CSS/Zig/Swift/SQL).
        return []
