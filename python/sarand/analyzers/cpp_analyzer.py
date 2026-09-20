"""C/C++ analyzer: ctest (if a configured CMake build dir exists) +
cppcheck, gated on CMakeLists.txt.

Deliberately does NOT run `cmake configure` or `cmake --build` itself --
that can be slow and, on a misconfigured project, genuinely destructive
(wrong toolchain, wrong generator). sarand only runs tests/checks against
a build the user already configured; see AGENTS.md §3's rule about
warning before doing anything heavy.
"""

from __future__ import annotations

import json
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
            # Source list comes from compile_commands.json itself -- the
            # authoritative record of what was really compiled -- instead
            # of globbing the tree: a glob also sweeps up CMake's own
            # generated compiler-ID probe file (build/CMakeFiles/.../
            # CompilerIdCXX/CMakeCXXCompilerId.cpp), confirmed by a real run.
            # لیست سورس‌ها از خودِ compile_commands.json می‌آید -- مرجع
            # واقعیِ چیزی که کامپایل شده -- نه glob روی درخت پروژه: glob
            # فایل probe خودکارِ CMake را هم می‌گیرد (build/CMakeFiles/.../
            # CompilerIdCXX/CMakeCXXCompilerId.cpp)، که با اجرای واقعی تأیید شد.
            compile_db_files: set[str] = set()

            try:
                compile_db = json.loads(compile_commands.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                compile_db = None

            if isinstance(compile_db, list):
                for entry in compile_db:
                    if not isinstance(entry, dict):
                        continue

                    file_value = entry.get("file")
                    if not isinstance(file_value, str):
                        continue

                    file_path = Path(file_value)

                    if not file_path.is_absolute():
                        directory = entry.get("directory")
                        if isinstance(directory, str):
                            file_path = Path(directory) / file_path
                        else:
                            file_path = root / file_path

                    # Entries outside the project root are ignored.
                    # ورودی‌های بیرون از ریشه‌ی پروژه نادیده گرفته می‌شوند.
                    try:
                        relative = file_path.resolve().relative_to(root.resolve())
                    except ValueError:
                        continue

                    # Defense in depth: drop CMake-generated paths even if
                    # they ended up in the compile db.
                    # دفاع لایه‌ای: مسیرهای تولیدشده‌ی CMake حتی اگر در
                    # compile db باشند حذف می‌شوند.
                    if (
                        relative.suffix.lower() in {".c", ".cc", ".cpp", ".cxx"}
                        and "CMakeFiles" not in relative.parts
                        and not any(
                            part.startswith("cmake-build") for part in relative.parts
                        )
                    ):
                        compile_db_files.add(relative.as_posix())

            files = sorted(compile_db_files)[:200]

            if files:
                cmd = [
                    "clang-tidy",
                    "-p",
                    str(compile_commands.parent),
                    "--quiet",
                ]

                # Default check set only when the project has no
                # .clang-tidy of its own (an existing config must win).
                # مجموعه‌ی چک پیش‌فرض فقط وقتی که پروژه .clang-tidy
                # خودش را ندارد (کانفیگ موجود باید برنده باشد).
                if not (root / ".clang-tidy").exists():
                    checks = (
                        "-*,"
                        "clang-diagnostic-*,"
                        "bugprone-*,"
                        "readability-*,"
                        "performance-*,"
                        "modernize-*,"
                        "cppcoreguidelines-*,"
                        "-modernize-use-trailing-return-type,"
                        "-readability-magic-numbers,"
                        "-readability-identifier-length"
                    )
                    cmd.append(f"-checks={checks}")

                cmd.extend(files)

                rc, out, dur = await run_cmd_async(
                    cmd,
                    root,
                    LONG_CMD_TIMEOUT,
                )
                results.append(
                    make_command_result(
                        "clang-tidy",
                        rc,
                        out,
                        dur,
                    )
                )
            else:
                results.append(
                    make_command_result(
                        "clang-tidy",
                        0,
                        "",
                        0.0,
                        skipped=True,
                        skip_reason=(
                            "no C/C++ source files found in compile_commands.json"
                        ),
                    )
                )

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
