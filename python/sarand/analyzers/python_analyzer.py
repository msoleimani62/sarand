"""Python analyzer: pytest + ruff, gated on real Python markers.

Unlike the old bxt behaviour, ``ruff``/``pytest`` are never run just
because they happen to be installed globally -- ``matches()`` must be
True first.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.python")

_MARKERS = ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")
_ENTRY_POINTS = ("src/main.py", "main.py", "cli.py", "__main__.py", "app.py")


class PythonAnalyzer:
    name = "Python"

    def matches(self, root: Path) -> bool:
        return any((root / m).exists() for m in _MARKERS)

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).exists()]

    async def run_tests(self, root: Path) -> CommandResult | None:
        if shutil.which("pytest") is None:
            return make_command_result("pytest", 127, "", 0.0, skipped=True, skip_reason="pytest not found in PATH")
        logger.info("Running pytest -q")
        rc, output, duration = await run_cmd_async(["pytest", "-q", "--tb=short"], root, LONG_CMD_TIMEOUT)
        return make_command_result("pytest", rc, output, duration)

    async def run_quality(self, root: Path) -> list[CommandResult]:
        if shutil.which("ruff") is None:
            return [make_command_result("ruff", 127, "", 0.0, skipped=True, skip_reason="ruff not installed")]
        results = []
        rc, out, dur = await run_cmd_async(["ruff", "check", ".", "--output-format=concise"], root, LONG_CMD_TIMEOUT)
        results.append(make_command_result("ruff check", rc, out, dur))
        rc, out, dur = await run_cmd_async(["ruff", "format", ".", "--check"], root, LONG_CMD_TIMEOUT)
        results.append(make_command_result("ruff format --check", rc, out, dur))
        return results
