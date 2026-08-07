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

# (display name, binary, fix-it hint)
_TOOL_CHECKS: tuple[tuple[str, str, str], ...] = (
    ("Python: pytest", "pytest", "pip install pytest"),
    ("Python: ruff", "ruff", "pip install ruff"),
    ("Python: pip-audit", "pip-audit", "pip install pip-audit"),
    ("Python: bandit", "bandit", "pip install bandit"),
    ("Rust: cargo", "cargo", "install rustup: https://rustup.rs"),
    ("Rust: cargo-audit", "cargo-audit", "cargo install cargo-audit"),
    ("Go: go", "go", "install Go: https://go.dev/dl/"),
    ("Go: govulncheck", "govulncheck", "go install golang.org/x/vuln/cmd/govulncheck@latest"),
    ("Node.js: npm", "npm", "install Node.js: https://nodejs.org"),
    ("C/C++: cmake", "cmake", "install CMake: https://cmake.org/download/"),
    ("C/C++: cppcheck", "cppcheck", "install cppcheck (e.g. apt/pacman/brew install cppcheck)"),
    ("Java/Kotlin: mvn", "mvn", "install Maven: https://maven.apache.org/install.html"),
    ("Java/Kotlin: gradle", "gradle", "install Gradle, or rely on a project's ./gradlew wrapper"),
)


@dataclass
class DoctorCheck:
    name: str
    ok: bool
    detail: str
    fix: str = ""
    critical: bool = False


def _tool_check(name: str, binary: str, fix: str) -> DoctorCheck:
    found = shutil.which(binary) is not None
    return DoctorCheck(
        name=name,
        ok=found,
        detail=f"`{binary}` found in PATH" if found else f"`{binary}` not found in PATH",
        fix="" if found else fix,
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
        )
    )

    for name, binary, fix in _TOOL_CHECKS:
        checks.append(_tool_check(name, binary, fix))

    return checks


def run_doctor() -> int:
    """Print the full diagnostic report and return an exit code.

    Returns:
        0 unless a *critical* check failed (currently: Python version
        too old). Missing optional per-language tools never fail the
        command itself.
    """
    checks = collect_checks()

    console.print("[bold]sarand doctor[/bold]")
    console.print()
    for check in checks:
        badge = "[green]OK[/green]" if check.ok else "[yellow]--[/yellow]"
        console.print(f"  [{badge}] {check.name}: {check.detail}")
        if check.fix:
            console.print(f"        fix: {check.fix}")

    console.print()
    critical_failed = [c for c in checks if c.critical and not c.ok]
    if critical_failed:
        console.print("[red]✗ Critical check failed -- see above.[/red]")
        return 1

    missing_optional = [c for c in checks if not c.ok and not c.critical]
    if missing_optional:
        console.print(
            f"[green]✓ No critical issues.[/green] {len(missing_optional)} optional tool(s) marked "
            "'--' only affect that specific language or check -- install as needed."
        )
    else:
        console.print("[green]✓ Everything checked is present.[/green]")
    return 0
