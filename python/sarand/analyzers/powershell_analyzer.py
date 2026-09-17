"""PowerShell analyzer: Pester (tests) + PSScriptAnalyzer (quality),
gated shallowly on a top-level .ps1/.psm1/.psd1 file -- same shallow,
no-manifest detection shape as ShellAnalyzer, since PowerShell scripts
have no standard project-manifest file either.

Targets `pwsh` (PowerShell 7+, cross-platform) rather than legacy
Windows `powershell.exe`, matching sarand's Linux/macOS/Termux-first
environment (AGENTS.md §1). Whether the Pester/PSScriptAnalyzer
*modules* are actually installed is not checked separately, same
tradeoff as RAnalyzer's Rscript packages -- a missing module surfaces
as a failed CommandResult, not a clean skip.

آنالایزر PowerShell: Pester (تست) + PSScriptAnalyzer (کیفیت)، فقط با
وجود یک فایل .ps1/.psm1/.psd1 سطح-ریشه -- همان شکل تشخیص کم‌عمق و
بدون-مانیفست ShellAnalyzer، چون اسکریپت‌های PowerShell هم فایل
مانیفستِ پروژه‌ی استانداردی ندارند.

هدف `pwsh` (پاورشل ۷ به بعد، چندسکویی) است نه `powershell.exe` قدیمیِ
ویندوز، هم‌خوان با محیط لینوکس/مک/ترموکس-محورِ sarand (§1 در
AGENTS.md). این‌که خودِ ماژول‌های Pester/PSScriptAnalyzer واقعاً نصب
هستند جداگانه چک نمی‌شود، همان مصالحه‌ی پکیج‌های Rscript در
RAnalyzer -- یک ماژول غایب به‌صورت CommandResult ناموفق ظاهر می‌شود،
نه یک skip تمیز.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.powershell")

_PS_EXTENSIONS = (".ps1", ".psm1", ".psd1")
_ENTRY_POINTS = ("main.ps1", "Invoke-Build.ps1")


def _top_level_ps_files(root: Path) -> list[Path]:
    try:
        return sorted(
            p
            for p in root.iterdir()
            if p.is_file() and p.suffix.lower() in _PS_EXTENSIONS
        )
    except OSError:
        return []


class PowerShellAnalyzer:
    name = "PowerShell"

    def matches(self, root: Path) -> bool:
        return bool(_top_level_ps_files(root))

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).is_file()]

    async def run_tests(self, root: Path) -> CommandResult | None:
        has_pester_tests = any(root.rglob("*.Tests.ps1"))
        if not has_pester_tests:
            return None
        if shutil.which("pwsh") is None:
            return make_command_result(
                "Invoke-Pester",
                127,
                "",
                0.0,
                skipped=True,
                skip_reason="pwsh not found in PATH",
            )
        logger.info("Running Invoke-Pester -CI")
        rc, out, dur = await run_cmd_async(
            ["pwsh", "-NoProfile", "-Command", "Invoke-Pester -CI"],
            root,
            LONG_CMD_TIMEOUT,
        )
        return make_command_result("Invoke-Pester", rc, out, dur)

    async def run_quality(self, root: Path) -> list[CommandResult]:
        if shutil.which("pwsh") is None:
            return [
                make_command_result(
                    "Invoke-ScriptAnalyzer",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="pwsh not found in PATH",
                )
            ]
        logger.info("Running Invoke-ScriptAnalyzer -EnableExit")
        rc, out, dur = await run_cmd_async(
            [
                "pwsh",
                "-NoProfile",
                "-Command",
                "Invoke-ScriptAnalyzer -Path . -Recurse -EnableExit",
            ],
            root,
            LONG_CMD_TIMEOUT,
        )
        return [make_command_result("Invoke-ScriptAnalyzer", rc, out, dur)]

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
