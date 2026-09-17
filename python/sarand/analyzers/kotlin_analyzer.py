"""Kotlin analyzer: ktlint + detekt, gated on a Kotlin Gradle project.

Deliberately does not run `gradlew test`/`mvn test` itself -- that
stays JavaAnalyzer's job. Both analyzers match the same Kotlin project
simultaneously rather than one replacing the other, the same way
TypeScriptAnalyzer/NodeAnalyzer do; this analyzer's entire
contribution is quality. JavaAnalyzer's own run_quality deliberately
returns [] because checkstyle/ktlint/spotless configs vary too much to
guess safely at the Java/Kotlin level -- but ktlint and detekt
specifically are close to de-facto standard for Kotlin, so this
analyzer runs them when present rather than leaving Kotlin-specific
quality unaddressed.

Detection note: `build.gradle.kts` strictly means "this build script
is written in the Kotlin DSL", not "this project's application code is
Kotlin" -- a pure-Java project can use the Kotlin DSL for its build
file alone. In practice the two correlate heavily enough that this is
an acceptable heuristic (the same shallow-heuristic tradeoff
CssAnalyzer/LuaAnalyzer already make), not a claim of certainty.

آنالایزر Kotlin: ktlint + detekt، فقط وقتی پروژه‌ی Gradle از Kotlin
استفاده کند.

عمداً خودش `gradlew test`/`mvn test` را اجرا نمی‌کند -- آن همچنان کار
JavaAnalyzer است. هر دو آنالایزر هم‌زمان روی یک پروژه‌ی Kotlin تطابق
پیدا می‌کنند، نه این‌که یکی جای دیگری بنشیند، دقیقاً همان‌طور که
TypeScriptAnalyzer/NodeAnalyzer این کار را می‌کنند؛ کل سهم این
آنالایزر quality است. خودِ run_quality در JavaAnalyzer عمداً [] برمی‌گرداند
چون کانفیگ‌های checkstyle/ktlint/spotless بین پروژه‌ها آن‌قدر متفاوت‌اند
که حدس زدنشان ایمن نیست -- اما ktlint و detekt مشخصاً تقریباً استاندارد
بلامنازع Kotlin هستند، پس این آنالایزر وقتی موجود باشند اجرایشان می‌کند
تا quality مخصوص Kotlin بی‌جواب نماند.

نکته‌ی تشخیص: `build.gradle.kts` دقیقاً یعنی «اسکریپت build با
Kotlin DSL نوشته شده»، نه «کد اپلیکیشن این پروژه Kotlin است» -- یک
پروژه‌ی خالص Java می‌تواند فقط برای فایل build خودش از Kotlin DSL
استفاده کند. در عمل این دو آن‌قدر هم‌بستگی دارند که این یک heuristic
قابل‌قبول است (همان معامله‌ی heuristicِ کم‌عمق که CssAnalyzer/LuaAnalyzer
از قبل می‌کنند)، نه ادعای قطعیت.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.kotlin")

_ENTRY_POINTS = ("src/main/kotlin",)
_KOTLIN_PLUGIN_MARKERS = (
    "org.jetbrains.kotlin",
    "kotlin-gradle-plugin",
    "'kotlin'",
    '"kotlin"',
)


def _is_kotlin_project(root: Path) -> bool:
    if (root / "build.gradle.kts").is_file():
        return True
    gradle_file = root / "build.gradle"
    if not gradle_file.is_file():
        return False
    try:
        text = gradle_file.read_text(errors="replace")
    except OSError:
        return False
    return any(marker in text for marker in _KOTLIN_PLUGIN_MARKERS)


class KotlinAnalyzer:
    name = "Kotlin"

    def matches(self, root: Path) -> bool:
        return _is_kotlin_project(root)

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).exists()]

    async def run_tests(self, root: Path) -> CommandResult | None:
        # Test execution is JavaAnalyzer's job (mvn/gradle test) -- see
        # the module docstring.
        return None

    async def run_quality(self, root: Path) -> list[CommandResult]:
        results: list[CommandResult] = []

        ktlint = shutil.which("ktlint")
        if ktlint is None:
            results.append(
                make_command_result(
                    "ktlint",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="ktlint not found in PATH",
                )
            )
        else:
            logger.info("Running ktlint")
            rc, out, dur = await run_cmd_async([ktlint], root, LONG_CMD_TIMEOUT)
            results.append(make_command_result("ktlint", rc, out, dur))

        detekt = shutil.which("detekt")
        if detekt is None:
            results.append(
                make_command_result(
                    "detekt",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="detekt not found in PATH",
                )
            )
        else:
            logger.info("Running detekt")
            rc, out, dur = await run_cmd_async([detekt], root, LONG_CMD_TIMEOUT)
            results.append(make_command_result("detekt", rc, out, dur))

        return results

    async def run_security(self, root: Path) -> list[CommandResult]:
        # Dependency auditing is JavaAnalyzer's job (OWASP
        # dependency-check via mvn/gradle).
        return []
