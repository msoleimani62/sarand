"""Tests for the XML analyzer."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from _helpers import write
from sarand.analyzers.registry import discover_analyzers, matching_analyzers
from sarand.analyzers.xml_analyzer import XmlAnalyzer


def test_xml_analyzer_matches_on_top_level_xml_file() -> None:
    analyzer = XmlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False

        write(root / "pom.xml", "<project></project>\n")

        assert analyzer.matches(root) is True


def test_xml_analyzer_does_not_match_nested_xml_without_root_signal() -> None:
    analyzer = XmlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "vendor" / "lib" / "config.xml", "<a/>\n")

        assert analyzer.matches(root) is False


def test_xml_analyzer_matches_alongside_other_language_markers() -> None:
    """pom.xml (Java's Maven marker) is still a top-level XML file --
    XmlAnalyzer complements JavaAnalyzer rather than deferring to it."""

    analyzer = XmlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pom.xml", "<project></project>\n")

        assert analyzer.matches(root) is True


def test_xml_analyzer_entry_points() -> None:
    analyzer = XmlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pom.xml", "<project></project>\n")

        assert analyzer.entry_points(root) == ["pom.xml"]


def test_xml_analyzer_run_tests_is_always_none() -> None:
    analyzer = XmlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pom.xml", "<project></project>\n")

        result = asyncio.run(analyzer.run_tests(root))

    assert result is None


def test_xml_analyzer_run_quality_skips_cleanly_without_xmllint() -> None:
    analyzer = XmlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pom.xml", "<project></project>\n")

        results = asyncio.run(analyzer.run_quality(root))

    assert len(results) == 1
    assert results[0].kind == "xmllint --noout"
    if results[0].skipped:
        assert "not found" in results[0].skip_reason.lower()


def test_xml_analyzer_run_security_is_always_empty() -> None:
    analyzer = XmlAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pom.xml", "<project></project>\n")

        results = asyncio.run(analyzer.run_security(root))

    assert results == []


def test_xml_analyzer_in_discover_and_matching() -> None:
    analyzers = discover_analyzers()
    assert any(a.name == "XML" for a in analyzers)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pom.xml", "<project></project>\n")

        matched = matching_analyzers(root, analyzers)

    assert any(a.name == "XML" for a in matched)
