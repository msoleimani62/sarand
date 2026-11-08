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

`not_applicable` is reserved: no result records it yet, so it cannot be told
apart from `skipped` (R13-D adds the signal). A check is "executed" only in the
states `passed` and `failed`.

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


def is_executed(result: CommandResult) -> bool:
    """True when the check reached a verdict (passed or failed)."""
    return check_state(result) in EXECUTED_STATES
