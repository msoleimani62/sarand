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

# Both legacy (.eslintrc*) and flat-config (eslint.config.*, ESLint 9+)
# forms -- same "project-aware" reasoning as css_analyzer.py's
# _CONFIG_FILES: run eslint only when the project actually configured
# it, not just because the `eslint` binary happens to exist somewhere
# on PATH (a global install proves nothing about this project).
#
# هم فرم قدیمی (.eslintrc*) هم فرم flat-config (eslint.config.*،
# ESLint 9+) -- همان استدلال «project-aware»ی _CONFIG_FILES در
# css_analyzer.py: eslint فقط وقتی اجرا شود که پروژه واقعاً
# کانفیگش کرده، نه صرفاً چون باینری `eslint` یه‌جایی روی PATH هست
# (یک نصب global هیچی درباره‌ی این پروژه‌ی خاص ثابت نمی‌کند).
_ESLINT_CONFIG_FILES = (
    "eslint.config.js",
    "eslint.config.mjs",
    "eslint.config.cjs",
    "eslint.config.ts",
    ".eslintrc",
    ".eslintrc.js",
    ".eslintrc.cjs",
    ".eslintrc.json",
    ".eslintrc.yaml",
    ".eslintrc.yml",
)


def _local_or_global_eslint(root: Path) -> str | None:
    """Prefer `node_modules/.bin/eslint` (npm-installed, version-pinned
    for this project) over a global `eslint` binary of the same name --
    same precedent as css_analyzer.py's `_local_or_global_stylelint`."""
    local = root / "node_modules" / ".bin" / "eslint"
    if local.is_file():
        return str(local)
    return shutil.which("eslint")


def _has_eslint_config(root: Path) -> bool:
    return any((root / name).is_file() for name in _ESLINT_CONFIG_FILES)


class NodeAnalyzer:
    name = "Node.js"

    def matches(self, root: Path) -> bool:
        return (root / "package.json").exists()

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).exists()]

    def _scripts(self, root: Path) -> dict:
        try:
            return json.loads((root / "package.json").read_text(encoding="utf-8")).get(
                "scripts", {}
            )
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
            return make_command_result(
                "npm test",
                127,
                "",
                0.0,
                skipped=True,
                skip_reason="npm not found in PATH",
            )
        logger.info("Running npm test")
        rc, output, duration = await run_cmd_async(
            ["npm", "test", "--silent"], root, LONG_CMD_TIMEOUT
        )
        return make_command_result("npm test", rc, output, duration)

    async def run_quality(self, root: Path) -> list[CommandResult]:
        results: list[CommandResult] = []

        if self._scripts(root).get("lint"):
            if shutil.which("npm") is None:
                results.append(
                    make_command_result(
                        "npm run lint",
                        127,
                        "",
                        0.0,
                        skipped=True,
                        skip_reason="npm not found in PATH",
                    )
                )
            else:
                rc, out, dur = await run_cmd_async(
                    ["npm", "run", "lint", "--silent"], root, LONG_CMD_TIMEOUT
                )
                results.append(make_command_result("npm run lint", rc, out, dur))

        # Separate from "npm run lint" above on purpose: a project can
        # have an ESLint config with no "lint" script wired up in
        # package.json (or a "lint" script that runs something else
        # entirely, e.g. just prettier) -- direct eslint invocation
        # catches that case instead of silently deferring to whatever
        # package.json happens to define.
        #
        # عمداً از "npm run lint" بالا جداست: یک پروژه ممکن است کانفیگ
        # ESLint داشته باشد بدون اینکه اسکریپت "lint" در package.json
        # سیمش کشیده شده باشد (یا یک اسکریپت "lint" که چیز کاملاً
        # دیگری اجرا می‌کند، مثلاً فقط prettier) -- فراخوانی مستقیم
        # eslint آن حالت را هم می‌گیرد، به‌جای واگذاری بی‌صدا به هرچه
        # package.json تعریف کرده.
        if _has_eslint_config(root):
            eslint = _local_or_global_eslint(root)
            if eslint is None:
                results.append(
                    make_command_result(
                        "eslint",
                        127,
                        "",
                        0.0,
                        skipped=True,
                        skip_reason=(
                            "eslint not found (node_modules/.bin/eslint or global)"
                        ),
                    )
                )
            else:
                rc, out, dur = await run_cmd_async(
                    [eslint, "."], root, LONG_CMD_TIMEOUT
                )
                results.append(make_command_result("eslint", rc, out, dur))

        return results

    async def run_security(self, root: Path) -> list[CommandResult]:
        if shutil.which("npm") is None:
            return [
                make_command_result(
                    "npm audit",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="npm not found in PATH",
                )
            ]
        # npm audit exits non-zero when it finds vulnerabilities -- that's
        # a legitimate FAIL result, not a crash, so we still wrap it normally.
        # npm audit وقتی آسیب‌پذیری پیدا کند با کد غیرصفر خارج می‌شود -- این
        # یک نتیجه‌ی FAIL معتبر است، نه یک کرش، پس طبق روال عادی wrap می‌شود.
        rc, out, dur = await run_cmd_async(
            ["npm", "audit", "--audit-level=moderate"], root, LONG_CMD_TIMEOUT
        )
        return [make_command_result("npm audit", rc, out, dur)]
