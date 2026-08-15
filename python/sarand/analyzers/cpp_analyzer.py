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
        if (
            shutil.which("clang-format") is None
            or not (root / ".clang-format").exists()
        ):
            return []

        # Cap the file count so a huge repo doesn't blow past command-line
        # length limits -- this is a lint pass, not exhaustive enforcement.
        # سقف تعداد فایل تا در یک ریپوی بزرگ از محدودیت طول خط فرمان
        # عبور نکنیم -- این یک پاس lint است، نه اجرای جامع.
        files = [
            str(p.relative_to(root))
            for p in sorted(root.rglob("*"))
            if p.is_file() and p.suffix in {".c", ".cpp", ".cc", ".h", ".hpp"}
        ][:200]
        if not files:
            return []

        rc, out, dur = await run_cmd_async(
            ["clang-format", "--dry-run", "--Werror", *files], root, LONG_CMD_TIMEOUT
        )
        return [make_command_result("clang-format --dry-run", rc, out, dur)]

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
