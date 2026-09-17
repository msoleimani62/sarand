"""Nix analyzer: format-analyzer style, same shape as
TomlAnalyzer/YamlAnalyzer -- gated shallowly on a top-level *.nix
file, no separate project-manifest concept to key off of.

`run_tests` only fires for an actual flake (`flake.nix`), since
`nix flake check` specifically validates a flake's outputs (including
any `checks` it defines) -- there is nothing equivalent to run against
a bare *.nix file with no flake. No standard Nix
dependency-vulnerability-audit tool is broadly adopted as of this
writing (vulnix exists but is not de-facto-standard the way
cargo-audit/pip-audit are) -- run_security is an honest empty, same
precedent as the other format analyzers.

آنالایزر Nix: به سبک آنالایزرهای فرمت‌محور، همان شکل
TomlAnalyzer/YamlAnalyzer -- فقط با وجود یک فایل *.nix سطح-ریشه، بدون
مفهوم جداگانه‌ی مانیفست پروژه برای تکیه‌کردن به آن.

`run_tests` فقط برای یک flake واقعی (`flake.nix`) فعال می‌شود، چون
`nix flake check` مشخصاً خروجی‌های یک flake (شامل هر `checks`ی که
تعریف کرده) را اعتبارسنجی می‌کند -- در برابر یک فایل *.nix خالی بدون
flake چیزی معادل برای اجرا وجود ندارد. تا این لحظه ابزار audit
آسیب‌پذیریِ وابستگیِ Nix به‌طور گسترده پذیرفته‌شده‌ای وجود ندارد (vulnix
هست ولی به‌اندازه‌ی cargo-audit/pip-audit استاندارد بالفعل نیست) --
run_security یک خالیِ صادقانه است، همان سابقه‌ی آنالایزرهای فرمت‌محور
دیگر.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.nix")


def _has_top_level_nix_file(root: Path) -> bool:
    try:
        return any(root.glob("*.nix"))
    except OSError:
        return False


class NixAnalyzer:
    name = "Nix"

    def matches(self, root: Path) -> bool:
        return _has_top_level_nix_file(root)

    def entry_points(self, root: Path) -> list[str]:
        ep = root / "flake.nix"
        return [ep.name] if ep.is_file() else []

    async def run_tests(self, root: Path) -> CommandResult | None:
        if not (root / "flake.nix").is_file():
            return None
        if shutil.which("nix") is None:
            return make_command_result(
                "nix flake check",
                127,
                "",
                0.0,
                skipped=True,
                skip_reason="nix not found in PATH",
            )
        logger.info("Running nix flake check")
        rc, out, dur = await run_cmd_async(
            ["nix", "flake", "check"], root, LONG_CMD_TIMEOUT
        )
        return make_command_result("nix flake check", rc, out, dur)

    async def run_quality(self, root: Path) -> list[CommandResult]:
        if shutil.which("nixpkgs-fmt") is None:
            return [
                make_command_result(
                    "nixpkgs-fmt --check",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="nixpkgs-fmt not found in PATH",
                )
            ]
        files = [str(p.relative_to(root)) for p in sorted(root.glob("*.nix"))]
        logger.info("Running nixpkgs-fmt --check")
        rc, out, dur = await run_cmd_async(
            ["nixpkgs-fmt", "--check", *files], root, LONG_CMD_TIMEOUT
        )
        return [make_command_result("nixpkgs-fmt --check", rc, out, dur)]

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
