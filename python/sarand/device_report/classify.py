"""Risk classification for cleanup-decision evidence.

Pure string/path matching, ported 1:1 from the bash `classify_path`
case statement -- no portability concerns here, kept as its own small
module because it's independently testable and the mapping itself
(not the mechanism) is what matters.

طبقه‌بندی ریسک برای شواهد تصمیم‌گیری پاک‌سازی. تطبیق رشته/مسیر خالص،
عیناً از case statement بش پورت شده -- نگرانی پرتابل‌بودن ندارد، فقط
چون خودش مستقل قابل‌تست است و نگاشت (نه مکانیزم) چیزی است که اهمیت
دارد، ماژول جدا شده است.
"""

from __future__ import annotations

from pathlib import PurePosixPath

LIKELY_RECLAIMABLE = "LIKELY_RECLAIMABLE"
SAFE_TO_REVIEW = "SAFE_TO_REVIEW"
REQUIRES_REVIEW = "REQUIRES_REVIEW"
DO_NOT_DELETE_AUTOMATICALLY = "DO_NOT_DELETE_AUTOMATICALLY"
SYSTEM_CRITICAL = "SYSTEM_CRITICAL"

_RECLAIMABLE_NAMES = frozenset(
    {
        ".cache",
        "node_modules",
        "target",
        "build",
        "dist",
        ".gradle",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
    }
)
_SAFE_TO_REVIEW_SUFFIXES = frozenset(
    {
        (".cargo", "registry"),
        (".cargo", "git"),
    }
)
_SAFE_TO_REVIEW_NAMES = frozenset({".rustup", ".npm", ".m2", "Download", "Downloads"})
_SYSTEM_CRITICAL_PREFIXES = (
    "/system",
    "/vendor",
    "/product",
    "/data/system",
    "/data/misc",
    "/data/app",
)


def classify_path(path_str: str) -> str:
    path = PurePosixPath(path_str)
    parts = path.parts

    for prefix in _SYSTEM_CRITICAL_PREFIXES:
        if path_str == prefix or path_str.startswith(prefix + "/"):
            return SYSTEM_CRITICAL

    if ".git" in parts:
        return DO_NOT_DELETE_AUTOMATICALLY

    for a, b in _SAFE_TO_REVIEW_SUFFIXES:
        if a in parts and b in parts and parts.index(b) == parts.index(a) + 1:
            return SAFE_TO_REVIEW

    if any(name in parts for name in _SAFE_TO_REVIEW_NAMES):
        return SAFE_TO_REVIEW

    if any(name in parts for name in _RECLAIMABLE_NAMES):
        return LIKELY_RECLAIMABLE

    return REQUIRES_REVIEW
