"""Perl analyzer: prove + perlcritic, gated on a real cpanfile.

`cpanfile` is preferred over the older `Makefile.PL`/`Build.PL` as the
detection marker -- it is the modern, declarative dependency manifest
(cpanm-driven) and, unlike Makefile.PL, is pure data rather than a
Perl script that would need to be executed to even know what it
declares. No broadly standard Perl dependency-vulnerability-audit tool
exists as of this writing -- run_security is an honest empty, same
precedent as R/Dart/Lua/CSS/Zig/Swift.

آنالایزر Perl: prove + perlcritic، فقط وقتی یک cpanfile واقعی وجود
داشته باشد.

`cpanfile` نسبت به `Makefile.PL`/`Build.PL` قدیمی‌تر به‌عنوان نشانگر
تشخیص ترجیح داده شده -- مانیفست وابستگیِ مدرن و اعلانی (مبتنی بر cpanm)
است و، برخلاف Makefile.PL، خودِ داده است نه اسکریپت Perl‌ای که برای
دانستن محتوایش باید اجرا شود. ابزار audit آسیب‌پذیریِ وابستگیِ Perl به‌طور
گسترده استانداردی تا این لحظه وجود ندارد -- run_security یک خالیِ
صادقانه است، همان سابقه‌ی R/Dart/Lua/CSS/Zig/Swift.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.perl")

_ENTRY_POINTS = ("bin/app.pl", "script/app.pl", "main.pl")


class PerlAnalyzer:
    name = "Perl"

    def matches(self, root: Path) -> bool:
        return (root / "cpanfile").is_file()

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).is_file()]

    async def run_tests(self, root: Path) -> CommandResult | None:
        tests_dir = root / "t"
        if not tests_dir.is_dir() or not any(tests_dir.glob("*.t")):
            return None
        if shutil.which("prove") is None:
            return make_command_result(
                "prove",
                127,
                "",
                0.0,
                skipped=True,
                skip_reason="prove not found in PATH",
            )
        logger.info("Running prove -r t")
        rc, out, dur = await run_cmd_async(["prove", "-r", "t"], root, LONG_CMD_TIMEOUT)
        return make_command_result("prove", rc, out, dur)

    async def run_quality(self, root: Path) -> list[CommandResult]:
        if shutil.which("perlcritic") is None:
            return [
                make_command_result(
                    "perlcritic",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="perlcritic not found in PATH",
                )
            ]
        logger.info("Running perlcritic .")
        rc, out, dur = await run_cmd_async(["perlcritic", "."], root, LONG_CMD_TIMEOUT)
        return [make_command_result("perlcritic", rc, out, dur)]

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
