"""R analyzer: testthat + lintr, gated on a real R package DESCRIPTION
file.

R has no de-facto dependency-vulnerability-audit tool the way pip-audit
or cargo-audit do -- run_security is an honest empty, same precedent
as Dart/Lua/CSS/Zig/Swift. `Rscript` is a real, broadly-available
binary (ships with any R install), but whether the `testthat`/`lintr`
*packages* themselves are installed is something sarand cannot check
without executing R code -- a missing package therefore surfaces as a
normal non-zero-exit CommandResult, not a clean skip. This mirrors how
other analyzers only guarantee the *binary* is present, not every
library the invoked command might need (e.g. CSharpAnalyzer's
`dotnet` check does not verify individual NuGet packages either).

آنالایزر R: testthat + lintr، فقط وقتی یک فایل DESCRIPTION واقعیِ
بسته‌ی R وجود داشته باشد.

R ابزار audit آسیب‌پذیریِ وابستگی‌های به‌طور گسترده استاندارد ندارد --
run_security یک خالیِ صادقانه است، همان سابقه‌ی Dart/Lua/CSS/Zig/Swift.
`Rscript` یک باینریِ واقعی و به‌طور گسترده در دسترس است (همراه هر نصب
R می‌آید)، اما این‌که خودِ پکیج‌های `testthat`/`lintr` نصب هستند یا نه
چیزی است که sarand بدون اجرای کد R نمی‌تواند چک کند -- پس پکیج غایب
به‌صورت یک CommandResult ناموفق معمولی ظاهر می‌شود، نه یک skip تمیز.
این با نحوه‌ی رفتار آنالایزرهای دیگر هم‌خوان است که فقط وجود *باینری*
را تضمین می‌کنند، نه هر کتابخانه‌ای که دستور فراخوانی‌شده نیاز دارد
(مثلاً چک `dotnet` در CSharpAnalyzer هم پکیج‌های تکی NuGet را چک
نمی‌کند).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.r")

_ENTRY_POINTS = ("R/main.R", "main.R", "app.R")


class RAnalyzer:
    name = "R"

    def matches(self, root: Path) -> bool:
        return (root / "DESCRIPTION").is_file()

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).is_file()]

    async def run_tests(self, root: Path) -> CommandResult | None:
        tests_dir = root / "tests" / "testthat"
        if not tests_dir.is_dir():
            return None
        if shutil.which("Rscript") is None:
            return make_command_result(
                "testthat",
                127,
                "",
                0.0,
                skipped=True,
                skip_reason="Rscript not found in PATH",
            )
        logger.info("Running testthat::test_dir()")
        rc, out, dur = await run_cmd_async(
            [
                "Rscript",
                "-e",
                "testthat::test_dir('tests/testthat', stop_on_failure = TRUE)",
            ],
            root,
            LONG_CMD_TIMEOUT,
        )
        return make_command_result("testthat", rc, out, dur)

    async def run_quality(self, root: Path) -> list[CommandResult]:
        if shutil.which("Rscript") is None:
            return [
                make_command_result(
                    "lintr",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="Rscript not found in PATH",
                )
            ]
        logger.info("Running lintr::lint_dir()")
        rc, out, dur = await run_cmd_async(
            ["Rscript", "-e", "lintr::lint_dir('.')"],
            root,
            LONG_CMD_TIMEOUT,
        )
        return [make_command_result("lintr", rc, out, dur)]

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
