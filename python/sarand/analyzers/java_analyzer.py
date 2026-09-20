"""Java/Kotlin analyzer: Maven or Gradle, whichever the project uses.

Prefers a project's own `./gradlew` wrapper over a system-wide `gradle`
when both could apply -- the wrapper pins the exact Gradle version the
project expects, a system install may not match.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.discovery.android import is_android_project
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.java")

_ENTRY_POINTS = ("src/main/java", "src/main/kotlin")


class JavaAnalyzer:
    name = "Java/Kotlin"

    def _build_tool(self, root: Path) -> str | None:
        if (root / "pom.xml").exists():
            return "maven"
        if (root / "build.gradle.kts").exists() or (root / "build.gradle").exists():
            return "gradle"
        return None

    def _gradle_invocation(self, root: Path) -> tuple[str, bool]:
        """Return (binary_or_wrapper_path, found) for Gradle."""
        wrapper = root / "gradlew"
        if wrapper.exists():
            return str(wrapper), True
        if shutil.which("gradle") is not None:
            return "gradle", True
        return "", False

    def matches(self, root: Path) -> bool:
        # Android projects are handled by AndroidAnalyzer instead --
        # its Gradle task names (testDebugUnitTest, lintDebug, ...)
        # differ from plain Java/Kotlin Gradle, and running both
        # analyzers on the same project would mean two conflicting sets
        # of test/lint commands. Kept as a one-line exclusion here
        # rather than merging the two analyzers -- see
        # android_analyzer.py's module docstring for the full reasoning.
        # پروژه‌های اندروید توسط AndroidAnalyzer مدیریت می‌شوند -- نام
        # تسک‌های Gradle آن (testDebugUnitTest، lintDebug، ...) با
        # Gradle خالص جاوا/کاتلین فرق دارد، و اجرای هر دو آنالایزر روی
        # یک پروژه یعنی دو دسته دستور تست/lint متناقض. این‌جا فقط یک
        # حذف یک‌خطی نگه داشته شده، نه ادغام دو آنالایزر -- استدلال
        # کامل در docstring ماژول android_analyzer.py است.
        if is_android_project(root):
            return False
        return self._build_tool(root) is not None

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).exists()]

    async def run_tests(self, root: Path) -> CommandResult | None:
        tool = self._build_tool(root)

        if tool == "maven":
            if shutil.which("mvn") is None:
                return make_command_result(
                    "mvn test",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="mvn not found in PATH",
                )
            logger.info("Running mvn -B test")
            rc, out, dur = await run_cmd_async(
                ["mvn", "-B", "test"], root, LONG_CMD_TIMEOUT
            )
            return make_command_result("mvn test", rc, out, dur)

        if tool == "gradle":
            binary, found = self._gradle_invocation(root)
            if not found:
                return make_command_result(
                    "gradle test",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="gradle not found in PATH and no ./gradlew wrapper present",
                )
            logger.info("Running %s test", binary)
            rc, out, dur = await run_cmd_async(
                [binary, "test", "--console=plain"], root, LONG_CMD_TIMEOUT
            )
            return make_command_result("gradle test", rc, out, dur)

        return None

    async def run_quality(self, root: Path) -> list[CommandResult]:
        tool = self._build_tool(root)
        results: list[CommandResult] = []

        if tool == "maven":
            if shutil.which("mvn") is None:
                return [
                    make_command_result(
                        "mvn checkstyle:check",
                        127,
                        "",
                        0.0,
                        skipped=True,
                        skip_reason="mvn not found in PATH",
                    )
                ]
            # Same ad-hoc-full-coordinate trick run_security already uses
            # for OWASP dependency-check below: invoking a plugin's goal
            # by its full groupId:artifactId:goal works even when the
            # project's own pom.xml never declared it, and Checkstyle's
            # bundled default ruleset (Sun conventions) means this is a
            # safe, meaningful default with zero project-specific config
            # required -- unlike Gradle below, where no such ad-hoc path
            # exists.
            #
            # همان ترفند مختصات-کامل-ad-hoc که run_security پایین‌تر
            # برای OWASP dependency-check دارد: فراخوانی goal یک پلاگین
            # با groupId:artifactId:goal کامل حتی وقتی pom.xml خودِ
            # پروژه هرگز آن را تعریف نکرده هم کار می‌کند، و ruleset
            # پیش‌فرض داخلیِ Checkstyle (قراردادهای Sun) یعنی این یک
            # پیش‌فرض امن و معنادار است بدون نیاز به هیچ کانفیگ
            # مخصوص پروژه -- برخلاف Gradle پایین‌تر، جایی که چنین
            # مسیر ad-hoc‌ای اصلاً وجود ندارد.
            rc, out, dur = await run_cmd_async(
                ["mvn", "-B", "org.apache.maven.plugins:maven-checkstyle-plugin:check"],
                root,
                LONG_CMD_TIMEOUT,
            )
            results.append(make_command_result("mvn checkstyle:check", rc, out, dur))

            rc, out, dur = await run_cmd_async(
                ["mvn", "-B", "com.github.spotbugs:spotbugs-maven-plugin:check"],
                root,
                LONG_CMD_TIMEOUT,
            )
            results.append(make_command_result("mvn spotbugs:check", rc, out, dur))
            return results

        if tool == "gradle":
            binary, found = self._gradle_invocation(root)
            if not found:
                return [
                    make_command_result(
                        "gradle checkstyleMain/spotbugsMain",
                        127,
                        "",
                        0.0,
                        skipped=True,
                        skip_reason=(
                            "gradle not found in PATH and no ./gradlew wrapper present"
                        ),
                    )
                ]
            # Gradle has no equivalent of Maven's "invoke an undeclared
            # plugin by full coordinate" -- a task only exists if the
            # project's own build.gradle(.kts) applied the plugin. So,
            # unlike Maven above, this is genuinely gated on a real
            # project marker (§4.3): grep the build file for the plugin
            # id before ever trying to run its task, rather than letting
            # gradle fail with "task not found" for every project that
            # doesn't happen to use these two plugins.
            #
            # Gradle معادلی برای «فراخوانی یک پلاگین اعلام‌نشده با
            # مختصات کامل»ی Maven ندارد -- یک تسک فقط وقتی وجود دارد که
            # build.gradle(.kts) خودِ پروژه آن پلاگین را apply کرده
            # باشد. پس، برخلاف Maven بالا، این واقعاً روی یک نشانگر
            # واقعی پروژه gate شده (§4.3): قبل از هر تلاشی برای اجرای
            # تسکش، فایل build را برای شناسه‌ی پلاگین grep می‌کنیم، به‌جای
            # اینکه بگذاریم gradle برای هر پروژه‌ای که این دو پلاگین را
            # ندارد با «task not found» شکست بخورد.
            build_file = root / "build.gradle.kts"
            if not build_file.is_file():
                build_file = root / "build.gradle"
            try:
                build_text = build_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                build_text = ""

            if "checkstyle" in build_text:
                rc, out, dur = await run_cmd_async(
                    [binary, "checkstyleMain", "--console=plain"],
                    root,
                    LONG_CMD_TIMEOUT,
                )
                results.append(
                    make_command_result("gradle checkstyleMain", rc, out, dur)
                )
            else:
                results.append(
                    make_command_result(
                        "gradle checkstyleMain",
                        0,
                        "",
                        0.0,
                        skipped=True,
                        skip_reason=(
                            "checkstyle plugin not applied in build.gradle(.kts)"
                        ),
                    )
                )

            if "spotbugs" in build_text:
                rc, out, dur = await run_cmd_async(
                    [binary, "spotbugsMain", "--console=plain"],
                    root,
                    LONG_CMD_TIMEOUT,
                )
                results.append(make_command_result("gradle spotbugsMain", rc, out, dur))
            else:
                results.append(
                    make_command_result(
                        "gradle spotbugsMain",
                        0,
                        "",
                        0.0,
                        skipped=True,
                        skip_reason="spotbugs plugin not applied in build.gradle(.kts)",
                    )
                )
            return results

        return []

    async def run_security(self, root: Path) -> list[CommandResult]:
        tool = self._build_tool(root)

        if tool == "maven":
            if shutil.which("mvn") is None:
                return [
                    make_command_result(
                        "mvn dependency-check",
                        127,
                        "",
                        0.0,
                        skipped=True,
                        skip_reason="mvn not found in PATH",
                    )
                ]
            # Runs the OWASP dependency-check plugin ad-hoc via its full
            # coordinate, without requiring it to be pre-declared in
            # pom.xml. First run needs network access to fetch the plugin.
            # پلاگین OWASP dependency-check را به‌صورت ad-hoc از طریق
            # مختصات کامل اجرا می‌کند، بدون نیاز به تعریف قبلی در pom.xml.
            # اجرای اول به دسترسی اینترنت برای دریافت پلاگین نیاز دارد.
            rc, out, dur = await run_cmd_async(
                ["mvn", "-B", "org.owasp:dependency-check-maven:check"],
                root,
                LONG_CMD_TIMEOUT,
            )
            return [make_command_result("mvn dependency-check", rc, out, dur)]

        if tool == "gradle":
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
            rc, out, dur = await run_cmd_async(
                [binary, "dependencyCheckAnalyze", "--console=plain"],
                root,
                LONG_CMD_TIMEOUT,
            )
            return [make_command_result("gradle dependencyCheckAnalyze", rc, out, dur)]

        return []
