"""Scala analyzer: `sbt test` and scalafmt (when the project opted in).

Matches on a root-level `build.sbt`. sbt runs with `-batch` so it can never
stop at an interactive prompt (an unattended scan would otherwise hang).
`scalafmtCheckAll` is an sbt *plugin* task: it only exists when
`project/plugins.sbt` names `sbt-scalafmt`, so it is only run then --
otherwise sbt fails with "not a valid command" and the report would blame
the project for a check it never adopted.

تحلیل‌گر Scala: `sbt test` و scalafmt (وقتی پروژه انتخابش کرده باشد).

روی `build.sbt` در ریشه match می‌شود. sbt با `-batch` اجرا می‌شود تا هرگز
روی یک prompt تعاملی متوقف نشود (وگرنه یک اسکن بدون مراقبت گیر می‌کرد).
`scalafmtCheckAll` یک task از *پلاگین* sbt است: فقط وقتی وجود دارد که
`project/plugins.sbt` اسم `sbt-scalafmt` را ببرد، پس فقط آن‌وقت اجرا می‌شود --
وگرنه sbt با «not a valid command» شکست می‌خورد و گزارش پروژه را به‌خاطر
چکی که هرگز نپذیرفته مقصر می‌کرد.
"""

from __future__ import annotations

from pathlib import Path

from sarand.analyzers._tooling import existing, read_text_safely, run_tool
from sarand.models.results import CommandResult


class ScalaAnalyzer:
    name = "Scala"

    def matches(self, root: Path) -> bool:
        return (root / "build.sbt").is_file()

    def entry_points(self, root: Path) -> list[str]:
        return existing(root, ("build.sbt", "src/main/scala"))

    async def run_tests(self, root: Path) -> CommandResult | None:
        return await run_tool(root, "sbt test", ["sbt", "-batch", "test"])

    async def run_quality(self, root: Path) -> list[CommandResult]:
        if "sbt-scalafmt" not in read_text_safely(root / "project" / "plugins.sbt"):
            return []
        return [
            await run_tool(
                root, "sbt scalafmtCheckAll", ["sbt", "-batch", "scalafmtCheckAll"]
            )
        ]

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
