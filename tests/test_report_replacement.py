"""Atomic report replacement and checksum consistency tests."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from sarand import cli


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _checksum_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".sha256")


def test_success_replaces_report_and_checksum_as_a_consistent_pair(
    tmp_path: Path,
) -> None:
    output = tmp_path / "report.md"
    checksum = _checksum_path(output)
    _write(output, "old report")
    _write(checksum, "old checksum")

    digest = cli.atomic_write_report(
        output, lambda staged: _write(staged, "new report")
    )

    assert output.read_text(encoding="utf-8") == "new report"
    assert digest == hashlib.sha256(b"new report").hexdigest()
    assert checksum.read_text(encoding="utf-8") == f"{digest}  report.md\n"
    assert not list(tmp_path.glob(".report.md.*"))


def test_renderer_failure_preserves_the_previous_report_and_checksum(
    tmp_path: Path,
) -> None:
    output = tmp_path / "report.md"
    checksum = _checksum_path(output)
    _write(output, "old report")
    _write(checksum, "old checksum")

    def fail(staged: Path) -> None:
        _write(staged, "partial output")
        raise RuntimeError("renderer failed")

    with pytest.raises(RuntimeError, match="renderer failed"):
        cli.atomic_write_report(output, fail)

    assert output.read_text(encoding="utf-8") == "old report"
    assert checksum.read_text(encoding="utf-8") == "old checksum"
    assert not list(tmp_path.glob(".report.md.*"))


def test_checksum_replace_failure_rolls_back_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "report.md"
    checksum = _checksum_path(output)
    _write(output, "old report")
    _write(checksum, "old checksum")

    real_replace = os.replace
    calls = 0

    def fail_second_replace(
        source: os.PathLike[str], destination: os.PathLike[str]
    ) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated checksum commit failure")
        real_replace(source, destination)

    monkeypatch.setattr(cli.os, "replace", fail_second_replace)

    with pytest.raises(OSError, match="simulated checksum commit failure"):
        cli.atomic_write_report(output, lambda staged: _write(staged, "new report"))

    assert output.read_text(encoding="utf-8") == "old report"
    assert checksum.read_text(encoding="utf-8") == "old checksum"
    assert not list(tmp_path.glob(".report.md.*"))


def test_failed_first_write_does_not_create_a_report_or_checksum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "report.md"

    def fail(staged: Path) -> None:
        raise OSError("simulated staging failure")

    with pytest.raises(OSError, match="simulated staging failure"):
        cli.atomic_write_report(output, fail)

    assert not output.exists()
    assert not _checksum_path(output).exists()
    assert not list(tmp_path.iterdir())


def test_announcement_does_not_delete_the_previous_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "report.md"
    _write(output, "keep until commit")
    messages: list[str] = []
    monkeypatch.setattr(cli, "status", messages.append)

    cli.announce_report_replacement(output)

    assert output.read_text(encoding="utf-8") == "keep until commit"
    assert messages and "replaced only after the new report is ready" in messages[0]


def test_report_replace_failure_preserves_the_previous_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "report.md"
    checksum = _checksum_path(output)
    _write(output, "old report")
    _write(checksum, "old checksum")

    def fail_replace(source: os.PathLike[str], destination: os.PathLike[str]) -> None:
        raise OSError("simulated report commit failure")

    monkeypatch.setattr(cli.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated report commit failure"):
        cli.atomic_write_report(output, lambda staged: _write(staged, "new report"))

    assert output.read_text(encoding="utf-8") == "old report"
    assert checksum.read_text(encoding="utf-8") == "old checksum"
    assert {path.name for path in tmp_path.iterdir()} == {
        "report.md",
        "report.md.sha256",
    }


def test_checksum_commit_failure_without_previous_report_removes_new_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "report.md"
    real_replace = os.replace
    calls = 0

    def fail_second_replace(
        source: os.PathLike[str], destination: os.PathLike[str]
    ) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated checksum commit failure")
        real_replace(source, destination)

    monkeypatch.setattr(cli.os, "replace", fail_second_replace)

    with pytest.raises(OSError, match="simulated checksum commit failure"):
        cli.atomic_write_report(output, lambda staged: _write(staged, "new report"))

    assert not output.exists()
    assert not _checksum_path(output).exists()
    assert not list(tmp_path.iterdir())


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_new_files_follow_the_umask_not_the_private_temp_default(
    tmp_path: Path,
) -> None:
    output = tmp_path / "report.md"
    previous_umask = os.umask(0o022)
    try:
        cli.atomic_write_report(output, lambda staged: _write(staged, "new report"))
    finally:
        os.umask(previous_umask)

    assert output.stat().st_mode & 0o777 == 0o644
    assert _checksum_path(output).stat().st_mode & 0o777 == 0o644


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_a_replacement_keeps_the_permissions_of_the_previous_report(
    tmp_path: Path,
) -> None:
    output = tmp_path / "report.md"
    _write(output, "old report")
    output.chmod(0o640)

    cli.atomic_write_report(output, lambda staged: _write(staged, "new report"))

    assert output.stat().st_mode & 0o777 == 0o640
    assert _checksum_path(output).stat().st_mode & 0o777 == 0o640
