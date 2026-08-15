"""Android project detection -- shared by discovery/project_detector.py
(for the report's top-line "Detected: ..." label) and
analyzers/android_analyzer.py (for matches()/JavaAnalyzer's exclusion
of it). Lives in discovery/, not analyzers/, so the dependency runs
the natural direction: analyzers consume discovery, not the reverse.

تشخیص پروژه اندروید -- مشترک بین discovery/project_detector.py (برای
برچسب «Detected: ...» خط اول گزارش) و analyzers/android_analyzer.py
(برای matches()/حذف آن در JavaAnalyzer). در discovery/ است، نه
analyzers/، تا جهت وابستگی طبیعی بماند: آنالایزرها از discovery
مصرف می‌کنند، نه برعکس.
"""

from __future__ import annotations

from pathlib import Path

# Bounded, shallow globs -- covers the standard single-module ("app/")
# and common multi-module ("<module>/") Android layouts without an
# unbounded rglob() that could be slow on a large monorepo.
_ANDROID_MANIFEST_GLOBS = (
    "AndroidManifest.xml",
    "*/src/main/AndroidManifest.xml",
    "*/*/src/main/AndroidManifest.xml",
)

_AGP_MARKERS = ("com.android.application", "com.android.library")
_BUILD_FILE_CANDIDATES = (
    "build.gradle",
    "build.gradle.kts",
    "app/build.gradle",
    "app/build.gradle.kts",
)


def is_android_project(root: Path) -> bool:
    """True if this looks like an Android app/library module.

    Two independent signals, either is sufficient:
    1. An AndroidManifest.xml in a standard location.
    2. The Android Gradle Plugin (`com.android.application` or
       `com.android.library`) referenced in a top-level build file.
    """
    for pattern in _ANDROID_MANIFEST_GLOBS:
        if any(root.glob(pattern)):
            return True

    for name in _BUILD_FILE_CANDIDATES:
        candidate = root / name
        if not candidate.exists():
            continue
        try:
            text = candidate.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(marker in text for marker in _AGP_MARKERS):
            return True

    return False
