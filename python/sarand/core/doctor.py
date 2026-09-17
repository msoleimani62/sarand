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
    (
        "Go",
        "govulncheck",
        "go install golang.org/x/vuln/cmd/govulncheck@latest",
        "--security",
    ),
    ("Node.js", "npm", "install Node.js: https://nodejs.org", "running tests"),
    (
        "TypeScript",
        "tsc",
        "npm install -g typescript (or add to project devDependencies)",
        "--quality (type-check via tsc --noEmit)",
    ),
    (
        "CSS",
        "stylelint",
        "npm install -g stylelint (or add to project devDependencies)",
        "--quality",
    ),
    (
        "Zig",
        "zig",
        "install Zig: https://ziglang.org/download/",
        "running tests / --quality (zig fmt) / project detection",
    ),
    (
        "Swift",
        "swift",
        "install Swift: https://www.swift.org/install/",
        "running tests (SwiftPM packages) / project detection",
    ),
    (
        "Swift",
        "swift-format",
        "https://github.com/apple/swift-format (or `brew install swift-format`)",
        "--quality",
    ),
    (
        "Swift",
        "xcodebuild",
        "install Xcode + Command Line Tools (macOS only)",
        "running tests for Xcode-only projects (no Package.swift)",
    ),
    ("SQL", "sqlfluff", "pip install sqlfluff", "--quality"),
    (
        "C/C++",
        "cmake",
        "install CMake: https://cmake.org/download/",
        "project detection",
    ),
    (
        "C/C++",
        "cppcheck",
        "install cppcheck (e.g. apt/pacman/brew install cppcheck)",
        "--security",
    ),
    (
        "Java / Kotlin / Android",
        "mvn",
        "install Maven: https://maven.apache.org/install.html",
        "Maven projects",
    ),
    (
        "Java / Kotlin / Android",
        "gradle",
        "install Gradle, or rely on a project's ./gradlew wrapper",
        "Gradle & Android projects (skipped automatically if ./gradlew exists)",
    ),
    (
        "PDF export",
        "wkhtmltopdf",
        "install wkhtmltopdf (e.g. apt/pacman install wkhtmltopdf)",
        "--format pdf",
    ),
    (
        "PDF export",
        "weasyprint",
        "pip install weasyprint",
        "--format pdf (fallback engine)",
    ),
    ("Lua", "busted", "luarocks install busted", "running tests"),
    ("Lua", "luacheck", "luarocks install luacheck", "--quality"),
    ("Ruby", "bundle", "gem install bundler", "running tests / --quality / --security"),
    (
        "PHP",
        "composer",
        "install Composer: https://getcomposer.org/download/",
        "--security (and running project-local vendor/bin/phpunit or phpstan)",
    ),
    (
        "Dart / Flutter",
        "dart",
        "install the Dart SDK: https://dart.dev/get-dart",
        "running tests / --quality (Flutter projects use `flutter` instead)",
    ),
    (
        "Kotlin",
        "ktlint",
        "install ktlint: https://pinterest.github.io/ktlint/install/cli/",
        "--quality",
    ),
    (
        "Kotlin",
        "detekt",
        "install detekt: https://detekt.dev/docs/gettingstarted/cli",
        "--quality",
    ),
    (
        "C#",
        "dotnet",
        "install the .NET SDK: https://dotnet.microsoft.com/download",
        "running tests / --quality (dotnet format) / --security (dotnet list package)",
    ),
    (
        "Shell",
        "shellcheck",
        "install shellcheck (e.g. apt/pacman/brew install shellcheck)",
        "--quality",
    ),
    (
        "Shell",
        "bats",
        "install bats-core: https://bats-core.readthedocs.io/en/stable/installation.html",
        "running tests (only when a tests/*.bats suite exists)",
    ),
    ("YAML", "yamllint", "pip install yamllint", "--quality"),
    (
        "JSON",
        "jsonlint",
        (
            "npm install -g jsonlint (optional -- falls back to a "
            "built-in syntax-only check without it)"
        ),
        "--quality",
    ),
    (
        "TOML",
        "taplo",
        "install taplo: https://taplo.tamasfe.dev/cli/installation/",
        "--quality",
    ),
    (
        "XML",
        "xmllint",
        "install libxml2 (e.g. apt/pacman install libxml2)",
        "--quality",
    ),
    (
        "R",
        "Rscript",
        "install R: https://www.r-project.org/",
        "running tests (testthat) / --quality (lintr)",
    ),
    (
        "Perl",
        "prove",
        "install Perl (ships with prove) or: cpan Test::Harness",
        "running tests",
    ),
    (
        "Perl",
        "perlcritic",
        "cpan Perl::Critic",
        "--quality",
    ),
    (
        "Julia",
        "julia",
        "install Julia: https://julialang.org/downloads/",
        "running tests (Pkg.test())",
    ),
    (
        "Objective-C",
        "xcodebuild",
        "install Xcode + Command Line Tools (macOS only)",
        "running tests for Xcode/CocoaPods projects",
    ),
    (
        "Groovy",
        "codenarc",
        "install CodeNarc: https://codenarc.org/",
        "--quality",
    ),
    (
        "PowerShell",
        "pwsh",
        "install PowerShell 7+: https://aka.ms/powershell",
        "running tests (Pester) / --quality (PSScriptAnalyzer)",
    ),
    (
        "Nix",
        "nix",
        "install Nix: https://nixos.org/download.html",
        "running tests (nix flake check)",
    ),
    (
        "Nix",
        "nixpkgs-fmt",
        "nix-env -iA nixpkgs.nixpkgs-fmt",
        "--quality",
    ),
)

