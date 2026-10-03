"""Regression tests for backlog item 15 (PDF and report portability) --
see AGENTS.md section 5.46 and `renderers/pdf.py`'s module docstring.

Every test here is hermetic: the "engine" is a tiny fake `weasyprint`
package written to a temporary directory and put on `sys.path` and
`PYTHONPATH`, so the whole path (discovery, argv, subprocess, output
checks, fallback) runs on every OS without wkhtmltopdf, WeasyPrint or
Pango installed. The tests that need a REAL engine stay in
test_new_renderers.py and skip visibly when none is installed.
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from _golden_fixtures import FIXTURES
from sarand import cli
from sarand.models.results import ReportData
from sarand.renderers import pdf
from sarand.renderers.pdf import RenderOutcome

_FAKE_MAIN = """\
import sys, time
from pathlib import Path

mode = Path(__file__).with_name("mode.txt").read_text().strip()
html, out = Path(sys.argv[1]), Path(sys.argv[2])
if mode == "ok":
    out.write_bytes(b"%PDF-1.7\\n% html bytes: " + str(len(html.read_bytes())).encode())
elif mode == "crash":
    sys.stderr.write("OSError: cannot load library 'libpango-1.0-0'")
    sys.exit(1)
elif mode == "junk":
    out.write_bytes(b"<html>not a pdf</html>")
elif mode == "sleep":
    time.sleep(30)
"""


@contextmanager
def engine(mode: str) -> Iterator[Path]:
    """A fake `weasyprint` package that behaves according to `mode`, run
    through the real interpreter (`python -m weasyprint`) exactly like
    the module fallback of the real discovery code."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        package = base / "weasyprint"
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "__main__.py").write_text(_FAKE_MAIN, encoding="utf-8")
        (package / "mode.txt").write_text(mode, encoding="utf-8")
        env = {"PYTHONPATH": str(base) + os.pathsep + os.environ.get("PYTHONPATH", "")}
        with (
            mock.patch.dict(os.environ, env),
            mock.patch.object(pdf.shutil, "which", return_value=None),
            mock.patch.object(
                pdf,
                "_weasyprint_command",
                return_value=[sys.executable, "-m", "weasyprint"],
            ),
        ):
            yield base


def _data(root: Path) -> ReportData:
    return FIXTURES["minimal"](root)


