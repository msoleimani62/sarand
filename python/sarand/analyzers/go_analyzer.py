"""Go analyzer: go test + go vet/gofmt, gated on go.mod."""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.go")

_ENTRY_POINTS = ("main.go", "cmd/main.go")


class GoAnalyzer:
    name = "Go"

    def matches(self, root: Path) -> bool:
        return (root / "go.mod").exists()

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).exists()]

    async def run_tests(self, root: Path) -> CommandResult | None:
        if shutil.which("go") is None:
            return make_command_result("go test", 127, "", 0.0, skipped=True, skip_reason="go not found in PATH")
        logger.info("Running go test ./...")
        rc, output, duration = await run_cmd_async(["go", "test", "./..."], root, LONG_CMD_TIMEOUT)
        return make_command_result("go test", rc, output, duration)

    async def run_quality(self, root: Path) -> list[CommandResult]:
        if shutil.which("go") is None:
            return [make_command_result("go vet", 127, "", 0.0, skipped=True, skip_reason="go not found in PATH")]
        rc, out, dur = await run_cmd_async(["go", "vet", "./..."], root, LONG_CMD_TIMEOUT)
        return [make_command_result("go vet", rc, out, dur)]
