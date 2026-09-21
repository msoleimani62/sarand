"""GitHub Actions analyzer: actionlint on `.github/workflows/*.yml|yaml`.

Matches when the project has workflow files. The workflow paths are passed
to actionlint explicitly (relative to the project root), so it does not
depend on actionlint finding a git repository. Nothing is ever executed
from the workflows; actionlint only parses them. The generic YAML analyzer
also lints these files for syntax -- this one checks what YAML tooling
cannot: expressions, contexts, action inputs, shell scripts in `run:`.

تحلیل‌گر GitHub Actions: actionlint روی `.github/workflows/*.yml|yaml`.

وقتی پروژه فایل workflow داشته باشد match می‌شود. مسیر workflow ها صریحاً
(نسبت به ریشه‌ی پروژه) به actionlint داده می‌شود، پس به پیداکردن یک git repo
توسط actionlint وابسته نیست. هیچ چیز از workflow ها اجرا نمی‌شود؛ actionlint
فقط آن‌ها را parse می‌کند. آنالایزر عمومی YAML هم سینتکس این فایل‌ها را lint
می‌کند -- این یکی چیزی را بررسی می‌کند که ابزار YAML نمی‌تواند: expression ها،
context ها، ورودی action ها و اسکریپت‌های shell داخل `run:`.
"""

from __future__ import annotations

from pathlib import Path

from sarand.analyzers._tooling import run_tool
from sarand.models.results import CommandResult


def _workflows(root: Path) -> list[str]:
    directory = root / ".github" / "workflows"
    try:
        return sorted(
            f".github/workflows/{entry.name}"
            for entry in directory.iterdir()
            if entry.is_file() and entry.suffix.lower() in {".yml", ".yaml"}
        )
    except OSError:
        return []


class GitHubActionsAnalyzer:
    name = "GitHub Actions"

    def matches(self, root: Path) -> bool:
        return bool(_workflows(root))

    def entry_points(self, root: Path) -> list[str]:
        return _workflows(root)

    async def run_tests(self, root: Path) -> CommandResult | None:
        return None

    async def run_quality(self, root: Path) -> list[CommandResult]:
        return [
            await run_tool(
                root, "actionlint", ["actionlint", "-no-color", *_workflows(root)]
            )
        ]

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
