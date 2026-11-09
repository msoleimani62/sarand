"""The one interpretation of what happened to a check (R13-B, extended by R13-D).

Every consumer that asks "did this check run, and with what outcome?" (execution
coverage now; health scoring and risk rules in R13-D) must read the state from
`check_state`, so the report cannot say two different things about one record.

States (a `CommandResult` is in exactly one):

- `passed`        the tool ran and exited 0 with a verdict.
- `failed`        the tool ran and exited non-zero (see core/failures.py for the
                  kind of failure). It EXECUTED; it just did not succeed.
- `skipped`       the check did not run (tool missing, option, not applicable).
- `inconclusive`  the tool exited 0 but could not finish its job (for example
                  the network was unreachable): partial, no verdict.
- `unavailable`   the runner could not run the tool at all (timeout, tool not
                  found, operating-system error), recognised by core/failures.py.
- `unknown`       a contradictory record (skipped AND inconclusive): never
                  counted as executed, never hidden.

`not_applicable` is a reserved name and has no producer, on purpose (R13-D): an
analyzer runs only when its project marker exists (AGENTS.md 4.3), so a check
that does not apply to the project is never requested and is not in the
expected workload. A tool that is requested but cannot run is `skipped` or
`unavailable`, never "not applicable". A check is "executed" only in the states
`passed` and `failed`.

R13-D: this module is the ONE reading of a check's state. core/health.py,
core/risks.py, core/quick_context.py, core/package_summary.py and the Markdown
and HTML status badges ask `check_state`; none of them reads `skipped`,
`inconclusive` or the runner sentinels itself (tests/test_check_state_consistency.py
fails if they do). The full table is docs/CHECK_STATES.md.

یک تفسیر واحد از «چه بر سر چک آمد». executed فقط passed و failed است؛ unavailable
یعنی runner اصلاً نتوانست ابزار را اجرا کند؛ unknown هرگز موفق حساب نمی‌شود.
"""

from __future__ import annotations

from sarand.core.failures import execution_cause
from sarand.models.results import CommandResult

STATE_PASSED = "passed"
STATE_FAILED = "failed"
STATE_SKIPPED = "skipped"
STATE_INCONCLUSIVE = "inconclusive"
STATE_UNAVAILABLE = "unavailable"
STATE_UNKNOWN = "unknown"

CHECK_STATES: tuple[str, ...] = (
    STATE_PASSED,
    STATE_FAILED,
    STATE_SKIPPED,
    STATE_INCONCLUSIVE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
# States in which the check reached a verdict, successful or not.
# حالت‌هایی که چک به حکم رسیده، چه موفق چه ناموفق.
EXECUTED_STATES: frozenset[str] = frozenset({STATE_PASSED, STATE_FAILED})


def check_state(result: CommandResult) -> str:
    """The state of one check result. Pure and deterministic."""
    if result.skipped and result.inconclusive:
        return STATE_UNKNOWN
    if result.skipped:
        return STATE_SKIPPED
    if result.inconclusive:
        return STATE_INCONCLUSIVE
    if execution_cause(result):
        return STATE_UNAVAILABLE
    return STATE_PASSED if result.returncode == 0 else STATE_FAILED


# The states in which a check gave NO verdict: it must not earn score points, must
# not be reported as a finding, and must stay visible (coverage gap, risk,
# Quick Context). Every state that is not `passed` or `failed`.
# حالت‌هایی که چک حکمی نداده: نه امتیاز می‌گیرد، نه «یافته» حساب می‌شود، و دیده می‌ماند.
NO_VERDICT_STATES: tuple[str, ...] = (
    STATE_SKIPPED,
    STATE_INCONCLUSIVE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)


def is_executed(result: CommandResult) -> bool:
    """True when the check reached a verdict (passed or failed)."""
    return check_state(result) in EXECUTED_STATES


def has_no_verdict(result: CommandResult) -> bool:
    """True when the check gave no verdict (any state but passed / failed)."""
    return check_state(result) in NO_VERDICT_STATES


def unavailable_cause(result: CommandResult) -> str:
    """Why the runner could not run the tool (`timeout`, `tool_not_found`,
    `os_error`), or "" when it could. Meaningful for the `unavailable` state.
    """
    return execution_cause(result)


# LEGACY readings (R13-B): the deprecated `health.confidence`, `checks_run`,
# `checks_skipped`, `checks_inconclusive` and `missing_tools` keep their original
# arithmetic, in which a timed-out or not-found tool COUNTS AS RAN. They live here,
# next to the state function, so that the only code that reads the raw record
# flags is this module; new code must use `check_state`.
# خواندن‌های قدیمی: حساب اصلی فیلدهای منسوخ را نگه می‌دارند (timeout «اجراشده» است).
def legacy_ran(result: CommandResult) -> bool:
    """Legacy: not skipped and not inconclusive (so unavailable counts as ran)."""
    return not result.skipped and not result.inconclusive


def legacy_skipped(result: CommandResult) -> bool:
    """Legacy: the record's `skipped` flag (also true for an `unknown` record)."""
    return result.skipped


def legacy_inconclusive(result: CommandResult) -> bool:
    """Legacy: the record's `inconclusive` flag (also true for `unknown`)."""
    return result.inconclusive
