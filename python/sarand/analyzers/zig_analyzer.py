"""Zig analyzer: `zig build test` + `zig fmt --check`, gated on a real
build.zig.

A single `zig` binary provides the whole toolchain (build, test,
format) -- unlike most other analyzers there is no separate lint tool
to find; `zig fmt --check` (Zig's own built-in, opinionated formatter)
is quality's entire job here.

آنالایزر Zig: `zig build test` + `zig fmt --check`، فقط وقتی build.zig
واقعی وجود داشته باشد.

یک باینری واحد `zig` کل toolchain را فراهم می‌کند (build، test،
format) -- برخلاف اکثر آنالایزرهای دیگر، هیچ ابزار لینت جداگانه‌ای
برای پیدا کردن نیست؛ `zig fmt --check` (فرمتر عقیده‌مند و
داخلی‌خودِ Zig) کل کار quality اینجاست.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.zig")

_ENTRY_POINTS = ("src/main.zig", "build.zig")


class ZigAnalyzer:
    name = "Zig"

    def matches(self, root: Path) -> bool:
        return (root / "build.zig").is_file()

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).is_file()]

    async def run_tests(self, root: Path) -> CommandResult | None:
        if shutil.which("zig") is None:
            return make_command_result(
                "zig build test",
                127,
                "",
                0.0,
                skipped=True,
                skip_reason="zig not found in PATH",
            )
        logger.info("Running zig build test")
        rc, out, dur = await run_cmd_async(
            ["zig", "build", "test"], root, LONG_CMD_TIMEOUT
        )
        return make_command_result("zig build test", rc, out, dur)

    async def run_quality(self, root: Path) -> list[CommandResult]:
        if shutil.which("zig") is None:
            return [
                make_command_result(
                    "zig fmt --check",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="zig not found in PATH",
                )
            ]
        rc, out, dur = await run_cmd_async(
            ["zig", "fmt", "--check", "."], root, LONG_CMD_TIMEOUT
        )
        return [make_command_result("zig fmt --check", rc, out, dur)]

    async def run_security(self, root: Path) -> list[CommandResult]:
        # No standard Zig package-manager audit tool exists as of this
        # writing -- honest empty, same precedent as other ecosystems
        # without one (Dart/Lua/CSS).
        #
        # هیچ ابزار audit استاندارد بسته‌مدیرِ Zig تا زمان نوشتن این کد
        # وجود ندارد -- خالیِ صادقانه، همان سابقه‌ی اکوسیستم‌های دیگر
        # بدون این ابزار (Dart/Lua/CSS).
        return []
