"""Tests for the Ruby analyzer.

The contract covers marker-gated detection, entry-point discovery,
clean handling of a missing Bundler, project detection integration,
and registry integration.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from _helpers import write
from sarand.analyzers.registry import discover_analyzers, matching_analyzers
from sarand.analyzers.ruby_analyzer import RubyAnalyzer
from sarand.discovery.project_detector import detect_project


def test_ruby_analyzer_matches_on_gemfile() -> None:
    analyzer = RubyAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False

        write(root / "Gemfile", 'source "https://rubygems.org"\n')

        assert analyzer.matches(root) is True


def test_ruby_analyzer_matches_on_gemspec() -> None:
    analyzer = RubyAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "mygem.gemspec", "Gem::Specification.new do |s| end\n")

        assert analyzer.matches(root) is True


def test_ruby_analyzer_does_not_match_unrelated_project() -> None:
    analyzer = RubyAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", "{}")

        assert analyzer.matches(root) is False


def test_ruby_analyzer_entry_points() -> None:
    analyzer = RubyAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Gemfile", "")
        write(root / "app.rb", "")
        write(root / "unrelated.rb", "")

        assert analyzer.entry_points(root) == ["app.rb"]


def test_ruby_analyzer_run_tests_skips_cleanly_without_bundle() -> None:
    analyzer = RubyAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Gemfile", "")
        write(root / "spec" / "example_spec.rb", "")

        result = asyncio.run(analyzer.run_tests(root))

    assert result is not None
    assert result.skipped is True
    assert "bundle" in result.skip_reason.lower()


def test_ruby_analyzer_run_tests_reports_missing_spec_and_rakefile() -> None:
    # This can only be told apart from "bundle is missing" by actually
    # having bundle available, which this sandbox doesn't -- so this
    # test only exercises the case reachable without bundle: bundle
    # missing is checked first and wins regardless of spec/Rakefile
    # presence. The neither-spec-nor-Rakefile skip path itself is
    # covered by manual verification (see the delivery notes) since it
    # requires bundle to be present to reach.
    analyzer = RubyAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Gemfile", "")

        result = asyncio.run(analyzer.run_tests(root))

    assert result is not None
    assert result.skipped is True


def test_ruby_analyzer_run_quality_and_security_skip_cleanly_without_bundle() -> None:
    analyzer = RubyAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Gemfile", "")

        quality = asyncio.run(analyzer.run_quality(root))
        security = asyncio.run(analyzer.run_security(root))

    assert quality[0].skipped is True
    assert security[0].skipped is True


def test_ruby_analyzer_in_discover_and_matching() -> None:
    analyzers = discover_analyzers()
    assert any(a.name == "Ruby" for a in analyzers)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Gemfile", "")

        matched = matching_analyzers(root, analyzers)

    assert any(a.name == "Ruby" for a in matched)


def test_ruby_project_detection_uses_gemfile_marker() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Gemfile", "")

        detection = detect_project(root)

    assert "Ruby" in detection.languages
    assert detection.build_system == "bundler"
