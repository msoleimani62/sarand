"""Which sarand is running, and is it the one you think? (stale editable
installs and shadowing copies on PATH)."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest
from _helpers import write
from sarand import cli as cli_module
from sarand.core import doctor as doctor_module
from sarand.utils import installation
from sarand.utils.installation import (
    InstallationInfo,
    installation_info,
    other_sarand_executables,
    probe_version,
    stale_note,
)


def _info(*, version: str, source: str | None, editable: bool) -> InstallationInfo:
    return InstallationInfo(version, Path("/pkg/sarand"), editable, source)


def test_an_editable_install_behind_its_source_tree_is_stale() -> None:
    info = _info(version="0.1.5", source="0.5.1", editable=True)

    assert info.stale is True
    note = stale_note(info)
    assert note is not None
    assert "0.1.5" in note and "0.5.1" in note
    assert "maturin develop" in note


@pytest.mark.parametrize(
    "info",
    [
        _info(version="0.5.1", source="0.5.1", editable=True),
        _info(version="0.1.5", source="0.5.1", editable=False),
        _info(version="0.5.1", source=None, editable=True),
    ],
)
def test_everything_else_is_not_stale(info: InstallationInfo) -> None:
    assert info.stale is False
    assert stale_note(info) is None


class _Distribution:
    def __init__(self, direct_url: str | None) -> None:
        self._direct_url = direct_url

    def read_text(self, name: str) -> str | None:
        return self._direct_url if name == "direct_url.json" else None


def test_direct_url_json_marks_editable_installs() -> None:
    editable = _Distribution('{"url": "file:///x", "dir_info": {"editable": true}}')
    regular = _Distribution('{"url": "file:///x", "dir_info": {}}')

    assert installation._direct_url_says_editable(editable) is True  # type: ignore[arg-type]
    assert installation._direct_url_says_editable(regular) is False  # type: ignore[arg-type]
    assert installation._direct_url_says_editable(_Distribution(None)) is False  # type: ignore[arg-type]
    assert installation._direct_url_says_editable(_Distribution("not json")) is False  # type: ignore[arg-type]


def test_the_source_tree_version_is_read_from_pyproject() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(
            root / "pyproject.toml",
            '[build-system]\nrequires = ["maturin"]\n\n[project]\n'
            'name = "sarand"\nversion = "0.5.1"\n\n[tool.other]\nversion = "9"\n',
        )
        package_dir = root / "python" / "sarand"
        package_dir.mkdir(parents=True)

        pyproject = installation._source_pyproject(package_dir)

        assert pyproject == root / "pyproject.toml"
        match = installation._VERSION_IN_PYPROJECT.search(
            pyproject.read_text(encoding="utf-8")
        )
        assert match is not None and match.group(1) == "0.5.1"


def test_a_pyproject_of_another_project_is_not_a_source_checkout() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pyproject.toml", '[project]\nname = "something-else"\n')
        (root / "python" / "sarand").mkdir(parents=True)

        assert installation._source_pyproject(root / "python" / "sarand") is None


def test_the_running_installation_can_describe_itself() -> None:
    info = installation_info()

    assert info.package_dir.is_dir()
    assert info.version


def _executable(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "sarand"
    path.write_bytes(b"#!/bin/sh\n")
    return path


def test_other_installations_on_path_are_found_but_not_the_running_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        own = root / "own" / "bin"
        other = root / "other" / "bin"
        _executable(own)
        stale = _executable(other)
        monkeypatch.setattr(installation, "_own_script_dirs", lambda: {own.resolve()})
        monkeypatch.setenv(
            "PATH", os.pathsep.join([str(own), str(other), str(other), "", str(root)])
        )

        assert other_sarand_executables() == [stale.resolve()]


@pytest.mark.skipif(
    sys.platform == "win32", reason="symlinks need privileges on Windows"
)
def test_a_symlink_into_the_running_installation_is_the_same_installation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pipx puts `~/.local/bin/sarand` as a link into its own venv."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        real = _executable(root / "venv" / "bin")
        link_dir = root / "local" / "bin"
        link_dir.mkdir(parents=True)
        (link_dir / "sarand").symlink_to(real)
        monkeypatch.setattr(
            installation, "_own_script_dirs", lambda: {real.parent.resolve()}
        )
        monkeypatch.setenv("PATH", str(link_dir))

        assert other_sarand_executables() == []


def test_probe_version_reads_the_first_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        installation, "run_cmd", lambda cmd, cwd, timeout: (0, "sarand 0.1.5\n", 0.1)
    )
    assert probe_version(Path("/x/sarand")) == "0.1.5"

    monkeypatch.setattr(
        installation, "run_cmd", lambda cmd, cwd, timeout: (1, "boom", 0.1)
    )
    assert probe_version(Path("/x/sarand")) is None

    monkeypatch.setattr(
        installation, "run_cmd", lambda cmd, cwd, timeout: (0, "usage: other", 0.1)
    )
    assert probe_version(Path("/x/sarand")) is None


def test_version_flag_prints_the_version_and_explains_a_stale_copy(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        cli_module,
        "installation_info",
        lambda: _info(version="0.1.5", source="0.5.1", editable=True),
    )

    with pytest.raises(SystemExit) as exit_info:
        cli_module.build_parser().parse_args(["--version"])

    captured = capsys.readouterr()
    assert exit_info.value.code == 0
    assert captured.out == "sarand 0.1.5\n"
    assert "0.5.1" in captured.err


def test_version_flag_is_silent_about_a_healthy_install(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        cli_module,
        "installation_info",
        lambda: _info(version="0.5.1", source="0.5.1", editable=True),
    )

    with pytest.raises(SystemExit):
        cli_module.build_parser().parse_args(["--version"])

    captured = capsys.readouterr()
    assert captured.out == "sarand 0.5.1\n"
    assert captured.err == ""


def test_doctor_reports_the_running_installation_and_a_shadowing_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        doctor_module,
        "installation_info",
        lambda: _info(version="0.1.5", source="0.5.1", editable=True),
    )
    monkeypatch.setattr(
        doctor_module,
        "other_sarand_executables",
        lambda: [Path("/home/u/.local/bin/sarand")],
    )
    monkeypatch.setattr(doctor_module, "probe_version", lambda path: "0.5.1")

    checks = {c.name: c for c in doctor_module.collect_checks() if c.category == "Core"}

    installation_check = checks["Installation"]
    assert installation_check.ok is False
    assert "sarand 0.1.5" in installation_check.detail
    assert "(editable install)" in installation_check.detail
    assert "maturin develop" in installation_check.fix
    other = checks["Other sarand on PATH"]
    assert other.ok is False and other.critical is False
    assert "sarand 0.5.1" in other.detail
    assert "which -a sarand" in other.fix


def test_doctor_is_quiet_about_a_single_healthy_installation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        doctor_module,
        "installation_info",
        lambda: _info(version="0.5.1", source="0.5.1", editable=False),
    )
    monkeypatch.setattr(doctor_module, "other_sarand_executables", list)

    checks = {c.name: c for c in doctor_module.collect_checks() if c.category == "Core"}

    assert checks["Installation"].ok is True
    assert "Other sarand on PATH" not in checks
