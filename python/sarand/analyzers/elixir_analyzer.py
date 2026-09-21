"""Elixir analyzer: `mix test`, `mix format --check-formatted`, Credo, Hex audit.

Matches on a root-level `mix.exs`. `mix format` and `mix hex.audit` are
built into Mix/Hex; Credo (`mix credo`) and MixAudit (`mix deps.audit`) are
project dependencies, so -- like RuboCop under Bundler -- they are only run
when `mix.exs` actually names them; otherwise `mix` would fail with "task
not found" and the report would blame the project for a check it never
opted into.

تحلیل‌گر Elixir: `mix test`، `mix format --check-formatted`، Credo و Hex audit.

روی `mix.exs` در ریشه match می‌شود. `mix format` و `mix hex.audit` جزو خود
Mix/Hex هستند؛ Credo (`mix credo`) و MixAudit (`mix deps.audit`) وابستگی
پروژه‌اند، پس -- مثل RuboCop زیر Bundler -- فقط وقتی اجرا می‌شوند که `mix.exs`
واقعاً اسمشان را ببرد؛ وگرنه `mix` با «task not found» شکست می‌خورد و گزارش
پروژه را به‌خاطر چکی که هرگز انتخابش نکرده مقصر می‌کرد.
"""

from __future__ import annotations

from pathlib import Path

from sarand.analyzers._tooling import existing, read_text_safely, run_tool
from sarand.models.results import CommandResult


class ElixirAnalyzer:
    name = "Elixir"

    def matches(self, root: Path) -> bool:
        return (root / "mix.exs").is_file()

    def entry_points(self, root: Path) -> list[str]:
        return existing(root, ("mix.exs", "config/config.exs"))

    async def run_tests(self, root: Path) -> CommandResult | None:
        return await run_tool(root, "mix test", ["mix", "test"])

    async def run_quality(self, root: Path) -> list[CommandResult]:
        results = [
            await run_tool(root, "mix format", ["mix", "format", "--check-formatted"])
        ]
        if "credo" in read_text_safely(root / "mix.exs"):
            results.append(await run_tool(root, "mix credo", ["mix", "credo"]))
        return results

    async def run_security(self, root: Path) -> list[CommandResult]:
        results = [await run_tool(root, "mix hex.audit", ["mix", "hex.audit"])]
        if "mix_audit" in read_text_safely(root / "mix.exs"):
            results.append(
                await run_tool(root, "mix deps.audit", ["mix", "deps.audit"])
            )
        return results
