"""Objective-C analyzer: `xcodebuild test`, gated on a CocoaPods
Podfile, a top-level .m/.mm file, or a top-level .xcworkspace/.xcodeproj.

Complementary to SwiftAnalyzer rather than a replacement for it: a
mixed Swift/Objective-C project (extremely common in older iOS/macOS
codebases mid-migration) legitimately has both analyzers match at
once, the same complementary-match shape as TypeScriptAnalyzer/
NodeAnalyzer or KotlinAnalyzer/JavaAnalyzer. The xcodebuild
scheme-detection helper is intentionally duplicated here rather than
imported from swift_analyzer.py -- every analyzer in this package is
self-contained by convention (see AGENTS.md §5), so adding a language
never risks touching another analyzer's file.

xcodebuild itself only exists on macOS with Xcode installed, so this
path is expected to report skipped almost everywhere sarand runs; it
exists for completeness/portability, same as SwiftAnalyzer's own
xcodebuild fallback.

آنالایزر Objective-C: `xcodebuild test`، فقط وقتی یک Podfile واقعیِ
CocoaPods، یک فایل .m/.mm سطح-ریشه، یا یک .xcworkspace/.xcodeproj
سطح-ریشه وجود داشته باشد.

مکملِ SwiftAnalyzer است، نه جایگزین آن: یک پروژه‌ی ترکیبیِ
Swift/Objective-C (در کدبیس‌های قدیمی‌تر iOS/macOS در حال مهاجرت خیلی
رایج است) به‌طور مشروع هر دو آنالایزر را هم‌زمان تطابق می‌دهد، همان شکل
تطابقِ مکملِ TypeScriptAnalyzer/NodeAnalyzer یا KotlinAnalyzer/
JavaAnalyzer. کمکیِ تشخیص scheme برای xcodebuild عمداً اینجا تکرار
شده به‌جای import از swift_analyzer.py -- هر آنالایزر در این پکیج طبق
قرارداد (§5 در AGENTS.md) خودمختار است، پس افزودن یک زبان هرگز فایل
آنالایزر دیگری را در خطر تغییر نمی‌اندازد.

خودِ xcodebuild فقط روی macOS با Xcode نصب‌شده وجود دارد، پس انتظار
می‌رود این مسیر تقریباً همه‌جایی که sarand اجرا می‌شود skipped گزارش
شود؛ برای کامل‌بودن/قابل‌حمل‌بودن است، همانند fallback خودِ xcodebuild
در SwiftAnalyzer.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.objectivec")

_ENTRY_POINTS = ("main.m", "Sources/main.m")
_OBJC_EXTENSIONS = (".m", ".mm")


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


def _top_level_objc_files(root: Path) -> list[Path]:
    try:
        return sorted(
            p
            for p in root.iterdir()
            if p.is_file() and p.suffix.lower() in _OBJC_EXTENSIONS
        )
    except OSError:
        return []


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


class ObjectiveCAnalyzer:
    name = "Objective-C"

    def matches(self, root: Path) -> bool:
        if (root / "Podfile").is_file():
            return True
        if _top_level_objc_files(root):
            return True
        return _find_xcode_project(root) is not None

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).is_file()]

    async def run_tests(self, root: Path) -> CommandResult | None:
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
        if (
            shutil.which("clang-format") is None
            or not (root / ".clang-format").exists()
        ):
            return []

        files = [
            str(p.relative_to(root))
            for p in sorted(root.rglob("*"))
            if p.is_file() and p.suffix.lower() in _OBJC_EXTENSIONS
        ][:200]
        if not files:
            return []

        rc, out, dur = await run_cmd_async(
            ["clang-format", "--dry-run", "--Werror", *files], root, LONG_CMD_TIMEOUT
        )
        return [make_command_result("clang-format --dry-run", rc, out, dur)]

    async def run_security(self, root: Path) -> list[CommandResult]:
        # No standard CocoaPods/Objective-C vulnerability-audit tool
        # exists as of this writing -- honest empty, same precedent as
        # SwiftAnalyzer.
        return []
