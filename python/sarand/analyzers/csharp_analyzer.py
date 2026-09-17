"""C# analyzer: `dotnet test` + `dotnet format --verify-no-changes` +
`dotnet list package --vulnerable`, gated on a top-level *.csproj or
*.sln.

A single `dotnet` binary provides the whole toolchain (test, format,
package listing) -- same shape as ZigAnalyzer's single `zig` binary.

آنالایزر C#: `dotnet test` + `dotnet format --verify-no-changes` +
`dotnet list package --vulnerable`، فقط وقتی یک *.csproj یا *.sln
سطح-ریشه وجود داشته باشد.

یک باینری واحد `dotnet` کل toolchain را فراهم می‌کند (test، format،
لیست پکیج‌ها) -- شکلی مشابه باینری واحد `zig` در ZigAnalyzer.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.csharp")

_ENTRY_POINTS = ("Program.cs", "src/Program.cs")


def _has_project_file(root: Path) -> bool:
    try:
        return any(root.glob("*.csproj")) or any(root.glob("*.sln"))
    except OSError:
        return False


class CSharpAnalyzer:
    name = "C#"

    def matches(self, root: Path) -> bool:
        return _has_project_file(root)

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).is_file()]

    async def run_tests(self, root: Path) -> CommandResult | None:
        if shutil.which("dotnet") is None:
            return make_command_result(
                "dotnet test",
                127,
                "",
                0.0,
                skipped=True,
                skip_reason="dotnet not found in PATH",
            )
        logger.info("Running dotnet test")
        rc, out, dur = await run_cmd_async(["dotnet", "test"], root, LONG_CMD_TIMEOUT)
        return make_command_result("dotnet test", rc, out, dur)

    async def run_quality(self, root: Path) -> list[CommandResult]:
        if shutil.which("dotnet") is None:
            return [
                make_command_result(
                    "dotnet format --verify-no-changes",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="dotnet not found in PATH",
                )
            ]
        rc, out, dur = await run_cmd_async(
            ["dotnet", "format", "--verify-no-changes"], root, LONG_CMD_TIMEOUT
        )
        return [make_command_result("dotnet format --verify-no-changes", rc, out, dur)]

    async def run_security(self, root: Path) -> list[CommandResult]:
        if shutil.which("dotnet") is None:
            return [
                make_command_result(
                    "dotnet list package --vulnerable",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="dotnet not found in PATH",
                )
            ]
        rc, out, dur = await run_cmd_async(
            ["dotnet", "list", "package", "--vulnerable", "--include-transitive"],
            root,
            LONG_CMD_TIMEOUT,
        )
        return [make_command_result("dotnet list package --vulnerable", rc, out, dur)]
