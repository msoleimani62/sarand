"""Rust analyzer: cargo test + cargo fmt/clippy/deny, gated on Cargo.toml."""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.rust")

_ENTRY_POINTS = ("src/main.rs", "src/lib.rs")

# `rustfmt`/`cargo-clippy` usually ship with a rustup toolchain but are
# each their own component, not guaranteed -- check the two binaries
# independently instead of assuming both exist just because `cargo`
# does, so a missing one skips cleanly (§4.11) instead of `cargo fmt`/
# `cargo clippy` failing with a confusing toolchain error that looks
# like a real lint failure.
#
# `rustfmt`/`cargo-clippy` معمولاً همراه یک toolchain rustup می‌آیند اما
# هرکدام کامپوننت جداگانه‌ی خودشان هستند، نه تضمین‌شده -- این دو باینری
# جدا از هم چک می‌شوند نه با فرض اینکه چون `cargo` هست پس آن‌ها هم
# هستند، تا کامپوننت غایب تمیز رد شود (§4.11) نه اینکه `cargo fmt`/
# `cargo clippy` با یک خطای گنگ toolchain شکست بخورد که شبیه یک شکست
# lint واقعی به‌نظر می‌رسد.


class RustAnalyzer:
    name = "Rust"

    def matches(self, root: Path) -> bool:
        return (root / "Cargo.toml").exists()

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).exists()]

    async def run_tests(self, root: Path) -> CommandResult | None:
        if shutil.which("cargo") is None:
            return make_command_result(
                "cargo test",
                127,
                "",
                0.0,
                skipped=True,
                skip_reason="cargo not found in PATH",
            )
        logger.info("Running cargo test --all")
        rc, output, duration = await run_cmd_async(
            ["cargo", "test", "--all"], root, LONG_CMD_TIMEOUT
        )
        return make_command_result("cargo test", rc, output, duration)

    async def run_quality(self, root: Path) -> list[CommandResult]:
        if shutil.which("cargo") is None:
            return [
                make_command_result(
                    "cargo fmt/clippy",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="cargo not found in PATH",
                )
            ]
        results = []

        if shutil.which("rustfmt") is None:
            results.append(
                make_command_result(
                    "cargo fmt --check",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="rustfmt component not installed "
                    "(rustup component add rustfmt)",
                )
            )
        else:
            rc, out, dur = await run_cmd_async(
                ["cargo", "fmt", "--all", "--check"], root, LONG_CMD_TIMEOUT
            )
            results.append(make_command_result("cargo fmt --check", rc, out, dur))

        if shutil.which("cargo-clippy") is None:
            results.append(
                make_command_result(
                    "cargo clippy",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="clippy component not installed "
                    "(rustup component add clippy)",
                )
            )
        else:
            rc, out, dur = await run_cmd_async(
                [
                    "cargo",
                    "clippy",
                    "--all-targets",
                    "--all-features",
                    "--",
                    "-D",
                    "warnings",
                ],
                root,
                LONG_CMD_TIMEOUT,
            )
            results.append(make_command_result("cargo clippy", rc, out, dur))

        return results

    async def run_security(self, root: Path) -> list[CommandResult]:
        # cargo-audit and cargo-deny are fully independent tools (own
        # binary, own gating, own reason to skip) -- run them
        # concurrently via asyncio.gather (§4.7), the same pattern
        # python_analyzer.py uses for pip-audit + bandit. Gating one
        # behind the other's binary/opt-out check would silently skip
        # cargo-deny on a machine that has cargo-deny but not
        # cargo-audit (or vice versa), which is a real bug this
        # structure avoids by construction.
        #
        # cargo-audit و cargo-deny ابزارهایی کاملاً مستقل‌اند (باینری
        # خودشان، gating خودشان، دلیل رد کردن خودشان) -- با
        # asyncio.gather هم‌زمان اجرا می‌شوند (§4.7)، همان الگویی که
        # python_analyzer.py برای pip-audit + bandit استفاده می‌کند.
        # گره‌زدن یکی پشت باینری/opt-out دیگری یعنی روی دستگاهی که
        # cargo-deny دارد ولی cargo-audit ندارد (یا برعکس)، cargo-deny
        # بی‌صدا رد شود -- باگ واقعی‌ای که این ساختار از پایه جلویش را
        # می‌گیرد.
        audit_result, deny_result = await asyncio.gather(
            self._run_cargo_audit(root), self._run_cargo_deny(root)
        )
        return [audit_result, deny_result]

    async def _run_cargo_audit(self, root: Path) -> CommandResult:
        # `cargo audit` is a cargo *subcommand*, provided by the separate
        # `cargo-audit` binary -- check for that binary, not "cargo" itself.
        # `cargo audit` یک زیردستور cargo است که توسط باینری جداگانه‌ی
        # `cargo-audit` فراهم می‌شود -- باید همان باینری چک شود، نه خودِ cargo.
        if shutil.which("cargo-audit") is None:
            return make_command_result(
                "cargo audit",
                127,
                "",
                0.0,
                skipped=True,
                skip_reason="cargo-audit not installed",
            )
        # Same opt-out as pip-audit and for the same reason: a
        # vulnerability-database audit's cost isn't something sarand's
        # own code can reduce further once it's already scoped
        # correctly. See python_analyzer.py's matching comment.
        #
        # همان مسیر رد کردن pip-audit و به همان دلیل: هزینه‌ی یک audit
        # پایگاه‌داده‌ی آسیب‌پذیری، وقتی از قبل درست محدود شده، چیزی
        # نیست که کد خودِ sarand دیگر بتواند کمترش کند. کامنت مشابه در
        # python_analyzer.py را ببینید.
        if os.environ.get("SARAND_SKIP_AUDIT"):
            return make_command_result(
                "cargo audit",
                0,
                "",
                0.0,
                skipped=True,
                skip_reason="skipped via --skip-audit",
            )
        rc, out, dur = await run_cmd_async(["cargo", "audit"], root, LONG_CMD_TIMEOUT)
        return make_command_result("cargo audit", rc, out, dur)

    async def _run_cargo_deny(self, root: Path) -> CommandResult:
        # `cargo-deny` is a separate binary too (same shape as
        # cargo-audit above): advisories/bans/licenses/sources policy,
        # broader than cargo-audit's vulnerability-only scope.
        #
        # `cargo-deny` هم یک باینری جداگانه است (همان شکل cargo-audit
        # بالا): سیاست advisories/bans/licenses/sources، فراتر از دامنه‌ی
        # فقط-آسیب‌پذیریِ cargo-audit.
        if shutil.which("cargo-deny") is None:
            return make_command_result(
                "cargo deny check",
                127,
                "",
                0.0,
                skipped=True,
                skip_reason="cargo-deny not installed",
            )

        # cargo-deny reads its policy from deny.toml at the project
        # root and refuses to run (with a confusing error, not a clean
        # skip) if that file is absent. §4.3 requires gating on a real
        # project marker before invoking an external tool -- deny.toml
        # is that marker here, same role Cargo.toml plays for the
        # analyzer as a whole.
        #
        # cargo-deny سیاست خودش را از deny.toml در ریشه‌ی پروژه
        # می‌خواند و اگر آن فایل نباشد اجرا نمی‌شود (با یک خطای گنگ، نه
        # یک رد تمیز). §4.3 می‌گوید قبل از فراخوانی یک ابزار خارجی باید
        # روی یک نشانگر واقعی پروژه gate بزنیم -- اینجا deny.toml همان
        # نشانگر است، دقیقاً همان نقشی که Cargo.toml برای کل آنالایزر
        # دارد.
        if not (root / "deny.toml").exists():
            return make_command_result(
                "cargo deny check",
                0,
                "",
                0.0,
                skipped=True,
                skip_reason="no deny.toml in project root (run: cargo deny init)",
            )

        # Same opt-out as cargo-audit/pip-audit, for the same reason:
        # cargo-deny's advisory/license checks carry a fixed external
        # cost this project's own code cannot reduce further.
        #
        # همان مسیر رد کردن cargo-audit/pip-audit، به همان دلیل:
        # بررسی‌های advisory/license در cargo-deny یک هزینه‌ی خارجیِ
        # ثابت دارند که کد خودِ این پروژه دیگر نمی‌تواند کمترش کند.
        if os.environ.get("SARAND_SKIP_AUDIT"):
            return make_command_result(
                "cargo deny check",
                0,
                "",
                0.0,
                skipped=True,
                skip_reason="skipped via --skip-audit",
            )

        rc, out, dur = await run_cmd_async(
            ["cargo", "deny", "check"], root, LONG_CMD_TIMEOUT
        )
        return make_command_result("cargo deny check", rc, out, dur)
