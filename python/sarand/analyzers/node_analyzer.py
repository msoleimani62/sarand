"""Node.js analyzer: npm test, gated on package.json AND a real "test" script."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.node")

_ENTRY_POINTS = ("index.js", "src/index.js", "server.js", "src/index.ts")


class NodeAnalyzer:
    name = "Node.js"

    def matches(self, root: Path) -> bool:
        return (root / "package.json").exists()

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).exists()]

    def _scripts(self, root: Path) -> dict:
        try:
            return json.loads((root / "package.json").read_text(encoding="utf-8")).get("scripts", {})
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not parse package.json: %s", exc)
            return {}

    async def run_tests(self, root: Path) -> CommandResult | None:
        # A real "test" script is required -- otherwise `npm test` just
        # fails with "Error: no test specified", which is noise, not signal.
        # وجود اسکریپت واقعی "test" الزامی است -- وگرنه `npm test` صرفاً
        # با «Error: no test specified» شکست می‌خورد که نویز است، نه سیگنال.
        if not self._scripts(root).get("test"):
            return None
        if shutil.which("npm") is None:
            return make_command_result("npm test", 127, "", 0.0, skipped=True, skip_reason="npm not found in PATH")
        logger.info("Running npm test")
        rc, output, duration = await run_cmd_async(["npm", "test", "--silent"], root, LONG_CMD_TIMEOUT)
        return make_command_result("npm test", rc, output, duration)

    async def run_quality(self, root: Path) -> list[CommandResult]:
        if not self._scripts(root).get("lint"):
            return []
        if shutil.which("npm") is None:
            return [make_command_result("npm run lint", 127, "", 0.0, skipped=True, skip_reason="npm not found in PATH")]
        rc, out, dur = await run_cmd_async(["npm", "run", "lint", "--silent"], root, LONG_CMD_TIMEOUT)
        return [make_command_result("npm run lint", rc, out, dur)]

    async def run_security(self, root: Path) -> list[CommandResult]:
        if shutil.which("npm") is None:
            return [make_command_result("npm audit", 127, "", 0.0, skipped=True, skip_reason="npm not found in PATH")]
        # npm audit exits non-zero when it finds vulnerabilities -- that's
        # a legitimate FAIL result, not a crash, so we still wrap it normally.
        # npm audit وقتی آسیب‌پذیری پیدا کند با کد غیرصفر خارج می‌شود -- این
        # یک نتیجه‌ی FAIL معتبر است، نه یک کرش، پس طبق روال عادی wrap می‌شود.
        rc, out, dur = await run_cmd_async(["npm", "audit", "--audit-level=moderate"], root, LONG_CMD_TIMEOUT)
        return [make_command_result("npm audit", rc, out, dur)]
