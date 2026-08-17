"""Tests for the Lua analyzer.

The contract covers marker-gated detection, entry-point discovery,
clean handling of missing external tools, project detection integration,
and registry integration.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from _helpers import write
from sarand.analyzers.lua_analyzer import LuaAnalyzer
from sarand.analyzers.registry import discover_analyzers, matching_analyzers
from sarand.discovery.project_detector import detect_project


def test_lua_analyzer_matches_on_rockspec() -> None:
    analyzer = LuaAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False

        write(root / "foo-1.0-1.rockspec", 'package = "foo"\n')

        assert analyzer.matches(root) is True


def test_lua_analyzer_matches_on_init_lua() -> None:
    analyzer = LuaAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False

        write(root / "init.lua", "return {}\n")

        assert analyzer.matches(root) is True


def test_lua_analyzer_matches_on_main_lua() -> None:
    analyzer = LuaAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "main.lua", "print('hi')\n")

        assert analyzer.matches(root) is True


def test_lua_analyzer_matches_on_top_level_lua_file() -> None:
    analyzer = LuaAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "util.lua", "local M = {}\nreturn M\n")

        assert analyzer.matches(root) is True


def test_lua_analyzer_does_not_match_nested_lua_without_root_signal() -> None:
    """A nested Lua file alone must not force a project-level match."""

    analyzer = LuaAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "vendor" / "lib" / "thing.lua", "return 1\n")

        assert analyzer.matches(root) is False


def test_lua_analyzer_entry_points() -> None:
    analyzer = LuaAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "init.lua", "return {}\n")
        write(root / "main.lua", "print(1)\n")
        write(root / "src" / "main.lua", "print(2)\n")

        found = analyzer.entry_points(root)

        assert found == ["init.lua", "main.lua", "src/main.lua"]


def test_lua_analyzer_run_tests_skips_cleanly_without_busted() -> None:
    analyzer = LuaAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "init.lua", "return {}\n")

        result = asyncio.run(analyzer.run_tests(root))

        assert result is not None
        assert result.kind == "busted"

        if result.skipped:
            assert "not found" in result.skip_reason.lower()


def test_lua_analyzer_run_quality_skips_cleanly_without_luacheck() -> None:
    analyzer = LuaAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "main.lua", "print('x')\n")

        results = asyncio.run(analyzer.run_quality(root))

        assert len(results) == 1
        assert results[0].kind == "luacheck"

        if results[0].skipped:
            assert "not installed" in results[0].skip_reason.lower()


def test_lua_analyzer_run_security_is_empty() -> None:
    analyzer = LuaAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "init.lua", "return {}\n")

        results = asyncio.run(analyzer.run_security(root))

        assert results == []


def test_lua_analyzer_in_discover_and_matching() -> None:
    pool = discover_analyzers()
    names = {analyzer.name for analyzer in pool}

    assert "Lua" in names

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "init.lua", "return {}\n")

        active = matching_analyzers(root, pool)

        assert any(analyzer.name == "Lua" for analyzer in active)


def test_lua_analyzer_does_not_match_empty_tree() -> None:
    analyzer = LuaAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False


def test_lua_project_detection_uses_lua_marker() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "init.lua", "return {}\n")

        detection = detect_project(root)

        assert "Lua" in detection.languages
        assert detection.primary_language == "Lua"
        assert detection.project_type == "module/library"
        assert detection.build_system == "none"
        assert "init.lua" in detection.markers_found
        assert "init.lua" in detection.entry_points


def test_lua_project_detection_uses_extension_fallback() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        write(root / "script.lua", "print('hello')\n")

        detection = detect_project(root)

        assert detection.primary_language == "Lua"
        assert "Lua" in detection.languages
