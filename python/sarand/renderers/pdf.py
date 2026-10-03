"""PDF renderer -- converts the HTML report via an already-installed
HTML-to-PDF engine (wkhtmltopdf or WeasyPrint), rather than pulling in a
heavy Python PDF library. Neither engine is required for sarand to work;
PDF is optional and degrades gracefully (backlog item 15).

Unlike every other renderer, PDF output is binary. This module does
NOT implement the `Renderer` protocol's `render(data) -> str` --
instead it exposes `render_to_file(data, output_path)`, which writes
directly to disk and returns a RenderOutcome. cli.py treats "pdf" as a
distinct code path for exactly this reason, and falls back to a
Markdown report when no PDF can be produced.

Engines, tried in this order (unchanged):

1. `wkhtmltopdf` on PATH. Upstream archived the project in 2023, so
   distro packages vary and some distributions no longer ship it.
2. WeasyPrint, found three ways: the `weasyprint` command on PATH, the
   `weasyprint` script inside the Python environment sarand runs from,
   or the importable module (`python -m weasyprint`). The last two matter
   for `pipx inject sarand weasyprint`: pipx keeps its scripts inside the
   environment, off PATH, so a PATH-only lookup could never see them.
   WeasyPrint itself needs the Pango system library (a pip install does
   not provide it).

Failure reporting (the audit's third finding): the old fall-through
always said "No PDF engine found. Install one" -- even when an engine
WAS found and crashed, discarding its real error. `render_to_file` now
returns what actually happened: either "not installed" with install
hints, or each engine's own failure reason, clipped.

Not verified here: Termux and Android (no native wheel or package for
either engine was checked). Use `--format html` and print from a browser
there; see the README.

موتورهای PDF: wkhtmltopdf (پروژه‌ی بالادستی ۲۰۲۳ بایگانی شد) و WeasyPrint
(از PATH، از اسکریپت داخل همان محیط پایتون، یا از ماژول؛ دو حالت آخر
برای `pipx inject sarand weasyprint` لازم است چون pipx اسکریپت‌ها را خارج
از PATH نگه می‌دارد). WeasyPrint کتابخانه‌ی سیستمی Pango می‌خواهد.

گزارش خطا: پیام قبلی همیشه «موتوری پیدا نشد» می‌گفت حتی وقتی موتور پیدا
شده و کرش کرده بود؛ حالا دلیل واقعیِ هر موتور برمی‌گردد.
"""

from __future__ import annotations

import importlib.util
import shutil

# sarand exists to run external tools; every call below passes a fixed argv
# list (never a shell string), so bandit B404/B603 is accepted by design.
# وظیفه‌ی sarand اجرای ابزارهای خارجی است؛ هر فراخوانیِ زیر یک لیست argv
# ثابت می‌گیرد (هرگز رشته‌ی shell)، پس B404/B603 در bandit عمداً پذیرفته شده.
import subprocess  # nosec B404
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sarand.models.results import ReportData
from sarand.progress import status
from sarand.renderers import html as html_renderer

_TIMEOUT_SECONDS = 120
_MAX_DETAIL_CHARS = 300

_INSTALL_HINT = (
    "Install one: `wkhtmltopdf` (e.g. `apt install wkhtmltopdf`; some distributions "
    "no longer package it) or WeasyPrint (`pip install weasyprint`, or "
    "`pipx inject sarand weasyprint` for a pipx install; it also needs the Pango "
    "system library). `--format html` gives the same content without either."
)
_NATIVE_LIBRARY_HINT = (
    "WeasyPrint needs the Pango system library (e.g. `apt install libpango-1.0-0` "
    "or `pacman -S pango`)."
)


@dataclass
class RenderOutcome:
    ok: bool
    detail: str


def _clip(text: str) -> str:
    flat = " ".join(text.split())
    if len(flat) <= _MAX_DETAIL_CHARS:
        return flat
    return flat[: _MAX_DETAIL_CHARS - 1] + "…"


