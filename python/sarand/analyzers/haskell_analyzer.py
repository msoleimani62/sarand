"""Haskell analyzer: `stack test` / `cabal test`, and `hlint`.

Matches on a root-level `stack.yaml`, `cabal.project`, `package.yaml` or
`*.cabal`. Tests run through Stack when the project has a `stack.yaml`,
otherwise through Cabal; the tool that is not installed produces a clean
skipped result. Both may download and compile dependencies (like `npm
test` or `cargo test`), which is why they share the long command timeout.

تحلیل‌گر Haskell: `stack test` / `cabal test` و `hlint`.

روی `stack.yaml`، `cabal.project`، `package.yaml` یا `*.cabal` در ریشه
match می‌شود. اگر پروژه `stack.yaml` داشته باشد تست‌ها با Stack اجرا می‌شوند،
وگرنه با Cabal؛ ابزار نصب‌نشده یک نتیجه‌ی skipped تمیز می‌دهد. هر دو ممکن
است وابستگی‌ها را دانلود و کامپایل کنند (مثل `npm test` یا `cargo test`)،
برای همین timeout بلند مشترک دارند.
"""

from __future__ import annotations

from pathlib import Path

from sarand.analyzers._tooling import existing, run_tool, top_level_files
from sarand.models.results import CommandResult

_MARKERS = ("stack.yaml", "cabal.project", "package.yaml")


class HaskellAnalyzer:
    name = "Haskell"

    def matches(self, root: Path) -> bool:
        return bool(existing(root, _MARKERS)) or bool(
            top_level_files(root, lambda name: name.endswith(".cabal"))
        )

    def entry_points(self, root: Path) -> list[str]:
        return existing(root, ("app/Main.hs", "Main.hs", "src/Main.hs"))

    async def run_tests(self, root: Path) -> CommandResult | None:
        if (root / "stack.yaml").is_file():
            return await run_tool(root, "stack test", ["stack", "test"])
        return await run_tool(root, "cabal test", ["cabal", "test"])

    async def run_quality(self, root: Path) -> list[CommandResult]:
        return [await run_tool(root, "hlint", ["hlint", "."])]

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
