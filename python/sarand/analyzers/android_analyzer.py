"""Android/Kotlin analyzer: Gradle-based Android app/library modules.

Takes priority over the generic JavaAnalyzer for Android projects (see
is_android_project() and JavaAnalyzer.matches()'s exclusion of it).
Android's test/quality/security task names differ enough from plain
Java/Kotlin Gradle (build-variant-qualified task names, instrumented
tests that need a running device, Android Lint instead of a generic
linter) that folding this into JavaAnalyzer would mean guessing at the
wrong task names for both Android and non-Android Gradle projects.

آنالایزر اختصاصی Android/Kotlin: ماژول‌های app/library مبتنی بر Gradle.
برای پروژه‌های اندروید نسبت به JavaAnalyzer عمومی اولویت دارد. نام
تسک‌های تست/کیفیت/امنیت اندروید آن‌قدر با Gradle خالص جاوا/کاتلین فرق
دارد (نام تسک وابسته به build variant، تست‌های instrumented که به
دستگاه در حال اجرا نیاز دارند، Android Lint به‌جای یک linter عمومی)
که ادغام این منطق در JavaAnalyzer یعنی حدس زدن نام تسک اشتباه هم برای
پروژه‌های اندروید و هم غیراندروید.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.discovery.android import is_android_project
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.android")

_ENTRY_POINTS = (
    "app/src/main/AndroidManifest.xml",
    "AndroidManifest.xml",
    "app/src/main/java",
    "app/src/main/kotlin",
)


class AndroidAnalyzer:
    name = "Android/Kotlin"

    def matches(self, root: Path) -> bool:
        return is_android_project(root)

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).exists()]

    def _gradle_invocation(self, root: Path) -> tuple[str, bool]:
        """Return (binary_or_wrapper_path, found). Prefers the project's
        own ./gradlew wrapper -- it pins the exact Gradle/AGP version the
        project expects, a system-wide `gradle` may not match."""
        wrapper = root / "gradlew"
        if wrapper.exists():
            return str(wrapper), True
        if shutil.which("gradle") is not None:
            return "gradle", True
        return "", False

    async def run_tests(self, root: Path) -> CommandResult | None:
        binary, found = self._gradle_invocation(root)
        if not found:
            return make_command_result(
                "gradle testDebugUnitTest",
                127,
                "",
                0.0,
                skipped=True,
                skip_reason="gradle not found in PATH and no ./gradlew wrapper present",
            )

        # Only unit tests. Instrumented tests (connectedAndroidTest) need
        # a running emulator/device, which sarand never assumes exists --
        # running them unconditionally would just be a confusing failure,
        # not a useful signal.
        # فقط تست‌های واحد. تست‌های instrumented (connectedAndroidTest) به
        # یک شبیه‌ساز/دستگاه در حال اجرا نیاز دارند که sarand هرگز فرض
        # نمی‌کند وجود دارد -- اجرای بی‌قیدوشرط آن‌ها فقط یک شکست
        # گیج‌کننده است، نه یک سیگنال مفید.
        logger.info("Running %s testDebugUnitTest", binary)
        rc, out, dur = await run_cmd_async([binary, "testDebugUnitTest", "--console=plain"], root, LONG_CMD_TIMEOUT)

        if rc != 0 and "not found in root project" in out:
            # Some modules don't have a "debug" build type under that
            # exact task name (custom build-variant setups) -- fall back
            # to the generic 'test' task, which Gradle aggregates across
            # whatever variants actually exist.
            # برخی ماژول‌ها دقیقاً همین نام تسک برای build type دیباگ را
            # ندارند (تنظیمات سفارشی build variant) -- به تسک عمومی
            # 'test' برمی‌گردیم که Gradle آن را روی هر واریانتی که
            # واقعاً وجود دارد جمع می‌کند.
            logger.info("testDebugUnitTest not found, falling back to generic 'test' task")
            rc, out, dur = await run_cmd_async([binary, "test", "--console=plain"], root, LONG_CMD_TIMEOUT)
            return make_command_result("gradle test", rc, out, dur)

        return make_command_result("gradle testDebugUnitTest", rc, out, dur)

    async def run_quality(self, root: Path) -> list[CommandResult]:
        binary, found = self._gradle_invocation(root)
        if not found:
            return [
                make_command_result(
                    "gradle lint",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="gradle not found in PATH and no ./gradlew wrapper present",
                )
            ]

        logger.info("Running %s lintDebug", binary)
        rc, out, dur = await run_cmd_async([binary, "lintDebug", "--console=plain"], root, LONG_CMD_TIMEOUT)
        if rc != 0 and "not found in root project" in out:
            rc, out, dur = await run_cmd_async([binary, "lint", "--console=plain"], root, LONG_CMD_TIMEOUT)
            return [make_command_result("gradle lint", rc, out, dur)]
        return [make_command_result("gradle lintDebug", rc, out, dur)]

    async def run_security(self, root: Path) -> list[CommandResult]:
        binary, found = self._gradle_invocation(root)
        if not found:
            return [
                make_command_result(
                    "gradle dependencyCheckAnalyze",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="gradle not found in PATH and no ./gradlew wrapper present",
                )
            ]
        rc, out, dur = await run_cmd_async([binary, "dependencyCheckAnalyze", "--console=plain"], root, LONG_CMD_TIMEOUT)
        return [make_command_result("gradle dependencyCheckAnalyze", rc, out, dur)]
