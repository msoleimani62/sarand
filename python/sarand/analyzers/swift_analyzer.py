"""Swift analyzer: `swift test` for SwiftPM packages, `xcodebuild
test` for Xcode-only projects, gated on a real Package.swift or a
top-level .xcworkspace/.xcodeproj.

SwiftPM is preferred whenever Package.swift exists: `swift` itself is
cross-platform (Linux included, via swift.org's toolchain) and needs
no scheme guessing. xcodebuild is only reached for a project that has
*no* Package.swift at all -- and xcodebuild itself only exists on
macOS with Xcode installed, so that path is expected to report skipped
almost everywhere sarand runs; it exists for completeness/portability,
not because it's expected to fire on this project's own devices.

sarand has no way to know a project's intended scheme name up front,
so it asks xcodebuild itself (`-list -json`) and uses the first scheme
reported -- the same "ask the tool, don't guess" approach
AndroidAnalyzer/JavaAnalyzer use for Gradle's wrapper detection.

آنالایزر Swift: `swift test` برای پکیج‌های SwiftPM، `xcodebuild test`
برای پروژه‌های فقط-Xcode، فقط وقتی Package.swift واقعی یا یک
.xcworkspace/.xcodeproj سطح-ریشه وجود داشته باشد.

هروقت Package.swift وجود دارد SwiftPM ترجیح داده می‌شود: خودِ `swift`
کراس‌پلتفرم است (شامل Linux، از طریق toolchain سایت swift.org) و نیازی
به حدس زدن scheme ندارد. xcodebuild فقط برای پروژه‌ای که اصلاً
Package.swift ندارد به کار می‌رود -- و خودِ xcodebuild فقط روی macOS با
Xcode نصب‌شده وجود دارد، پس انتظار می‌رود این مسیر تقریباً همه‌جایی که
sarand اجرا می‌شود skipped گزارش شود؛ برای کامل‌بودن/قابل‌حمل‌بودن است،
نه چون انتظار می‌رود روی دستگاه‌های خودِ این پروژه فعال شود.

sarand از قبل راهی برای دانستن scheme مورد نظر یک پروژه ندارد، پس خودِ
xcodebuild را می‌پرسد (`-list -json`) و اولین scheme گزارش‌شده را
استفاده می‌کند -- همان رویکرد «از ابزار بپرس، حدس نزن» که
AndroidAnalyzer/JavaAnalyzer برای تشخیص wrapper گریدل استفاده می‌کنند.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.swift")

_ENTRY_POINTS = ("Sources/main.swift", "main.swift")


def _find_xcode_project(root: Path) -> Path | None:
    """Return the first top-level .xcworkspace or .xcodeproj, preferring
    a workspace (what Xcode itself defaults to when both exist)."""
    try:
        entries = list(root.iterdir())
    except OSError:
        return None
    for entry in entries:
        if entry.is_dir() and entry.suffix == ".xcworkspace":
            return entry
    for entry in entries:
        if entry.is_dir() and entry.suffix == ".xcodeproj":
            return entry
    return None


async def _first_xcodebuild_scheme(root: Path, project: Path) -> str | None:
    flag = "-workspace" if project.suffix == ".xcworkspace" else "-project"
    rc, out, _dur = await run_cmd_async(
        ["xcodebuild", flag, str(project), "-list", "-json"], root, LONG_CMD_TIMEOUT
    )
    if rc != 0:
        return None
    try:
        data = json.loads(out)
    except (json.JSONDecodeError, TypeError):
        return None
    container = data.get("workspace") or data.get("project") or {}
    schemes = container.get("schemes") or []
    return schemes[0] if schemes else None


class SwiftAnalyzer:
    name = "Swift"

    def matches(self, root: Path) -> bool:
        if (root / "Package.swift").is_file():
            return True
        return _find_xcode_project(root) is not None

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).is_file()]

    async def run_tests(self, root: Path) -> CommandResult | None:
        if (root / "Package.swift").is_file():
            if shutil.which("swift") is None:
                return make_command_result(
                    "swift test",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="swift not found in PATH",
                )
            logger.info("Running swift test")
            rc, out, dur = await run_cmd_async(
                ["swift", "test"], root, LONG_CMD_TIMEOUT
            )
            return make_command_result("swift test", rc, out, dur)

        project = _find_xcode_project(root)
        if project is None:
            return None
        if shutil.which("xcodebuild") is None:
            return make_command_result(
                "xcodebuild test",
                127,
                "",
                0.0,
                skipped=True,
                skip_reason="xcodebuild not found (macOS + Xcode only)",
            )
        scheme = await _first_xcodebuild_scheme(root, project)
        if scheme is None:
            return make_command_result(
                "xcodebuild test",
                1,
                "",
                0.0,
                skipped=True,
                skip_reason=f"no scheme reported by xcodebuild for {project.name}",
            )
        flag = "-workspace" if project.suffix == ".xcworkspace" else "-project"
        logger.info("Running xcodebuild test (scheme=%s)", scheme)
        rc, out, dur = await run_cmd_async(
            ["xcodebuild", flag, str(project), "-scheme", scheme, "test"],
            root,
            LONG_CMD_TIMEOUT,
        )
        return make_command_result(f"xcodebuild test ({scheme})", rc, out, dur)

    async def run_quality(self, root: Path) -> list[CommandResult]:
        formatter = shutil.which("swift-format")
        if formatter is None:
            return [
                make_command_result(
                    "swift-format lint",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="swift-format not found in PATH",
                )
            ]
        rc, out, dur = await run_cmd_async(
            [formatter, "lint", "--recursive", "."], root, LONG_CMD_TIMEOUT
        )
        return [make_command_result("swift-format lint", rc, out, dur)]

    async def run_security(self, root: Path) -> list[CommandResult]:
        # No standard SwiftPM dependency-audit tool exists as of this
        # writing -- honest empty, same precedent as other ecosystems
        # without one (Dart/Lua/CSS/Zig).
        return []
