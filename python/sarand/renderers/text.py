"""Plain-text report renderer."""

from __future__ import annotations

from sarand.models.results import ReportData
from sarand.progress import status


def render(
    data: ReportData, *, include_source: bool = True, full_output: bool = False
) -> str:
    status("Rendering plain-text report...")
    lines = [
        f"sarand report — {data.project_root.name}",
        f"Generated: {data.generated_at}",
        f"Host: {data.environment.hostname}",
        "",
        f"Detected: {', '.join(data.detection.languages) or 'unknown'} ({data.detection.build_system})",
        *(f"{label}: {text}" for label, text in data.detection.details.items()),
        f"Scan engine: {'Rust core' if data.used_rust_core else 'pure-Python fallback'}",
        f"Python: {data.environment.python}",
        f"Git: {data.git.branch} @ {data.git.commit} (dirty={data.git.dirty})",
        "",
        f"Files: {data.stats.total_files}  LOC: {data.stats.total_loc}",
    ]
    if data.health:
        health_line = f"Health: {data.health.score}/100 ({data.health.grade})"
        if data.health.checks_skipped:
            health_line += (
                f" -- confidence {round(data.health.confidence * 100)}% "
                f"({len(data.health.checks_skipped)} check(s) skipped: "
                "tool not installed)"
            )
        lines.append(health_line)
    if data.secret_findings:
        lines.append(
            f"Secrets: {len(data.secret_findings)} potential finding(s) -- see full report"
        )
    return "\n".join(lines)
