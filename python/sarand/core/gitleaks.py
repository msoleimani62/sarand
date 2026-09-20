"""gitleaks: a broader, dedicated secret-scanning pass over the whole
project (git history included, when there is one), complementary to
--- not a replacement for --- the always-on regex scanner in
core/secrets.py.

The two serve different roles and both stay: secrets.py's scan is a
safety *guarantee* (AGENTS.md §4.10) -- it runs unconditionally on
every file about to be embedded in a report and is what keeps a
credential out of the report's own source dump, regardless of whether
gitleaks is installed. gitleaks is a much deeper, purpose-built
detector (hundreds of provider-specific rules, git-history scanning
including already-deleted-but-still-in-history secrets) that
secrets.py's five hand-rolled patterns were never meant to replace --
it only runs when explicitly requested (--security) and only adds a
finding to the report, it never gates what gets embedded the way
secrets.py's exclude_flagged_files does.

gitleaks: یک پاس اسکن secret گسترده‌تر و مخصوص روی کل پروژه (شامل
تاریخچه‌ی گیت، وقتی وجود دارد)، مکمل --- نه جایگزین --- اسکنر regex
همیشه-روشنِ core/secrets.py.

این دو نقش متفاوتی دارند و هر دو می‌مانند: اسکن secrets.py یک *تضمین*
ایمنی است (AGENTS.md §4.10) -- بدون قید و شرط روی هر فایلی که قرار است
در گزارش embed شود اجرا می‌شود و همان چیزی است که یک اعتبارنامه را از
خودِ source dump گزارش دور نگه می‌دارد، صرف‌نظر از اینکه gitleaks نصب
باشد یا نه. gitleaks یک دیتکتور بسیار عمیق‌تر و مخصوص همین کار است
(صدها قانون مخصوص provider، اسکن تاریخچه‌ی گیت شامل secretهایی که حذف
شده‌اند ولی هنوز در تاریخچه هستند) که پنج الگوی دستی‌نوشته‌ی
secrets.py هرگز قرار نبوده جایگزینش شوند -- فقط وقتی صراحتاً درخواست
شود (--security) اجرا می‌شود و فقط یک finding به گزارش اضافه می‌کند،
هرگز مثل exclude_flagged_files در secrets.py تعیین نمی‌کند چه چیزی
embed می‌شود.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("core.gitleaks")


async def run_gitleaks(root: Path) -> CommandResult:
    """Run gitleaks over `root`, scanning git history when one exists.

    Not gated behind SARAND_SKIP_AUDIT like cargo-audit/pip-audit: this
    is a local, offline scan (no vulnerability-database network call),
    so the "fixed external cost" reasoning those two document doesn't
    apply here -- only the --security flag and the binary's presence
    gate this.
    """
    if shutil.which("gitleaks") is None:
        return make_command_result(
            "gitleaks",
            127,
            "",
            0.0,
            skipped=True,
            skip_reason=(
                "gitleaks not installed (see https://github.com/gitleaks/gitleaks)"
            ),
        )

    # `--redact` is not optional here: without it, gitleaks prints the
    # actual matched secret value into its own output, which sarand
    # would then embed verbatim in the report -- exactly the leak
    # AGENTS.md §4.10 exists to prevent. secrets.py's own findings
    # never carry the matched value for the same reason; gitleaks must
    # be forced into the same posture explicitly, since its default
    # behavior is the opposite.
    #
    # `--redact` اینجا اختیاری نیست: بدونش، gitleaks مقدار واقعیِ
    # secretِ پیدا‌شده را در خروجی خودش چاپ می‌کند، که sarand بعد آن
    # را عیناً در گزارش embed می‌کند -- دقیقاً همان نشتی که §4.10
    # AGENTS.md برای جلوگیری از آن وجود دارد. findingهای خودِ
    # secrets.py هم به همین دلیل هرگز مقدار مطابقت‌یافته را حمل
    # نمی‌کنند؛ gitleaks باید صراحتاً به همین حالت مجبور شود، چون
    # رفتار پیش‌فرضش برعکس است.
    #
    # `--verbose` prints each finding (rule, file, line, commit) -- without
    # it gitleaks only prints "leaks found: N" and the report is not
    # actionable. It is only safe *because* `--redact` is always present
    # (see tests: verbose without redact must never be built).
    # `--no-color` keeps ANSI escape codes out of the embedded report.
    #
    # `--verbose` هر finding را چاپ می‌کند (rule، فایل، خط، commit) --
    # بدونش gitleaks فقط «leaks found: N» می‌نویسد و گزارش قابل پیگیری
    # نیست. این فقط به‌خاطر حضور همیشگیِ `--redact` امن است (تست‌ها
    # تضمین می‌کنند verbose بدون redact هرگز ساخته نشود). `--no-color`
    # کدهای ANSI را از گزارش دور نگه می‌دارد.
    cmd = [
        "gitleaks",
        "detect",
        "--source",
        ".",
        "--no-banner",
        "--no-color",
        "--redact",
        "--verbose",
    ]
    if not (root / ".git").exists():
        # No git history to walk -- working-tree-only scan instead of
        # letting gitleaks fail on "not a git repository".
        # تاریخچه‌ی گیتی برای طی‌کردن نیست -- به‌جای اینکه بگذاریم
        # gitleaks روی «مخزن گیت نیست» شکست بخورد، فقط working tree
        # را اسکن می‌کنیم.
        cmd.append("--no-git")

    rc, out, dur = await run_cmd_async(cmd, root, LONG_CMD_TIMEOUT)
    return make_command_result("gitleaks", rc, out, dur)
