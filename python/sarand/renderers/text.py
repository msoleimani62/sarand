"""Plain-text report renderer."""

from __future__ import annotations

from sarand.models.results import ReportData
from sarand.progress import status


def render(data: ReportData, *, include_source: bool = True) -> str:
    status("Rendering plain-text report...")
    lines = [
        f"sarand report — {data.project_root.name}",
        f"Generated: {data.generated_at}",
        f"Host: {data.environment.hostname}",
        "",
        f"Detected: {', '.join(data.detection.languages) or 'unknown'} ({data.detection.build_system})",
        f"Scan engine: {'Rust core' if data.used_rust_core else 'pure-Python fallback'}",
        f"Python: {data.environment.python}",
        f"Git: {data.git.branch} @ {data.git.commit} (dirty={data.git.dirty})",
        "",
        f"Files: {data.stats.total_files}  LOC: {data.stats.total_loc}",
    ]
    if data.health:
        lines.append(f"Health: {data.health.score}/100 ({data.health.grade})")
    if data.secret_findings:
        lines.append(
            f"Secrets: {len(data.secret_findings)} potential finding(s) -- see full report"
        )
    return "\n".join(lines)