_CATEGORY_ORDER = (
    "Python",
    "Rust",
    "Go",
    "Node.js",
    "TypeScript",
    "CSS",
    "Zig",
    "Swift",
    "C/C++",
    "Java / Kotlin / Android",
    "Kotlin",
    "C#",
    "Shell",
    "Lua",
    "Ruby",
    "PHP",
    "Dart / Flutter",
    "SQL",
    "YAML",
    "JSON",
    "TOML",
    "XML",
    "R",
    "Perl",
    "Julia",
    "Objective-C",
    "Groovy",
    "PowerShell",
    "Nix",
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
            fix=""
            if RUST_CORE_AVAILABLE
            else "cd into the sarand repo and run: maturin develop --release",
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
            + (
                f"(output_dir = {output_dir})"
                if output_dir
                else "(not set yet -- using built-in default)"
            ),
            category="Core",
        )
    )

    for category, binary, fix, used_for in _TOOL_CHECKS:
        checks.append(_tool_check(category, binary, fix, used_for))

    return checks


def _print_core(checks: list[DoctorCheck]) -> None:
    """Core checks as a single narrow-friendly panel: one wrapped text
    line per check instead of a table, so nothing gets column-truncated
    on a phone-width terminal (Termux, SSH from a small screen, etc.)."""
    from rich.panel import Panel

    lines: list[str] = []
    for check in checks:
        if check.category != "Core":
            continue
        icon = "[green]✓[/green]" if check.ok else "[red]✗[/red]"
        line = f"{icon} [bold]{check.name}[/bold] -- {check.detail}"
        if not check.ok and check.fix:
            line += f"\n   [dim]fix:[/dim] {check.fix}"
        lines.append(line)

    console.print(
        Panel("\n".join(lines), title="Core", title_align="left", expand=True)
    )


def _print_language_tools(checks: list[DoctorCheck]) -> None:
    """One panel per language category, each tool as a wrapped text
    line (icon, name, what it's for, and a fix hint only when missing).

    Deliberately not a table: a 5-column table truncates every cell to
    a sliver on a phone-width terminal, which is unreadable regardless
    of how the columns are tuned. Plain wrapped text inside a panel
    degrades gracefully at any width instead -- narrower terminals just
    wrap onto more lines, nothing is ever cut off or ellipsized.
    """
    from rich.console import Group
    from rich.panel import Panel

    panels = []
    for category in _CATEGORY_ORDER:
        cat_checks = [c for c in checks if c.category == category]
        if not cat_checks:
            continue
        lines: list[str] = []
        for check in cat_checks:
            icon = "[green]✓[/green]" if check.ok else "[yellow]○[/yellow]"
            line = f"{icon} [bold]{check.name}[/bold]"
            if check.used_for:
                line += f"\n   [dim]{check.used_for}[/dim]"
            if not check.ok and check.fix:
                line += f"\n   [dim]fix:[/dim] {check.fix}"
            lines.append(line)
        panels.append(
            Panel(
                "\n".join(lines),
                title=category,
                title_align="left",
                expand=True,
            )
        )

    console.print(
        "[bold]Optional per-language tools[/bold] "
        "[dim](only needed for the languages you actually scan)[/dim]"
    )
    console.print()
    console.print(Group(*panels))


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

    console.print(
        Panel("[bold]sarand doctor[/bold]\nEnvironment diagnostics", expand=False)
    )
    console.print()
    _print_core(checks)
    console.print()
    _print_language_tools(checks)
    console.print()

    critical_failed = [c for c in checks if c.critical and not c.ok]
    if critical_failed:
        console.print(
            Panel(
                "[bold red]✗ Critical check failed[/bold red] -- see Core above.",
                expand=False,
            )
        )
        return 1

    missing_optional = [
        c for c in checks if not c.ok and not c.critical and c.category != "Core"
    ]
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
        console.print(
            Panel(
                "[bold green]✓ Everything checked is present.[/bold green]",
                expand=False,
            )
        )
    return 0
