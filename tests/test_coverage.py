"""The coverage matrix is derived from the code and must stay in sync."""

from __future__ import annotations

from pathlib import Path

from sarand.analyzers.registry import builtin_analyzers
from sarand.core.coverage import (
    DOCTOR_CATEGORIES,
    NON_ECOSYSTEM_CATEGORIES,
    build_coverage,
    render_markdown,
)
from sarand.core.doctor import tool_catalog

_ROOT = Path(__file__).resolve().parent.parent


def test_every_builtin_analyzer_is_classified_for_the_matrix() -> None:
    names = {analyzer.name for analyzer in builtin_analyzers()}

    assert names == set(DOCTOR_CATEGORIES)


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


def test_docs_coverage_md_is_up_to_date() -> None:
    path = _ROOT / "docs" / "COVERAGE.md"
    if not path.is_file():
        return  # e.g. tests run from an sdist that does not ship docs/

    assert path.read_text(encoding="utf-8") == render_markdown(), (
        "docs/COVERAGE.md is stale; regenerate it with "
        "`python -m sarand.core.coverage > docs/COVERAGE.md`"
    )
