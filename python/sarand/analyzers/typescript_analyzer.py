"""TypeScript analyzer: `tsc --noEmit` type-checking, gated on a real
tsconfig.json.

Test execution and dependency auditing for a TypeScript project are
already covered by NodeAnalyzer (`npm test` / `npm audit`), since a
TypeScript project is still a Node.js project underneath (same
package.json). This analyzer adds exactly the one thing NodeAnalyzer
cannot see on its own: whether the project's types actually check --
run_tests/run_security are intentionally no-ops here rather than
duplicating what NodeAnalyzer already runs.

Prefers the project-local `node_modules/.bin/tsc` (the exact compiler
version pinned in package.json) over a global `tsc`, for the same
reason PhpAnalyzer prefers `vendor/bin/<tool>` over a global binary.

آنالایزر TypeScript: type-check با `tsc --noEmit`، فقط وقتی
tsconfig.json واقعی وجود داشته باشد.

اجرای تست و آدیت وابستگی‌های یک پروژه‌ی TypeScript از قبل توسط
NodeAnalyzer پوشش داده می‌شود (`npm test` / `npm audit`)، چون یک
پروژه‌ی TypeScript در زیر همچنان یک پروژه‌ی Node.js است (همان
package.json). این آنالایزر دقیقاً همان یک چیزی را اضافه می‌کند که
NodeAnalyzer خودش نمی‌تواند ببیند: این‌که تایپ‌های پروژه واقعاً
type-check می‌شوند یا نه -- run_tests/run_security عمداً اینجا کاری
انجام نمی‌دهند تا کاری که NodeAnalyzer از قبل انجام می‌دهد تکرار نشود.

باینری محلیِ پروژه در `node_modules/.bin/tsc` (نسخه‌ای که دقیقاً در
package.json pin شده) را به `tsc` سراسری ترجیح می‌دهد، به همان دلیلی
که PhpAnalyzer باینری `vendor/bin/<tool>` را به باینری global ترجیح
می‌دهد.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.typescript")

_ENTRY_POINTS = ("src/index.ts", "src/main.ts", "index.ts")


def _local_or_global_tsc(root: Path) -> str | None:
    """Prefer `node_modules/.bin/tsc` (npm-installed, version-pinned
    for this project) over a global `tsc` binary of the same name."""
    local = root / "node_modules" / ".bin" / "tsc"
    if local.is_file():
        return str(local)
    return shutil.which("tsc")


class TypeScriptAnalyzer:
    name = "TypeScript"

    def matches(self, root: Path) -> bool:
        return (root / "tsconfig.json").is_file()

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).is_file()]

    async def run_tests(self, root: Path) -> CommandResult | None:
        # Test execution is NodeAnalyzer's job (npm test) -- see the
        # module docstring.
        #
        # اجرای تست کار NodeAnalyzer است (npm test) -- دکیومنت ماژول
        # را ببینید.
        return None

    async def run_quality(self, root: Path) -> list[CommandResult]:
        tsc = _local_or_global_tsc(root)
        if tsc is None:
            return [
                make_command_result(
                    "tsc --noEmit",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="tsc not found (node_modules/.bin/tsc or global)",
                )
            ]
        logger.info("Running %s --noEmit", tsc)
        rc, out, dur = await run_cmd_async([tsc, "--noEmit"], root, LONG_CMD_TIMEOUT)
        return [make_command_result("tsc --noEmit", rc, out, dur)]

    async def run_security(self, root: Path) -> list[CommandResult]:
        # Dependency auditing is NodeAnalyzer's job (npm audit) -- a
        # separate `tsc`-specific audit doesn't exist and would just
        # duplicate that scan.
        #
        # آدیت وابستگی‌ها کار NodeAnalyzer است (npm audit) -- آدیت
        # جداگانه‌ی مخصوص `tsc` وجود ندارد و فقط همان اسکن را تکرار
        # می‌کند.
        return []
