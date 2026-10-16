"""End-to-end checks of the secret handling wired into cli.run()
(AGENTS.md 5.67): the explicit fixture allowlist and gitleaks-driven
exclusion. The pipeline is the real one; only the slow or external parts
(git, analyzers, the gitleaks/syft binaries, the renderer) are replaced, and
the renderer captures the ReportData it is handed.

Credential-shaped values are assembled at runtime so no realistic token sits
in this file as one literal.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sarand import cli
from sarand.models.results import CommandResult, EnvironmentInfo, GitSnapshot


def _cat(*parts: str) -> str:
    """Join fragments at runtime so no token exists as one source literal."""
    return "".join(parts)


_FAKE_AWS = _cat("AKIA", "ABCDEFGHIJKLMNOP")


async def _no_git(root: Path) -> GitSnapshot:
    return GitSnapshot()


async def _no_results(*args: Any, **kwargs: Any) -> list[CommandResult]:
    return []


def _passed(kind: str) -> Any:
    async def run(root: Path) -> CommandResult:
        return CommandResult(kind=kind, returncode=0, summary="ok")

    return run


def _run_pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    extra_args: list[str],
    gitleaks_output: str = "",
) -> Any:
    project = tmp_path / "project"
    output = tmp_path / "output"
    args = cli.build_parser().parse_args(
        [
            "--project",
            str(project),
            "--output-dir",
            str(output),
            "--skip-tests",
            "--no-health",
            "--no-source",
            *extra_args,
        ]
    )
    config = cli.SarandConfig.from_args(args)

    captured: dict[str, Any] = {}

    def render(
        data: Any, include_source: bool = False, full_output: bool = False
    ) -> str:
        captured["data"] = data
        return "report"

    async def gitleaks(root: Path) -> CommandResult:
        return CommandResult(
            kind="gitleaks", returncode=1, summary="", raw_output=gitleaks_output
        )

    monkeypatch.setattr(cli, "collect_environment_info", lambda root: EnvironmentInfo())
    monkeypatch.setattr(cli, "collect_git_snapshot", _no_git)
    monkeypatch.setattr(cli, "discover_analyzers", list)
    monkeypatch.setattr(cli, "matching_analyzers", lambda root, analyzers: [])
    monkeypatch.setattr(cli, "generate_ai_summary", lambda data: None)
    monkeypatch.setattr(cli, "remove_previous_report", lambda path: None)
    monkeypatch.setattr(cli, "write_sha256", lambda path: "digest")
    monkeypatch.setattr(cli, "run_security_concurrently", _no_results)
    monkeypatch.setattr(cli, "run_component_security", _no_results)
    monkeypatch.setattr(cli, "run_gitleaks", gitleaks)
    monkeypatch.setattr(cli, "run_syft", _passed("syft"))
    monkeypatch.setattr(cli, "run_lockfile_check", _passed("lockfile"))
    monkeypatch.setattr(cli, "_RENDERERS", {"markdown": SimpleNamespace(render=render)})

    assert asyncio.run(cli.run(config)) == 0
    return captured["data"]


def _make_project(tmp_path: Path, sarand_toml: str | None) -> None:
    project = tmp_path / "project"
    (project / "tests").mkdir(parents=True)
    (project / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (project / "leak.py").write_text(f'KEY = "{_FAKE_AWS}"\n', encoding="utf-8")
    (project / "tests" / "test_fx.py").write_text(
        f'KEY = "{_FAKE_AWS}"\n', encoding="utf-8"
    )
    if sarand_toml is not None:
        (project / ".sarand.toml").write_text(sarand_toml, encoding="utf-8")


def _fixture_flags(data: Any) -> dict[str, bool]:
    return {f.path: f.is_test_fixture for f in data.secret_findings}


def test_without_an_allowlist_no_finding_is_a_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_project(tmp_path, None)
    data = _run_pipeline(tmp_path, monkeypatch, [])
    assert _fixture_flags(data) == {"leak.py": False, "tests/test_fx.py": False}


def test_the_allowlist_marks_exactly_the_listed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_project(tmp_path, '[secrets]\nfixture_paths = ["tests/test_fx.py"]\n')
    data = _run_pipeline(tmp_path, monkeypatch, [])
    assert _fixture_flags(data) == {"leak.py": False, "tests/test_fx.py": True}
    # Allow-listed or not, a file with a finding is never embedded.
    assert Path("tests/test_fx.py") not in data.included_files
    assert Path("tests/test_fx.py") in data.excluded_secret_files
    assert Path("leak.py") in data.excluded_secret_files
    assert Path("main.py") in data.included_files
    assert Path("leak.py") not in data.included_files


def test_an_invalid_secrets_table_warns_and_counts_every_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_project(tmp_path, "[secrets]\nbogus = 1\n")
    data = _run_pipeline(tmp_path, monkeypatch, [])
    assert _fixture_flags(data) == {"leak.py": False, "tests/test_fx.py": False}
    captured = capsys.readouterr()
    assert "unknown key" in captured.out + captured.err


def test_gitleaks_flagged_files_are_kept_out_of_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (project / "odd.py").write_text("VALUE = 1\n", encoding="utf-8")
    output = (
        "Finding:     VALUE = REDACTED\n"
        "File:        odd.py\n"
        "Line:        1\n"
        "File:        deleted-long-ago.py\n"
    )
    data = _run_pipeline(tmp_path, monkeypatch, ["--security"], gitleaks_output=output)
    assert data.included_files == [Path("main.py")]
    assert data.excluded_secret_files == [Path("odd.py")]


def test_gitleaks_is_not_consulted_without_the_security_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "odd.py").write_text("VALUE = 1\n", encoding="utf-8")
    data = _run_pipeline(
        tmp_path, monkeypatch, [], gitleaks_output="File:        odd.py\n"
    )
    assert data.included_files == [Path("odd.py")]
    assert data.excluded_secret_files == []
