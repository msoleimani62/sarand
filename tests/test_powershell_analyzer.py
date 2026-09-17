"""Tests for the PowerShell analyzer.

The contract covers shallow marker-gated detection, entry-point
discovery, clean handling of missing external tools, extension-fallback
project detection, and registry integration.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from _helpers import write
from sarand.analyzers.powershell_analyzer import PowerShellAnalyzer
from sarand.analyzers.registry import discover_analyzers, matching_analyzers
from sarand.discovery.project_detector import detect_project


def test_powershell_analyzer_matches_on_top_level_ps1_file() -> None:
    analyzer = PowerShellAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False

        write(root / "Deploy.ps1", "Write-Host 'hi'\n")

        assert analyzer.matches(root) is True


def test_powershell_analyzer_matches_on_top_level_psm1_module() -> None:
    analyzer = PowerShellAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "Tools.psm1", "function Foo {}\n")

        assert analyzer.matches(root) is True


def test_powershell_analyzer_does_not_match_nested_ps1_without_root_signal() -> None:
    analyzer = PowerShellAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "scripts" / "deep" / "thing.ps1", "\n")

        assert analyzer.matches(root) is False


def test_powershell_analyzer_does_not_match_unrelated_project() -> None:
    analyzer = PowerShellAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "main.py", "print('hi')\n")

        assert analyzer.matches(root) is False


def test_powershell_analyzer_entry_points() -> None:
    analyzer = PowerShellAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "main.ps1", "Write-Host 'hi'\n")

        found = analyzer.entry_points(root)

        assert found == ["main.ps1"]


def test_powershell_analyzer_run_tests_is_none_without_pester_suite() -> None:
    analyzer = PowerShellAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "main.ps1", "Write-Host 'hi'\n")

        result = asyncio.run(analyzer.run_tests(root))

        assert result is None


def test_powershell_analyzer_run_tests_skips_cleanly_without_pwsh() -> None:
    analyzer = PowerShellAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "main.ps1", "Write-Host 'hi'\n")
        write(root / "tests" / "Main.Tests.ps1", "Describe 'x' { It 'y' {} }\n")

        result = asyncio.run(analyzer.run_tests(root))

        assert result is not None
        assert result.kind == "Invoke-Pester"

        if result.skipped:
            assert "not found" in result.skip_reason.lower()


def test_powershell_analyzer_run_quality_skips_cleanly_without_pwsh() -> None:
    analyzer = PowerShellAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "main.ps1", "Write-Host 'hi'\n")

        results = asyncio.run(analyzer.run_quality(root))

        assert len(results) == 1
        assert results[0].kind == "Invoke-ScriptAnalyzer"

        if results[0].skipped:
            assert "not found" in results[0].skip_reason.lower()


def test_powershell_analyzer_run_security_is_always_empty() -> None:
    analyzer = PowerShellAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "main.ps1", "Write-Host 'hi'\n")

        results = asyncio.run(analyzer.run_security(root))

        assert results == []


def test_powershell_analyzer_in_discover_and_matching() -> None:
    pool = discover_analyzers()
    names = {analyzer.name for analyzer in pool}

    assert "PowerShell" in names

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "main.ps1", "Write-Host 'hi'\n")

        active = matching_analyzers(root, pool)

        assert any(analyzer.name == "PowerShell" for analyzer in active)


def test_powershell_analyzer_does_not_match_empty_tree() -> None:
    analyzer = PowerShellAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False


def test_powershell_project_detection_uses_extension_fallback() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "main.ps1", "Write-Host 'hi'\n")

        detection = detect_project(root)

        assert detection.primary_language == "PowerShell"
