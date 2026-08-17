"""Tests for analyzer registry discovery and concurrent execution."""

from __future__ import annotations

import asyncio
from pathlib import Path

from sarand.analyzers.registry import (
    matching_analyzers,
    run_quality_concurrently,
    run_security_concurrently,
    run_tests_concurrently,
)
from sarand.models.results import CommandResult


class FakeAnalyzer:
    """Minimal analyzer implementation for registry concurrency tests."""

    def __init__(
        self,
        name: str,
        *,
        delay: float = 0.05,
        test_result: CommandResult | None = None,
    ) -> None:
        self.name = name
        self.delay = delay
        self.test_result = test_result
        self.events: list[str] = []

    def matches(self, root: Path) -> bool:
        return True

    def entry_points(self, root: Path) -> list[str]:
        return []

    async def run_tests(self, root: Path) -> CommandResult | None:
        self.events.append("test-start")
        await asyncio.sleep(self.delay)
        self.events.append("test-end")
        return self.test_result

    async def run_quality(self, root: Path) -> list[CommandResult]:
        self.events.append("quality-start")
        await asyncio.sleep(self.delay)
        self.events.append("quality-end")
        return [self._result("quality")]

    async def run_security(self, root: Path) -> list[CommandResult]:
        self.events.append("security-start")
        await asyncio.sleep(self.delay)
        self.events.append("security-end")
        return [self._result("security")]

    def _result(self, kind: str) -> CommandResult:
        return CommandResult(
            kind=f"{self.name}:{kind}",
            returncode=0,
            summary="ok",
            raw_output="",
            warnings=[],
            errors=[],
            duration_seconds=self.delay,
            skipped=False,
            skip_reason="",
        )


def test_matching_analyzers_uses_supplied_pool(tmp_path: Path) -> None:
    first = FakeAnalyzer("first")
    second = FakeAnalyzer("second")

    active = matching_analyzers(tmp_path, [first, second])

    assert active == [first, second]


def test_run_tests_concurrently_runs_analyzers_in_parallel(tmp_path: Path) -> None:
    first = FakeAnalyzer(
        "first",
        delay=0.15,
        test_result=CommandResult(
            kind="first:test",
            returncode=0,
            summary="ok",
            raw_output="",
            warnings=[],
            errors=[],
            duration_seconds=0.15,
            skipped=False,
            skip_reason="",
        ),
    )
    second = FakeAnalyzer(
        "second",
        delay=0.15,
        test_result=CommandResult(
            kind="second:test",
            returncode=0,
            summary="ok",
            raw_output="",
            warnings=[],
            errors=[],
            duration_seconds=0.15,
            skipped=False,
            skip_reason="",
        ),
    )

    async def scenario() -> tuple[list[CommandResult], float]:
        start = asyncio.get_running_loop().time()
        results = await run_tests_concurrently(tmp_path, [first, second])
        duration = asyncio.get_running_loop().time() - start
        return results, duration

    results, duration = asyncio.run(scenario())

    assert {result.kind for result in results} == {"first:test", "second:test"}
    assert first.events == ["test-start", "test-end"]
    assert second.events == ["test-start", "test-end"]
    assert duration < 0.27


def test_run_tests_concurrently_filters_none_results(tmp_path: Path) -> None:
    analyzer = FakeAnalyzer("none", test_result=None)

    results = asyncio.run(run_tests_concurrently(tmp_path, [analyzer]))

    assert results == []


def test_run_quality_concurrently_flattens_results(tmp_path: Path) -> None:
    analyzers = [FakeAnalyzer("first"), FakeAnalyzer("second")]

    results = asyncio.run(run_quality_concurrently(tmp_path, analyzers))

    assert [result.kind for result in results] == [
        "first:quality",
        "second:quality",
    ]


def test_run_security_concurrently_flattens_results(tmp_path: Path) -> None:
    analyzers = [FakeAnalyzer("first"), FakeAnalyzer("second")]

    results = asyncio.run(run_security_concurrently(tmp_path, analyzers))

    assert [result.kind for result in results] == [
        "first:security",
        "second:security",
    ]
