"""Tests for the CSS analyzer.

The contract covers marker-gated detection (config file or top-level
stylesheet), entry-point discovery, the intentional run_tests no-op,
clean handling of a missing stylelint, always-empty run_security,
project detection integration, and registry integration.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from _helpers import write
from sarand.analyzers.css_analyzer import CssAnalyzer
from sarand.analyzers.registry import discover_analyzers, matching_analyzers
from sarand.discovery.project_detector import detect_project


def test_css_analyzer_matches_on_stylelint_config() -> None:
    analyzer = CssAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False

        write(root / ".stylelintrc.json", "{}\n")

        assert analyzer.matches(root) is True


def test_css_analyzer_matches_on_top_level_css_file() -> None:
    analyzer = CssAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "style.css", "body { margin: 0; }\n")

        assert analyzer.matches(root) is True


def test_css_analyzer_matches_on_top_level_scss_file() -> None:
    analyzer = CssAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "main.scss", "$color: red;\n")

        assert analyzer.matches(root) is True


def test_css_analyzer_does_not_match_nested_css_without_root_signal() -> None:
    """A nested stylesheet alone must not force a project-level match."""

    analyzer = CssAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "vendor" / "lib" / "reset.css", "* { margin: 0; }\n")

        assert analyzer.matches(root) is False


def test_css_analyzer_does_not_match_unrelated_project() -> None:
    analyzer = CssAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", "{}")

        assert analyzer.matches(root) is False


def test_css_analyzer_is_independent_of_package_json() -> None:
    """A plain static-site CSS project with no package.json at all
    must still be picked up (per the module docstring)."""

    analyzer = CssAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "index.css", "body { margin: 0; }\n")

        assert analyzer.matches(root) is True


def test_css_analyzer_entry_points() -> None:
    analyzer = CssAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "index.css", "body { margin: 0; }\n")
        write(root / "unrelated.css", "* { padding: 0; }\n")

        assert analyzer.entry_points(root) == ["index.css"]


def test_css_analyzer_run_tests_is_always_none() -> None:
    analyzer = CssAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "index.css", "body { margin: 0; }\n")

        result = asyncio.run(analyzer.run_tests(root))

    assert result is None


def test_css_analyzer_run_quality_skips_cleanly_without_stylelint() -> None:
    analyzer = CssAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "index.css", "body { margin: 0; }\n")

        results = asyncio.run(analyzer.run_quality(root))

        assert len(results) == 1
        assert results[0].kind == "stylelint"

        if results[0].skipped:
            assert "not found" in results[0].skip_reason.lower()


def test_css_analyzer_run_security_is_always_empty() -> None:
    analyzer = CssAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "index.css", "body { margin: 0; }\n")

        results = asyncio.run(analyzer.run_security(root))

        assert results == []


def test_css_analyzer_in_discover_and_matching() -> None:
    analyzers = discover_analyzers()
    assert any(a.name == "CSS" for a in analyzers)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "index.css", "body { margin: 0; }\n")

        matched = matching_analyzers(root, analyzers)

    assert any(a.name == "CSS" for a in matched)


def test_css_analyzer_does_not_match_empty_tree() -> None:
    analyzer = CssAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False


def test_css_project_detection_uses_extension_fallback() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "style.css", "body { margin: 0; }\n")

        detection = detect_project(root)

    assert detection.primary_language == "CSS"
    assert "CSS" in detection.languages
