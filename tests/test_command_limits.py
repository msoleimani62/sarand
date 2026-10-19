"""Tests for the two limits in utils/command.py (AGENTS.md 5.73): how many external
commands run at once, and how much of a command's output is kept."""

from __future__ import annotations

import asyncio
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sarand.utils.command import run_cmd_async, set_max_concurrent_commands

_PY = sys.executable


@contextmanager
def _limit(value: int | None) -> Iterator[None]:
    set_max_concurrent_commands(value)
    try:
        yield
    finally:
        set_max_concurrent_commands(None)


def _span_command(seconds: float) -> list[str]:
    code = (
        f"import time; a = time.time(); time.sleep({seconds}); "
        "b = time.time(); print(a, b)"
    )
    return [_PY, "-c", code]


async def _spans(count: int, seconds: float) -> list[tuple[float, float]]:
    with tempfile.TemporaryDirectory() as tmp:
        results = await asyncio.gather(
            *(run_cmd_async(_span_command(seconds), Path(tmp)) for _ in range(count))
        )
    spans: list[tuple[float, float]] = []
    for code, output, _duration in results:
        assert code == 0, output
        start, end = output.split()
        spans.append((float(start), float(end)))
    return sorted(spans)


def _overlaps(spans: list[tuple[float, float]]) -> bool:
    return any(spans[i][1] > spans[i + 1][0] for i in range(len(spans) - 1))


def test_a_limit_of_one_never_runs_two_commands_at_the_same_time() -> None:
    with _limit(1):
        spans = asyncio.run(_spans(3, 0.4))
    assert not _overlaps(spans)


def test_without_a_limit_commands_run_together() -> None:
    with _limit(None):  # an earlier test may have left a limit behind
        spans = asyncio.run(_spans(3, 1.0))
    assert _overlaps(spans)


def test_a_limit_of_two_allows_two_at_once_but_not_three() -> None:
    with _limit(2):
        spans = asyncio.run(_spans(4, 0.8))
    starts = [s for s, _ in spans]
    ends = [e for _, e in spans]
    # No instant has three commands alive.
    for moment in starts:
        alive = sum(1 for s, e in spans if s <= moment < e)
        assert alive <= 2
    assert ends[0] > starts[1], "two commands should have overlapped"


def test_the_limit_is_rebuilt_for_each_event_loop() -> None:
    with _limit(1):
        first = asyncio.run(_spans(2, 0.2))
        second = asyncio.run(_spans(2, 0.2))
    assert not _overlaps(first)
    assert not _overlaps(second)


def test_the_timeout_does_not_include_the_wait_for_a_free_slot() -> None:
    async def scenario() -> list[tuple[int, str, float]]:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            # The second command waits for the first; its 3 s timeout must only
            # start once it runs, so it still finishes normally.
            return list(
                await asyncio.gather(
                    run_cmd_async(_span_command(1.5), cwd, 30),
                    run_cmd_async(_span_command(0.1), cwd, 3),
                )
            )

    with _limit(1):
        results = asyncio.run(scenario())
    assert [code for code, _o, _d in results] == [0, 0]


def test_output_over_the_cap_keeps_the_head_and_the_tail_and_says_so() -> None:
    code = "import sys; sys.stdout.write('A' * 100000 + 'M' * 100000 + 'Z' * 100000)"

    async def scenario() -> tuple[int, str, float]:
        with tempfile.TemporaryDirectory() as tmp:
            return await run_cmd_async(
                [_PY, "-c", code], Path(tmp), max_output_bytes=2000
            )

    returncode, output, _duration = asyncio.run(scenario())
    assert returncode == 0  # the child was drained, never blocked on a full pipe
    assert output.startswith("A" * 1000)
    assert output.endswith("Z" * 1000)
    assert "[sarand: " in output
    assert "bytes omitted from the middle of this output]" in output
    assert len(output) < 2400
    assert "M" * 50 not in output


def test_output_within_the_cap_is_returned_unchanged() -> None:
    async def scenario() -> tuple[int, str, float]:
        with tempfile.TemporaryDirectory() as tmp:
            return await run_cmd_async(
                [_PY, "-c", "print('hello', 'world')"], Path(tmp), max_output_bytes=2000
            )

    returncode, output, _duration = asyncio.run(scenario())
    assert returncode == 0
    assert output.strip() == "hello world"
    assert "[sarand: " not in output


def test_a_command_that_fills_the_pipe_and_then_times_out_still_returns() -> None:
    code = "import sys, time; sys.stdout.write('x' * 500000); sys.stdout.flush(); time.sleep(30)"

    async def scenario() -> tuple[int, str, float]:
        with tempfile.TemporaryDirectory() as tmp:
            return await run_cmd_async(
                [_PY, "-c", code], Path(tmp), timeout=2, max_output_bytes=4000
            )

    returncode, output, _duration = asyncio.run(scenario())
    assert returncode == 124
    assert output.startswith("x" * 100)
    assert len(output) < 4400


def test_a_huge_output_stays_bounded_in_memory() -> None:
    code = (
        "import sys\n"
        "chunk = 'y' * 65536\n"
        "for _ in range(400):\n"
        "    sys.stdout.write(chunk)\n"
    )  # about 25 MiB

    async def scenario() -> tuple[int, str, float]:
        with tempfile.TemporaryDirectory() as tmp:
            return await run_cmd_async(
                [_PY, "-c", code], Path(tmp), max_output_bytes=64 * 1024
            )

    returncode, output, _duration = asyncio.run(scenario())
    assert returncode == 0
    assert len(output) < 70 * 1024