def _render(mode: str) -> tuple[RenderOutcome, bool]:
    """(outcome, whether a file was left at the output path)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out = root / "report.pdf"
        with engine(mode):
            outcome = pdf.render_to_file(_data(root), out)
        return outcome, out.exists()


def test_a_working_engine_produces_a_real_pdf_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out = root / "report.pdf"
        with engine("ok"):
            outcome = pdf.render_to_file(_data(root), out)
        assert outcome == RenderOutcome(True, "rendered via weasyprint")
        assert out.read_bytes().startswith(b"%PDF-")


def test_no_engine_installed_says_so_with_install_guidance() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        with (
            mock.patch.object(pdf.shutil, "which", return_value=None),
            mock.patch.object(pdf, "_weasyprint_command", return_value=None),
        ):
            outcome = pdf.render_to_file(_data(root), root / "r.pdf")
        assert not outcome.ok
        assert "No PDF engine found" in outcome.detail
        assert "pipx inject sarand weasyprint" in outcome.detail
        assert "--format html" in outcome.detail
        assert not (root / "r.pdf").exists()


def test_a_crashing_engine_reports_its_own_error_not_no_engine_found() -> None:
    outcome, left_behind = _render("crash")
    assert not outcome.ok and not left_behind
    assert "weasyprint failed" in outcome.detail
    assert "cannot load library" in outcome.detail
    assert "Pango system library" in outcome.detail
    assert "No PDF engine found" not in outcome.detail


def test_an_engine_that_writes_a_non_pdf_is_a_failure_and_leaves_no_file() -> None:
    outcome, left_behind = _render("junk")
    assert not outcome.ok and not left_behind
    assert "not a PDF" in outcome.detail


def test_an_engine_that_exits_zero_without_writing_is_a_failure() -> None:
    outcome, left_behind = _render("silent")
    assert not outcome.ok and not left_behind
    assert "weasyprint failed" in outcome.detail


def test_an_engine_that_hangs_is_stopped_with_a_clear_message() -> None:
    with mock.patch.object(pdf, "_TIMEOUT_SECONDS", 1):
        outcome, left_behind = _render("sleep")
    assert not outcome.ok and not left_behind
    assert "timed out after 1s" in outcome.detail


def test_the_next_engine_is_tried_when_the_first_fails() -> None:
    calls: list[str] = []

    def broken(html: Path, out: Path) -> RenderOutcome | None:
        calls.append("first")
        return RenderOutcome(False, "first failed: boom")

    def works(html: Path, out: Path) -> RenderOutcome | None:
        calls.append("second")
        out.write_bytes(b"%PDF-1.4")
        return RenderOutcome(True, "rendered via second")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        with mock.patch.object(pdf, "_ENGINES", (broken, works)):
            outcome = pdf.render_to_file(_data(root), root / "r.pdf")
        assert outcome.ok and calls == ["first", "second"]


def test_every_failing_engine_is_named_in_the_final_message() -> None:
    def one(html: Path, out: Path) -> RenderOutcome | None:
        return RenderOutcome(False, "wkhtmltopdf failed: no display")

    def two(html: Path, out: Path) -> RenderOutcome | None:
        return RenderOutcome(False, "weasyprint failed: no pango")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        with mock.patch.object(pdf, "_ENGINES", (one, two)):
            outcome = pdf.render_to_file(_data(root), root / "r.pdf")
        assert not outcome.ok
        assert "wkhtmltopdf failed: no display" in outcome.detail
        assert "weasyprint failed: no pango" in outcome.detail


def test_weasyprint_is_found_on_path_then_beside_python_then_as_a_module() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scripts = Path(tmp)
        (scripts / "weasyprint").write_text("#!/bin/sh\n", encoding="utf-8")
        fake_python = str(scripts / "python")

        with mock.patch.object(pdf.shutil, "which", return_value="/usr/bin/weasyprint"):
            assert pdf._weasyprint_command() == ["/usr/bin/weasyprint"]

        with (
            mock.patch.object(pdf.shutil, "which", return_value=None),
            mock.patch.object(pdf.sys, "executable", fake_python),
        ):
            assert pdf._weasyprint_command() == [str(scripts / "weasyprint")]

        (scripts / "weasyprint").unlink()
        with (
            mock.patch.object(pdf.shutil, "which", return_value=None),
            mock.patch.object(pdf.sys, "executable", fake_python),
            mock.patch.object(pdf.importlib.util, "find_spec", return_value=object()),
        ):
            assert pdf._weasyprint_command() == [fake_python, "-m", "weasyprint"]

        with (
            mock.patch.object(pdf.shutil, "which", return_value=None),
            mock.patch.object(pdf.sys, "executable", fake_python),
            mock.patch.object(pdf.importlib.util, "find_spec", return_value=None),
        ):
            assert pdf._weasyprint_command() is None


def test_available_engines_lists_what_can_be_found() -> None:
    with (
        mock.patch.object(pdf.shutil, "which", return_value=None),
        mock.patch.object(pdf, "_weasyprint_command", return_value=None),
    ):
        assert pdf.available_engines() == []
    with (
        mock.patch.object(pdf.shutil, "which", return_value="/usr/bin/wkhtmltopdf"),
        mock.patch.object(pdf, "_weasyprint_command", return_value=["w"]),
    ):
        assert pdf.available_engines() == ["wkhtmltopdf", "weasyprint"]


def test_pdf_failure_keeps_the_full_report_as_markdown_and_exits_nonzero() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        project = base / "proj"
        project.mkdir()
        (project / "app.py").write_text("print('hi')\n", encoding="utf-8")
        reports = base / "reports"
        reports.mkdir()
        failure = RenderOutcome(False, "weasyprint failed: no pango")
        with mock.patch.object(pdf, "render_to_file", return_value=failure):
            code = cli.main(
                [
                    "-p",
                    str(project),
                    "-d",
                    str(reports),
                    "--skip-tests",
                    "--format",
                    "pdf",
                    "-o",
                    "report.pdf",
                ]
            )
        assert code == 1
        assert not (reports / "report.pdf").exists()
        fallback = reports / "report.md"
        assert fallback.is_file()
        text = fallback.read_text(encoding="utf-8")
        assert "## Quick Context" in text and "app.py" in text
        assert any(
            p.name.startswith("report.md") and p.suffix == ".sha256"
            for p in reports.iterdir()
        )


def test_pdf_success_still_returns_zero_and_writes_only_the_pdf() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        project = base / "proj"
        project.mkdir()
        (project / "app.py").write_text("print('hi')\n", encoding="utf-8")
        reports = base / "reports"
        reports.mkdir()

        def fake_render(
            data: ReportData, output_path: Path, **kwargs: object
        ) -> RenderOutcome:
            output_path.write_bytes(b"%PDF-1.7 fake")
            return RenderOutcome(True, "rendered via fake")

        with mock.patch.object(pdf, "render_to_file", side_effect=fake_render):
            code = cli.main(
                [
                    "-p",
                    str(project),
                    "-d",
                    str(reports),
                    "--skip-tests",
                    "--format",
                    "pdf",
                    "-o",
                    "report.pdf",
                ]
            )
        assert code == 0
        assert (reports / "report.pdf").read_bytes().startswith(b"%PDF-")
        assert not (reports / "report.md").exists()
