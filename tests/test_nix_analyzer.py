"""Tests for the Nix analyzer.

The contract covers shallow marker-gated detection, entry-point
discovery, clean handling of missing external tools, extension-fallback
project detection, and registry integration.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from _helpers import write
from sarand.analyzers.nix_analyzer import NixAnalyzer
from sarand.analyzers.registry import discover_analyzers, matching_analyzers
from sarand.discovery.project_detector import detect_project


def test_nix_analyzer_matches_on_top_level_nix_file() -> None:
    analyzer = NixAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False

        write(root / "default.nix", "{ pkgs ? import <nixpkgs> {} }: {}\n")

        assert analyzer.matches(root) is True


def test_nix_analyzer_matches_on_flake_nix() -> None:
    analyzer = NixAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "flake.nix", "{ outputs = { self }: {}; }\n")

        assert analyzer.matches(root) is True


def test_nix_analyzer_does_not_match_nested_nix_without_root_signal() -> None:
    analyzer = NixAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "pkgs" / "foo" / "default.nix", "{}\n")

        assert analyzer.matches(root) is False


def test_nix_analyzer_does_not_match_unrelated_project() -> None:
    analyzer = NixAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "main.py", "print('hi')\n")

        assert analyzer.matches(root) is False


def test_nix_analyzer_entry_points() -> None:
    analyzer = NixAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "flake.nix", "{ outputs = { self }: {}; }\n")

        found = analyzer.entry_points(root)

        assert found == ["flake.nix"]


def test_nix_analyzer_run_tests_is_none_without_flake() -> None:
    analyzer = NixAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "default.nix", "{}\n")

        result = asyncio.run(analyzer.run_tests(root))

        assert result is None


def test_nix_analyzer_run_tests_skips_cleanly_without_nix_binary() -> None:
    analyzer = NixAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "flake.nix", "{ outputs = { self }: {}; }\n")

        result = asyncio.run(analyzer.run_tests(root))

        assert result is not None
        assert result.kind == "nix flake check"

        if result.skipped:
            assert "not found" in result.skip_reason.lower()


def test_nix_analyzer_run_quality_skips_cleanly_without_nixpkgs_fmt() -> None:
    analyzer = NixAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "default.nix", "{}\n")

        results = asyncio.run(analyzer.run_quality(root))

        assert len(results) == 1
        assert results[0].kind == "nixpkgs-fmt --check"

        if results[0].skipped:
            assert "not found" in results[0].skip_reason.lower()


def test_nix_analyzer_run_security_is_always_empty() -> None:
    analyzer = NixAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "default.nix", "{}\n")

        results = asyncio.run(analyzer.run_security(root))

        assert results == []


def test_nix_analyzer_in_discover_and_matching() -> None:
    pool = discover_analyzers()
    names = {analyzer.name for analyzer in pool}

    assert "Nix" in names

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "default.nix", "{}\n")

        active = matching_analyzers(root, pool)

        assert any(analyzer.name == "Nix" for analyzer in active)


def test_nix_analyzer_does_not_match_empty_tree() -> None:
    analyzer = NixAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False


def test_nix_project_detection_uses_extension_fallback() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "default.nix", "{}\n")

        detection = detect_project(root)

        assert detection.primary_language == "Nix"
