"""PHP analyzer: PHPUnit + PHPStan + `composer audit`, gated on a
real composer.json.

Prefers a project-local `vendor/bin/<tool>` (the version Composer
actually installed for this project) over a global binary, since a
globally-installed PHPUnit/PHPStan can easily be a different major
version than the one the project's composer.json expects.

آنالایزر PHP: PHPUnit + PHPStan + `composer audit`، فقط وقتی
composer.json واقعی وجود داشته باشد.

باینری محلیِ پروژه در `vendor/bin/<tool>` (نسخه‌ای که Composer واقعاً
برای همین پروژه نصب کرده) را به باینری global ترجیح می‌دهد، چون
PHPUnit/PHPStan نصب‌شده‌ی global می‌تواند به‌راحتی نسخه‌ی اصلیِ متفاوتی
از چیزی باشد که composer.json پروژه انتظار دارد.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.php")

_ENTRY_POINTS = ("public/index.php", "index.php", "src/index.php")


def _local_or_global_binary(root: Path, name: str) -> str | None:
    """Prefer `vendor/bin/<name>` (Composer-installed, version-pinned
    for this project) over a global binary of the same name."""
    local = root / "vendor" / "bin" / name
    if local.is_file():
        return str(local)
    return shutil.which(name)


class PhpAnalyzer:
    name = "PHP"

    def matches(self, root: Path) -> bool:
        return (root / "composer.json").is_file()

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).is_file()]

    async def run_tests(self, root: Path) -> CommandResult | None:
        phpunit = _local_or_global_binary(root, "phpunit")
        if phpunit is None:
            return make_command_result(
                "phpunit",
                127,
                "",
                0.0,
                skipped=True,
                skip_reason="phpunit not found (neither vendor/bin/phpunit nor PATH)",
            )
        logger.info("Running %s", phpunit)
        rc, output, duration = await run_cmd_async([phpunit], root, LONG_CMD_TIMEOUT)
        return make_command_result("phpunit", rc, output, duration)

    async def run_quality(self, root: Path) -> list[CommandResult]:
        phpstan = _local_or_global_binary(root, "phpstan")
        if phpstan is None:
            return [
                make_command_result(
                    "phpstan",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason=(
                        "phpstan not found (neither vendor/bin/phpstan nor PATH)"
                    ),
                )
            ]
        rc, out, dur = await run_cmd_async(
            [phpstan, "analyse", "--no-progress"], root, LONG_CMD_TIMEOUT
        )
        return [make_command_result("phpstan", rc, out, dur)]

    async def run_security(self, root: Path) -> list[CommandResult]:
        if shutil.which("composer") is None:
            return [
                make_command_result(
                    "composer audit",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="composer not installed",
                )
            ]
        rc, out, dur = await run_cmd_async(
            ["composer", "audit"], root, LONG_CMD_TIMEOUT
        )
        return [make_command_result("composer audit", rc, out, dur)]
