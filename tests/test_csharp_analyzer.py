"""Tests for the C# analyzer."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from _helpers import write
from sarand.analyzers.csharp_analyzer import CSharpAnalyzer
from sarand.analyzers.registry import discover_analyzers, matching_analyzers
from sarand.discovery.project_detector import detect_project


def test_csharp_analyzer_matches_on_csproj() -> None:
    analyzer = CSharpAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False

        write(root / "App.csproj", "")

        assert analyzer.matches(root) is True


def test_csharp_analyzer_matches_on_sln() -> None:
    analyzer = CSharpAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "App.sln", "")

        assert analyzer.matches(root) is True


def test_csharp_analyzer_does_not_match_unrelated_project() -> None:
    analyzer = CSharpAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", "{}")

        assert analyzer.matches(root) is False


def test_csharp_analyzer_entry_points() -> None:
    analyzer = CSharpAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "App.csproj", "")
        write(root / "Program.cs", "")

        assert analyzer.entry_points(root) == ["Program.cs"]


def test_csharp_analyzer_run_tests_skips_cleanly_without_dotnet() -> None:
    analyzer = CSharpAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "App.csproj", "")

        result = asyncio.run(analyzer.run_tests(root))

    assert result is not None
    assert result.skipped is True
    assert "dotnet" in result.skip_reason.lower()


def test_csharp_analyzer_run_quality_skips_cleanly_without_dotnet() -> None:
    analyzer = CSharpAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "App.csproj", "")

        results = asyncio.run(analyzer.run_quality(root))

    assert len(results) == 1
    assert results[0].skipped is True


def test_csharp_analyzer_run_security_skips_cleanly_without_dotnet() -> None:
    analyzer = CSharpAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "App.csproj", "")

        results = asyncio.run(analyzer.run_security(root))

    assert len(results) == 1
    assert results[0].skipped is True


def test_csharp_analyzer_in_discover_and_matching() -> None:
    analyzers = discover_analyzers()
    assert any(a.name == "C#" for a in analyzers)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "App.csproj", "")

        matched = matching_analyzers(root, analyzers)

    assert any(a.name == "C#" for a in matched)


def test_csharp_project_detection_uses_extension_fallback() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Program.cs", "")

        detection = detect_project(root)

    assert detection.primary_language == "C#"
