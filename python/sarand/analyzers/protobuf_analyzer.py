"""Protobuf analyzer: `buf lint`.

Matches on a root-level `buf.yaml`/`buf.work.yaml`, a root-level `*.proto`
file, or a first-level `proto/` directory containing one. `buf lint` only
reads the definitions; it never generates code. `protoc` is deliberately
not used: it can compile but not lint, and `buf` is the standard linter.

تحلیل‌گر Protobuf: `buf lint`.

روی `buf.yaml`/`buf.work.yaml` در ریشه، یک فایل `*.proto` در ریشه، یا یک
پوشه‌ی سطح اول `proto/` که یکی داشته باشد match می‌شود. `buf lint` فقط
تعریف‌ها را می‌خواند و هرگز کد تولید نمی‌کند. `protoc` عمداً استفاده نمی‌شود:
compile می‌کند ولی lint نمی‌کند و `buf` لینتر استاندارد است.
"""

from __future__ import annotations

from pathlib import Path

from sarand.analyzers._tooling import existing, run_tool, top_level_files
from sarand.models.results import CommandResult


def _has_proto_dir(root: Path) -> bool:
    return bool(top_level_files(root / "proto", lambda name: name.endswith(".proto")))


class ProtobufAnalyzer:
    name = "Protobuf"

    def matches(self, root: Path) -> bool:
        return (
            bool(existing(root, ("buf.yaml", "buf.work.yaml")))
            or bool(top_level_files(root, lambda name: name.endswith(".proto")))
            or _has_proto_dir(root)
        )

    def entry_points(self, root: Path) -> list[str]:
        return existing(root, ("buf.yaml", "buf.work.yaml", "buf.gen.yaml", "proto"))

    async def run_tests(self, root: Path) -> CommandResult | None:
        return None

    async def run_quality(self, root: Path) -> list[CommandResult]:
        return [await run_tool(root, "buf lint", ["buf", "lint"])]

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
