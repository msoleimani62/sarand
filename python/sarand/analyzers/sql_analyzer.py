"""SQL analyzer: sqlfluff, gated on real SQL project signals.

Detection deliberately mirrors LuaAnalyzer/CssAnalyzer's shallow,
deterministic check rather than a deep recursive scan: a sqlfluff
config file, a top-level *.sql file, or a top-level migrations/
directory that itself directly contains at least one *.sql file.

No `run_tests`: there is no dialect-agnostic, broadly standard
executable-test-suite convention for raw SQL projects (a project using
dbt or pgTAP has its own convention, but assuming either one would be
wrong for the other). No `run_security` either: no broadly standard
SQL vulnerability-audit tool exists as of this writing -- returning an
empty list is honest about that rather than reaching for something
that doesn't fit (same precedent as DartAnalyzer/LuaAnalyzer/
CssAnalyzer/ZigAnalyzer/SwiftAnalyzer).

آنالایزر SQL: sqlfluff، فقط وقتی نشانگر واقعی پروژه SQL باشد.

تشخیص عمداً همان بررسیِ کم‌عمق و قطعیِ LuaAnalyzer/CssAnalyzer را تکرار
می‌کند به‌جای یک اسکن بازگشتیِ عمیق: یک فایل کانفیگ sqlfluff، یک فایل
*.sql سطح-ریشه، یا یک پوشه‌ی migrations/ سطح-ریشه که خودش مستقیماً
حداقل یک *.sql دارد.

بدون run_tests: هیچ قرارداد test-suiteِ قابل‌اجرا و مستقل‌از-دیالکتِ
به‌طور گسترده استانداردی برای پروژه‌های SQL خام وجود ندارد (پروژه‌ای که
از dbt یا pgTAP استفاده می‌کند قرارداد خودش را دارد، اما فرض کردن هر
کدام برای دیگری اشتباه است). بدون run_security هم: تا زمان نوشتن این
کد هیچ ابزار audit آسیب‌پذیریِ به‌طور گسترده استاندارد برای SQL وجود
ندارد -- برگرداندن یک لیست خالی صادقانه است به‌جای دست‌بردن به چیزی که
تناسب ندارد (همان سابقه‌ی DartAnalyzer/LuaAnalyzer/CssAnalyzer/
ZigAnalyzer/SwiftAnalyzer).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.sql")

_ENTRY_POINTS = ("schema.sql", "init.sql", "seed.sql")
_CONFIG_FILES = (".sqlfluff", ".sqlfluffrc", "sqlfluff.cfg")


def _has_top_level_sql(directory: Path) -> bool:
    try:
        return any(
            p.is_file() and p.suffix.lower() == ".sql" for p in directory.iterdir()
        )
    except OSError:
        return False


class SqlAnalyzer:
    name = "SQL"

    def matches(self, root: Path) -> bool:
        for name in _CONFIG_FILES:
            if (root / name).is_file():
                return True

        if _has_top_level_sql(root):
            return True

        migrations = root / "migrations"
        return migrations.is_dir() and _has_top_level_sql(migrations)

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).is_file()]

    async def run_tests(self, root: Path) -> CommandResult | None:
        return None

    async def run_quality(self, root: Path) -> list[CommandResult]:
        sqlfluff = shutil.which("sqlfluff")
        if sqlfluff is None:
            return [
                make_command_result(
                    "sqlfluff lint",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="sqlfluff not found in PATH",
                )
            ]
        rc, out, dur = await run_cmd_async(
            [sqlfluff, "lint", "."], root, LONG_CMD_TIMEOUT
        )
        return [make_command_result("sqlfluff lint", rc, out, dur)]

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
