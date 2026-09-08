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
            return make_command_result(
                "pytest",
                127,
                "",
                0.0,
                skipped=True,
                skip_reason="pytest not found in PATH",
            )
        logger.info("Running pytest -q")
        rc, output, duration = await run_cmd_async(
            ["pytest", "-q", "--tb=short"], root, LONG_CMD_TIMEOUT
        )
        return make_command_result("pytest", rc, output, duration)

    async def run_quality(self, root: Path) -> list[CommandResult]:
        if shutil.which("ruff") is None:
            return [
                make_command_result(
                    "ruff", 127, "", 0.0, skipped=True, skip_reason="ruff not installed"
                )
            ]
        results = []
        rc, out, dur = await run_cmd_async(
            ["ruff", "check", ".", "--output-format=concise"], root, LONG_CMD_TIMEOUT
        )
        results.append(make_command_result("ruff check", rc, out, dur))
        rc, out, dur = await run_cmd_async(
            ["ruff", "format", ".", "--check"], root, LONG_CMD_TIMEOUT
        )
        results.append(make_command_result("ruff format --check", rc, out, dur))
        return results

    async def run_security(self, root: Path) -> list[CommandResult]:
        results: list[CommandResult] = []

        if shutil.which("pip-audit") is None:
            results.append(
                make_command_result(
                    "pip-audit",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="pip-audit not installed",
                )
            )
        else:
            # BUG FIX (user report: --full's security phase took 157.6s,
            # by far the dominant cost). Bare `pip-audit` with no path
            # argument audits the *entire active environment* -- every
            # installed package, not just this project's own
            # dependencies. That means dozens of dev-only packages
            # (mypy, bandit, ruff, pytest, cyclonedx-python-lib and all
            # of pip-audit's own transitive deps) each get their own
            # network round-trip against the vulnerability database,
            # none of which say anything about sarand's actual runtime
            # security posture. `pip-audit .` (per pip-audit's own
            # docs: "Audit dependencies for a local Python project")
            # scopes the audit to exactly what pyproject.toml declares
            # -- for sarand that's `filelock` and `rich` plus their own
            # few direct deps, cutting the query count from dozens to a
            # handful.
            #
            # اصلاح باگ (گزارش کاربر: فاز امنیت --full روی ۱۵۷.۶ ثانیه
            # ماند، به‌مراتب پرهزینه‌ترین بخش). `pip-audit` خام بدون
            # آرگومان مسیر، کل محیط فعال را audit می‌کند -- هر پکیج
            # نصب‌شده، نه فقط وابستگی‌های خودِ این پروژه. یعنی ده‌ها
            # پکیج فقط-توسعه (mypy، bandit، ruff، pytest،
            # cyclonedx-python-lib و همه‌ی وابستگی‌های transitive خودِ
            # pip-audit) هرکدام یک رفت‌وبرگشت شبکه‌ای جدا به پایگاه‌داده‌ی
            # آسیب‌پذیری می‌گیرند، که هیچ‌کدام چیزی درباره‌ی وضعیت امنیتی
            # واقعیِ runtime سرند نمی‌گویند. `pip-audit .` (طبق مستندات
            # خودِ pip-audit: «Audit dependencies for a local Python
            # project») audit را دقیقاً به همان چیزی که pyproject.toml
            # اعلام کرده محدود می‌کند -- برای sarand یعنی `filelock` و
            # `rich` به‌علاوه‌ی چند وابستگی مستقیم خودشان، که تعداد
            # کوئری را از ده‌ها به چندتا کاهش می‌دهد.
            rc, out, dur = await run_cmd_async(
                ["pip-audit", "."], root, LONG_CMD_TIMEOUT
            )
            results.append(make_command_result("pip-audit", rc, out, dur))

        if shutil.which("bandit") is None:
            results.append(
                make_command_result(
                    "bandit",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="bandit not installed",
                )
            )
        else:
            rc, out, dur = await run_cmd_async(
                ["bandit", "-r", ".", "-q"], root, LONG_CMD_TIMEOUT
            )
            results.append(make_command_result("bandit", rc, out, dur))

        return results
