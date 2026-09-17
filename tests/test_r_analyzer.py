"""Tests for the R analyzer.

The contract covers marker-gated detection, entry-point discovery,
clean handling of missing external tools, project detection integration,
and registry integration.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from _helpers import write
from sarand.analyzers.r_analyzer import RAnalyzer
from sarand.analyzers.registry import discover_analyzers, matching_analyzers
from sarand.discovery.project_detector import detect_project


def test_r_analyzer_matches_on_description() -> None:
    analyzer = RAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False

        write(root / "DESCRIPTION", "Package: foo\nVersion: 0.1.0\n")

        assert analyzer.matches(root) is True


def test_r_analyzer_does_not_match_unrelated_project() -> None:
    analyzer = RAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "main.py", "print('hi')\n")

        assert analyzer.matches(root) is False


def test_r_analyzer_entry_points() -> None:
    analyzer = RAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "DESCRIPTION", "Package: foo\n")
        write(root / "R" / "main.R", "main <- function() {}\n")
        write(root / "app.R", "shinyApp()\n")

        found = analyzer.entry_points(root)

        assert found == ["R/main.R", "app.R"]


def test_r_analyzer_run_tests_is_none_without_testthat_dir() -> None:
    analyzer = RAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "DESCRIPTION", "Package: foo\n")

        result = asyncio.run(analyzer.run_tests(root))

        assert result is None


def test_r_analyzer_run_tests_skips_cleanly_without_rscript() -> None:
    analyzer = RAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "DESCRIPTION", "Package: foo\n")
        write(root / "tests" / "testthat" / "test-foo.R", "test_that('x', {})\n")

        result = asyncio.run(analyzer.run_tests(root))

        assert result is not None
        assert result.kind == "testthat"

        if result.skipped:
            assert "not found" in result.skip_reason.lower()


def test_r_analyzer_run_quality_reports_kind() -> None:
    analyzer = RAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "DESCRIPTION", "Package: foo\n")

        results = asyncio.run(analyzer.run_quality(root))

        assert len(results) == 1
        assert results[0].kind == "lintr"

        if results[0].skipped:
            assert "not found" in results[0].skip_reason.lower()


def test_r_analyzer_run_security_is_empty() -> None:
    analyzer = RAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "DESCRIPTION", "Package: foo\n")

        results = asyncio.run(analyzer.run_security(root))

        assert results == []


def test_r_analyzer_in_discover_and_matching() -> None:
    pool = discover_analyzers()
    names = {analyzer.name for analyzer in pool}

    assert "R" in names

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "DESCRIPTION", "Package: foo\n")

        active = matching_analyzers(root, pool)

        assert any(analyzer.name == "R" for analyzer in active)


def test_r_analyzer_does_not_match_empty_tree() -> None:
    analyzer = RAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False


def test_r_project_detection_uses_description_marker() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "DESCRIPTION", "Package: foo\n")

        detection = detect_project(root)

        assert detection.primary_language == "R"
        assert detection.project_type == "package"
