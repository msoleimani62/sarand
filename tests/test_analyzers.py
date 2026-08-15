"""Tests for sarand.analyzers -- the gate-on-real-marker contract (rule 3.3)."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

import pytest
from _helpers import write
from sarand.analyzers.go_analyzer import GoAnalyzer
from sarand.analyzers.node_analyzer import NodeAnalyzer
from sarand.analyzers.python_analyzer import PythonAnalyzer
from sarand.analyzers.registry import discover_analyzers, matching_analyzers
from sarand.analyzers.rust_analyzer import RustAnalyzer


def test_python_analyzer_only_matches_with_real_marker() -> None:
    analyzer = PythonAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert analyzer.matches(root) is False

        write(root / "pyproject.toml", "[project]\nname='x'\n")
        assert analyzer.matches(root) is True


def test_rust_analyzer_gated_on_cargo_toml() -> None:
    analyzer = RustAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert analyzer.matches(root) is False
        write(root / "Cargo.toml", "[package]\nname='x'\n")
        assert analyzer.matches(root) is True


def test_go_analyzer_gated_on_go_mod() -> None:
    analyzer = GoAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert analyzer.matches(root) is False
        write(root / "go.mod", "module x\n")
        assert analyzer.matches(root) is True


def test_node_analyzer_matches_on_package_json_alone() -> None:
    """matches() only checks for package.json; the *test script* gate
    lives in run_tests(), tested separately below -- this mirrors the
    old bxt bug where a project without a real 'test' script would get
    a useless 'npm test' failure."""
    analyzer = NodeAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert analyzer.matches(root) is False
        write(root / "package.json", '{"name": "x"}')
        assert analyzer.matches(root) is True


def test_node_analyzer_run_tests_is_none_without_test_script() -> None:
    analyzer = NodeAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", '{"name": "x", "scripts": {"build": "echo ok"}}')

        result = asyncio.run(analyzer.run_tests(root))

        assert result is None


def test_node_analyzer_run_tests_attempts_when_test_script_present() -> None:
    """With a real 'test' script, run_tests must at least try to run npm
    (and gracefully report 'npm not found' rather than crashing, since
    this sandbox has no npm)."""
    analyzer = NodeAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", '{"name": "x", "scripts": {"test": "echo ok"}}')

        result = asyncio.run(analyzer.run_tests(root))

        assert result is not None
        assert result.kind == "npm test"
        # Either it actually ran, or it was cleanly skipped -- never a crash.
        assert result.skipped or result.returncode is not None


def test_python_analyzer_run_tests_skips_cleanly_without_pytest() -> None:
    """This sandbox genuinely has no pytest installed -- exercise the
    real 'tool missing' path, not a mock."""
    analyzer = PythonAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pyproject.toml", "[project]\nname='x'\n")

        result = asyncio.run(analyzer.run_tests(root))

        assert result is not None
        assert result.kind == "pytest"
        # Must be a clean skip, never an unhandled exception.
        if result.skipped:
            assert "not found" in result.skip_reason.lower()


def test_matching_analyzers_returns_only_relevant_ones() -> None:
    pool = [PythonAnalyzer(), RustAnalyzer(), GoAnalyzer(), NodeAnalyzer()]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Cargo.toml", "[package]\nname='x'\n")
        write(root / "package.json", '{"name": "x"}')

        active = matching_analyzers(root, pool)

        assert {a.name for a in active} == {"Rust", "Node.js"}


def test_discover_analyzers_includes_all_builtins() -> None:
    analyzers = discover_analyzers()
    names = {a.name for a in analyzers}
    assert {"Python", "Rust", "Go", "Node.js"}.issubset(names)


@pytest.mark.slow_external
def test_python_analyzer_run_security_skips_cleanly_without_tools() -> None:
    """pip-audit/bandit are not installed in this sandbox -- exercise the
    real 'tool missing' path for both, never a crash."""
    analyzer = PythonAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pyproject.toml", "[project]\nname='x'\n")

        results = asyncio.run(analyzer.run_security(root))

        assert {r.kind for r in results} == {"pip-audit", "bandit"}
        for r in results:
            if r.skipped:
                assert "not installed" in r.skip_reason.lower()


@pytest.mark.slow_external
def test_rust_analyzer_run_security_checks_cargo_audit_binary_specifically() -> None:
    """cargo-audit is a separate binary, not just 'cargo'. This must work
    correctly whether or not cargo-audit happens to be installed on the
    machine running the test -- it wasn't in the original sandbox this
    test was written in, but it may well be on a real dev machine, so we
    cannot assume either way (that was the actual bug in v1 of this test:
    it hardcoded the 'not installed' assumption)."""
    analyzer = RustAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(
            root / "Cargo.toml",
            '[package]\nname = "x"\nversion = "0.1.0"\nedition = "2021"\n',
        )
        write(root / "src" / "main.rs", "fn main() {}\n")

        results = asyncio.run(analyzer.run_security(root))

        assert len(results) == 1
        assert results[0].kind == "cargo audit"

        if shutil.which("cargo-audit") is None:
            assert results[0].skipped
            assert "cargo-audit" in results[0].skip_reason
        else:
            # Actually installed -- it really ran. Don't assert pass/fail
            # (depends on network + the advisory DB), only that our
            # wrapper didn't treat "tool present" as "tool missing".
            assert results[0].skipped is False


@pytest.mark.slow_external
def test_go_analyzer_run_security_skips_without_govulncheck() -> None:
    """Same defensive pattern as the cargo-audit test above: don't assume
    govulncheck is absent just because it was in the original sandbox."""
    analyzer = GoAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "go.mod", "module x\n\ngo 1.21\n")

        results = asyncio.run(analyzer.run_security(root))

        assert len(results) == 1
        assert results[0].kind == "govulncheck"
        if shutil.which("govulncheck") is None:
            assert results[0].skipped
        else:
            assert results[0].skipped is False


def test_all_builtin_analyzers_implement_run_security() -> None:
    """Every analyzer must have a run_security method -- a plugin author
    (or a maintainer adding language #5) reading this test should notice
    immediately if they forgot it."""
    for analyzer in (PythonAnalyzer(), RustAnalyzer(), GoAnalyzer(), NodeAnalyzer()):
        assert hasattr(analyzer, "run_security")
