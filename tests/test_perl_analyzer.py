"""Tests for the Perl analyzer.

The contract covers marker-gated detection, entry-point discovery,
clean handling of missing external tools, project detection integration,
and registry integration.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from _helpers import write
from sarand.analyzers.perl_analyzer import PerlAnalyzer
from sarand.analyzers.registry import discover_analyzers, matching_analyzers
from sarand.discovery.project_detector import detect_project


def test_perl_analyzer_matches_on_cpanfile() -> None:
    analyzer = PerlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False

        write(root / "cpanfile", "requires 'Moose';\n")

        assert analyzer.matches(root) is True


def test_perl_analyzer_does_not_match_unrelated_project() -> None:
    analyzer = PerlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "main.py", "print('hi')\n")

        assert analyzer.matches(root) is False


def test_perl_analyzer_entry_points() -> None:
    analyzer = PerlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "cpanfile", "requires 'Moose';\n")
        write(root / "bin" / "app.pl", "#!/usr/bin/env perl\n")

        found = analyzer.entry_points(root)

        assert found == ["bin/app.pl"]


def test_perl_analyzer_run_tests_is_none_without_t_dir() -> None:
    analyzer = PerlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "cpanfile", "requires 'Moose';\n")

        result = asyncio.run(analyzer.run_tests(root))

        assert result is None


def test_perl_analyzer_run_tests_skips_cleanly_without_prove() -> None:
    analyzer = PerlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "cpanfile", "requires 'Moose';\n")
        write(root / "t" / "basic.t", "ok(1);\n")

        result = asyncio.run(analyzer.run_tests(root))

        assert result is not None
        assert result.kind == "prove"

        if result.skipped:
            assert "not found" in result.skip_reason.lower()


def test_perl_analyzer_run_quality_reports_kind() -> None:
    analyzer = PerlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "cpanfile", "requires 'Moose';\n")

        results = asyncio.run(analyzer.run_quality(root))

        assert len(results) == 1
        assert results[0].kind == "perlcritic"

        if results[0].skipped:
            assert "not found" in results[0].skip_reason.lower()


def test_perl_analyzer_run_security_is_empty() -> None:
    analyzer = PerlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "cpanfile", "requires 'Moose';\n")

        results = asyncio.run(analyzer.run_security(root))

        assert results == []


def test_perl_analyzer_in_discover_and_matching() -> None:
    pool = discover_analyzers()
    names = {analyzer.name for analyzer in pool}

    assert "Perl" in names

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "cpanfile", "requires 'Moose';\n")

        active = matching_analyzers(root, pool)

        assert any(analyzer.name == "Perl" for analyzer in active)


def test_perl_analyzer_does_not_match_empty_tree() -> None:
    analyzer = PerlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False


def test_perl_project_detection_uses_cpanfile_marker() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "cpanfile", "requires 'Moose';\n")

        detection = detect_project(root)

        assert detection.primary_language == "Perl"
        assert detection.project_type == "application/module"
