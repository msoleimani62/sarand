"""Tests for the C/C++ and Java/Kotlin analyzers added in Phase C."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

import pytest
from _helpers import write
from sarand.analyzers.cpp_analyzer import CppAnalyzer
from sarand.analyzers.java_analyzer import JavaAnalyzer
from sarand.analyzers.registry import discover_analyzers, matching_analyzers


def test_cpp_analyzer_gated_on_cmakelists() -> None:
    analyzer = CppAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert analyzer.matches(root) is False
        write(root / "CMakeLists.txt", "cmake_minimum_required(VERSION 3.10)\n")
        assert analyzer.matches(root) is True


def test_cpp_analyzer_skips_tests_cleanly_without_configured_build_dir() -> None:
    """A CMakeLists.txt with no configured build/ dir must not attempt to
    configure or build anything -- just report why it's skipping."""
    analyzer = CppAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "CMakeLists.txt", "cmake_minimum_required(VERSION 3.10)\n")

        result = asyncio.run(analyzer.run_tests(root))

        assert result is not None
        assert result.kind == "ctest"
        assert result.skipped
        assert "no configured cmake build directory" in result.skip_reason.lower()


def test_cpp_analyzer_finds_configured_build_dir() -> None:
    analyzer = CppAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "CMakeLists.txt", "cmake_minimum_required(VERSION 3.10)\n")
        write(root / "build" / "CTestTestfile.cmake", "# Generated\n")

        build_dir = analyzer._configured_build_dir(root)

        assert build_dir == root / "build"


def test_cpp_analyzer_quality_skips_clang_format_without_config() -> None:
    analyzer = CppAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "CMakeLists.txt", "cmake_minimum_required(VERSION 3.10)\n")
        write(root / "main.cpp", "int main() { return 0; }\n")

        results = asyncio.run(analyzer.run_quality(root))

    # No .clang-format -> clang-format is left out entirely (not even a
    # skip entry, matching the original behavior). clang-tidy is always
    # evaluated though (it's independent), and skips on its own gate.
    assert not any(r.kind == "clang-format --dry-run" for r in results)
    tidy = next(r for r in results if r.kind == "clang-tidy")
    assert tidy.skipped is True


def test_cpp_analyzer_clang_tidy_skips_without_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_which(name: str) -> str | None:
        if name == "clang-tidy":
            return None
        return f"/usr/bin/{name}"

    monkeypatch.setattr(shutil, "which", fake_which)
    analyzer = CppAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "CMakeLists.txt", "cmake_minimum_required(VERSION 3.10)\n")
        write(root / "compile_commands.json", "[]")

        results = asyncio.run(analyzer.run_quality(root))

    tidy = next(r for r in results if r.kind == "clang-tidy")
    assert tidy.skipped is True
    assert "not installed" in tidy.skip_reason


def test_cpp_analyzer_clang_tidy_skips_without_compile_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    analyzer = CppAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "CMakeLists.txt", "cmake_minimum_required(VERSION 3.10)\n")
        # deliberately no compile_commands.json anywhere

        results = asyncio.run(analyzer.run_quality(root))

    tidy = next(r for r in results if r.kind == "clang-tidy")
    assert tidy.skipped is True
    assert "compile_commands.json" in tidy.skip_reason


def test_cpp_analyzer_clang_tidy_runs_with_compile_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sarand.analyzers.cpp_analyzer as cpp_analyzer_module

    captured_cmds: list[list[str]] = []

    async def fake_run_cmd_async(cmd, cwd, timeout):
        captured_cmds.append(cmd)
        return 0, "ok", 0.1

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(cpp_analyzer_module, "run_cmd_async", fake_run_cmd_async)

    analyzer = CppAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "CMakeLists.txt", "cmake_minimum_required(VERSION 3.10)\n")
        write(root / "main.cpp", "int main() { return 0; }\n")
        write(root / "build" / "compile_commands.json", "[]")

        results = asyncio.run(analyzer.run_quality(root))

    tidy = next(r for r in results if r.kind == "clang-tidy")
    assert tidy.skipped is False
    tidy_cmd = next(c for c in captured_cmds if c[0] == "clang-tidy")
    assert "-p" in tidy_cmd
    assert "main.cpp" in tidy_cmd


@pytest.mark.slow_external
def test_cpp_analyzer_security_skips_cleanly_without_cppcheck() -> None:
    analyzer = CppAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "CMakeLists.txt", "cmake_minimum_required(VERSION 3.10)\n")

        results = asyncio.run(analyzer.run_security(root))

        assert len(results) == 1
        assert results[0].kind == "cppcheck"
        if shutil.which("cppcheck") is None:
            assert results[0].skipped


def test_java_analyzer_matches_maven_project() -> None:
    analyzer = JavaAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert analyzer.matches(root) is False
        write(root / "pom.xml", "<project></project>\n")
        assert analyzer.matches(root) is True


def test_java_analyzer_matches_gradle_project() -> None:
    analyzer = JavaAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "build.gradle.kts", "plugins {}\n")
        assert analyzer.matches(root) is True


def test_java_analyzer_prefers_maven_when_both_markers_present() -> None:
    analyzer = JavaAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pom.xml", "<project></project>\n")
        write(root / "build.gradle", "apply plugin: 'java'\n")
        assert analyzer._build_tool(root) == "maven"


@pytest.mark.slow_external
def test_java_analyzer_run_tests_skips_cleanly_when_no_tool_available() -> None:
    analyzer = JavaAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pom.xml", "<project></project>\n")

        result = asyncio.run(analyzer.run_tests(root))

        assert result is not None
        assert result.kind == "mvn test"
        if shutil.which("mvn") is None:
            assert result.skipped


def test_java_analyzer_run_tests_gradle_uses_wrapper_when_present() -> None:
    analyzer = JavaAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "build.gradle", "apply plugin: 'java'\n")
        wrapper = write(root / "gradlew", "#!/bin/sh\necho fake gradlew\n")
        wrapper.chmod(0o755)

        binary, found = analyzer._gradle_invocation(root)

        assert found is True
        assert binary == str(root / "gradlew")


def test_java_analyzer_all_methods_present() -> None:
    analyzer = JavaAnalyzer()
    for attr in ("matches", "entry_points", "run_tests", "run_quality", "run_security"):
        assert hasattr(analyzer, attr)


def test_registry_includes_cpp_and_java_analyzers() -> None:
    names = {a.name for a in discover_analyzers()}
    assert "C/C++" in names
    assert "Java/Kotlin" in names


def test_matching_analyzers_picks_up_cpp_project() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "CMakeLists.txt", "cmake_minimum_required(VERSION 3.10)\n")

        active = matching_analyzers(root, discover_analyzers())

        assert {a.name for a in active} == {"C/C++"}
