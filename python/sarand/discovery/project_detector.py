"""Detect what kind of project lives at a given path.

Deliberately uses stdlib logging only (not sarand.utils.logging) to
keep this module dependency-light and cycle-safe -- see the note in
models/results.py about layering.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sarand.constants import ENTRY_POINT_CANDIDATES, IGNORE_DIRS, PROJECT_MARKERS
from sarand.discovery.android import is_android_project
from sarand.models.results import ProjectDetection

logger = logging.getLogger("sarand.discovery")


def _find_entry_points(root: Path, language: str) -> list[str]:
    found: list[str] = []
    for candidate in ENTRY_POINT_CANDIDATES.get(language, ()):
        if (root / candidate).exists():
            found.append(candidate)
    return found


def detect_project(root: Path) -> ProjectDetection:
    """Inspect ``root`` and detect its language(s), type and build system."""
    logger.info("Detecting project type at %s", root)

    languages: list[str] = []
    markers_found: list[str] = []
    entry_points: list[str] = []
    primary_language = "Unknown"
    project_type = "unknown"
    build_system = "unknown"

    for marker, (language, ptype, build) in PROJECT_MARKERS.items():
        if not (root / marker).exists():
            continue
        markers_found.append(marker)
        if language not in languages:
            languages.append(language)
        if primary_language == "Unknown":
            primary_language = language
            project_type = ptype
            build_system = build
        entry_points.extend(_find_entry_points(root, language))

    if not markers_found:
        guess = _guess_from_extensions(root)
        if guess:
            languages.append(guess)
            primary_language = guess
            project_type = "unknown (no build-system marker found)"
            build_system = "none detected"

    # Relabel generic "Java/Kotlin" (from a bare build.gradle(.kts) or
    # pom.xml marker) as specifically Android when the deeper Android
    # signals are present -- matches what AndroidAnalyzer actually runs
    # against this project (§ its module docstring), so the report's
    # opening line doesn't undersell what was actually detected/run.
    # برچسب عمومی «Java/Kotlin» (که فقط از یک build.gradle(.kts) یا
    # pom.xml خام آمده) را وقتی سیگنال‌های عمیق‌تر اندروید وجود دارند،
    # مشخصاً به Android تغییر می‌دهد -- با چیزی که AndroidAnalyzer واقعاً
    # روی این پروژه اجرا می‌کند هماهنگ می‌شود، تا خط اول گزارش کم‌تر از
    # چیزی که واقعاً تشخیص/اجرا شده نشان ندهد.
    if primary_language == "Java/Kotlin" and is_android_project(root):
        primary_language = "Android/Kotlin"
        project_type = "mobile application"
        languages = [
            "Android/Kotlin" if lang == "Java/Kotlin" else lang for lang in languages
        ]

    return ProjectDetection(
        languages=languages,
        primary_language=primary_language,
        project_type=project_type,
        build_system=build_system,
        markers_found=markers_found,
        entry_points=sorted(set(entry_points)),
    )


def _guess_from_extensions(root: Path, sample_limit: int = 500) -> str:
    counts: dict[str, int] = {}
    ext_to_lang = {
        ".py": "Python",
        ".rs": "Rust",
        ".go": "Go",
        ".js": "Node.js",
        ".ts": "Node.js",
        ".java": "Java/Kotlin",
        ".kt": "Java/Kotlin",
        ".c": "C/C++",
        ".cpp": "C/C++",
    }
    scanned = 0
    for path in root.rglob("*"):
        if scanned >= sample_limit:
            break
        if not path.is_file():
            continue
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        scanned += 1
        lang = ext_to_lang.get(path.suffix.lower())
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    if not counts:
        return ""
    return max(counts.items(), key=lambda kv: kv[1])[0]
