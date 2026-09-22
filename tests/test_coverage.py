"""The coverage matrix is derived from the code and must stay in sync."""

from __future__ import annotations

import tempfile
from pathlib import Path

from _helpers import write
from sarand.analyzers.registry import builtin_analyzers
from sarand.core.coverage import (
    DOCTOR_CATEGORIES,
    NON_ECOSYSTEM_CATEGORIES,
    _ci_installs_tool,
    _classify_depth,
    _has_fixture_coverage,
    build_coverage,
    render_markdown,
)
from sarand.core.doctor import collect_checks, tool_catalog

_ROOT = Path(__file__).resolve().parent.parent


def test_every_builtin_analyzer_is_classified_for_the_matrix() -> None:
    names = {analyzer.name for analyzer in builtin_analyzers()}

    assert names == set(DOCTOR_CATEGORIES)


def test_every_analyzer_is_visible_in_doctor() -> None:
    """An ecosystem missing from `--doctor` looks unsupported to the user
    (Assembly once was). Every analyzer must be shown there, either through
    the tools it drives or through a built-in, detection-only row."""
    shown = {check.category for check in collect_checks() if check.category != "Core"}
    hidden = sorted(
        name
        for name, categories in DOCTOR_CATEGORIES.items()
        if not any(category in shown for category in categories)
    )

    assert hidden == []


def test_every_doctor_category_belongs_to_some_analyzer() -> None:
    mapped = {category for cats in DOCTOR_CATEGORIES.values() for category in cats}
    listed = {category for category, _bin, _hint, _used in tool_catalog()}

    assert listed - NON_ECOSYSTEM_CATEGORIES <= mapped


def test_capabilities_are_read_from_the_analyzer_code() -> None:
    rows = {row.ecosystem: row for row in build_coverage()}

    assert (rows["Python"].tests, rows["Python"].quality, rows["Python"].security) == (
        True,
        True,
        True,
    )
    assert (rows["CSS"].tests, rows["CSS"].quality, rows["CSS"].security) == (
        False,
        True,
        False,
    )
    # Assembly needs no external tool and runs nothing: detection only.
    assembly = rows["Assembly"]
    assert (assembly.tests, assembly.quality, assembly.security) == (
        False,
        False,
        False,
    )
    assert assembly.tools == ()


def test_fixture_coverage_finds_a_real_class_reference() -> None:
    """Every current built-in analyzer's class name is referenced by a
    real test somewhere under tests/ (several share one test module
    instead of a dedicated `test_<name>_analyzer.py`, which is exactly
    why this checks test *content*, not a filename convention)."""
    rows = {row.ecosystem: row for row in build_coverage()}
    assert rows["Python"].fixture_coverage is True
    assert rows["Haskell"].fixture_coverage is True  # shares test_new_ecosystems.py


def test_fixture_coverage_is_false_for_an_unreferenced_class_name() -> None:
    """A class name nothing under tests/ mentions must not be reported
    as covered -- the negative case for the check above."""

    # Deliberately made-up class name -- nothing under tests/ mentions it.
    # نام کلاسِ عمداً ساختگی -- هیچ‌چیز زیر tests/ به آن اشاره نمی‌کند.
    class _NotActuallyTestedAnalyzer:
        pass

    with tempfile.TemporaryDirectory() as tmp:
        tests_dir = Path(tmp)
        write(tests_dir / "test_something_else.py", "def test_x():\n    pass\n")
        assert _has_fixture_coverage(_NotActuallyTestedAnalyzer(), tests_dir) is False


def test_ci_installed_matches_the_real_workflow_file() -> None:
    """sarand's own CI (.github/workflows/ci.yml) installs Python
    tooling via `pip install -e ".[dev]"` and then genuinely invokes
    `ruff`/`mypy`/`pytest` as commands, and sets up the Rust toolchain
    then genuinely invokes `cargo`/`rustfmt`/`clippy` -- so those two
    ecosystems (and only those two, among everything sarand analyzes)
    should show ci_installed=True. Everything else sarand supports
    (Go, Node, Ruby, ...) is never installed in CI at all."""
    rows = {row.ecosystem: row for row in build_coverage()}
    assert rows["Python"].ci_installed is True
    assert rows["Rust"].ci_installed is True
    assert rows["Go"].ci_installed is False


def test_ci_installed_does_not_false_positive_on_a_prose_comment() -> None:
    """Regression test for a real bug caught before this shipped:
    Haskell's `stack` binary matched CI's own comment "...prints every
    thread's *stack*..." under a naive whole-file word-boundary search.
    `_ci_installs_tool` must ignore `#`-comment lines."""
    with tempfile.TemporaryDirectory() as tmp:
        workflow = write(
            Path(tmp) / "ci.yml",
            "steps:\n"
            "  - name: explain a timeout\n"
            "    run: |\n"
            "      # prints every thread's stack if a test hangs\n"
            "      echo done\n",
        )
        assert _ci_installs_tool(("stack",), workflow) is False


def test_depth_classification_is_a_fixed_rule() -> None:
    """Deep/Partial/Shallow must come from the (tests, quality, security,
    fixture_coverage) tuple alone, per the rule documented in
    coverage.py -- never a per-analyzer judgment call."""
    assert _classify_depth(True, True, True, True) == "Deep"
    # All three checks present but no fixture coverage -- still not Deep,
    # since an unverified analyzer must never be labeled fully mature.
    assert _classify_depth(True, True, True, False) == "Partial"
    assert _classify_depth(True, False, False, True) == "Partial"
    assert _classify_depth(False, False, False, True) == "Shallow"


def test_docs_coverage_md_is_up_to_date() -> None:
    path = _ROOT / "docs" / "COVERAGE.md"
    if not path.is_file():
        return  # e.g. tests run from an sdist that does not ship docs/

    assert path.read_text(encoding="utf-8") == render_markdown(), (
        "docs/COVERAGE.md is stale; regenerate it with "
        "`python -m sarand.core.coverage > docs/COVERAGE.md`"
    )
