"""Tests for core/concurrency.py -- the `--jobs` limit (AGENTS.md 5.73)."""

from __future__ import annotations

import argparse

from sarand import cli
from sarand.config import SarandConfig
from sarand.core.concurrency import (
    default_jobs,
    jobs_argument,
    parse_jobs,
    resolve_jobs,
)

_GIB = 1024 * 1024 * 1024
_MIB = 1024 * 1024


def test_default_follows_the_cpu_count_up_to_the_cap() -> None:
    assert default_jobs(1, 64 * _GIB) == 1
    assert default_jobs(2, 64 * _GIB) == 2
    assert default_jobs(8, 64 * _GIB) == 8
    assert default_jobs(64, 64 * _GIB) == 8  # DEFAULT_MAX_JOBS
    assert default_jobs(None, 64 * _GIB) == 1


def test_default_follows_the_free_memory_one_job_per_gib() -> None:
    assert default_jobs(8, 1800 * _MIB) == 1  # the owner's 2 GB laptop
    assert default_jobs(8, 900 * _MIB) == 1  # never below one
    assert default_jobs(8, 2048 * _MIB) == 2
    assert default_jobs(8, 3500 * _MIB) == 3  # a 6 GB phone with some memory in use
    assert default_jobs(2, 64 * _GIB) == 2  # never above the CPU count
    assert default_jobs(16, 40 * _GIB) == 8  # a workstation: the cap


def test_default_ignores_memory_when_the_system_does_not_report_it() -> None:
    assert default_jobs(8, None) == 8
    assert default_jobs(3, None) == 3


def test_parse_jobs_accepts_one_to_the_limit_only() -> None:
    assert parse_jobs(" 3 ", "x") == 3
    assert parse_jobs("64", "x") == 64
    for bad in ("0", "-1", "65", "two", "", "1.5"):
        try:
            parse_jobs(bad, "SARAND_JOBS")
        except ValueError as exc:
            assert "SARAND_JOBS" in str(exc), bad
        else:
            raise AssertionError(f"{bad!r} should be rejected")


def test_the_command_line_wins_over_the_environment_and_the_default() -> None:
    env = {"SARAND_JOBS": "3"}
    assert resolve_jobs(2, env, 8, 8 * _GIB) == 2
    assert resolve_jobs(None, env, 8, 8 * _GIB) == 3
    assert resolve_jobs(None, {}, 8, 8 * _GIB) == 8
    assert resolve_jobs(None, {"SARAND_JOBS": "  "}, 8, 8 * _GIB) == 8


def test_an_invalid_environment_value_is_reported_not_swallowed() -> None:
    try:
        resolve_jobs(None, {"SARAND_JOBS": "lots"}, 8, 8 * _GIB)
    except ValueError as exc:
        assert "SARAND_JOBS" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_jobs_argument_is_an_argparse_type() -> None:
    assert jobs_argument("2") == 2
    try:
        jobs_argument("0")
    except argparse.ArgumentTypeError as exc:
        assert "--jobs" in str(exc)
    else:
        raise AssertionError("expected ArgumentTypeError")


def test_the_cli_parses_jobs_into_the_config() -> None:
    parser = cli.build_parser()
    assert SarandConfig.from_args(parser.parse_args(["--jobs", "2"])).jobs == 2
    assert SarandConfig.from_args(parser.parse_args([])).jobs is None


def test_the_cli_rejects_a_bad_jobs_value() -> None:
    parser = cli.build_parser()
    for bad in ("0", "65", "many"):
        try:
            parser.parse_args(["--jobs", bad])
        except SystemExit as exc:
            assert exc.code == 2, bad
        else:
            raise AssertionError(f"--jobs {bad} should be rejected")
