"""Lua analyzer: busted + luacheck, gated on real Lua project markers.

Never executes arbitrary project Lua source. Only invokes known host
binaries (busted, luacheck) when they are present in PATH, and only after
matches(root) is True. Missing tools produce a clean skipped CommandResult
rather than a crash.

آنالایزر Lua: busted + luacheck، فقط وقتی نشانگر واقعی پروژه Lua باشد.
هرگز سورس Lua پروژه را اجرا نمی‌کند. فقط باینری‌های شناخته‌شده‌ی میزبان
را در صورت وجود در PATH صدا می‌زند و فقط بعد از matches(root). ابزار
غایب به صورت skipped تمیز برمی‌گردد، نه کرش.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.lua")

_ENTRY_POINTS = (
    "init.lua",
    "main.lua",
    "app.lua",
    "src/main.lua",
    "src/init.lua",
)


class LuaAnalyzer:
    name = "Lua"

    def matches(self, root: Path) -> bool:
        """Return True when the tree looks like a Lua project.

        Detection is intentionally shallow and deterministic:
        1. a root-level LuaRocks specification
        2. a conventional root-level entry point
        3. a top-level Lua source file

        Deep recursive scans are avoided so vendored or unrelated nested
        Lua files do not force a project-level match.
        """
        try:
            if any(root.glob("*.rockspec")):
                return True

            for name in ("init.lua", "main.lua", "app.lua"):
                if (root / name).is_file():
                    return True

            for path in root.iterdir():
                if path.is_file() and path.suffix.lower() == ".lua":
                    return True
        except OSError:
            return False

        return False

    def entry_points(self, root: Path) -> list[str]:
        return [
            entry_point
            for entry_point in _ENTRY_POINTS
            if (root / entry_point).is_file()
        ]

    async def run_tests(self, root: Path) -> CommandResult | None:
        if shutil.which("busted") is None:
            return make_command_result(
                "busted",
                127,
                "",
                0.0,
                skipped=True,
                skip_reason="busted not found in PATH",
            )

        logger.info("Running busted")
        return_code, output, duration = await run_cmd_async(
            ["busted"],
            root,
            LONG_CMD_TIMEOUT,
        )
        return make_command_result(
            "busted",
            return_code,
            output,
            duration,
        )

    async def run_quality(self, root: Path) -> list[CommandResult]:
        if shutil.which("luacheck") is None:
            return [
                make_command_result(
                    "luacheck",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="luacheck not installed",
                )
            ]

        logger.info("Running luacheck .")
        return_code, output, duration = await run_cmd_async(
            ["luacheck", "."],
            root,
            LONG_CMD_TIMEOUT,
        )
        return [
            make_command_result(
                "luacheck",
                return_code,
                output,
                duration,
            )
        ]

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
