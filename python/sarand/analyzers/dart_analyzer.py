"""Dart/Flutter analyzer: dart/flutter test + analyze, gated on a
real pubspec.yaml.

A Flutter project is still a Dart project (same pubspec.yaml marker),
but needs the `flutter` command instead of bare `dart` for test/analyze
to correctly pick up widget-test bindings and Flutter-specific lints.
Detected via a `flutter:` dependency entry in pubspec.yaml, not just
the presence of the `flutter` binary (a machine could have Flutter
installed without this particular project using it).

No `run_security` tool: unlike npm/cargo/pip/composer/bundler, the
Dart/Flutter ecosystem doesn't yet have a broadly standard
vulnerability-database audit command as of this writing -- returning
an empty list here is honest about that rather than reaching for
something that doesn't fit (same precedent as LuaAnalyzer).

آنالایزر Dart/Flutter: تست/analyze با dart یا flutter، فقط وقتی
pubspec.yaml واقعی وجود داشته باشد.

یک پروژه‌ی Flutter همچنان یک پروژه‌ی Dart است (همان نشانگر
pubspec.yaml)، اما برای تست/analyze به دستور `flutter` نیاز دارد نه
`dart` خام، تا بایندینگ‌های widget-test و lintهای مخصوص Flutter را
درست تشخیص دهد. تشخیص از طریق یک ورودی وابستگی `flutter:` در
pubspec.yaml است، نه صرفاً وجود باینری `flutter` (یک ماشین می‌تواند
Flutter نصب داشته باشد بدون این‌که همین پروژه خاص از آن استفاده کند).

بدون ابزار run_security: برخلاف npm/cargo/pip/composer/bundler،
اکوسیستم Dart/Flutter تا زمان نوشتن این کد هنوز یک دستور audit
پایگاه‌داده‌ی آسیب‌پذیریِ به‌طور گسترده استاندارد ندارد -- برگرداندن یک
لیست خالی اینجا صادقانه است به‌جای دست‌بردن به چیزی که تناسب ندارد
(همان سابقه‌ی LuaAnalyzer).
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.dart")

_ENTRY_POINTS = ("lib/main.dart", "bin/main.dart")
_FLUTTER_DEPENDENCY_RE = re.compile(r"^\s*flutter\s*:\s*$", re.MULTILINE)


def _is_flutter_project(root: Path) -> bool:
    try:
        text = (root / "pubspec.yaml").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return bool(_FLUTTER_DEPENDENCY_RE.search(text))


class DartAnalyzer:
    name = "Dart"

    def matches(self, root: Path) -> bool:
        return (root / "pubspec.yaml").is_file()

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).is_file()]

    def _tool(self, root: Path) -> str | None:
        if _is_flutter_project(root) and shutil.which("flutter") is not None:
            return "flutter"
        if shutil.which("dart") is not None:
            return "dart"
        return None

    async def run_tests(self, root: Path) -> CommandResult | None:
        tool = self._tool(root)
        if tool is None:
            return make_command_result(
                "dart test",
                127,
                "",
                0.0,
                skipped=True,
                skip_reason="neither flutter nor dart found in PATH",
            )
        logger.info("Running %s test", tool)
        rc, output, duration = await run_cmd_async(
            [tool, "test"], root, LONG_CMD_TIMEOUT
        )
        return make_command_result(f"{tool} test", rc, output, duration)

    async def run_quality(self, root: Path) -> list[CommandResult]:
        tool = self._tool(root)
        if tool is None:
            return [
                make_command_result(
                    "dart analyze",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="neither flutter nor dart found in PATH",
                )
            ]
        rc, out, dur = await run_cmd_async([tool, "analyze"], root, LONG_CMD_TIMEOUT)
        return [make_command_result(f"{tool} analyze", rc, out, dur)]

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
