"""Markdown analyzer: markdownlint, gated on a top-level *.md file.

A format analyzer, not a language analyzer -- same shape as
YamlAnalyzer/JsonAnalyzer/TomlAnalyzer/XmlAnalyzer: no run_tests (no
executable-test concept for prose), no run_security (no broadly
standard Markdown vulnerability-audit tool), honest empty for both.
Added specifically because README/documentation quality matters for a
tool whose own primary output (--full reports) is meant to be read by
both humans and AI models -- see AGENTS.md §5.10's P0 list.

Matches independently of whatever else claims the same file: a
top-level README.md is documentation for every other analyzer in this
project, and linting its Markdown syntax/style is a separate,
complementary concern, same precedent as YamlAnalyzer matching
docker-compose.yml independently of whatever else uses it.

آنالایزر Markdown: markdownlint، فقط وقتی یک فایل *.md سطح-ریشه وجود
داشته باشد.

یک آنالایزر فرمت است، نه زبان -- همان شکل YamlAnalyzer/JsonAnalyzer/
TomlAnalyzer/XmlAnalyzer: بدون run_tests (بدون مفهوم test قابل‌اجرا
برای نثر)، بدون run_security (بدون ابزار audit آسیب‌پذیریِ به‌طور
گسترده استاندارد برای Markdown)، هر دو خالیِ صادقانه. مشخصاً به این
دلیل اضافه شده که کیفیت README/documentation برای ابزاری که خروجی
اصلی خودش (گزارش‌های --full) قرار است هم توسط انسان هم مدل‌های AI
خوانده شود اهمیت دارد -- لیست P0 در §5.10 از AGENTS.md را ببینید.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.markdown")

_ENTRY_POINTS = ("README.md", "CHANGELOG.md", "CONTRIBUTING.md")
_MARKDOWN_EXTENSIONS = (".md", ".markdown")


def _top_level_markdown_files(root: Path) -> list[Path]:
    try:
        return sorted(
            p
            for p in root.iterdir()
            if p.is_file() and p.suffix.lower() in _MARKDOWN_EXTENSIONS
        )
    except OSError:
        return []


class MarkdownAnalyzer:
    name = "Markdown"

    def matches(self, root: Path) -> bool:
        return bool(_top_level_markdown_files(root))

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).is_file()]

    async def run_tests(self, root: Path) -> CommandResult | None:
        return None

    async def run_quality(self, root: Path) -> list[CommandResult]:
        files = _top_level_markdown_files(root)
        if shutil.which("markdownlint") is None:
            return [
                make_command_result(
                    "markdownlint",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason=(
                        "markdownlint not installed (npm install -g markdownlint-cli)"
                    ),
                )
            ]
        rc, out, dur = await run_cmd_async(
            ["markdownlint", *(str(p.name) for p in files)], root, LONG_CMD_TIMEOUT
        )
        return [make_command_result("markdownlint", rc, out, dur)]

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
