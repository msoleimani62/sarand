"""Tests for sarand.renderers -- given a fixed ReportData, check each
renderer's output contains the expected content and is well-formed."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path

from sarand.core.health import compute_health_score
from sarand.models.results import (
    CommandResult,
    EnvironmentInfo,
    GitSnapshot,
    ProjectDetection,
    ProjectStats,
    ReportData,
)
from sarand.renderers import json_renderer, markdown, text

from _helpers import write


def _fixture_data(root: Path) -> ReportData:
    write(root / "main.py", "print('hi')\n")
    detection = ProjectDetection(
        languages=["Python"],
        primary_language="Python",
        project_type="package",
        build_system="pip/poetry/uv",
        markers_found=["pyproject.toml"],
        entry_points=["main.py"],
    )
    data = ReportData(
        project_root=root,
        generated_at=datetime(2026, 1, 1, 12, 0, 0),
        environment=EnvironmentInfo(python="Python 3.13.0"),
        git=GitSnapshot(branch="main", commit="abc123"),
        stats=ProjectStats(total_files=1, total_loc=1, files_by_extension={".py": 1}),
        detection=detection,
        used_rust_core=False,
        test_results=[CommandResult(kind="pytest", returncode=0, summary="1 passed")],
        tree_text=f"{root.name}/\n└── main.py",
        included_files=[Path("main.py")],
    )
    data.health = compute_health_score(data)
    return data


def test_markdown_renderer_contains_key_sections() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = _fixture_data(Path(tmp))
        output = markdown.render(data, include_source=True)

        assert "# sarand report" in output
        assert "## Detected Project" in output
        assert "Python" in output
        assert "## Health Score" in output
        assert "## Test results" in output
        assert "pytest" in output
        assert "### FILE: `main.py`" in output
        assert "print('hi')" in output


def test_markdown_renderer_respects_include_source_false() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = _fixture_data(Path(tmp))
        output = markdown.render(data, include_source=False)
        assert "### FILE:" not in output


def test_json_renderer_produces_valid_round_trippable_json() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = _fixture_data(Path(tmp))
        output = json_renderer.render(data)

        parsed = json.loads(output)  # must not raise
        assert parsed["detection"]["primary_language"] == "Python"
        assert parsed["stats"]["total_files"] == 1
        assert parsed["health"]["grade"] in {"A", "B", "C", "D", "F"}


def test_text_renderer_is_short_and_contains_essentials() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = _fixture_data(Path(tmp))
        output = text.render(data)

        assert "Detected: Python" in output
        assert "Health:" in output
        assert len(output.splitlines()) < 20  # stays a summary, not a dump


def test_markdown_renderer_shows_excluded_secrets_and_findings() -> None:
    from sarand.models.results import SecretFinding

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        data = _fixture_data(root)
        data.excluded_secret_files = [Path(".env")]
        data.secret_findings = [SecretFinding(path="main.py", line_number=2, pattern_name="AWS Access Key ID")]

        output = markdown.render(data, include_source=False)

        assert "Excluded (credential-shaped filenames" in output
        assert "`.env`" in output
        assert "Potential hardcoded secrets detected" in output
        assert "AWS Access Key ID" in output
        # The finding must never contain an actual key-shaped value.
        assert "AKIA" not in output
