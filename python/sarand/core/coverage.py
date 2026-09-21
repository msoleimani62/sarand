"""The coverage matrix: what sarand does for each ecosystem, derived from
the code itself.

Which languages sarand supports, and *how deeply*, is easy to state wrongly
by hand (a README says "31 analyzers"; `--doctor` lists tools; the analyzers
themselves decide what actually runs). This module builds one table from
those real sources and `docs/COVERAGE.md` is generated from it, with a test
that fails when the file is stale:

- **Tests / Quality / Security** -- true when the analyzer's `run_tests` /
  `run_quality` / `run_security` is more than a bare `return None` /
  `return []` (read from the analyzer's source with `ast`, so it cannot drift
  from the code).
- **Tools** -- the external tools `--doctor` lists for that ecosystem.
- **Build tools** -- the build/package manager sarand's project detector
  recognises from the project's marker files.

Regenerate the file with `python -m sarand.core.coverage > docs/COVERAGE.md`.

ماتریس پوشش: sarand برای هر اکوسیستم چه می‌کند، مستقیماً از خودِ کد استخراج
می‌شود. اینکه sarand کدام زبان‌ها را و *با چه عمقی* پشتیبانی می‌کند به‌سادگی
با دست غلط نوشته می‌شود (README می‌گوید «۳۱ آنالایزر»؛ `--doctor` ابزارها را
فهرست می‌کند؛ خودِ آنالایزرها تصمیم می‌گیرند واقعاً چه اجرا شود). این ماژول
یک جدول از همان منابع واقعی می‌سازد و `docs/COVERAGE.md` از آن تولید می‌شود،
با تستی که وقتی فایل کهنه باشد شکست می‌خورد.
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import dataclass
from pathlib import Path

from sarand.analyzers.registry import builtin_analyzers
from sarand.constants import PROJECT_MARKERS
from sarand.core.doctor import tool_catalog

# analyzer name -> the `--doctor` categories that list its tools. An empty
# tuple means "needs no external tool" (detection only).
# نام آنالایزر -> دسته‌های `--doctor` که ابزارهایش را فهرست می‌کنند. تاپل
# خالی یعنی «به ابزار خارجی نیاز ندارد» (فقط شناسایی).
DOCTOR_CATEGORIES: dict[str, tuple[str, ...]] = {
    "Python": ("Python",),
    "Rust": ("Rust",),
    "Go": ("Go",),
    "Node.js": ("Node.js",),
    "TypeScript": ("TypeScript",),
    "CSS": ("CSS",),
    "Zig": ("Zig",),
    "Assembly": (),
    "Swift": ("Swift",),
    "Objective-C": ("Objective-C",),
    "C/C++": ("C/C++",),
    "Lua": ("Lua",),
    "Ruby": ("Ruby",),
    "PHP": ("PHP",),
    "Dart": ("Dart / Flutter",),
    "R": ("R",),
    "Perl": ("Perl",),
    "Julia": ("Julia",),
    "SQL": ("SQL",),
    "Android/Kotlin": ("Java / Kotlin / Android",),
    "Java/Kotlin": ("Java / Kotlin / Android",),
    "Kotlin": ("Kotlin",),
    "Groovy": ("Groovy",),
    "C#": ("C#",),
    "Shell": ("Shell",),
    "PowerShell": ("PowerShell",),
    "Nix": ("Nix",),
    "YAML": ("YAML",),
    "JSON": ("JSON",),
    "TOML": ("TOML",),
    "XML": ("XML",),
    "Markdown": ("Markdown",),
    "Haskell": ("Haskell",),
    "Elixir": ("Elixir",),
    "Erlang": ("Erlang",),
    "Scala": ("Scala",),
    "Dockerfile": ("Dockerfile",),
    "GitHub Actions": ("GitHub Actions",),
    "Terraform": ("Terraform",),
    "Protobuf": ("Protobuf",),
}

# Doctor categories that are not an ecosystem an analyzer detects.
# دسته‌های doctor که اکوسیستمِ قابل‌شناسایی برای یک آنالایزر نیستند.
NON_ECOSYSTEM_CATEGORIES = frozenset({"Supply chain", "PDF export"})

# analyzer name -> language names used in constants.PROJECT_MARKERS
# (defaults to the analyzer's own name).
_MARKER_LANGUAGES: dict[str, tuple[str, ...]] = {
    "Dart": ("Dart/Flutter",),
    "Java/Kotlin": ("Java", "Java/Kotlin"),
    "Android/Kotlin": ("Java/Kotlin",),
}


@dataclass(frozen=True)
class CoverageRow:
    ecosystem: str
    tests: bool
    quality: bool
    security: bool
    tools: tuple[str, ...]
    build_tools: tuple[str, ...]


def _is_trivial(function: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    """True if the body is only a docstring and `return None` / `return []`."""
    body = [
        statement
        for statement in function.body
        if not (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        )
    ]
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        return False
    value = body[0].value
    if value is None:
        return True
    if isinstance(value, ast.Constant):
        return value.value is None
    return isinstance(value, ast.List) and not value.elts


def _capabilities(analyzer: object) -> tuple[bool, bool, bool]:
    source_file = inspect.getsourcefile(type(analyzer))
    if source_file is None:
        return (False, False, False)
    tree = ast.parse(Path(source_file).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == type(analyzer).__name__:
            methods = {
                child.name: child
                for child in node.body
                if isinstance(child, (ast.AsyncFunctionDef, ast.FunctionDef))
            }
            flags = [
                name in methods and not _is_trivial(methods[name])
                for name in ("run_tests", "run_quality", "run_security")
            ]
            return (flags[0], flags[1], flags[2])
    return (False, False, False)


def build_coverage() -> list[CoverageRow]:
    catalog = tool_catalog()
    rows: list[CoverageRow] = []
    for analyzer in builtin_analyzers():
        categories = DOCTOR_CATEGORIES[analyzer.name]
        tools: list[str] = []
        for category, binary, _hint, _used in catalog:
            if category in categories and binary not in tools:
                tools.append(binary)
        languages = _MARKER_LANGUAGES.get(analyzer.name, (analyzer.name,))
        builds: list[str] = []
        for language, _type, build in PROJECT_MARKERS.values():
            if language in languages and build not in builds and build != "none":
                builds.append(build)
        tests, quality, security = _capabilities(analyzer)
        rows.append(
            CoverageRow(
                analyzer.name, tests, quality, security, tuple(tools), tuple(builds)
            )
        )
    return rows


def render_markdown() -> str:
    def flag(value: bool) -> str:
        return "yes" if value else "-"

    lines = [
        "# Coverage matrix",
        "",
        "What sarand does for each ecosystem, derived from the code (see",
        "`sarand/core/coverage.py`). **Do not edit by hand:** regenerate with",
        "`python -m sarand.core.coverage > docs/COVERAGE.md`; a test fails when",
        "this file is stale.",
        "",
        "- **Tests / Quality / Security**: the analyzer implements that check.",
        "- **Tools**: external tools `sarand --doctor` lists for it (all optional;",
        "  a missing tool is skipped, never fatal).",
        "- **Build tools**: recognised from the project's marker files.",
        "",
        "| Ecosystem | Tests | Quality | Security | Tools | Build tools |",
        "|---|---|---|---|---|---|",
    ]
    for row in build_coverage():
        tools = ", ".join(f"`{t}`" for t in row.tools) or "none needed (detection only)"
        builds = ", ".join(row.build_tools) or "-"
        lines.append(
            f"| {row.ecosystem} | {flag(row.tests)} | {flag(row.quality)} | "
            f"{flag(row.security)} | {tools} | {builds} |"
        )
    lines.append("")
    lines.append(
        "Project-wide checks (`--security`, any ecosystem): gitleaks, syft (SBOM and "
        "license policy), lockfile check."
    )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    print(render_markdown(), end="")
