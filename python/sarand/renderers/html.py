"""HTML dashboard renderer.

Self-contained single file (inline CSS, no external assets) so the
report works when opened directly from a filesystem, no server needed.
Also serves as the PDF renderer's input (renderers/pdf.py converts this
output via an installed HTML-to-PDF tool) -- keep the markup simple and
print-friendly for that reason.
"""

from __future__ import annotations

from html import escape

from sarand.models.results import CommandResult, Issue, ReportData
from sarand.progress import status
from sarand.utils.fs import human_size

_CSS = """
:root {
  color-scheme: dark light;
  --bg: #0f1117; --fg: #e6e6e6; --muted: #9aa0aa; --card: #171a21;
  --border: #262a33; --accent: #4f8cff; --ok: #3fb950; --warn: #d29922; --fail: #f85149;
}
* { box-sizing: border-box; }
body {
  background: var(--bg); color: var(--fg); margin: 0; padding: 2rem;
  font-family: -apple-system, "Segoe UI", Roboto, sans-serif; line-height: 1.5;
  max-width: 960px; margin-inline: auto;
}
h1 { font-size: 1.6rem; margin-bottom: 0.2rem; }
h2 { font-size: 1.15rem; border-bottom: 1px solid var(--border); padding-bottom: 0.3rem; margin-top: 2rem; }
.meta { color: var(--muted); font-size: 0.9rem; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; margin: 0.75rem 0; }
table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
th, td { border: 1px solid var(--border); padding: 0.4rem 0.6rem; text-align: left; }
th { color: var(--muted); font-weight: 600; }
code, pre { font-family: "SF Mono", Consolas, monospace; }
pre { background: #0b0d12; border: 1px solid var(--border); border-radius: 6px; padding: 0.75rem; overflow-x: auto; white-space: pre-wrap; }
.badge { display: inline-block; padding: 0.1rem 0.55rem; border-radius: 999px; font-size: 0.78rem; font-weight: 600; }
.badge-ok { background: rgba(63,185,80,0.15); color: var(--ok); }
.badge-warn { background: rgba(210,153,34,0.15); color: var(--warn); }
.badge-fail { background: rgba(248,81,73,0.15); color: var(--fail); }
details { margin: 0.5rem 0; }
summary { cursor: pointer; font-weight: 600; padding: 0.3rem 0; }
.health-score { font-size: 2.2rem; font-weight: 700; }
.grade-A, .grade-B { color: var(--ok); }
.grade-C, .grade-D { color: var(--warn); }
.grade-F { color: var(--fail); }
@media print { body { color: #111; background: #fff; } .card { border-color: #ccc; } pre { background: #f4f4f4; } }
"""


def _badge(text: str, kind: str) -> str:
    return f'<span class="badge badge-{kind}">{escape(text)}</span>'


def _status_badge_html(result: CommandResult) -> str:
    if result.skipped:
        return _badge("SKIP", "warn")
    return _badge("PASS", "ok") if result.passed else _badge("FAIL", "fail")


def _command_section(title: str, results: list[CommandResult]) -> str:
    if not results:
        return ""
    rows = []
    for r in results:
        detail = r.skip_reason if r.skipped else (r.summary or "(no output)")
        rows.append(
            f"<details><summary>{escape(r.kind)} {_status_badge_html(r)}</summary>"
            f"<pre>{escape(detail)}</pre></details>"
        )
    return f"<h2>{escape(title)}</h2>" + "".join(rows)


def _issues_table(title: str, issues: list[Issue]) -> str:
    if not issues:
        return ""
    rows = "".join(
        f"<tr><td>{escape(i.source)}</td><td><code>{escape(i.message)}</code></td></tr>"
        for i in issues[:500]
    )
    return f"<h2>{escape(title)} ({len(issues)})</h2><table><tr><th>Source</th><th>Message</th></tr>{rows}</table>"


