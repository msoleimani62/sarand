"""Execution coverage (R13-B): which REQUESTED checks reached a verdict.

Not to be confused with core/coverage.py, which is the per-ecosystem coverage
matrix of what sarand supports. This module is about one run of the checks.
با core/coverage.py (ماتریس پوشش اکوسیستم‌ها) اشتباه نشود؛ این ماژول درباره‌ی
یک اجرای چک‌هاست.

    execution_coverage = executed / requested

- `requested`: the records in the test, quality and security results. A check
  that was never requested (for example no `--quality`) has no record, so it is
  not in the denominator; the per-group counts say so explicitly instead of
  letting "100%" read as "everything".
- `executed`: records in the state `passed` or `failed` (core/check_states.py). A
  failed check executed; a skipped, inconclusive, unavailable (timeout, tool not
  found) or unknown one did not.
- Nothing requested: there is no denominator, so the value is `None` (reported as
  "not available"), never 100%.
- Records are counted one by one: two results of the same tool are two checks.

This is a measure of WHAT RAN. It is not analytical confidence, completeness of
the analysis, or a statement about the project.

Pure and deterministic; the sentences below are the only place a report words it,
so every renderer says the same thing.

پوشش اجرا = executed / requested؛ فقط می‌گوید کدام چک‌های درخواست‌شده به حکم
رسیده‌اند. وقتی چیزی درخواست نشده مقدار None است (هرگز ۱۰۰٪ نیست). درستی یا
کامل‌بودن تحلیل را نمی‌سنجد.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from sarand.core.check_states import (
    EXECUTED_STATES,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    check_state,
)
from sarand.core.failures import execution_cause
from sarand.models.results import CommandResult, CoverageGap, HealthScore

GROUPS: tuple[str, ...] = ("tests", "quality", "security")
_MAX_GAPS_IN_TEXT = 6
_REASON_CLIP = 80

NOTE = (
    "Execution coverage counts which requested checks ran to a verdict. It does "
    "not measure how complete or correct the analysis is."
)


@dataclass(frozen=True)
class CoverageSummary:
    requested: int = 0
    executed: int = 0
    coverage: float | None = None
    by_group: dict[str, dict[str, int]] = field(default_factory=dict)
    gaps: tuple[CoverageGap, ...] = ()


def _reason(result: CommandResult, state: str) -> str:
    if state == STATE_UNAVAILABLE:
        return execution_cause(result)
    if state == STATE_UNKNOWN:
        return "contradictory record (skipped and inconclusive)"
    text = result.inconclusive_reason if result.inconclusive else result.skip_reason
    flat = " ".join(str(text).split())
    return flat if len(flat) <= _REASON_CLIP else flat[: _REASON_CLIP - 1] + "…"


def summarize_coverage(
    test_results: Iterable[CommandResult],
    quality_results: Iterable[CommandResult],
    security_results: Iterable[CommandResult],
) -> CoverageSummary:
    """Count requested and executed checks, per group and in total."""
    by_group: dict[str, dict[str, int]] = {}
    gaps: list[CoverageGap] = []
    requested = executed = 0
    for group, results in zip(
        GROUPS, (test_results, quality_results, security_results), strict=True
    ):
        group_requested = group_executed = 0
        for result in results:
            state = check_state(result)
            group_requested += 1
            if state in EXECUTED_STATES:
                group_executed += 1
            else:
                gaps.append(CoverageGap(result.kind, state, _reason(result, state)))
        by_group[group] = {"requested": group_requested, "executed": group_executed}
        requested += group_requested
        executed += group_executed
    coverage = round(executed / requested, 4) if requested else None
    return CoverageSummary(requested, executed, coverage, by_group, tuple(gaps))


def coverage_percent(value: float) -> int:
    """A coverage fraction as a whole percent, rounded half up (never banker's
    rounding, so 0.725 is 73% everywhere)."""
    return int(value * 100 + 0.5)


def coverage_headline(health: HealthScore) -> str:
    """One clause for a health line: the percentage with its basis, or the
    honest statement that there is no percentage."""
    if health.execution_coverage is None:
        return "execution coverage not available (no check was requested)"
    return (
        f"execution coverage {coverage_percent(health.execution_coverage)}% "
        f"({health.checks_executed} of {health.checks_requested} requested "
        "checks ran to a verdict)"
    )


def _gap_text(gap: CoverageGap) -> str:
    return f"{gap.kind} ({gap.state}{': ' + gap.reason if gap.reason else ''})"


def coverage_not_run(health: HealthScore) -> str:
    """ "cargo audit (skipped: not installed), ..." or "" when every requested
    check ran; capped, with the rest counted."""
    gaps = health.coverage_gaps
    if not gaps:
        return ""
    shown = ", ".join(_gap_text(g) for g in gaps[:_MAX_GAPS_IN_TEXT])
    extra = len(gaps) - _MAX_GAPS_IN_TEXT
    return shown + (f" (+{extra} more)" if extra > 0 else "")


def coverage_empty_groups(health: HealthScore) -> list[str]:
    """Groups in which no check was requested (so they are not in the
    percentage), only when at least one other group has checks."""
    if health.execution_coverage is None:
        return []
    return [
        g for g, c in health.coverage_by_group.items() if c.get("requested", 0) == 0
    ]


def coverage_oneline(health: HealthScore) -> str:
    """Headline plus what did not run, for one-line health summaries (text
    report, CLI summary)."""
    not_run = coverage_not_run(health)
    return coverage_headline(health) + (f"; not run: {not_run}" if not_run else "")


def coverage_lines(health: HealthScore) -> list[str]:
    """The explanatory lines for the Markdown and HTML Health Score sections:
    headline, what did not run, which groups had nothing requested, and the
    permanent note that this is not analytical confidence."""
    lines = [
        f"Execution coverage: {coverage_headline(health).removeprefix('execution coverage ')}"
    ]
    not_run = coverage_not_run(health)
    if not_run:
        lines.append(f"Not run: {not_run}")
    empty = coverage_empty_groups(health)
    if empty:
        lines.append("No check was requested in: " + ", ".join(empty))
    lines.append(NOTE)
    return lines
