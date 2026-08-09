"""Tests for cli.remove_previous_report -- explicit check/remove/replace
of an existing report at the exact output path before writing a new one."""

from __future__ import annotations

import tempfile
from pathlib import Path

from sarand.cli import remove_previous_report


def test_removes_existing_report_and_its_checksum() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output_path = Path(tmp) / "sarand-demo-report.md"
        checksum_path = Path(tmp) / "sarand-demo-report.md.sha256"
        output_path.write_text("old report content")
        checksum_path.write_text("old checksum")

        remove_previous_report(output_path)

        assert not output_path.exists()
        assert not checksum_path.exists()


def test_is_a_noop_when_nothing_exists_yet() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output_path = Path(tmp) / "sarand-demo-report.md"

        remove_previous_report(output_path)  # must not raise

        assert not output_path.exists()


def test_removes_report_even_without_a_checksum_file() -> None:
    """An old report from a version that predates the .sha256 companion
    (or one where it was deleted separately) must still be handled."""
    with tempfile.TemporaryDirectory() as tmp:
        output_path = Path(tmp) / "sarand-demo-report.md"
        output_path.write_text("old report content")

        remove_previous_report(output_path)

        assert not output_path.exists()


def test_does_not_touch_unrelated_files_in_the_same_directory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output_path = Path(tmp) / "sarand-demo-report.md"
        unrelated = Path(tmp) / "sarand-other-project-report.md"
        output_path.write_text("old")
        unrelated.write_text("keep me")

        remove_previous_report(output_path)

        assert not output_path.exists()
        assert unrelated.exists()
        assert unrelated.read_text() == "keep me"
