"""R13-B: the shared check-state interpretation (core/check_states.py).

Every state, its edge cases, and the guarantee that a runner-level failure (a
timeout, a missing tool) is never read as an executed check.
R13-B: تفسیر مشترک وضعیت چک؛ شکست سطح runner هرگز «اجراشده» حساب نمی‌شود.
"""

from __future__ import annotations

from sarand.constants import SENTINEL_NOT_FOUND, SENTINEL_OS_ERROR, SENTINEL_TIMEOUT
from sarand.core.check_states import (
    CHECK_STATES,
    EXECUTED_STATES,
    STATE_FAILED,
    STATE_INCONCLUSIVE,
    STATE_PASSED,
    STATE_SKIPPED,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    check_state,
    is_executed,
)
from sarand.models.results import CommandResult


def _r(
    rc: int = 0,
    out: str = "",
    *,
    skipped: bool = False,
    inconclusive: str = "",
) -> CommandResult:
    return CommandResult(
        kind="tool",
        returncode=rc,
        summary="",
        raw_output=out,
        skipped=skipped,
        skip_reason="because" if skipped else "",
        inconclusive_reason=inconclusive,
    )


def test_the_vocabulary_is_fixed_and_not_applicable_is_not_invented() -> None:
    assert CHECK_STATES == (
        "passed",
        "failed",
        "skipped",
        "inconclusive",
        "unavailable",
        "unknown",
    )
    assert EXECUTED_STATES == {STATE_PASSED, STATE_FAILED}


def test_a_check_that_exited_zero_passed_and_non_zero_failed_but_both_executed() -> (
    None
):
    assert check_state(_r(0)) == STATE_PASSED
    for rc in (1, 2, 101, 255, -9):
        assert check_state(_r(rc, "boom")) == STATE_FAILED, rc
    assert is_executed(_r(0)) and is_executed(_r(1, "boom"))


def test_skipped_and_inconclusive_are_not_executed() -> None:
    assert check_state(_r(0, skipped=True)) == STATE_SKIPPED
    assert (
        check_state(_r(0, inconclusive="the network was unreachable"))
        == STATE_INCONCLUSIVE
    )
    assert not is_executed(_r(0, skipped=True))
    assert not is_executed(_r(0, inconclusive="x"))


def test_a_skipped_check_stays_skipped_even_with_a_failing_exit_code() -> None:
    assert (
        check_state(_r(127, f"{SENTINEL_NOT_FOUND} cargo", skipped=True))
        == STATE_SKIPPED
    )


def test_runner_level_failures_are_unavailable_never_executed() -> None:
    cases = (
        (124, f"partial\n{SENTINEL_TIMEOUT}"),
        (127, f"{SENTINEL_NOT_FOUND} cargo-audit"),
        (1, f"{SENTINEL_OS_ERROR} [Errno 13] Permission denied"),
    )
    for rc, out in cases:
        assert check_state(_r(rc, out)) == STATE_UNAVAILABLE, rc
        assert not is_executed(_r(rc, out))


def test_a_tool_that_really_exits_124_or_127_executed_and_failed() -> None:
    assert check_state(_r(124, "the tool's own message")) == STATE_FAILED
    assert check_state(_r(127, "the tool's own message")) == STATE_FAILED


def test_a_sentinel_text_with_exit_zero_is_just_a_passed_check() -> None:
    assert check_state(_r(0, SENTINEL_TIMEOUT)) == STATE_PASSED


def test_a_contradictory_record_is_unknown_and_never_executed() -> None:
    state = check_state(_r(0, skipped=True, inconclusive="and also inconclusive"))
    assert state == STATE_UNKNOWN and not is_executed(
        _r(0, skipped=True, inconclusive="x")
    )


def test_the_state_is_a_pure_function_of_the_record() -> None:
    record = _r(1, "boom")
    assert [check_state(record) for _ in range(3)] == [STATE_FAILED] * 3
    assert record == _r(1, "boom")
