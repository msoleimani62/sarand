"""`sarand doctor` -- one-shot environment diagnostic (AGENTS.md §4.11).

Never lets a missing tool fail silently: every check prints a clear
pass/fail line and, on failure, the exact command to fix it. Missing
per-language toolchains are informational, not failures -- no single
machine is expected to have every language's tools installed; the
Python-version check is the only one that can fail the whole command.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass

from sarand.progress import console
from sarand.rust_bridge import RUST_CORE_AVAILABLE
from sarand.userconfig import get_config_path, load_persisted_config

_MIN_PYTHON = (3, 10)

# (category, binary, fix-it hint, what it's used for)
# Grouped by category so the table reads as "here's what's available
# for language X", not a flat list that looks like sarand itself is
# missing 15 features.
_TOOL_CHECKS: tuple[tuple[str, str, str, str], ...] = (
    ("Python", "pytest", "pip install pytest", "running tests"),
    ("Python", "ruff", "pip install ruff", "--quality"),
    ("Python", "pip-audit", "pip install pip-audit", "--security"),
    ("Python", "bandit", "pip install bandit", "--security"),
    ("Rust", "cargo", "install rustup: https://rustup.rs", "running tests"),
    ("Rust", "cargo-audit", "cargo install cargo-audit", "--security"),
    ("Go", "go", "install Go: https://go.dev/dl/", "running tests"),
    ("Go", "govulncheck", "go install golang.org/x/vuln/cmd/govulncheck@latest", "--security"),
    ("Node.js", "npm", "install Node.js: https://nodejs.org", "running tests"),
    ("C/C++", "cmake", "install CMake: https://cmake.org/download/", "project detection"),
    ("C/C++", "cppcheck", "install cppcheck (e.g. apt/pacman/brew install cppcheck)", "--security"),
    ("Java / Kotlin / Android", "mvn", "install Maven: https://maven.apache.org/install.html", "Maven projects"),
    (
        "Java / Kotlin / Android",
        "gradle",
        "install Gradle, or rely on a project's ./gradlew wrapper",
        "Gradle & Android projects (skipped automatically if ./gradlew exists)",
    ),
    ("PDF export", "wkhtmltopdf", "install wkhtmltopdf (e.g. apt/pacman install wkhtmltopdf)", "--format pdf"),
    ("PDF export", "weasyprint", "pip install weasyprint", "--format pdf (fallback engine)"),
)

_CATEGORY_ORDER = (
    "Python",
    "Rust",
    "Go",
    "Node.js",
    "C/C++",
    "Java / Kotlin / Android",
    "PDF export",
)


@dataclass
class DoctorCheck:
    name: str
    ok: bool
    detail: str
    fix: str = ""
    critical: bool = False
    category: str = "Core"
    used_for: str = ""


def _tool_check(category: str, binary: str, fix: str, used_for: str) -> DoctorCheck:
    found = shutil.which(binary) is not None
    return DoctorCheck(
        name=binary,
        ok=found,
        detail="found in PATH" if found else "not found in PATH",
        fix="" if found else fix,
        category=category,
        used_for=used_for,
    )


def collect_checks() -> list[DoctorCheck]:
    """Gather every diagnostic check. Pure function, no printing -- kept
    separate from run_doctor() so it's directly unit-testable."""
    checks: list[DoctorCheck] = []

    py_ok = sys.version_info >= _MIN_PYTHON
    checks.append(
        DoctorCheck(
            name="Python version",
            ok=py_ok,
            detail=f"{sys.version.split()[0]} (need >= {'.'.join(map(str, _MIN_PYTHON))})",
            fix="Install Python 3.10 or newer." if not py_ok else "",
            critical=True,
            category="Core",
        )
    )

    checks.append(
        DoctorCheck(
            name="Rust core (sarand._core)",
            ok=RUST_CORE_AVAILABLE,
            detail="compiled and loaded"
            if RUST_CORE_AVAILABLE
            else "not built -- using the pure-Python fallback (slower, still correct)",
            fix="" if RUST_CORE_AVAILABLE else "cd into the sarand repo and run: maturin develop --release",
            category="Core",
        )
    )

    persisted = load_persisted_config()
    output_dir = persisted.get("output_dir")
    checks.append(
        DoctorCheck(
            name="Persisted config",
            ok=True,
            detail=f"{get_config_path()} "
            + (f"(output_dir = {output_dir})" if output_dir else "(not set yet -- using built-in default)"),
            category="Core",
        )
    )

    for category, binary, fix, used_for in _TOOL_CHECKS:
        checks.append(_tool_check(category, binary, fix, used_for))

    return checks


def _print_core_table(checks: list[DoctorCheck]) -> None:
    from rich.table import Table

    table = Table(title="Core", title_justify="left", show_lines=False, expand=True)
    table.add_column("Check", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Detail")

    for check in [c for c in checks if c.category == "Core"]:
        status = "[green]OK[/green]" if check.ok else "[red]FAILED[/red]"
        detail = check.detail
        if check.fix:
            detail += f"\n[dim]fix: {check.fix}[/dim]"
        table.add_row(check.name, status, detail)

    console.print(table)


def _print_language_table(checks: list[DoctorCheck]) -> None:
    from rich.table import Table

    table = Table(
        title="Optional per-language tools (only needed for the languages you actually scan)",
        title_justify="left",
        show_lines=False,
        expand=True,
    )
    table.add_column("Category", style="bold")
    table.add_column("Tool")
    table.add_column("Status", justify="center")
    table.add_column("Used for")
    table.add_column("Fix if missing")

    last_category = None
    for check in checks:
        if check.category not in _CATEGORY_ORDER:
            continue
        status = "[green]present[/green]" if check.ok else "[yellow]not installed[/yellow]"
        category_cell = check.category if check.category != last_category else ""
        last_category = check.category
        table.add_row(category_cell, check.name, status, check.used_for, check.fix or "[dim]--[/dim]")

    console.print(table)


def run_doctor() -> int:
    """Print the full diagnostic report and return an exit code.

    Returns:
        0 unless a *critical* check failed (currently: Python version
        too old). Missing optional per-language tools never fail the
        command itself -- they're grouped and labeled as optional
        specifically so they don't read as sarand being incomplete.
    """
    from rich.panel import Panel

    checks = collect_checks()

    console.print(Panel("[bold]sarand doctor[/bold]\nEnvironment diagnostics", expand=False))
    console.print()
    _print_core_table(checks)
    console.print()
    _print_language_table(checks)
    console.print()

    critical_failed = [c for c in checks if c.critical and not c.ok]
    if critical_failed:
        console.print(Panel("[bold red]✗ Critical check failed[/bold red] -- see the Core table above.", expand=False))
        return 1

    missing_optional = [c for c in checks if not c.ok and not c.critical and c.category != "Core"]
    if missing_optional:
        console.print(
            Panel(
                f"[bold green]✓ No critical issues.[/bold green]\n"
                f"{len(missing_optional)} optional tool(s) not installed -- each only affects "
                "the specific language/format listed next to it. Install as needed.",
                expand=False,
            )
        )
    else:
        console.print(Panel("[bold green]✓ Everything checked is present.[/bold green]", expand=False))
    return 0
