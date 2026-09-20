"""Groovy analyzer: complementary match on a Gradle project that
actually contains Groovy source, quality-only via CodeNarc.

Same shape as KotlinAnalyzer's relationship to JavaAnalyzer: Gradle
project detection and test execution (`./gradlew test` / `gradle
test`) are JavaAnalyzer's job already -- this analyzer only adds a
second, complementary signal (native Groovy source actually present,
not just a build.gradle written in the Groovy DSL, which nearly every
Gradle project has regardless of source language) and a
Groovy-specific quality check. run_tests and run_security are
deliberately no-ops for the same reason KotlinAnalyzer's are.

آنالایزر Groovy: تطابقِ مکمل روی یک پروژه‌ی Gradle که واقعاً سورس
Groovy دارد، فقط quality از طریق CodeNarc.

همان شکل رابطه‌ی KotlinAnalyzer با JavaAnalyzer: تشخیص پروژه‌ی Gradle
و اجرای تست (`./gradlew test` / `gradle test`) از قبل کار JavaAnalyzer
است -- این آنالایزر فقط یک سیگنال دوم و مکمل اضافه می‌کند (سورس بومیِ
Groovy واقعاً موجود باشد، نه فقط یک build.gradle که با DSL گروویی
نوشته شده -- چیزی که تقریباً هر پروژه‌ی Gradle، فارغ از زبان سورس،
دارد) و یک چک کیفیتِ مخصوص Groovy. run_tests و run_security عمداً
no-op هستند، به همان دلیلی که در KotlinAnalyzer no-op‌اند.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.groovy")

_GRADLE_MARKERS = ("build.gradle", "build.gradle.kts")


def _has_groovy_source(root: Path) -> bool:
    if (root / "src" / "main" / "groovy").is_dir():
        return True
    try:
        return any(root.glob("*.groovy")) or any(root.glob("src/**/*.groovy"))
    except OSError:
        return False


class GroovyAnalyzer:
    name = "Groovy"

    def matches(self, root: Path) -> bool:
        has_gradle = any((root / marker).is_file() for marker in _GRADLE_MARKERS)
        return has_gradle and _has_groovy_source(root)

    def entry_points(self, root: Path) -> list[str]:
        ep = root / "src" / "main" / "groovy"
        return [ep.relative_to(root).as_posix()] if ep.is_dir() else []

    async def run_tests(self, root: Path) -> CommandResult | None:
        # Delegated to JavaAnalyzer's ./gradlew test / gradle test --
        # same reasoning as KotlinAnalyzer.
        return None

    async def run_quality(self, root: Path) -> list[CommandResult]:
        if shutil.which("codenarc") is None:
            return [
                make_command_result(
                    "codenarc",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="codenarc not found in PATH",
                )
            ]
        logger.info("Running codenarc")
        rc, out, dur = await run_cmd_async(
            ["codenarc", "-basedir", "."], root, LONG_CMD_TIMEOUT
        )
        return [make_command_result("codenarc", rc, out, dur)]

    async def run_security(self, root: Path) -> list[CommandResult]:
        # Dependency auditing is Gradle/Java's job already -- same
        # reasoning as KotlinAnalyzer.
        return []
