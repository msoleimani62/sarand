"""`--max-file-size` and the pre-render size estimate."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import pytest
from sarand.cli import build_parser
from sarand.config import SarandConfig
from sarand.core.estimate import (
    LARGE_REPORT_BYTES,
    estimate_source_bytes,
    size_advice,
)
from sarand.utils.sizes import parse_size, size_argument


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2048", 2048),
        ("512K", 512 * 1024),
        ("512k", 512 * 1024),
        ("2M", 2 * 1024**2),
        ("2MB", 2 * 1024**2),
        ("2MiB", 2 * 1024**2),
        ("1.5G", int(1.5 * 1024**3)),
        (" 4 M ", 4 * 1024**2),
    ],
)
def test_parse_size_accepts_plain_and_suffixed_numbers(
    text: str, expected: int
) -> None:
    assert parse_size(text) == expected


@pytest.mark.parametrize("text", ["", "M", "-1", "2X", "two", "1e3", "1..5M"])
def test_parse_size_rejects_everything_else(text: str) -> None:
    with pytest.raises(ValueError, match="not a size"):
        parse_size(text)
    with pytest.raises(argparse.ArgumentTypeError):
        size_argument(text)


def test_the_command_line_accepts_the_option() -> None:
    args = build_parser().parse_args(["--max-file-size", "512K"])

    assert args.max_file_size == 512 * 1024


def test_an_explicit_limit_beats_the_no_limit_behaviour_of_full() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        parser = build_parser()
        limited = SarandConfig.from_args(
            parser.parse_args(["--full", "--max-file-size", "1M", "-p", tmp])
        )
        unlimited = SarandConfig.from_args(parser.parse_args(["--full", "-p", tmp]))
        default = SarandConfig.from_args(parser.parse_args(["-p", tmp]))

    assert limited.max_file_size == 1024**2
    assert unlimited.max_file_size > 1024**3
    assert default.max_file_size == 2 * 1024**2


def test_a_limit_below_one_kib_is_refused_by_validation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        args = build_parser().parse_args(["--max-file-size", "10", "-p", tmp])
        config = SarandConfig.from_args(args)

        with pytest.raises(ValueError, match="1024"):
            config.validate()


def test_estimate_sums_only_the_files_that_will_be_embedded() -> None:
    records = [
        {"rel_path": "a.py", "size": 100},
        {"rel_path": "src/b.py", "size": 250},
        {"rel_path": "big.json", "size": 10_000_000},
    ]
    included = [Path("a.py"), Path("src") / "b.py"]

    assert estimate_source_bytes(records, included) == 350


def test_estimate_ignores_files_the_scan_did_not_report() -> None:
    assert estimate_source_bytes([], [Path("ghost.py")]) == 0


def test_small_reports_get_no_advice() -> None:
    assert size_advice(5 * 1024**2, available=8 * 1024**3) is None
    assert size_advice(5 * 1024**2, available=None) is None


def test_an_absolutely_large_report_is_flagged() -> None:
    advice = size_advice(LARGE_REPORT_BYTES, available=None)

    assert advice is not None
    assert "50.0 MiB" in advice
    assert "--no-source" in advice
    assert "--max-file-size" in advice


def test_a_report_that_is_large_for_this_machine_is_flagged() -> None:
    # 200 MiB free memory: 60 MiB of source is more than a quarter of it.
    advice = size_advice(60 * 1024**2, available=200 * 1024**2)

    assert advice is not None
    assert "of memory is free" in advice


def test_advice_never_asks_a_question_or_blocks() -> None:
    advice = size_advice(10 * 1024**3, available=1024**3)

    assert advice is not None
    assert "?" not in advice
