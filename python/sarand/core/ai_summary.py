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


def suggest_reading_order(root: Path, included: list[Path]) -> list[str]:
    """Suggest a sensible order for a human or AI to read the codebase."""
    high: list[str] = []
    mid: list[str] = []
    low: list[str] = []

    for p in included:
        s = str(p).lower()
        name = p.name.lower()
        if (
            name in {"readme.md", "readme.rst", "readme"}
            or s.startswith("docs/")
            or name
            in {
                "cargo.toml",
                "pyproject.toml",
                "setup.py",
                "setup.cfg",
                "package.json",
                "go.mod",
                "makefile",
            }
        ):
            high.append(str(p))
        elif (
            name
            in {
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
            or "core" in s
            or "analyzers" in s
            or "scanners" in s
            or "model" in s
        ):
            mid.append(str(p))
        else:
            low.append(str(p))

    return high + mid + sorted(low)
