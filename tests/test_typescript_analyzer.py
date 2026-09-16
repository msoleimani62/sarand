"""Tests for the TypeScript analyzer.

The contract covers marker-gated detection, entry-point discovery,
the intentional run_tests/run_security no-ops (delegated to
NodeAnalyzer -- see typescript_analyzer.py's module docstring), clean
handling of a missing tsc, project detection integration, and registry
integration.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from _helpers import write
from sarand.analyzers.registry import discover_analyzers, matching_analyzers
from sarand.analyzers.typescript_analyzer import TypeScriptAnalyzer
from sarand.discovery.project_detector import detect_project


def test_typescript_analyzer_matches_on_tsconfig() -> None:
    analyzer = TypeScriptAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False

        write(root / "tsconfig.json", "{}\n")

        assert analyzer.matches(root) is True


def test_typescript_analyzer_does_not_match_unrelated_project() -> None:
    analyzer = TypeScriptAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", "{}")

        assert analyzer.matches(root) is False


def test_typescript_analyzer_entry_points() -> None:
    analyzer = TypeScriptAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "tsconfig.json", "{}\n")
        write(root / "index.ts", "export {};\n")
        write(root / "unrelated.ts", "export {};\n")

        assert analyzer.entry_points(root) == ["index.ts"]


def test_typescript_analyzer_run_tests_is_always_none() -> None:
    # run_tests is intentionally a no-op here: test execution is
    # NodeAnalyzer's job (npm test). See the module docstring.
    analyzer = TypeScriptAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "tsconfig.json", "{}\n")

        result = asyncio.run(analyzer.run_tests(root))

    assert result is None


def test_typescript_analyzer_run_quality_skips_cleanly_without_tsc() -> None:
    analyzer = TypeScriptAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "tsconfig.json", "{}\n")

        results = asyncio.run(analyzer.run_quality(root))

        assert len(results) == 1
        assert results[0].kind == "tsc --noEmit"

        if results[0].skipped:
            assert "not found" in results[0].skip_reason.lower()


def test_typescript_analyzer_run_security_is_always_empty() -> None:
    # Dependency auditing is NodeAnalyzer's job (npm audit).
    analyzer = TypeScriptAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "tsconfig.json", "{}\n")

        results = asyncio.run(analyzer.run_security(root))

        assert results == []


def test_typescript_analyzer_in_discover_and_matching() -> None:
    analyzers = discover_analyzers()
    assert any(a.name == "TypeScript" for a in analyzers)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "tsconfig.json", "{}\n")

        matched = matching_analyzers(root, analyzers)

    assert any(a.name == "TypeScript" for a in matched)


def test_typescript_and_node_analyzers_both_match_a_typescript_project() -> None:
    # A TypeScript project is still a Node.js project underneath (same
    # package.json) -- both analyzers must run concurrently against it
    # rather than TypeScriptAnalyzer replacing NodeAnalyzer.
    analyzers = discover_analyzers()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "tsconfig.json", "{}\n")
        write(root / "package.json", '{"scripts": {"test": "jest"}}\n')

        matched = {a.name for a in matching_analyzers(root, analyzers)}

    assert "TypeScript" in matched
    assert "Node.js" in matched


def test_typescript_project_detection_uses_tsconfig_marker() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "tsconfig.json", "{}\n")

        detection = detect_project(root)

    assert "TypeScript" in detection.languages
    assert detection.build_system == "npm/tsc"
