"""Dockerfile analyzer: hadolint on the Dockerfiles in the project root.

Matches on root-level `Dockerfile`, `Dockerfile.*`, `*.Dockerfile` or
`Containerfile` (shallow and deterministic, like the other extension-based
analyzers, so vendored example files cannot force a match). It never
builds an image and never runs a container; `hadolint` only reads the
files. Missing hadolint produces a clean skipped result.

تحلیل‌گر Dockerfile: hadolint روی Dockerfile های ریشه‌ی پروژه.

روی `Dockerfile`، `Dockerfile.*`، `*.Dockerfile` یا `Containerfile` در ریشه
match می‌شود (سطحی و قطعی، مثل بقیه‌ی آنالایزرهای مبتنی بر پسوند، تا
نمونه‌های vendored نتوانند match را اجبار کنند). هرگز image نمی‌سازد و
container اجرا نمی‌کند؛ `hadolint` فقط فایل‌ها را می‌خواند. نبودن hadolint
یک نتیجه‌ی skipped تمیز می‌دهد.
"""

from __future__ import annotations

from pathlib import Path

from sarand.analyzers._tooling import run_tool, top_level_files
from sarand.models.results import CommandResult


def _is_dockerfile(name: str) -> bool:
    return (
        name in {"Dockerfile", "Containerfile"}
        or name.startswith(("Dockerfile.", "Containerfile."))
        or name.endswith((".Dockerfile", ".dockerfile"))
    )


class DockerfileAnalyzer:
    name = "Dockerfile"

    def matches(self, root: Path) -> bool:
        return bool(top_level_files(root, _is_dockerfile))

    def entry_points(self, root: Path) -> list[str]:
        return top_level_files(root, _is_dockerfile)

    async def run_tests(self, root: Path) -> CommandResult | None:
        return None

    async def run_quality(self, root: Path) -> list[CommandResult]:
        files = top_level_files(root, _is_dockerfile)
        return [await run_tool(root, "hadolint", ["hadolint", "--no-color", *files])]

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
