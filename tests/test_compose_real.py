"""Real `docker compose config` against small Compose files (round R10e).

Runs only when SARAND_REAL_COMPOSE is set (the CI job `compose` sets it), so a
normal `pytest` skips it visibly. It proves what the mocked tests cannot: that
`--quiet --no-interpolate` mean what sarand assumes, in particular that a
required variable (`${X:?}`) is not an error and that an override is checked
together with its base.

اجرای واقعی docker compose؛ فقط وقتی SARAND_REAL_COMPOSE تنظیم باشد.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest
import yaml
from _helpers import write
from sarand.analyzers.compose_analyzer import ComposeAnalyzer
from sarand.models.results import CommandResult

_CI = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"


def _require() -> None:
    if not os.environ.get("SARAND_REAL_COMPOSE"):
        pytest.skip("SARAND_REAL_COMPOSE is not set; see the CI job `compose`")


def _quality(root: Path) -> list[CommandResult]:
    return asyncio.run(ComposeAnalyzer().run_quality(root))


def test_a_valid_file_passes() -> None:
    _require()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "compose.yaml", "services:\n  web:\n    image: nginx\n")
        results = _quality(root)
        assert [r.passed for r in results] == [True], results[0].raw_output


def test_an_invalid_file_fails_and_says_why() -> None:
    _require()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(
            root / "compose.yaml",
            "services:\n  web:\n    image: nginx\n    not_a_compose_key: 1\n",
        )
        verdict = _quality(root)[0]
        assert not verdict.passed and not verdict.skipped, verdict.raw_output
        assert verdict.raw_output


def test_a_required_variable_is_not_an_error_without_interpolation() -> None:
    _require()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(
            root / "compose.yaml",
            "services:\n  web:\n    image: nginx\n    environment:\n"
            "      TOKEN: ${SARAND_TEST_REQUIRED:?must be set}\n",
        )
        env = {k: v for k, v in os.environ.items() if k != "SARAND_TEST_REQUIRED"}
        with mock.patch.dict(os.environ, env, clear=True):
            verdict = _quality(root)[0]
        assert verdict.passed, verdict.raw_output


def test_an_override_is_checked_together_with_its_base() -> None:
    _require()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "compose.yaml", "services:\n  web:\n    image: nginx\n")
        write(
            root / "compose.override.yaml",
            "services:\n  web:\n    environment:\n      A: '1'\n",
        )
        results = _quality(root)
        assert [r.kind for r in results] == [
            "docker compose config compose.yaml",
            "docker compose config compose.yaml + compose.override.yaml",
        ]
        assert all(r.passed for r in results), [r.raw_output for r in results]


def test_ci_has_a_compose_job_that_sets_the_switch() -> None:
    steps = yaml.safe_load(_CI.read_text(encoding="utf-8"))["jobs"]["compose"]["steps"]
    switched = [s for s in steps if "SARAND_REAL_COMPOSE" in s.get("env", {})]
    assert switched
    assert all(s.get("continue-on-error") is not True for s in switched)
