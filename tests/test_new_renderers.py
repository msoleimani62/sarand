"""Tests for the Phase D renderers: html, sarif, pdf."""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from sarand.core.health import compute_health_score
from sarand.models.results import (
    CommandResult,
    EnvironmentInfo,
    GitSnapshot,
    Issue,
    ProjectDetection,
    ProjectStats,
    ReportData,
    SecretFinding,
    TodoItem,
)
from sarand.renderers import html, sarif

from _helpers import write


def _fixture_data(root: Path) -> ReportData:
    write(root / "main.py", "print('hi')  # TODO: remove debug print\n")
    detection = ProjectDetection(
        languages=["Python"],
        primary_language="Python",
        project_type="package",
        build_system="pip/poetry/uv",
        markers_found=["pyproject.toml"],
        entry_points=["main.py"],
    )
    bad_result = CommandResult(
        kind="ruff check",
        returncode=1,
        summary="1 error",
        errors=[Issue(source="ruff check", message="F401 unused import", severity="error")],
    )
    data = ReportData(
        project_root=root,
        generated_at=datetime(2026, 1, 1, 12, 0, 0),
        environment=EnvironmentInfo(python="Python 3.13.0", hostname="test-host"),
        git=GitSnapshot(branch="main", commit="abc123"),
        stats=ProjectStats(total_files=1, total_loc=1, files_by_extension={".py": 1}),
        detection=detection,
        used_rust_core=False,
        test_results=[CommandResult(kind="pytest", returncode=0, summary="1 passed")],
        quality_results=[bad_result],
        tree_text=f"{root.name}/\n└── main.py",
        included_files=[Path("main.py")],
        excluded_secret_files=[Path(".env")],
        secret_findings=[SecretFinding(path="main.py", line_number=1, pattern_name="AWS Access Key ID")],
        todos=[TodoItem(path="main.py", line_number=1, kind="TODO", content="remove debug print")],
    )
    data.health = compute_health_score(data)
    return data


def test_html_renderer_produces_valid_wrapped_document() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = _fixture_data(Path(tmp))
        output = html.render(data, include_source=True)

        assert output.startswith("<!DOCTYPE html>")
        assert "</html>" in output
        assert "sarand report" in output
        assert "Python" in output
        assert "ruff check" in output


def test_html_renderer_escapes_content_properly() -> None:
    """A file containing HTML-special characters must not break out of
    its <pre> block or inject markup."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "evil.py", "x = '<script>alert(1)</script>'\n")
        data = _fixture_data(root)
        data.included_files = [Path("evil.py")]

        output = html.render(data, include_source=True)

        assert "<script>alert(1)</script>" not in output
        assert "&lt;script&gt;" in output


def test_html_renderer_shows_secrets_section() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = _fixture_data(Path(tmp))
        output = html.render(data, include_source=False)

        assert "Secrets" in output
        assert ".env" in output
        assert "AWS Access Key ID" in output


def test_sarif_renderer_produces_valid_json_with_expected_schema() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = _fixture_data(Path(tmp))
        output = sarif.render(data)

        parsed = json.loads(output)
        assert parsed["version"] == "2.1.0"
        assert "$schema" in parsed
        assert len(parsed["runs"]) == 1
        assert parsed["runs"][0]["tool"]["driver"]["name"] == "sarand"


def test_sarif_renderer_includes_secret_finding_as_error_with_location() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = _fixture_data(Path(tmp))
        parsed = json.loads(sarif.render(data))

        results = parsed["runs"][0]["results"]
        secret_results = [r for r in results if r["ruleId"].startswith("secret-detection/")]
        assert len(secret_results) == 1
        assert secret_results[0]["level"] == "error"
        assert secret_results[0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "main.py"
        assert secret_results[0]["locations"][0]["physicalLocation"]["region"]["startLine"] == 1


def test_sarif_renderer_includes_todo_as_note() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = _fixture_data(Path(tmp))
        parsed = json.loads(sarif.render(data))

        todo_results = [r for r in parsed["runs"][0]["results"] if r["ruleId"].startswith("todo/")]
        assert len(todo_results) == 1
        assert todo_results[0]["level"] == "note"


def test_sarif_renderer_includes_unlocated_quality_issue() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = _fixture_data(Path(tmp))
        parsed = json.loads(sarif.render(data))

        tool_results = [r for r in parsed["runs"][0]["results"] if r["ruleId"].startswith("tool-output/")]
        assert len(tool_results) == 1
        assert "locations" not in tool_results[0]
        assert tool_results[0]["level"] == "error"


def test_sarif_renderer_declares_every_used_rule() -> None:
    """Every ruleId referenced by a result must appear in the tool's
    declared rules list -- otherwise the SARIF file is technically
    incomplete for strict consumers."""
    with tempfile.TemporaryDirectory() as tmp:
        data = _fixture_data(Path(tmp))
        parsed = json.loads(sarif.render(data))

        declared = {r["id"] for r in parsed["runs"][0]["tool"]["driver"]["rules"]}
        used = {r["ruleId"] for r in parsed["runs"][0]["results"]}
        assert used.issubset(declared)


def test_pdf_renderer_reports_a_clear_fix_when_no_engine_installed() -> None:
    """If neither wkhtmltopdf nor weasyprint is on PATH, must fail with
    an actionable message, never a crash."""
    if shutil.which("wkhtmltopdf") or shutil.which("weasyprint"):
        return  # this sandbox happens to have one -- covered by the next test
    from sarand.renderers import pdf

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        data = _fixture_data(root)
        output_path = root / "report.pdf"

        outcome = pdf.render_to_file(data, output_path)

        assert outcome.ok is False
        assert "wkhtmltopdf" in outcome.detail or "weasyprint" in outcome.detail
        assert not output_path.exists()


def test_pdf_renderer_produces_a_real_pdf_when_engine_available() -> None:
    """When an engine IS installed, confirm real bytes come out --
    not just that the subprocess call didn't crash."""
    if not (shutil.which("wkhtmltopdf") or shutil.which("weasyprint")):
        return  # covered by the test above instead
    from sarand.renderers import pdf

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        data = _fixture_data(root)
        output_path = root / "report.pdf"

        outcome = pdf.render_to_file(data, output_path)

        assert outcome.ok is True
        assert output_path.exists()
        assert output_path.read_bytes()[:5] == b"%PDF-"
        assert output_path.stat().st_size > 500  # not a truncated/empty file
