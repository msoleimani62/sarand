"""Tests for sarand.core.doctor (§4.11)."""

from __future__ import annotations

from sarand.core.doctor import collect_checks


def test_collect_checks_includes_python_version_as_critical() -> None:
    checks = collect_checks()
    py_check = next(c for c in checks if c.name == "Python version")
    assert py_check.critical is True
    # This sandbox runs a modern Python -- the check itself must pass.
    assert py_check.ok is True


def test_collect_checks_includes_rust_core_status_non_critical() -> None:
    checks = collect_checks()
    rust_check = next(c for c in checks if c.name.startswith("Rust core"))
    assert rust_check.critical is False
    # Whichever way it goes, there must always be a usable next step.
    if not rust_check.ok:
        assert "maturin develop" in rust_check.fix


def test_collect_checks_never_marks_missing_language_tools_critical() -> None:
    """No single machine has every language's toolchain -- a missing
    Go/Java/C++ tool must never be treated as a critical failure."""
    checks = collect_checks()
    for check in checks:
        if check.name == "Python version" or check.name.startswith("Rust core"):
            continue
        assert check.critical is False


def test_collect_checks_provides_a_fix_for_every_failing_check() -> None:
    checks = collect_checks()
    for check in checks:
        if not check.ok:
            assert check.fix, f"{check.name} failed with no fix-it hint"


def test_persisted_config_check_is_always_ok() -> None:
    """Reporting *where* the config file is/would be is always
    informational, never a failure -- a missing config.json is normal
    on first run."""
    checks = collect_checks()
    config_check = next(c for c in checks if c.name == "Persisted config")
    assert config_check.ok is True
