"""C/C++ analyzer: ctest (if a configured CMake build dir exists) +
cppcheck, gated on CMakeLists.txt.

Deliberately does NOT run `cmake configure` or `cmake --build` itself --
that can be slow and, on a misconfigured project, genuinely destructive
(wrong toolchain, wrong generator). sarand only runs tests/checks against
a build the user already configured; see AGENTS.md §3's rule about
warning before doing anything heavy.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.cpp")

_ENTRY_POINTS = ("src/main.cpp", "src/main.c", "main.cpp", "main.c")
# Common configured-build directory names to look for a ctest manifest in.
# نام‌های رایج پوشه‌ی build کانفیگ‌شده که به دنبال مانیفست ctest در آن‌ها می‌گردیم.
_BUILD_DIR_CANDIDATES = ("build", "cmake-build-debug", "cmake-build-release", "out")


class CppAnalyzer:
    name = "C/C++"

    def matches(self, root: Path) -> bool:
        return (root / "CMakeLists.txt").exists()

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).exists()]

    def _configured_build_dir(self, root: Path) -> Path | None:
        for name in _BUILD_DIR_CANDIDATES:
            candidate = root / name
            if (candidate / "CTestTestfile.cmake").exists():
                return candidate
        return None

    def _compile_commands(self, root: Path) -> Path | None:
        # clang-tidy without a compilation database mostly produces
        # noise (wrong include paths, wrong defines) rather than real
        # signal -- §4.3's "gate on a real project marker" applies
        # here exactly like `_configured_build_dir` above for ctest.
        # Checked at root first (some projects symlink or copy it
        # there deliberately for tooling), then every known build-dir
        # candidate.
        #
        # clang-tidy بدون compilation database بیشتر نویز تولید
        # می‌کند (مسیر include اشتباه، define اشتباه) تا سیگنال واقعی
        # -- «gate روی یک نشانگر واقعی پروژه»ی §4.3 دقیقاً همین‌جا هم
        # صدق می‌کند، مثل `_configured_build_dir` بالا برای ctest.
        # اول در ریشه چک می‌شود (بعضی پروژه‌ها عمداً برای tooling
        # آنجا symlink یا کپی می‌کنند)، بعد هر build-dir شناخته‌شده.
        direct = root / "compile_commands.json"
        if direct.is_file():
            return direct
        for name in _BUILD_DIR_CANDIDATES:
            candidate = root / name / "compile_commands.json"
            if candidate.is_file():
                return candidate
        return None

    async def run_tests(self, root: Path) -> CommandResult | None:
        build_dir = self._configured_build_dir(root)
        if build_dir is None:
            return make_command_result(
                "ctest",
                0,
                "",
                0.0,
                skipped=True,
                skip_reason=(
                    "no configured CMake build directory found (looked for "
                    f"{'/'.join(_BUILD_DIR_CANDIDATES)}) -- run `cmake -S . -B build` "
                    "with testing enabled first"
                ),
            )
        if shutil.which("ctest") is None:
            return make_command_result(
                "ctest",
                127,
                "",
                0.0,
                skipped=True,
                skip_reason="ctest not found in PATH",
            )

        logger.info("Running ctest in %s", build_dir)
        rc, output, duration = await run_cmd_async(
            ["ctest", "--test-dir", str(build_dir), "--output-on-failure"],
            root,
            LONG_CMD_TIMEOUT,
        )
        return make_command_result("ctest", rc, output, duration)

    async def run_quality(self, root: Path) -> list[CommandResult]:
        results: list[CommandResult] = []

        if (
            shutil.which("clang-format") is not None
            and (root / ".clang-format").exists()
        ):
            # Cap the file count so a huge repo doesn't blow past
            # command-line length limits -- this is a lint pass, not
            # exhaustive enforcement.
            # سقف تعداد فایل تا در یک ریپوی بزرگ از محدودیت طول خط
            # فرمان عبور نکنیم -- این یک پاس lint است، نه اجرای جامع.
            files = [
                str(p.relative_to(root))
                for p in sorted(root.rglob("*"))
                if p.is_file() and p.suffix in {".c", ".cpp", ".cc", ".h", ".hpp"}
            ][:200]
            if files:
                rc, out, dur = await run_cmd_async(
                    ["clang-format", "--dry-run", "--Werror", *files],
                    root,
                    LONG_CMD_TIMEOUT,
                )
                results.append(
                    make_command_result("clang-format --dry-run", rc, out, dur)
                )

        compile_commands = self._compile_commands(root)
        if shutil.which("clang-tidy") is None:
            results.append(
                make_command_result(
                    "clang-tidy",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="clang-tidy not installed",
                )
            )
        elif compile_commands is None:
            results.append(
                make_command_result(
                    "clang-tidy",
                    0,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason=(
                        "no compile_commands.json found -- configure with "
                        "cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=ON"
                    ),
                )
            )
        else:
            files = [
                str(p.relative_to(root))
                for p in sorted(root.rglob("*"))
                if p.is_file() and p.suffix in {".c", ".cpp", ".cc"}
            ][:200]
            if files:
                rc, out, dur = await run_cmd_async(
                    ["clang-tidy", "-p", str(compile_commands.parent), *files],
                    root,
                    LONG_CMD_TIMEOUT,
                )
                results.append(make_command_result("clang-tidy", rc, out, dur))

        return results

    async def run_security(self, root: Path) -> list[CommandResult]:
        if shutil.which("cppcheck") is None:
            return [
                make_command_result(
                    "cppcheck",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="cppcheck not installed",
                )
            ]
        rc, out, dur = await run_cmd_async(
            [
                "cppcheck",
                "--enable=warning",
                "--inline-suppr",
                "--error-exitcode=1",
                ".",
            ],
            root,
            LONG_CMD_TIMEOUT,
        )
        return [make_command_result("cppcheck", rc, out, dur)]