def render(data: ReportData, *, include_source: bool = True) -> str:
    status("Rendering HTML report...")
    d = data.detection
    s = data.stats
    now = data.generated_at.strftime("%Y-%m-%d %H:%M:%S")

    parts: list[str] = [
        f"<h1>sarand report — {escape(data.project_root.name)}</h1>",
        (
            f'<p class="meta">Generated {escape(now)} on {escape(data.environment.hostname)} · '
            f"scan engine: {'Rust core' if data.used_rust_core else 'pure-Python fallback'}</p>"
        ),
    ]

    parts.append('<div class="card">')
    if d.is_recognized:
        parts.append(
            f"<strong>{escape(d.primary_language)}</strong> — {escape(d.project_type)} "
            f"({escape(d.build_system)})<br>"
        )
        parts.append(
            f'<span class="meta">Languages: {escape(", ".join(d.languages))}</span><br>'
        )
        if d.entry_points:
            parts.append(
                f'<span class="meta">Entry points: {escape(", ".join(d.entry_points))}</span>'
            )
    else:
        parts.append("No recognized project marker found in this directory.")
    parts.append("</div>")

    if data.health:
        h = data.health
        parts.append(
            f'<div class="card"><span class="health-score grade-{escape(h.grade)}">{h.score}/100 '
            f"({escape(h.grade)})</span>"
        )
        rows = "".join(
            f"<tr><td>{escape(k)}</td><td>{v}</td></tr>" for k, v in h.breakdown.items()
        )
        parts.append(f"<table>{rows}</table>")
        if h.critical_failures:
            parts.append(
                "<p><strong>Critical:</strong></p><ul>"
                + "".join(f"<li>{escape(c)}</li>" for c in h.critical_failures)
                + "</ul>"
            )
        if h.recommendations:
            parts.append(
                "<p><strong>Recommendations:</strong></p><ul>"
                + "".join(f"<li>{escape(r)}</li>" for r in h.recommendations)
                + "</ul>"
            )
        parts.append("</div>")

    if data.excluded_secret_files or data.secret_findings:
        parts.append("<h2>⚠ Secrets</h2>")
        if data.excluded_secret_files:
            parts.append(
                "<p>Excluded (credential-shaped, never embedded):</p><ul>"
                + "".join(
                    f"<li><code>{escape(str(p))}</code></li>"
                    for p in data.excluded_secret_files
                )
                + "</ul>"
            )
        if data.secret_findings:
            rows = "".join(
                f"<tr><td><code>{escape(f.path)}</code></td><td>{f.line_number}</td>"
                f"<td>{escape(f.pattern_name)}</td></tr>"
                for f in data.secret_findings
            )
            parts.append(
                f"<table><tr><th>File</th><th>Line</th><th>Pattern</th></tr>{rows}</table>"
            )

    top_ext = ", ".join(
        f"{ext} ({n})" for ext, n in list(s.files_by_extension.items())[:10]
    )
    parts.append(
        f"<h2>Project statistics</h2><div class='card'>"
        f"Total files: <strong>{s.total_files}</strong> · LOC: <strong>{s.total_loc}</strong><br>"
        f"By extension: {escape(top_ext) or 'n/a'}<br>"
        f"Binary: {s.binary_files} · Hidden: {s.hidden_files} · Empty: {len(s.empty_files)} · "
        f"Broken symlinks: {len(s.broken_symlinks)}</div>"
    )

    if data.ai_summary:
        parts.append(f"<h2>AI Summary</h2><pre>{escape(data.ai_summary)}</pre>")

    parts.append(_command_section("Test results", data.test_results))
    parts.append(_command_section("Quality checks", data.quality_results))
    parts.append(_command_section("Security checks", data.security_results))

    all_warnings: list[Issue] = []
    all_errors: list[Issue] = []
    for r in data.test_results + data.quality_results + data.security_results:
        all_warnings.extend(r.warnings)
        all_errors.extend(r.errors)
    parts.append(_issues_table("Errors detected", all_errors))
    parts.append(_issues_table("Warnings detected", all_warnings))

    parts.append(f"<h2>Project tree</h2><pre>{escape(data.tree_text)}</pre>")

    parts.append(
        f"<h2>Included files ({len(data.included_files)} included / {len(data.skipped_files)} skipped / "
        f"{len(data.excluded_secret_files)} excluded)</h2>"
    )

    if include_source:
        for rel in data.included_files:
            full = data.project_root / rel
            try:
                text = full.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                text = f"(error reading file: {exc})"
            try:
                size = human_size(full.stat().st_size)
            except OSError:
                size = "?"
            parts.append(
                f"<details><summary><code>{escape(str(rel))}</code> ({size})</summary>"
                f"<pre>{escape(text)}</pre></details>"
            )

    body = "\n".join(parts)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>sarand report — {escape(data.project_root.name)}</title>
<style>{_CSS}</style>
</head>
<body>
{body}
</body>
</html>
"""
