"""The pluggable analyzer contract.

This is the piece that was missing from bxt: instead of hardcoding
"if Cargo.toml: run cargo test" directly inside a test-runner module,
every language is a self-contained ``LanguageAnalyzer`` that knows how
to detect itself, test itself, and lint itself. Adding a new language
means adding one new file here (or a third-party plugin) -- nothing
else in sarand needs to change.

این همان تکه‌ای است که در bxt غایب بود: به‌جای هاردکد کردن «اگر
Cargo.toml هست، cargo test بزن» مستقیم داخل ماژول اجرای تست، هر زبان
یک ``LanguageAnalyzer`` خودمختار است که بلد است خودش را تشخیص بدهد،
تست کند و لینت کند. اضافه کردن یک زبان جدید یعنی افزودن یک فایل جدید
اینجا (یا یک پلاگین شخص‌ثالث) -- هیچ‌جای دیگر sarand نیاز به تغییر ندارد.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from sarand.models.results import CommandResult


@runtime_checkable
class LanguageAnalyzer(Protocol):
    """Contract every language analyzer (built-in or plugin) must satisfy."""

    #: Human-readable language name, e.g. "Python", "Rust".
    name: str

    def matches(self, root: Path) -> bool:
        """Return True if this analyzer applies to the project at root."""
        ...

    def entry_points(self, root: Path) -> list[str]:
        """Return known entry-point files/dirs that exist under root."""
        ...

    async def run_tests(self, root: Path) -> CommandResult | None:
        """Run this language's test suite, or None if nothing to run."""
        ...

    async def run_quality(self, root: Path) -> list[CommandResult]:
        """Run this language's lint/format checks. Empty list if none available."""
        ...

    async def run_security(self, root: Path) -> list[CommandResult]:
        """Run this language's dependency/vulnerability checks (e.g. pip-audit,
        cargo audit, govulncheck, npm audit). Empty list if none available.
        Gated the same way as run_quality (§4.3 in AGENTS.md): only ever
        called after matches(root) is True, and must never crash just
        because the underlying tool binary is missing -- return a skipped
        CommandResult instead."""
        ...
