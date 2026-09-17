"""YAML analyzer: yamllint, gated on a top-level *.yml/*.yaml file.

A format analyzer, not a language analyzer: no run_tests (no
executable-test concept for a data format) and no run_security (no
broadly standard YAML vulnerability-audit tool) -- same honest-empty
shape as CssAnalyzer/SqlAnalyzer. Matches independently of whatever
other analyzer also claims the same file for a different purpose (e.g.
DartAnalyzer already runs against pubspec.yaml) -- linting its YAML
syntax is a separate, complementary concern, the same way
TypeScriptAnalyzer/NodeAnalyzer both match one TS project.

آنالایزر YAML: yamllint، فقط وقتی یک فایل *.yml/*.yaml سطح-ریشه وجود
داشته باشد.

یک آنالایزر فرمت است، نه زبان: بدون run_tests (بدون مفهوم test
قابل‌اجرا برای یک فرمت داده) و بدون run_security (بدون ابزار audit
آسیب‌پذیریِ به‌طور گسترده استاندارد برای YAML) -- همان شکل خالیِ صادقانه‌ی
CssAnalyzer/SqlAnalyzer. مستقل از هر آنالایزر دیگری که همان فایل را
برای هدف دیگری claim می‌کند تطابق پیدا می‌کند (مثلاً DartAnalyzer از قبل
روی pubspec.yaml اجرا می‌شود) -- لینت کردن syntax YAML آن یک دغدغه‌ی
جدا و مکمل است، دقیقاً همان‌طور که TypeScriptAnalyzer/NodeAnalyzer هر
دو روی یک پروژه‌ی TS تطابق پیدا می‌کنند.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.yaml")

_ENTRY_POINTS = ("docker-compose.yml", "docker-compose.yaml")
_YAML_EXTENSIONS = (".yml", ".yaml")


def _top_level_yaml_files(root: Path) -> list[Path]:
    try:
        return sorted(
            p
            for p in root.iterdir()
            if p.is_file() and p.suffix.lower() in _YAML_EXTENSIONS
        )
    except OSError:
        return []


class YamlAnalyzer:
    name = "YAML"

    def matches(self, root: Path) -> bool:
        return bool(_top_level_yaml_files(root))

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).is_file()]

    async def run_tests(self, root: Path) -> CommandResult | None:
        return None

    async def run_quality(self, root: Path) -> list[CommandResult]:
        files = _top_level_yaml_files(root)
        if shutil.which("yamllint") is None:
            return [
                make_command_result(
                    "yamllint",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="yamllint not found in PATH",
                )
            ]
        rc, out, dur = await run_cmd_async(
            ["yamllint", *(str(p.name) for p in files)], root, LONG_CMD_TIMEOUT
        )
        return [make_command_result("yamllint", rc, out, dur)]

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
