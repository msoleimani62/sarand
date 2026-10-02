"""Minimal example sarand plugin: `just test` for projects with a justfile.

Only the public plugin surface is used: the `LanguageAnalyzer` contract
(documented in docs/PLUGINS.md), `CommandResult` and the two small
helpers in `sarand.utils.command`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async

_JUSTFILES = ("justfile", "Justfile", ".justfile")


class JustfileAnalyzer:
    """Runs the `test` recipe of a justfile."""

    name = "Just"
    api_version = 1

    def _justfile(self, root: Path) -> Path | None:
        for candidate in _JUSTFILES:
            if (root / candidate).is_file():
                return root / candidate
        return None

    def matches(self, root: Path) -> bool:
        return self._justfile(root) is not None

    def entry_points(self, root: Path) -> list[str]:
        found = self._justfile(root)
        return [found.name] if found else []

    async def run_tests(self, root: Path) -> CommandResult | None:
        if shutil.which("just") is None:
            return make_command_result(
                "just test",
                127,
                "",
                0.0,
                skipped=True,
                skip_reason="just not found in PATH",
            )
        code, output, duration = await run_cmd_async(["just", "test"], root, 300)
        return make_command_result("just test", code, output, duration)

    async def run_quality(self, root: Path) -> list[CommandResult]:
        return []

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
