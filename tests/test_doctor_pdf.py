"""`--doctor` must find WeasyPrint exactly as `--format pdf` does (see
AGENTS.md section 5.47): a pipx-injected install lives off PATH."""

from __future__ import annotations

from unittest import mock

from sarand.core import doctor

_FIX = "pip install weasyprint"


def _check(engines: list[str], on_path: str | None) -> doctor.DoctorCheck:
    with (
        mock.patch("sarand.renderers.pdf.available_engines", return_value=engines),
        mock.patch.object(doctor.shutil, "which", return_value=on_path),
    ):
        return doctor._tool_check("PDF export", "weasyprint", _FIX, "--format pdf")


def test_weasyprint_off_path_but_in_the_environment_is_reported_present() -> None:
    check = _check(["weasyprint"], on_path=None)
    assert check.ok and check.fix == ""
    assert check.detail == "found in sarand's Python environment"


def test_weasyprint_on_path_is_reported_as_such() -> None:
    check = _check(["weasyprint"], on_path="/usr/bin/weasyprint")
    assert check.ok and check.detail == "found in PATH"


def test_weasyprint_nowhere_is_missing_with_the_fix_text() -> None:
    check = _check([], on_path=None)
    assert not check.ok and check.fix == _FIX
    assert "importable module" in check.detail


def test_other_tools_are_still_probed_on_path_only() -> None:
    with (
        mock.patch(
            "sarand.renderers.pdf.available_engines", return_value=["weasyprint"]
        ),
        mock.patch.object(doctor.shutil, "which", return_value=None),
    ):
        check = doctor._tool_check("PDF export", "wkhtmltopdf", "x", "--format pdf")
    assert not check.ok and check.detail == "not found in PATH"


def test_the_real_weasyprint_row_names_pipx_inject_and_pango() -> None:
    row = next(r for r in doctor._TOOL_CHECKS if r[1] == "weasyprint")
    assert "pip install weasyprint" in row[2]
    assert "pipx inject sarand weasyprint" in row[2]
    assert "Pango" in row[2]
