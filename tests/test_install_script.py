"""install.sh must never leave the user without sarand.

The script used to uninstall the old copy first and build afterwards, so a
network hiccup during the build (it downloads maturin and the dependencies)
left no `sarand` at all. These tests run the real script against a fake
`pipx` whose build can be made to fail, and check that the previous
installation is only replaced by a *successful* build.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "install.sh"

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or not _SCRIPT.is_file(),
    reason="install.sh is a POSIX shell script",
)

_FAKE_PIPX = """#!/usr/bin/env bash
# Fake pipx: `install` fails the first $FAKE_FAILS times, then "builds" a venv.
if [ "$1" = "install" ]; then
    n=$(cat "$FAKE_STATE" 2>/dev/null || echo 0)
    n=$((n + 1))
    echo "$n" > "$FAKE_STATE"
    if [ "$n" -le "${FAKE_FAILS:-0}" ]; then
        echo "simulated build failure" >&2
        exit 1
    fi
    mkdir -p "$PIPX_HOME/venvs/sarand"
    echo new > "$PIPX_HOME/venvs/sarand/marker"
    if [ -n "${PIPX_BIN_DIR:-}" ]; then
        mkdir -p "$PIPX_BIN_DIR"
        printf '#!/bin/sh\necho "sarand 9.9.9"\n' > "$PIPX_BIN_DIR/sarand"
        chmod +x "$PIPX_BIN_DIR/sarand"
    fi
