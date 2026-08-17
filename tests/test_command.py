import asyncio
import os
import sys
import time
from pathlib import Path

import pytest
from sarand.utils.command import (
    make_command_result,
    run_cmd,
    run_cmd_async,
    scan_for_issues,
    summarize_tail,
)


def test_run_cmd_success(tmp_path: Path) -> None:
    returncode, output, duration = run_cmd(
        [sys.executable, "-c", "print('hello')"],
        tmp_path,
    )

    assert returncode == 0
    assert output.strip() == "hello"
    assert duration >= 0


def test_run_cmd_async_success(tmp_path: Path) -> None:
    async def scenario() -> tuple[int, str, float]:
        return await run_cmd_async(
            [sys.executable, "-c", "print('hello')"],
            tmp_path,
        )

    returncode, output, duration = asyncio.run(scenario())

    assert returncode == 0
    assert output.strip() == "hello"
    assert duration >= 0


def test_run_cmd_and_async_support_environment(tmp_path: Path) -> None:
    env = dict(os.environ)
    env["SARAND_TEST_VALUE"] = "expected"

    sync_result = run_cmd(
        [sys.executable, "-c", "import os; print(os.environ['SARAND_TEST_VALUE'])"],
        tmp_path,
        env=env,
    )

    async_result = asyncio.run(
        run_cmd_async(
            [sys.executable, "-c", "import os; print(os.environ['SARAND_TEST_VALUE'])"],
            tmp_path,
            env=env,
        )
    )

    assert sync_result[0] == 0
    assert sync_result[1].strip() == "expected"
    assert async_result[0] == 0
    assert async_result[1].strip() == "expected"


def test_run_cmd_timeout_preserves_output(tmp_path: Path) -> None:
    returncode, output, duration = run_cmd(
        [
            sys.executable,
            "-c",
            "import time; print('before-timeout', flush=True); time.sleep(2)",
        ],
        tmp_path,
        timeout=1,
    )

    assert returncode == 124
    assert "before-timeout" in output
    assert duration >= 1


def test_run_cmd_async_timeout_preserves_output(tmp_path: Path) -> None:
    async def scenario() -> tuple[int, str, float]:
        return await run_cmd_async(
            [
                sys.executable,
                "-c",
                "import time; print('before-timeout', flush=True); time.sleep(2)",
            ],
            tmp_path,
            timeout=1,
        )

    returncode, output, duration = asyncio.run(scenario())

    assert returncode == 124
    assert "before-timeout" in output
    assert duration >= 1


@pytest.mark.skipif(os.name != "posix", reason="Process-group lifecycle requires POSIX")
def test_run_cmd_async_timeout_terminates_process_group(tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"

    child_code = (
        "import os,time; "
        f"open({str(pid_file)!r}, 'w').write(str(os.getpid())); "
        "time.sleep(30)"
    )

    parent_code = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        "print('parent-started', flush=True); "
        "time.sleep(30)"
    )

    async def scenario() -> tuple[int, str, float]:
        return await run_cmd_async(
            [sys.executable, "-c", parent_code],
            tmp_path,
            timeout=1,
        )

    returncode, output, duration = asyncio.run(scenario())

    assert returncode == 124
    assert "parent-started" in output
    assert duration >= 1
    assert pid_file.exists()

    child_pid = int(pid_file.read_text())

    for _ in range(100):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break

        try:
            with open(f"/proc/{child_pid}/stat") as stat_file:
                state = stat_file.read().split()[2]
        except FileNotFoundError:
            break

        if state == "Z":
            break

        time.sleep(0.05)
    else:
        pytest.fail(f"Child process {child_pid} survived process-group termination")


@pytest.mark.skipif(os.name != "posix", reason="Process-group lifecycle requires POSIX")
def test_run_cmd_async_cancellation_terminates_process_group(tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"

    child_code = (
        "import os,time; "
        f"open({str(pid_file)!r}, 'w').write(str(os.getpid())); "
        "time.sleep(30)"
    )

    parent_code = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        "print('parent-started', flush=True); "
        "time.sleep(30)"
    )

    async def scenario() -> None:
        task = asyncio.create_task(
            run_cmd_async(
                [sys.executable, "-c", parent_code],
                tmp_path,
                timeout=30,
            )
        )

        for _ in range(100):
            if pid_file.exists():
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("Child process did not start")

        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    start = time.perf_counter()
    asyncio.run(scenario())
    duration = time.perf_counter() - start

    assert duration < 5

    child_pid = int(pid_file.read_text())

    for _ in range(100):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break

        try:
            with open(f"/proc/{child_pid}/stat") as stat_file:
                state = stat_file.read().split()[2]
        except FileNotFoundError:
            break

        if state == "Z":
            break

        time.sleep(0.05)
    else:
        pytest.fail(f"Child process {child_pid} survived cancellation cleanup")


def test_run_cmd_async_cancellation_cleans_up(tmp_path: Path) -> None:
    async def scenario() -> None:
        task = asyncio.create_task(
            run_cmd_async(
                [
                    sys.executable,
                    "-c",
                    "import time; time.sleep(30)",
                ],
                tmp_path,
                timeout=30,
            )
        )

        await asyncio.sleep(0.1)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    start = time.perf_counter()
    asyncio.run(scenario())

    assert time.perf_counter() - start < 5


def test_summarize_tail() -> None:
    output = "\n".join(f"line-{index}" for index in range(5))
    assert summarize_tail(output, lines=2) == "line-3\nline-4"


def test_summarize_tail_returns_stripped_output() -> None:
    output = "  first\nsecond\n\n"
    assert summarize_tail(output) == "first\nsecond"


def test_scan_for_issues() -> None:
    warnings, errors = scan_for_issues(
        "pytest",
        "warning: deprecated API\nerror: test failed",
    )

    assert len(warnings) == 1
    assert len(errors) == 1
    assert warnings[0].source == "pytest"
    assert errors[0].source == "pytest"


def test_scan_for_issues_ignores_empty_lines() -> None:
    warnings, errors = scan_for_issues(
        "pytest",
        "\nwarning: deprecated API\n\nerror: test failed\n",
    )

    assert len(warnings) == 1
    assert len(errors) == 1


def test_make_command_result() -> None:
    result = make_command_result(
        "pytest",
        1,
        "error: test failed",
        0.25,
    )

    assert result.kind == "pytest"
    assert result.returncode == 1
    assert result.raw_output == "error: test failed"
    assert result.duration_seconds == 0.25
    assert result.errors


def test_make_command_result_skipped() -> None:
    result = make_command_result(
        "pytest",
        0,
        "ignored output",
        0.25,
        skipped=True,
        skip_reason="tool unavailable",
    )

    assert result.kind == "pytest"
    assert result.returncode == 0
    assert result.skipped is True
    assert result.skip_reason == "tool unavailable"
    assert result.summary == "tool unavailable"
    assert result.raw_output == ""
    assert result.warnings == []
    assert result.errors == []
