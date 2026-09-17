"""XML analyzer: xmllint --noout, gated on a top-level *.xml file.

A format analyzer, not a language analyzer: no run_tests, and no
run_security (no broadly standard XML vulnerability-audit tool) --
same honest-empty shape as YamlAnalyzer/JsonAnalyzer/TomlAnalyzer.
Matches independently of whatever other analyzer also claims the same
file for a different purpose (e.g. JavaAnalyzer already runs against
pom.xml) -- same complementary-match precedent as YamlAnalyzer/
TomlAnalyzer. `xmllint` ships with libxml2, which is already present
on most Linux systems (Kali/Arch included), unlike the npm/pip/cargo-
installed tools most other analyzers depend on.

آنالایزر XML: xmllint --noout، فقط وقتی یک فایل *.xml سطح-ریشه وجود
داشته باشد.

یک آنالایزر فرمت است، نه زبان: بدون run_tests، و بدون run_security
(بدون ابزار audit آسیب‌پذیریِ به‌طور گسترده استاندارد برای XML) -- همان
شکل خالیِ صادقانه‌ی YamlAnalyzer/JsonAnalyzer/TomlAnalyzer. مستقل از هر
آنالایزر دیگری که همان فایل را برای هدف دیگری claim می‌کند تطابق پیدا
می‌کند (مثلاً JavaAnalyzer از قبل روی pom.xml اجرا می‌شود) -- همان
سابقه‌ی تطابقِ مکملِ YamlAnalyzer/TomlAnalyzer. `xmllint` همراه libxml2
می‌آید که از قبل روی اکثر سیستم‌های لینوکس (شامل Kali/Arch) نصب است،
برخلاف اکثر ابزارهای دیگرِ آنالایزرها که با npm/pip/cargo نصب می‌شوند.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.xml")

_ENTRY_POINTS = ("pom.xml",)


def _top_level_xml_files(root: Path) -> list[Path]:
    try:
        return sorted(
            p for p in root.iterdir() if p.is_file() and p.suffix.lower() == ".xml"
        )
    except OSError:
        return []


class XmlAnalyzer:
    name = "XML"

    def matches(self, root: Path) -> bool:
        return bool(_top_level_xml_files(root))

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).is_file()]

    async def run_tests(self, root: Path) -> CommandResult | None:
        return None

    async def run_quality(self, root: Path) -> list[CommandResult]:
        files = _top_level_xml_files(root)
        xmllint = shutil.which("xmllint")
        if xmllint is None:
            return [
                make_command_result(
                    "xmllint --noout",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="xmllint not found in PATH",
                )
            ]
        rc, out, dur = await run_cmd_async(
            [xmllint, "--noout", *(str(p.name) for p in files)],
            root,
            LONG_CMD_TIMEOUT,
        )
        return [make_command_result("xmllint --noout", rc, out, dur)]

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
