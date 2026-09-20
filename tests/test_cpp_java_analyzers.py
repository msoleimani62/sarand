"""Tests for the C/C++ and Java/Kotlin analyzers added in Phase C."""

from __future__ import annotations

import asyncio
import json
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
        write(
            root / "build" / "compile_commands.json",
            json.dumps(
                [
                    {
                        "directory": str(root),
                        "command": "c++ -c main.cpp -o main.o",
                        "file": str(root / "main.cpp"),
                    }
                ]
            ),
        )

        results = asyncio.run(analyzer.run_quality(root))

    tidy = next(r for r in results if r.kind == "clang-tidy")
    assert tidy.skipped is False
    tidy_cmd = next(c for c in captured_cmds if c[0] == "clang-tidy")
    assert "-p" in tidy_cmd
    assert "main.cpp" in tidy_cmd


def test_cpp_analyzer_clang_tidy_excludes_cmake_generated_probe_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression guard for a real bug the maintainer found by hand:
    CMake's own compiler-ID detection writes a throwaway .cpp file
    into build/CMakeFiles/.../CompilerIdCXX/ and (on some CMake
    versions) that entry can end up in compile_commands.json too --
    confirmed via a real `sarand --quality --format json` run showing
    clang-tidy actually processing it. Must be filtered out even if
    the compile db lists it, not just excluded from a directory glob."""
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
        probe = (
            root
            / "build"
            / "CMakeFiles"
            / "4.3.4"
            / "CompilerIdCXX"
            / "CMakeCXXCompilerId.cpp"
        )
        write(probe, "// generated by cmake\n")
        compile_db = json.dumps(
            [
                {
                    "directory": str(root / "build"),
                    "command": "c++ -c main.cpp",
                    "file": str(root / "main.cpp"),
                },
                {
                    "directory": str(probe.parent),
                    "command": "c++ -c CMakeCXXCompilerId.cpp",
                    "file": str(probe),
                },
            ]
        )
        write(root / "build" / "compile_commands.json", compile_db)

        asyncio.run(analyzer.run_quality(root))

    tidy_cmd = next(c for c in captured_cmds if c[0] == "clang-tidy")
    assert "main.cpp" in tidy_cmd
    assert not any("CompilerIdCXX" in arg for arg in tidy_cmd)
    assert not any("CMakeCXXCompilerId.cpp" in arg for arg in tidy_cmd)


def test_cpp_analyzer_security_skips_cleanly_without_cppcheck(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Hermetic: the "tool missing" path must not depend on what is installed
    # on the machine (a real Gradle/Maven/pip-audit run can take an hour).
    # ایزوله: مسیر «ابزار نصب نیست» نباید به نصب‌بودن ابزار روی ماشین بستگی
    # داشته باشد (یک اجرای واقعی Gradle/Maven/pip-audit می‌تواند یک ساعت طول بکشد).
    monkeypatch.setattr(shutil, "which", lambda name: None)
    analyzer = CppAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "CMakeLists.txt", "cmake_minimum_required(VERSION 3.10)\n")

        results = asyncio.run(analyzer.run_security(root))

    assert len(results) == 1
    assert results[0].kind == "cppcheck"
    assert results[0].skipped is True


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


def test_java_analyzer_run_tests_skips_cleanly_when_no_tool_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Hermetic: the "tool missing" path must not depend on what is installed
    # on the machine (a real Gradle/Maven/pip-audit run can take an hour).
    # ایزوله: مسیر «ابزار نصب نیست» نباید به نصب‌بودن ابزار روی ماشین بستگی
    # داشته باشد (یک اجرای واقعی Gradle/Maven/pip-audit می‌تواند یک ساعت طول بکشد).
    monkeypatch.setattr(shutil, "which", lambda name: None)
    analyzer = JavaAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pom.xml", "<project></project>\n")

        result = asyncio.run(analyzer.run_tests(root))

    assert result is not None
    assert result.kind == "mvn test"
    assert result.skipped is True


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


def test_java_analyzer_maven_quality_runs_checkstyle_and_spotbugs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sarand.analyzers.java_analyzer as java_analyzer_module

    captured_cmds: list[list[str]] = []

    async def fake_run_cmd_async(cmd, cwd, timeout):
        captured_cmds.append(cmd)
        return 0, "ok", 0.1

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(java_analyzer_module, "run_cmd_async", fake_run_cmd_async)

    analyzer = JavaAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pom.xml", "<project></project>\n")

        results = asyncio.run(analyzer.run_quality(root))

    kinds = {r.kind for r in results}
    assert kinds == {"mvn checkstyle:check", "mvn spotbugs:check"}
    assert all(not r.skipped for r in results)
    assert any(c[:2] == ["mvn", "-B"] and "checkstyle" in c[2] for c in captured_cmds)
    assert any(c[:2] == ["mvn", "-B"] and "spotbugs" in c[2] for c in captured_cmds)


def test_java_analyzer_gradle_quality_skips_without_plugins_applied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Hermetic: pretend gradle is installed, otherwise the result depends on
    # whether the machine running the tests happens to have gradle.
    # ایزوله: وانمود می‌کنیم gradle نصب است، وگرنه نتیجه به نصب‌بودن
    # gradle روی ماشینِ اجراکننده‌ی تست بستگی پیدا می‌کند.
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    analyzer = JavaAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "build.gradle", "apply plugin: 'java'\n")

        results = asyncio.run(analyzer.run_quality(root))

    by_kind = {r.kind: r for r in results}
    assert by_kind["gradle checkstyleMain"].skipped is True
    reason = by_kind["gradle checkstyleMain"].skip_reason
    assert "checkstyle plugin not applied" in reason
    assert by_kind["gradle spotbugsMain"].skipped is True
    assert "spotbugs plugin not applied" in by_kind["gradle spotbugsMain"].skip_reason


def test_java_analyzer_gradle_quality_runs_when_plugins_applied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sarand.analyzers.java_analyzer as java_analyzer_module

    captured_cmds: list[list[str]] = []

    async def fake_run_cmd_async(cmd, cwd, timeout):
        captured_cmds.append(cmd)
        return 0, "ok", 0.1

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(java_analyzer_module, "run_cmd_async", fake_run_cmd_async)

    analyzer = JavaAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(
            root / "build.gradle",
            "plugins { id 'checkstyle'; id 'com.github.spotbugs' }\n",
        )

        results = asyncio.run(analyzer.run_quality(root))

    by_kind = {r.kind: r for r in results}
    assert by_kind["gradle checkstyleMain"].skipped is False
    assert by_kind["gradle spotbugsMain"].skipped is False
    assert ["gradle", "checkstyleMain", "--console=plain"] in captured_cmds
    assert ["gradle", "spotbugsMain", "--console=plain"] in captured_cmds


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
