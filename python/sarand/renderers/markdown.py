"""Markdown report renderer."""

from __future__ import annotations

from sarand.constants import AI_NOTICE, LANG_MAP, MAX_ISSUE_ROWS
from sarand.models.results import CommandResult, Issue, ReportData
from sarand.progress import status
from sarand.utils.fs import human_size


def _status_badge(result: CommandResult) -> str:
    if result.skipped:
        return "SKIP"
    return "PASS" if result.passed else "FAIL"


def _render_issues(title: str, issues: list[Issue]) -> list[str]:
    if not issues:
        return [f"## {title}", "", "None detected.", ""]
    lines = [f"## {title}", ""]
    for issue in issues[:MAX_ISSUE_ROWS]:
        lines.append(f"- **{issue.source}**: `{issue.message}`")
    if len(issues) > MAX_ISSUE_ROWS:
        lines.append(f"- ... ({len(issues) - MAX_ISSUE_ROWS} more)")
    lines.append("")
    return lines


def _render_command_block(result: CommandResult) -> list[str]:
    badge = _status_badge(result)
    lines = [f"### {result.kind} [{badge}]"]
    if result.skipped:
        lines.extend(["", f"*Skipped:* {result.skip_reason}", ""])
        return lines
    lines.extend(["", "```text", result.summary or "(no output)", "```"])
    if result.returncode != 0 and result.raw_output:
        lines.extend(
            ["", "<details>", "<summary>Full output</summary>", "", "```text", result.raw_output, "```", "", "</details>", ""]
        )
    lines.append("")
    return lines


def _render_detected_project(data: ReportData) -> list[str]:
    d = data.detection
    lines = ["## Detected Project", ""]
    if not d.is_recognized:
        lines.extend(["No recognized project marker was found in this directory.", ""])
        return lines
    lines.extend(
        [
            f"- **Primary language:** {d.primary_language}",
            f"- **All detected languages:** {', '.join(d.languages)}",
            f"- **Project type:** {d.project_type}",
            f"- **Build system:** {d.build_system}",
            f"- **Markers found:** {', '.join(f'`{m}`' for m in d.markers_found)}",
            f"- **Scan engine:** {'Rust core (native)' if data.used_rust_core else 'pure-Python fallback'}",
        ]
    )
    if d.entry_points:
        lines.append(f"- **Entry points:** {', '.join(f'`{e}`' for e in d.entry_points)}")
    lines.append("")
    return lines


