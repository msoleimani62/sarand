"""Tests for the SQL analyzer.

Covers marker-gated detection (config file, top-level *.sql, or a
migrations/ dir with *.sql inside), the nested-without-root-signal
guard, entry-point discovery, the intentional run_tests no-op, clean
handling of a missing sqlfluff, always-empty run_security, project
detection integration, and registry integration.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from _helpers import write
from sarand.analyzers.registry import discover_analyzers, matching_analyzers
from sarand.analyzers.sql_analyzer import SqlAnalyzer
from sarand.discovery.project_detector import detect_project


def test_sql_analyzer_matches_on_sqlfluff_config() -> None:
    analyzer = SqlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False

        write(root / ".sqlfluff", "[sqlfluff]\ndialect = postgres\n")

        assert analyzer.matches(root) is True


def test_sql_analyzer_matches_on_top_level_sql_file() -> None:
    analyzer = SqlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "schema.sql", "CREATE TABLE t (id INT);\n")

        assert analyzer.matches(root) is True


def test_sql_analyzer_matches_on_migrations_dir_with_sql() -> None:
    analyzer = SqlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "migrations" / "0001_init.sql", "CREATE TABLE t (id INT);\n")

        assert analyzer.matches(root) is True


def test_sql_analyzer_does_not_match_nested_sql_without_root_signal() -> None:
    """A nested stylesheet-like SQL file (not top-level, not in
    migrations/) must not force a project-level match."""

    analyzer = SqlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "vendor" / "lib" / "seed.sql", "INSERT INTO t VALUES (1);\n")

        assert analyzer.matches(root) is False


def test_sql_analyzer_does_not_match_unrelated_project() -> None:
    analyzer = SqlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", "{}")

        assert analyzer.matches(root) is False


def test_sql_analyzer_entry_points() -> None:
    analyzer = SqlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "schema.sql", "CREATE TABLE t (id INT);\n")
        write(root / "unrelated.sql", "SELECT 1;\n")

        assert analyzer.entry_points(root) == ["schema.sql"]


def test_sql_analyzer_run_tests_is_always_none() -> None:
    analyzer = SqlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "schema.sql", "CREATE TABLE t (id INT);\n")

        result = asyncio.run(analyzer.run_tests(root))

    assert result is None


def test_sql_analyzer_run_quality_skips_cleanly_without_sqlfluff() -> None:
    analyzer = SqlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "schema.sql", "CREATE TABLE t (id INT);\n")

        results = asyncio.run(analyzer.run_quality(root))

        assert len(results) == 1
        assert results[0].kind == "sqlfluff lint"

        if results[0].skipped:
            assert "not found" in results[0].skip_reason.lower()


def test_sql_analyzer_run_security_is_always_empty() -> None:
    analyzer = SqlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "schema.sql", "CREATE TABLE t (id INT);\n")

        results = asyncio.run(analyzer.run_security(root))

        assert results == []


def test_sql_analyzer_in_discover_and_matching() -> None:
    analyzers = discover_analyzers()
    assert any(a.name == "SQL" for a in analyzers)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "schema.sql", "CREATE TABLE t (id INT);\n")

        matched = matching_analyzers(root, analyzers)

    assert any(a.name == "SQL" for a in matched)


def test_sql_analyzer_does_not_match_empty_tree() -> None:
    analyzer = SqlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False


def test_sql_project_detection_uses_extension_fallback() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "schema.sql", "CREATE TABLE t (id INT);\n")

        detection = detect_project(root)

    assert detection.primary_language == "SQL"
    assert "SQL" in detection.languages
