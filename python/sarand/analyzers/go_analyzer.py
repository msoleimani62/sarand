"""Go analyzer: go test + go vet/gofmt, gated on go.mod."""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.go")

_ENTRY_POINTS = ("main.go", "cmd/main.go")


class GoAnalyzer:
    name = "Go"

    def matches(self, root: Path) -> bool:
        return (root / "go.mod").exists()

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).exists()]

    async def run_tests(self, root: Path) -> CommandResult | None:
        if shutil.which("go") is None:
            return make_command_result(
                "go test",
                127,
                "",
                0.0,
                skipped=True,
                skip_reason="go not found in PATH",
            )
        logger.info("Running go test ./...")
        rc, output, duration = await run_cmd_async(
            ["go", "test", "./..."], root, LONG_CMD_TIMEOUT
        )
        return make_command_result("go test", rc, output, duration)

    async def run_quality(self, root: Path) -> list[CommandResult]:
        results: list[CommandResult] = []

        if shutil.which("go") is None:
            results.append(
                make_command_result(
                    "go vet",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="go not found in PATH",
                )
            )
        else:
            rc, out, dur = await run_cmd_async(
                ["go", "vet", "./..."], root, LONG_CMD_TIMEOUT
            )
            results.append(make_command_result("go vet", rc, out, dur))

        # Deliberately just staticcheck, not golangci-lint -- the report
        # that prompted this called staticcheck "core", golangci-lint a
        # "200-tool installer"; same "core, not kitchen-sink" reasoning
        # rust_analyzer.py/python_analyzer.py already follow. Independent
        # of `go` itself (its own binary, own install path), same shape
        # as cargo-audit/cargo-deny being independent of plain `cargo`.
        #
        # عمداً فقط staticcheck، نه golangci-lint -- همان گزارشی که این
        # دور را شروع کرد، staticcheck را «core» خواند و golangci-lint
        # را «یک نصب‌کننده‌ی ۲۰۰ ابزاری»؛ همان استدلال «core، نه
        # کیف‌ابزار کامل» که rust_analyzer.py/python_analyzer.py از قبل
        # دنبال می‌کنند. مستقل از خودِ `go` است (باینری خودش، مسیر نصب
        # خودش)، همان شکلی که cargo-audit/cargo-deny مستقل از `cargo`ی
        # ساده هستند.
        if shutil.which("staticcheck") is None:
            results.append(
                make_command_result(
                    "staticcheck",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="staticcheck not installed",
                )
            )
        else:
            rc, out, dur = await run_cmd_async(
                ["staticcheck", "./..."], root, LONG_CMD_TIMEOUT
            )
            results.append(make_command_result("staticcheck", rc, out, dur))

        return results

    async def run_security(self, root: Path) -> list[CommandResult]:
        if shutil.which("govulncheck") is None:
            return [
                make_command_result(
                    "govulncheck",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="govulncheck not installed",
                )
            ]
        rc, out, dur = await run_cmd_async(
            ["govulncheck", "./..."], root, LONG_CMD_TIMEOUT
        )
        return [make_command_result("govulncheck", rc, out, dur)]