def render(data: ReportData, *, include_source: bool = True) -> str:
    """Render a full professional Markdown report."""
    status("Rendering Markdown report...")
    now = data.generated_at.strftime("%Y-%m-%d %H:%M:%S")
    parts: list[str] = [
        f"# sarand report — {data.project_root.name}",
        "",
        f"**Generated:** {now}  ",
        f"**Host:** {data.environment.hostname}  ",
        f"**Project:** `{data.project_root}`  ",
        "",
        AI_NOTICE,
        "",
        "---",
        "",
        *_render_detected_project(data),
        "---",
        "",
        "## Environment",
        "",
        "| Fact | Value |",
        "|------|-------|",
        f"| Python | {data.environment.python} |",
        f"| Rust core | {data.environment.rust_core} |",
        f"| OS | {data.environment.os_name} |",
        f"| Architecture | {data.environment.architecture} |",
        f"| CPU | {data.environment.cpu_summary} |",
        f"| Memory | {data.environment.memory_summary} |",
        f"| Disk | {data.environment.disk_free} |",
        f"| Hostname | {data.environment.hostname} |",
    ]

    if data.environment.tool_versions:
        parts.extend(["", "### Detected tools", "", "| Tool | Version |", "|------|---------|"])
        for tool, version in data.environment.tool_versions.items():
            parts.append(f"| {tool} | {version} |")

    parts.extend(
        [
            "",
            "## Git",
            "",
            f"- **Branch:** {data.git.branch}",
            f"- **Commit:** {data.git.commit}",
            f"- **Dirty:** {data.git.dirty}",
            f"- **Ahead / Behind:** {data.git.ahead} / {data.git.behind}",
            "",
            "### Status",
            "```text",
            data.git.status or "(clean)",
            "```",
            "",
            "### Recent commits",
            "```text",
            data.git.log or "(none)",
            "```",
            "",
        ]
    )

    if data.git.untracked:
        parts.extend(["### Untracked files", "", *[f"- `{u}`" for u in data.git.untracked[:50]], ""])

    if data.health:
        h = data.health
        parts.extend(
            [
                "## Health Score",
                "",
                f"**Score:** {h.score} / {h.max_score}  **Grade:** {h.grade}",
                "",
                "| Category | Points |",
                "|----------|--------|",
            ]
        )
        for k, v in h.breakdown.items():
            parts.append(f"| {k} | {v} |")
        parts.append("")
        if h.critical_failures:
            parts.extend(["### Critical failures", "", *[f"- {c}" for c in h.critical_failures], ""])
        if h.recommendations:
            parts.extend(["### Recommendations", "", *[f"- {r}" for r in h.recommendations], ""])

    if data.ai_summary:
        parts.extend(["## AI Summary", "", "```text", data.ai_summary, "```", ""])

    if data.suggested_reading_order:
        parts.extend(
            [
                "## Suggested reading order",
                "",
                *[f"{i}. `{p}`" for i, p in enumerate(data.suggested_reading_order[:40], 1)],
                "",
            ]
        )

    s = data.stats
    top_ext = ", ".join(f"{ext} ({n})" for ext, n in list(s.files_by_extension.items())[:10])
    parts.extend(
        [
            "## Project statistics",
            "",
            f"- Total files: **{s.total_files}**",
            f"- By extension: {top_ext or 'n/a'}",
            f"- LOC: **{s.total_loc}** (code {s.code_lines} / comment {s.comment_lines} / blank {s.blank_lines})",
            f"- Binary files: {s.binary_files} · Hidden files: {s.hidden_files}",
            f"- Empty files: {len(s.empty_files)} · Broken symlinks: {len(s.broken_symlinks)}",
            f"- Temporary files: {len(s.temporary_files)} · Cache-like: {len(s.unused_cache_files)}",
            "",
        ]
    )

    if s.largest_files:
        parts.extend(["### Largest files", "", "| Path | Size |", "|------|------|"])
        for p, sz in s.largest_files[:15]:
            parts.append(f"| `{p}` | {human_size(sz)} |")
        parts.append("")

    if data.todos:
        parts.extend(["## TODO / FIXME markers", "", "| File | Line | Kind | Content |", "|------|------|------|---------|"])
        for t in data.todos[:100]:
            content = t.content.replace("|", "\\|")
            parts.append(f"| `{t.path}` | {t.line_number} | {t.kind} | `{content}` |")
        if len(data.todos) > 100:
            parts.append(f"| ... | ... | ... | ({len(data.todos) - 100} more) |")
        parts.append("")

    parts.extend(["## Test results", ""])
    if not data.test_results:
        parts.append("No tests executed.")
        parts.append("")
    else:
        for r in data.test_results:
            parts.extend(_render_command_block(r))

    if data.quality_results:
        parts.extend(["## Quality checks", ""])
        for r in data.quality_results:
            parts.extend(_render_command_block(r))

    if data.security_results:
        parts.extend(["## Security checks", ""])
        for r in data.security_results:
            parts.extend(_render_command_block(r))

    if data.known_issues:
        parts.extend(["## Known issues", "", *[f"- {i}" for i in data.known_issues], ""])

    all_warnings: list[Issue] = []
    all_errors: list[Issue] = []
    for r in data.test_results + data.quality_results + data.security_results:
        all_warnings.extend(r.warnings)
        all_errors.extend(r.errors)
    parts.extend(_render_issues("Warnings detected", all_warnings))
    parts.extend(_render_issues("Errors detected", all_errors))

    parts.extend(
        [
            "## Project tree",
            "",
            "```text",
            data.tree_text,
            "```",
            "",
            f"## Included files ({len(data.included_files)} included / {len(data.skipped_files)} skipped)",
            "",
        ]
    )

    if data.skipped_files:
        parts.extend(["### Skipped (too large)", "", *[f"- `{p}` ({human_size(sz)})" for p, sz in data.skipped_files], ""])

    if include_source:
        for rel in data.included_files:
            full = data.project_root / rel
            try:
                text = full.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                text = f"(error reading file: {exc})"
            lang = LANG_MAP.get(full.suffix.lower(), "")
            try:
                size = full.stat().st_size
            except OSError:
                size = 0
            parts.extend(["", f"### FILE: `{rel}`", "", f"Size: {human_size(size)}", "", f"```{lang}", text, "```"])

    return "\n".join(parts)
