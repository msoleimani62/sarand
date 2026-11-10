"""Plain-text report renderer."""

from __future__ import annotations

from sarand.core.architecture import l3_lines
from sarand.core.execution_coverage import coverage_oneline
from sarand.core.quick_context import build_quick_context, quick_context_lines
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
        "",
        "Quick Context",
        *(f"  {line}" for line in quick_context_lines(build_quick_context(data))),
        "",
        "Architecture and Risks",
        *(f"  {line}" for line in l3_lines(data)),
    ]
    if data.relevant_source is not None:
        from sarand.core.relevant_source import relevant_source_text

        # Not indented: the byte budget applies to the text as it is.
        # تورفتگی ندارد: سقف بایت روی خودِ متن است.
        lines += ["", "Relevant Source", relevant_source_text(data.relevant_source)]
    if data.health:
        lines.append(
            f"Health: {data.health.score}/100 ({data.health.grade}) -- "
            f"{coverage_oneline(data.health)}"
        )
    # The same facts the other formats list in full (counts only, R13-G).
    # همان واقعیت‌هایی که قالب‌های دیگر کامل می‌آورند (اینجا فقط شمارش).
    if data.failures:
        lines.append(f"Failures: {len(data.failures)} classified -- see full report")
    if data.advisories:
        lines.append(
            f"Advisories: {len(data.advisories)} reported by the security tools "
            "(tool results; applicability unknown) -- see full report"
        )
    if data.secret_findings:
        lines.append(
            f"Secrets: {len(data.secret_findings)} potential finding(s) -- see full report"
        )
    return "\n".join(lines)
