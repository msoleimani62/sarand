"""syft: generate a Software Bill of Materials (SBOM) for the whole
project -- every dependency across every detected language, in one
pass, rather than sarand trying to enumerate them itself per-language.

Deliberately a plain table, not a structured JSON dump embedded into
the report: a real dependency-inventory feature (counted, categorized
per language, license-annotated) is scoped as its own P2 item in
AGENTS.md §5.10 ("needs real design, not mechanical addition") -- this
is the P1-scope version, "run the tool and show what it found", same
posture as gitleaks in this same round.

syft: تولید یک Software Bill of Materials (SBOM) برای کل پروژه -- هر
وابستگی در هر زبان شناسایی‌شده، در یک اجرا، به‌جای این‌که خودِ sarand
سعی کند آن‌ها را تک‌تک به ازای هر زبان برشمارد.

عمداً یک جدول ساده است، نه یک dump ساخت‌یافته‌ی JSON که در گزارش embed
شود: یک قابلیت واقعیِ فهرست وابستگی‌ها (شمارش‌شده، دسته‌بندی‌شده به
تفکیک زبان، حاشیه‌نویسی‌شده با لایسنس) به‌عنوان آیتم P2 خودش در §5.10
AGENTS.md دامنه‌بندی شده («نیاز به طراحی واقعی دارد، نه اضافه‌ی
مکانیکی») -- این نسخه‌ی محدوده‌ی P1 است، «ابزار را اجرا کن و چیزی که
پیدا کرد را نشان بده»، همان موضع gitleaks در همین دور.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("core.sbom")


async def run_syft(root: Path) -> CommandResult:
    """Generate an SBOM for `root` with syft. Always "passes" (syft's
    own exit code is 0 whether it finds 0 or 500 components -- it
    isn't a pass/fail tool the way gitleaks or an audit tool is), so
    this is purely informational output for the report, same as a
    `git log` summary."""
    if shutil.which("syft") is None:
        return make_command_result(
            "syft (SBOM)",
            127,
            "",
            0.0,
            skipped=True,
            skip_reason="syft not installed (see https://github.com/anchore/syft)",
        )

    rc, out, dur = await run_cmd_async(
        ["syft", "dir:.", "-o", "table", "--quiet"], root, LONG_CMD_TIMEOUT
    )
    return make_command_result("syft (SBOM)", rc, out, dur)
