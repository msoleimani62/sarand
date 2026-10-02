"""Generate AI-friendly project summary and suggested reading order."""

from __future__ import annotations

from pathlib import Path

from sarand.models.results import ReportData


def generate_ai_summary(data: ReportData) -> str:
    """Produce a concise, structured summary for AI consumers."""
    stats = data.stats
    detection = data.detection

    languages = ", ".join(detection.languages) if detection.languages else "Unknown"
    lines = [
        f"Project: {data.project_root.name}",
        f"Detected languages: {languages}",
        f"Project type: {detection.project_type} (build system: {detection.build_system})",
    ]

    if detection.entry_points:
        lines.append(f"Entry points: {', '.join(detection.entry_points)}")
    lines.extend(f"{label}: {text}" for label, text in detection.details.items())

    top_exts = ", ".join(
        f"{ext} ({n})" for ext, n in list(stats.files_by_extension.items())[:8]
    )
    lines.extend(
        [
            f"File breakdown: {top_exts or 'n/a'}",
            f"Total files: {stats.total_files}, LOC: {stats.total_loc}",
            f"Git branch: {data.git.branch} @ {data.git.commit}",
            f"Dirty: {data.git.dirty}, Ahead: {data.git.ahead}, Behind: {data.git.behind}",
        ]
    )

    if data.health:
        lines.append(
            f"Health score: {data.health.score}/100 (grade {data.health.grade})"
        )

    if data.known_issues:
        lines.append("Known issues:")
        for issue in data.known_issues:
            lines.append(f"  - {issue}")

    return "\n".join(lines)


_TEST_DIRS = frozenset({"tests", "test", "__tests__", "spec", "specs"})
_FIRST_NAMES = frozenset(
    {
        "readme.md",
        "readme.rst",
        "readme",
        "cargo.toml",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "package.json",
        "go.mod",
        "makefile",
    }
)
_ENTRY_NAMES = frozenset(
    {
        "main.py",
        "cli.py",
        "lib.rs",
        "main.rs",
        "__main__.py",
        "app.py",
        "main.go",
        "index.js",
        "index.ts",
    }
)


def suggest_reading_order(root: Path, included: list[Path]) -> list[str]:
    """Suggest a sensible order for a human or AI to read the codebase.

    Entry points and manifests first, then core/model code, then docs,
    then everything else; shallow paths first within each group and
    test files never promoted (item 12 audit on a real report: the scan
    order put 33 alphabetical plugins, then docs and a test file, ahead
    of cli.py).
    ترتیب مطالعه: نقاط ورود و مانیفست‌ها، سپس هسته/مدل، سپس مستندات و
    بقیه؛ در هر گروه مسیر کم‌عمق‌تر اول و فایل تست هرگز ارتقا نمی‌یابد.
    """
    first: list[str] = []
    core: list[str] = []
    docs: list[str] = []
    rest: list[str] = []

    for p in included:
        posix = p.as_posix()
        s = posix.lower()
        name = p.name.lower()
        parts = s.split("/")
        in_tests = any(seg in _TEST_DIRS for seg in parts[:-1]) or name.startswith(
            "test_"
        )
        if in_tests:
            rest.append(posix)
        elif name in _FIRST_NAMES:
            first.append(posix)
        elif s.startswith("docs/"):
            docs.append(posix)
        elif name in _ENTRY_NAMES or "core" in s or "model" in s:
            core.append(posix)
        else:
            rest.append(posix)

    def by_depth(paths: list[str]) -> list[str]:
        return sorted(paths, key=lambda path: (len(Path(path).parts), path))

    return by_depth(first) + by_depth(core) + by_depth(docs) + by_depth(rest)
