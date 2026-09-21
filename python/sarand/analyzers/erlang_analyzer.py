"""Erlang analyzer: `rebar3 eunit` and `rebar3 xref`.

Matches on a root-level `rebar.config`. EUnit runs the project's tests and
xref checks calls to undefined functions -- both fast. Dialyzer is
deliberately not run by default: its first run builds a persistent lookup
table (PLT) of the whole OTP standard library, which takes many minutes
and would make an ordinary scan unpredictable.

تحلیل‌گر Erlang: `rebar3 eunit` و `rebar3 xref`.

روی `rebar.config` در ریشه match می‌شود. EUnit تست‌های پروژه را اجرا می‌کند
و xref فراخوانی توابع تعریف‌نشده را بررسی می‌کند -- هر دو سریع. Dialyzer
عمداً به‌طور پیش‌فرض اجرا نمی‌شود: اولین اجرایش یک جدول جست‌وجوی پایدار
(PLT) از کل کتابخانه‌ی استاندارد OTP می‌سازد که چند دقیقه طول می‌کشد و
یک اسکن معمولی را غیرقابل‌پیش‌بینی می‌کرد.
"""

from __future__ import annotations

from pathlib import Path

from sarand.analyzers._tooling import existing, run_tool
from sarand.models.results import CommandResult


class ErlangAnalyzer:
    name = "Erlang"

    def matches(self, root: Path) -> bool:
        return (root / "rebar.config").is_file()

    def entry_points(self, root: Path) -> list[str]:
        return existing(root, ("rebar.config", "src"))

    async def run_tests(self, root: Path) -> CommandResult | None:
        return await run_tool(root, "rebar3 eunit", ["rebar3", "eunit"])

    async def run_quality(self, root: Path) -> list[CommandResult]:
        return [await run_tool(root, "rebar3 xref", ["rebar3", "xref"])]

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
