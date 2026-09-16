"""CSS analyzer: stylelint, gated on real CSS/SCSS/Less project markers.

Detection deliberately mirrors LuaAnalyzer's shallow, deterministic
check (a stylelint config file, or a top-level stylesheet) rather than
a deep recursive scan, so vendored or unrelated nested stylesheets
don't force a project-level match. Independent of NodeAnalyzer/
TypeScriptAnalyzer: a plain static-site CSS project with no
package.json at all still gets picked up.

No `run_tests`: CSS has no established concept of an executable test
suite. No `run_security` either: no broadly standard CSS
vulnerability-audit tool exists as of this writing -- returning an
empty list here is honest about that rather than reaching for
something that doesn't fit (same precedent as DartAnalyzer/LuaAnalyzer).

آنالایزر CSS: stylelint، فقط وقتی نشانگر واقعی پروژه CSS/SCSS/Less
باشد.

تشخیص عمداً همان بررسیِ کم‌عمق و قطعیِ LuaAnalyzer را تکرار می‌کند
(یک فایل کانفیگ stylelint، یا یک stylesheet سطح-ریشه) به‌جای یک اسکن
بازگشتیِ عمیق، تا stylesheetهای تودرتوی vendored یا نامرتبط، تطابق در
سطح پروژه را اجباری نکنند. مستقل از NodeAnalyzer/TypeScriptAnalyzer
است: یک پروژه‌ی سایت استاتیک ساده‌ی CSS بدون هیچ package.json هم
تشخیص داده می‌شود.

بدون run_tests: CSS مفهوم جاافتاده‌ای از یک test suite قابل‌اجرا
ندارد. بدون run_security هم: تا زمان نوشتن این کد هیچ ابزار audit
آسیب‌پذیریِ به‌طور گسترده استاندارد برای CSS وجود ندارد -- برگرداندن
یک لیست خالی اینجا صادقانه است به‌جای دست‌بردن به چیزی که تناسب ندارد
(همان سابقه‌ی DartAnalyzer/LuaAnalyzer).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.css")

_ENTRY_POINTS = ("index.css", "style.css", "src/style.css", "src/styles/main.css")
_STYLE_EXTENSIONS = (".css", ".scss", ".less")
_CONFIG_FILES = (
    ".stylelintrc",
    ".stylelintrc.json",
    ".stylelintrc.yaml",
    ".stylelintrc.yml",
    ".stylelintrc.js",
    "stylelint.config.js",
)


def _local_or_global_stylelint(root: Path) -> str | None:
    """Prefer `node_modules/.bin/stylelint` (npm-installed, version-pinned
    for this project) over a global `stylelint` binary of the same name."""
    local = root / "node_modules" / ".bin" / "stylelint"
    if local.is_file():
        return str(local)
    return shutil.which("stylelint")


class CssAnalyzer:
    name = "CSS"

    def matches(self, root: Path) -> bool:
        """Return True when the tree looks like a CSS/SCSS/Less project.

        Detection is intentionally shallow and deterministic:
        1. a stylelint config file
        2. a top-level stylesheet file

        Deep recursive scans are avoided so vendored or unrelated nested
        stylesheets do not force a project-level match.
        """
        try:
            for name in _CONFIG_FILES:
                if (root / name).is_file():
                    return True

            for path in root.iterdir():
                if path.is_file() and path.suffix.lower() in _STYLE_EXTENSIONS:
                    return True
        except OSError:
            return False

        return False

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).is_file()]

    async def run_tests(self, root: Path) -> CommandResult | None:
        return None

    async def run_quality(self, root: Path) -> list[CommandResult]:
        stylelint = _local_or_global_stylelint(root)
        if stylelint is None:
            return [
                make_command_result(
                    "stylelint",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason=(
                        "stylelint not found (node_modules/.bin/stylelint or global)"
                    ),
                )
            ]
        logger.info("Running %s **/*.{css,scss,less}", stylelint)
        rc, out, dur = await run_cmd_async(
            [stylelint, "**/*.{css,scss,less}"], root, LONG_CMD_TIMEOUT
        )
        return [make_command_result("stylelint", rc, out, dur)]

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