fi
exit 0
"""


def _run(root: Path, *, fails: int, previous: bool, attempts: int = 3):
    home = root / "home"
    pipx_home = root / "pipx"
    bin_dir = root / "bin"
    for directory in (home, pipx_home, bin_dir):
        directory.mkdir()
    (bin_dir / "pipx").write_bytes(_FAKE_PIPX.encode("utf-8"))
    (bin_dir / "pipx").chmod(0o755)
    venv = pipx_home / "venvs" / "sarand"
    if previous:
        venv.mkdir(parents=True)
        (venv / "marker").write_bytes(b"old")

    env = {
        **os.environ,
        "HOME": str(home),
        "PIPX_HOME": str(pipx_home),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "FAKE_STATE": str(root / "attempts"),
        "FAKE_FAILS": str(fails),
        "SARAND_INSTALL_ATTEMPTS": str(attempts),
        "SARAND_INSTALL_RETRY_DELAY": "0",
    }
    result = subprocess.run(
        ["bash", str(_SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    marker = venv / "marker"
    marker_text = (
        marker.read_bytes().decode("utf-8").strip() if marker.is_file() else None
    )
    backup = pipx_home / ".sarand-previous-venv"
    return result, marker_text, backup.exists()


def test_a_successful_build_replaces_the_previous_installation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result, marker, backup_left = _run(Path(tmp), fails=0, previous=True)

    assert result.returncode == 0, result.stderr
    assert marker == "new"
    assert backup_left is False


def test_a_failed_build_restores_the_previous_installation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result, marker, backup_left = _run(Path(tmp), fails=99, previous=True)

    assert result.returncode != 0
    assert marker == "old"  # exactly what was there before
    assert backup_left is False
    assert "restored" in result.stderr


def test_a_transient_failure_is_retried_and_then_succeeds() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result, marker, _ = _run(Path(tmp), fails=1, previous=True, attempts=3)

    assert result.returncode == 0, result.stderr
    assert marker == "new"
    assert "retrying" in result.stdout


def test_a_first_install_that_fails_leaves_nothing_behind() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result, marker, backup_left = _run(Path(tmp), fails=99, previous=False)

    assert result.returncode != 0
    assert marker is None
    assert backup_left is False


def test_the_old_installation_is_never_removed_before_the_build_starts() -> None:
    lines = _SCRIPT.read_text(encoding="utf-8").splitlines()
    commands = [line for line in lines if not line.lstrip().startswith("#")]

    assert not any("pipx uninstall" in line for line in commands)


def _run_snippet(root: Path, snippet: str, *, previous: bool = True):
    """Source install.sh (functions only, nothing installed) and run `snippet`."""
    pipx_home = root / "pipx"
    venv = pipx_home / "venvs" / "sarand"
    if previous:
        venv.mkdir(parents=True)
        (venv / "marker").write_bytes(b"old")
    env = {
        **os.environ,
        "HOME": str(root),
        "PIPX_HOME": str(pipx_home),
        "SARAND_INSTALL_SOURCE_ONLY": "1",
        "SCRIPT": str(_SCRIPT),
    }
    result = subprocess.run(
        ["bash", "-c", f'. "$SCRIPT"; {snippet}'],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    marker = venv / "marker"
    marker_text = (
        marker.read_bytes().decode("utf-8").strip() if marker.is_file() else None
    )
    backup_left = (pipx_home / ".sarand-previous-venv").exists()
    return result, marker_text, backup_left, venv.exists()


def test_an_interrupt_after_the_old_install_was_set_aside_restores_it() -> None:
    snippet = 'mv "$PIPX_VENV_DIR" "$BACKUP_DIR"; STATE=aside; interrupted'
    with tempfile.TemporaryDirectory() as tmp:
        result, marker, backup_left, _ = _run_snippet(Path(tmp), snippet)

    assert result.returncode == 130
    assert marker == "old"
    assert backup_left is False


def test_an_interrupt_before_anything_changed_never_touches_an_existing_install() -> (
    None
):
    """The dangerous case: the trap fires before the old install has been set
    aside, and must not delete it."""
    with tempfile.TemporaryDirectory() as tmp:
        result, marker, backup_left, _ = _run_snippet(Path(tmp), "interrupted")

    assert result.returncode == 130
    assert marker == "old"
    assert backup_left is False


def test_an_interrupt_during_a_first_install_removes_the_partial_venv() -> None:
    snippet = 'mkdir -p "$PIPX_VENV_DIR"; STATE=fresh; interrupted'
    with tempfile.TemporaryDirectory() as tmp:
        result, _, _, venv_exists = _run_snippet(Path(tmp), snippet, previous=False)

    assert result.returncode == 130
    assert venv_exists is False


def test_the_interrupt_trap_is_installed_around_the_build() -> None:
    text = _SCRIPT.read_text(encoding="utf-8")

    assert "trap interrupted INT TERM" in text
    assert "trap - INT TERM" in text


def _run_verifying(root: Path, *, shadow: bool):
    """Successful install with PIPX_BIN_DIR set; optionally a stale `sarand`
    earlier on PATH (like a development virtualenv)."""
    home, pipx_home = root / "home", root / "pipx"
    bin_dir, pipx_bin, stale_bin = root / "bin", root / "pipxbin", root / "stalebin"
    for directory in (home, pipx_home, bin_dir, stale_bin):
        directory.mkdir()
    (bin_dir / "pipx").write_bytes(_FAKE_PIPX.encode("utf-8"))
    (bin_dir / "pipx").chmod(0o755)
    (stale_bin / "sarand").write_bytes(b'#!/bin/sh\necho "sarand 0.1.5"\n')
    (stale_bin / "sarand").chmod(0o755)
    path_parts = [str(pipx_bin), str(bin_dir), os.environ["PATH"]]
    if shadow:
        path_parts.insert(0, str(stale_bin))
    env = {
        **os.environ,
        "HOME": str(home),
        "PIPX_HOME": str(pipx_home),
        "PIPX_BIN_DIR": str(pipx_bin),
        "PATH": os.pathsep.join(path_parts),
        "FAKE_STATE": str(root / "attempts"),
        "SARAND_INSTALL_RETRY_DELAY": "0",
    }
    return subprocess.run(
        ["bash", str(_SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )


def test_the_installed_version_is_reported_from_the_pipx_copy() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = _run_verifying(Path(tmp), shadow=False)

    assert result.returncode == 0, result.stderr
    assert "Installed: sarand 9.9.9" in result.stdout
    assert "WARNING" not in result.stdout


def test_a_shadowing_copy_on_path_is_named_with_its_version() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = _run_verifying(Path(tmp), shadow=True)

    assert result.returncode == 0, result.stderr
    assert "Installed: sarand 9.9.9" in result.stdout
    assert "another 'sarand' comes first on PATH" in result.stdout
    assert "sarand 0.1.5" in result.stdout
    assert "stalebin" in result.stdout
