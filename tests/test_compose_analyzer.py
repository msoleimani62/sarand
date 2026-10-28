"""The Docker Compose analyzer (backlog item 13, round R10e).

The tool runner is replaced, so these tests pin sarand's wiring: which files are
given together, the exact command, what is skipped and why. The real `docker
compose` is exercised by `test_compose_real.py` in CI.

آنالایزر Docker Compose؛ ابزار جایگزین شده و سیم‌کشی sarand سنجیده می‌شود.
"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Sequence
from pathlib import Path
from unittest import mock

from _helpers import write
from sarand.analyzers import compose_analyzer as ca
from sarand.analyzers.compose_analyzer import ComposeAnalyzer, compose_groups
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result

_SERVICE = "services:\n  web:\n    image: nginx\n"
_HEAD = ["docker", "compose"]
_TAIL = ["config", "--quiet", "--no-interpolate"]


def _run(
    root: Path, *, code: int = 0, output: str = ""
) -> tuple[list[CommandResult], list[list[str]]]:
    calls: list[list[str]] = []

    async def fake_run_tool(
        _root: Path, kind: str, argv: Sequence[str]
    ) -> CommandResult:
        calls.append(list(argv))
        return make_command_result(kind, code, output, 0.0)

    with mock.patch("sarand.analyzers.compose_analyzer.run_tool", fake_run_tool):
        results = asyncio.run(ComposeAnalyzer().run_quality(root))
    return results, calls


def test_a_base_file_is_checked_alone_then_with_each_override_or_variant() -> None:
    assert compose_groups(
        [
            "compose.override.yaml",
            "compose.yaml",
            "compose.prod.yml",
        ]
    ) == [
        ["compose.yaml"],
        ["compose.yaml", "compose.override.yaml"],
        ["compose.yaml", "compose.prod.yml"],
    ]


def test_each_directory_is_grouped_on_its_own() -> None:
    assert compose_groups(
        ["deploy/compose.yaml", "deploy/compose.override.yaml", "compose.yaml"]
    ) == [
        ["compose.yaml"],
        ["deploy/compose.yaml"],
        ["deploy/compose.yaml", "deploy/compose.override.yaml"],
    ]


def test_with_no_base_file_each_file_is_checked_alone() -> None:
    assert compose_groups(["compose.prod.yaml", "compose.dev.yaml"]) == [
        ["compose.dev.yaml"],
        ["compose.prod.yaml"],
    ]


def test_a_second_base_style_name_is_its_own_group() -> None:
    assert compose_groups(["compose.yaml", "docker-compose.yml"]) == [
        ["compose.yaml"],
        ["docker-compose.yml"],
    ]


def test_it_matches_only_when_a_compose_file_exists() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert not ComposeAnalyzer().matches(root)
        write(root / "compose.yaml", _SERVICE)
        assert ComposeAnalyzer().matches(root)


def test_the_command_is_config_quiet_without_interpolation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "compose.yaml", _SERVICE)
        write(root / "compose.override.yaml", "services:\n  web:\n    ports: []\n")
        results, calls = _run(root)
        assert calls == [
            [*_HEAD, "-f", "compose.yaml", *_TAIL],
            [*_HEAD, "-f", "compose.yaml", "-f", "compose.override.yaml", *_TAIL],
        ]
        assert [r.kind for r in results] == [
            "docker compose config compose.yaml",
            "docker compose config compose.yaml + compose.override.yaml",
        ]
        assert all(r.passed for r in results)


def test_an_invalid_file_is_a_failed_check_with_the_tool_message() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "compose.yaml", _SERVICE)
        message = "validating compose.yaml: services.web additional properties"
        results, _ = _run(root, code=1, output=message)
        assert not results[0].passed and not results[0].skipped
        assert "additional properties" in results[0].raw_output


def test_a_remote_include_is_skipped_and_nothing_is_run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(
            root / "compose.yaml",
            "include:\n  - oci://example.com/stack:1\n" + _SERVICE,
        )
        results, calls = _run(root)
        assert calls == []
        assert results[0].skipped
        assert "remote" in results[0].skip_reason


def test_a_remote_extends_file_is_skipped() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(
            root / "compose.yaml",
            "services:\n  web:\n    extends:\n      file: https://x.test/c.yaml\n"
            "      service: web\n",
        )
        results, calls = _run(root)
        assert calls == [] and results[0].skipped


def test_a_local_include_is_not_remote() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "compose.yaml", "include:\n  - ./other.yaml\n" + _SERVICE)
        assert ca.remote_reference(root, ["compose.yaml"]) == ""


def test_a_missing_compose_plugin_is_a_skip_not_a_failure() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "compose.yaml", _SERVICE)
        results, _ = _run(
            root, code=1, output="docker: 'compose' is not a docker command.\n"
        )
        assert results[0].skipped
        assert "Compose plugin" in results[0].skip_reason


def test_a_compose_too_old_for_the_flag_is_a_skip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "compose.yaml", _SERVICE)
        results, _ = _run(root, code=1, output="unknown flag: --no-interpolate\n")
        assert results[0].skipped
        assert "too old" in results[0].skip_reason


def test_an_unreachable_daemon_is_a_skip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "compose.yaml", _SERVICE)
        results, _ = _run(
            root, code=1, output="Cannot connect to the Docker daemon at unix:///x\n"
        )
        assert results[0].skipped


def test_more_groups_than_the_limit_are_counted_not_silently_dropped() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for index in range(ca.MAX_GROUPS + 2):
            write(root / f"svc{index}" / "compose.yaml", _SERVICE)
        results, calls = _run(root)
        assert len(calls) == ca.MAX_GROUPS
        assert results[-1].skipped
        assert "2 more group" in results[-1].skip_reason


def test_it_runs_no_tests_and_no_security_checks() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "compose.yaml", _SERVICE)
        analyzer = ComposeAnalyzer()
        assert asyncio.run(analyzer.run_tests(root)) is None
        assert asyncio.run(analyzer.run_security(root)) == []
        assert analyzer.entry_points(root) == []
