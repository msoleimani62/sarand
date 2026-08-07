"""PDF renderer -- converts the HTML report via an already-installed
HTML-to-PDF tool (wkhtmltopdf or weasyprint), rather than pulling in a
heavy Python PDF library. Neither tool is required for sarand to work;
if neither is found, this returns a clear explanation of what to
install -- the same "gate on tool presence, never crash unexplained"
pattern every LanguageAnalyzer follows (AGENTS.md §4.3, §4.11).

Unlike every other renderer, PDF output is binary. This module does
NOT implement the `Renderer` protocol's `render(data) -> str` --
instead it exposes `render_to_file(data, output_path)`, which writes
directly to disk and returns a RenderOutcome. cli.py treats "pdf" as a
distinct code path for exactly this reason.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sarand.models.results import ReportData
from sarand.progress import status
from sarand.renderers import html as html_renderer

_TIMEOUT_SECONDS = 120


@dataclass
class RenderOutcome:
    ok: bool
    detail: str


def _via_wkhtmltopdf(html_path: Path, output_path: Path) -> RenderOutcome:
    binary = shutil.which("wkhtmltopdf")
    if not binary:
        return RenderOutcome(False, "wkhtmltopdf not found in PATH")
    try:
        result = subprocess.run(
            [binary, "--quiet", "--enable-local-file-access", str(html_path), str(output_path)],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return RenderOutcome(False, "wkhtmltopdf timed out")
    if result.returncode != 0 or not output_path.exists():
        return RenderOutcome(False, result.stderr.strip() or "wkhtmltopdf failed")
    return RenderOutcome(True, "rendered via wkhtmltopdf")


def _via_weasyprint(html_path: Path, output_path: Path) -> RenderOutcome:
    binary = shutil.which("weasyprint")
    if not binary:
        return RenderOutcome(False, "weasyprint not found in PATH")
    try:
        result = subprocess.run(
            [binary, str(html_path), str(output_path)],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return RenderOutcome(False, "weasyprint timed out")
    if result.returncode != 0 or not output_path.exists():
        return RenderOutcome(False, result.stderr.strip() or "weasyprint failed")
    return RenderOutcome(True, "rendered via weasyprint")


def render_to_file(data: ReportData, output_path: Path, *, include_source: bool = False) -> RenderOutcome:
    """Render `data` as PDF directly to `output_path`.

    Args:
        data: Complete report data.
        output_path: Where to write the PDF.
        include_source: Defaults to False for PDF specifically -- a full
            source dump becomes an enormous number of paginated PDF
            pages via an HTML-to-PDF converter, which is slow and a
            poor reading experience. Use --format html for a browsable
            full-source report instead.

    Returns:
        RenderOutcome(ok=False, detail=<fix-it text>) if no PDF engine
        was found or the conversion failed -- never raises for a missing
        optional tool.
    """
    status("Rendering PDF report...")
    html_content = html_renderer.render(data, include_source=include_source)

    with tempfile.TemporaryDirectory() as tmp:
        html_path = Path(tmp) / "report.html"
        html_path.write_text(html_content, encoding="utf-8")

        for attempt in (_via_wkhtmltopdf, _via_weasyprint):
            outcome = attempt(html_path, output_path)
            if outcome.ok:
                return outcome

    return RenderOutcome(
        False,
        "No PDF engine found. Install one: `wkhtmltopdf` (e.g. `apt install wkhtmltopdf` / "
        "`pacman -S wkhtmltopdf`) or `pip install weasyprint`. Falling back to --format html "
        "gives the same content without needing either.",
    )