def _run_engine(name: str, argv: list[str], output_path: Path) -> RenderOutcome:
    """Run one engine; success means it exited 0 AND wrote a PDF file."""
    try:
        result = subprocess.run(  # nosec B603
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return RenderOutcome(False, f"{name} timed out after {_TIMEOUT_SECONDS}s")
    except OSError as exc:
        return RenderOutcome(False, f"{name} could not be started: {_clip(str(exc))}")
    if result.returncode != 0 or not output_path.exists():
        reason = _clip(result.stderr or result.stdout) or f"{name} failed"
        if "pango" in reason.lower() or "cannot load library" in reason.lower():
            reason = f"{reason} -- {_NATIVE_LIBRARY_HINT}"
        return RenderOutcome(False, f"{name} failed: {reason}")
    if output_path.read_bytes()[:5] != b"%PDF-":
        output_path.unlink(missing_ok=True)
        return RenderOutcome(False, f"{name} wrote a file that is not a PDF")
    return RenderOutcome(True, f"rendered via {name}")


def _via_wkhtmltopdf(html_path: Path, output_path: Path) -> RenderOutcome | None:
    binary = shutil.which("wkhtmltopdf")
    if not binary:
        return None
    argv = [binary, "--quiet", "--enable-local-file-access"]
    return _run_engine(
        "wkhtmltopdf", [*argv, str(html_path), str(output_path)], output_path
    )


def _weasyprint_command() -> list[str] | None:
    """How to invoke WeasyPrint, or None when it is not installed."""
    binary = shutil.which("weasyprint")
    if binary:
        return [binary]
    env_scripts = Path(sys.executable).parent
    for name in ("weasyprint", "weasyprint.exe"):
        candidate = env_scripts / name
        if candidate.is_file():
            return [str(candidate)]
    if importlib.util.find_spec("weasyprint") is not None:
        return [sys.executable, "-m", "weasyprint"]
    return None


def _via_weasyprint(html_path: Path, output_path: Path) -> RenderOutcome | None:
    command = _weasyprint_command()
    if command is None:
        return None
    return _run_engine(
        "weasyprint", [*command, str(html_path), str(output_path)], output_path
    )


_ENGINES: tuple[Callable[[Path, Path], RenderOutcome | None], ...] = (
    _via_wkhtmltopdf,
    _via_weasyprint,
)


def available_engines() -> list[str]:
    """Names of the PDF engines this environment can find (for diagnostics)."""
    found: list[str] = []
    if shutil.which("wkhtmltopdf"):
        found.append("wkhtmltopdf")
    if _weasyprint_command() is not None:
        found.append("weasyprint")
    return found


def render_to_file(
    data: ReportData,
    output_path: Path,
    *,
    include_source: bool = False,
    full_output: bool = False,
) -> RenderOutcome:
    """Render `data` as PDF directly to `output_path`.

    Args:
        data: Complete report data.
        output_path: Where to write the PDF.
        include_source: Defaults to False for PDF specifically -- a full
            source dump becomes an enormous number of paginated PDF
            pages via an HTML-to-PDF converter, which is slow and a
            poor reading experience. Use --format html for a browsable
            full-source report instead.
        full_output: Same reasoning, same default -- uncapped tool
            output and issue lists belong in a scrollable HTML/JSON
            report, not a paginated PDF. Use --format html or
            --format json for the uncapped version.

    Returns:
        RenderOutcome(ok=True) on success. Otherwise ok=False with either
        install guidance (no engine installed) or each installed engine's
        own failure reason -- never raises for a missing or broken
        optional tool, and never leaves a partial file at `output_path`.
    """
    status("Rendering PDF report...")
    html_content = html_renderer.render(
        data, include_source=include_source, full_output=full_output
    )

    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        html_path = Path(tmp) / "report.html"
        html_path.write_text(html_content, encoding="utf-8")

        for attempt in _ENGINES:
            outcome = attempt(html_path, output_path)
            if outcome is None:
                continue
            if outcome.ok:
                return outcome
            failures.append(outcome.detail)
            output_path.unlink(missing_ok=True)

    if failures:
        return RenderOutcome(False, "; ".join(failures))
    return RenderOutcome(False, f"No PDF engine found. {_INSTALL_HINT}")
