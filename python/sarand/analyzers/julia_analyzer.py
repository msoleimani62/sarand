"""Julia analyzer: `Pkg.test()`, gated on a real Project.toml.

No broadly standard standalone lint CLI or dependency-vulnerability-
audit tool exists for Julia as of this writing (JuliaFormatter is a
library invoked from within a Julia session, not a stable dry-run
CLI sarand can shell out to safely) -- run_quality and run_security
are both honest empties, same precedent as other ecosystems without
one (Dart/Lua/CSS/Zig/Swift/R/Perl for security).

Detection note: `Project.toml` (capital P) is Julia's own manifest and
is a distinct filename from `pyproject.toml` -- no collision with
PythonAnalyzer. It is a *.toml file like any other, so TomlAnalyzer
also matches it independently for a separate, complementary concern
(syntax linting), same complementary-match precedent as
YamlAnalyzer/JsonAnalyzer.

آنالایزر Julia: `Pkg.test()`، فقط وقتی یک Project.toml واقعی وجود
داشته باشد.

تا این لحظه هیچ CLI لینتِ مستقلِ به‌طور گسترده استاندارد یا ابزار
audit آسیب‌پذیریِ وابستگی برای Julia وجود ندارد (JuliaFormatter
کتابخانه‌ای است که از داخل یک نشست Julia فراخوانی می‌شود، نه یک CLI
پایدارِ dry-run که sarand بتواند ایمن صدایش بزند) -- run_quality و
run_security هر دو خالیِ صادقانه‌اند، همان سابقه‌ی اکوسیستم‌های دیگر
بدون چنین ابزاری (Dart/Lua/CSS/Zig/Swift/R/Perl برای security).

نکته‌ی تشخیص: `Project.toml` (P بزرگ) مانیفست خودِ Julia است و نامی
جدا از `pyproject.toml` است -- تداخلی با PythonAnalyzer ندارد. یک
فایل *.toml مثل هر فایل دیگر است، پس TomlAnalyzer هم مستقل روی آن
تطابق پیدا می‌کند برای دغدغه‌ای جدا و مکمل (لینت syntax)، همان سابقه‌ی
تطابقِ مکملِ YamlAnalyzer/JsonAnalyzer.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.julia")

_ENTRY_POINTS = ("src/main.jl", "main.jl")


class JuliaAnalyzer:
    name = "Julia"

    def matches(self, root: Path) -> bool:
        return (root / "Project.toml").is_file()

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).is_file()]

    async def run_tests(self, root: Path) -> CommandResult | None:
        if shutil.which("julia") is None:
            return make_command_result(
                "julia Pkg.test()",
                127,
                "",
                0.0,
                skipped=True,
                skip_reason="julia not found in PATH",
            )
        logger.info("Running julia --project=. -e 'Pkg.test()'")
        rc, out, dur = await run_cmd_async(
            ["julia", "--project=.", "-e", "import Pkg; Pkg.test()"],
            root,
            LONG_CMD_TIMEOUT,
        )
        return make_command_result("julia Pkg.test()", rc, out, dur)

    async def run_quality(self, root: Path) -> list[CommandResult]:
        return []

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
