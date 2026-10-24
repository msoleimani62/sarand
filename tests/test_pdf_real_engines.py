"""Real PDF engines in CI (backlog item 12, round R10d).

Every other PDF test uses a fake engine. These two run the real thing, but only
for the engines named in SARAND_REAL_PDF_ENGINES (the CI job `pdf` sets it); a
normal `pytest` skips them visibly.

موتورهای واقعی PDF؛ فقط برای موتورهایی که در SARAND_REAL_PDF_ENGINES نام برده شده
اجرا می‌شوند (job به نام pdf در CI آن را می‌گذارد) و در اجرای عادی pytest رد می‌شوند.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from _golden_fixtures import FIXTURES
from sarand.renderers import html as html_renderer
from sarand.renderers import pdf
from sarand.renderers.pdf import RenderOutcome

_VIA: dict[str, Callable[[Path, Path], RenderOutcome | None]] = {
    "wkhtmltopdf": pdf._via_wkhtmltopdf,
    "weasyprint": pdf._via_weasyprint,
}
_CI = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"


def _wanted() -> list[str]:
    raw = os.environ.get("SARAND_REAL_PDF_ENGINES", "")
    names = [name.strip() for name in raw.split(",") if name.strip()]
    if not names:
        pytest.skip("SARAND_REAL_PDF_ENGINES is not set; see the CI job `pdf`")
    unknown = [name for name in names if name not in _VIA]
    assert unknown == [], f"unknown engine name(s): {unknown}"
    return names


def test_the_engines_that_were_asked_for_are_installed() -> None:
    for name in _wanted():
        assert name in pdf.available_engines(), f"{name} is not installed"


def test_each_requested_engine_renders_a_real_pdf() -> None:
    for name in _wanted():
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            page = root / "report.html"
            out = root / "report.pdf"
            page.write_text(
                html_renderer.render(
                    FIXTURES["minimal"](root), include_source=False, full_output=False
                ),
                encoding="utf-8",
            )
            outcome = _VIA[name](page, out)
            assert outcome is not None, f"{name} was not found"
            assert outcome.ok, f"{name}: {outcome.detail}"
            assert out.read_bytes()[:5] == b"%PDF-"
            assert out.stat().st_size > 500


def test_ci_has_a_pdf_job_where_only_wkhtmltopdf_may_fail() -> None:
    steps = yaml.safe_load(_CI.read_text(encoding="utf-8"))["jobs"]["pdf"]["steps"]
    engines = {
        str(step.get("env", {}).get("SARAND_REAL_PDF_ENGINES", "")): step
        for step in steps
        if "SARAND_REAL_PDF_ENGINES" in step.get("env", {})
    }
    assert engines["weasyprint"].get("continue-on-error") is not True
    assert engines["wkhtmltopdf"].get("continue-on-error") is True
