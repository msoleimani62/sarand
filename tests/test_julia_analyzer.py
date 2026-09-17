"""Tests for the Julia analyzer.

The contract covers marker-gated detection, entry-point discovery,
clean handling of missing external tools, project detection integration,
and registry integration.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from _helpers import write
from sarand.analyzers.julia_analyzer import JuliaAnalyzer
from sarand.analyzers.registry import discover_analyzers, matching_analyzers
from sarand.discovery.project_detector import detect_project


def test_julia_analyzer_matches_on_project_toml() -> None:
    analyzer = JuliaAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False

        write(root / "Project.toml", 'name = "Foo"\n')

        assert analyzer.matches(root) is True


def test_julia_analyzer_does_not_match_unrelated_project() -> None:
    analyzer = JuliaAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "main.py", "print('hi')\n")

        assert analyzer.matches(root) is False


def test_julia_analyzer_entry_points() -> None:
    analyzer = JuliaAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "Project.toml", 'name = "Foo"\n')
        write(root / "src" / "main.jl", "println(1)\n")

        found = analyzer.entry_points(root)

        assert found == ["src/main.jl"]


def test_julia_analyzer_run_tests_skips_cleanly_without_julia() -> None:
    analyzer = JuliaAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "Project.toml", 'name = "Foo"\n')

        result = asyncio.run(analyzer.run_tests(root))

        assert result is not None
        assert result.kind == "julia Pkg.test()"

        if result.skipped:
            assert "not found" in result.skip_reason.lower()


def test_julia_analyzer_run_quality_is_always_empty() -> None:
    analyzer = JuliaAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "Project.toml", 'name = "Foo"\n')

        results = asyncio.run(analyzer.run_quality(root))

        assert results == []


def test_julia_analyzer_run_security_is_always_empty() -> None:
    analyzer = JuliaAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "Project.toml", 'name = "Foo"\n')

        results = asyncio.run(analyzer.run_security(root))

        assert results == []


def test_julia_analyzer_in_discover_and_matching() -> None:
    pool = discover_analyzers()
    names = {analyzer.name for analyzer in pool}

    assert "Julia" in names

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "Project.toml", 'name = "Foo"\n')

        active = matching_analyzers(root, pool)

        assert any(analyzer.name == "Julia" for analyzer in active)


def test_julia_analyzer_does_not_match_empty_tree() -> None:
    analyzer = JuliaAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False


def test_julia_project_detection_uses_project_toml_marker() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "Project.toml", 'name = "Foo"\n')

        detection = detect_project(root)

        assert detection.primary_language == "Julia"
        assert detection.project_type == "package"
