"""Rust analyzer: cargo test + cargo fmt/clippy, gated on Cargo.toml."""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.rust")

_ENTRY_POINTS = ("src/main.rs", "src/lib.rs")


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
        rc, out, dur = await run_cmd_async(
            ["cargo", "fmt", "--all", "--check"], root, LONG_CMD_TIMEOUT
        )
        results.append(make_command_result("cargo fmt --check", rc, out, dur))
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
        # `cargo audit` is a cargo *subcommand*, provided by the separate
        # `cargo-audit` binary -- check for that binary, not "cargo" itself.
        # `cargo audit` یک زیردستور cargo است که توسط باینری جداگانه‌ی
        # `cargo-audit` فراهم می‌شود -- باید همان باینری چک شود، نه خودِ cargo.
        if shutil.which("cargo-audit") is None:
            return [
                make_command_result(
                    "cargo audit",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="cargo-audit not installed",
                )
            ]
        rc, out, dur = await run_cmd_async(["cargo", "audit"], root, LONG_CMD_TIMEOUT)
        return [make_command_result("cargo audit", rc, out, dur)]
