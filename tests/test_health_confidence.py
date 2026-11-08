"""The health score must say how much of it rests on checks that really ran."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sarand.core.health import compute_health_score
from sarand.models.results import (
    CommandResult,
    EnvironmentInfo,
    GitSnapshot,
    ProjectDetection,
    ProjectStats,
    ReportData,
)
from sarand.renderers import html, markdown, text


def _result(kind: str, *, skipped: bool = False, ok: bool = True) -> CommandResult:
    return CommandResult(
        kind=kind,
        returncode=0 if ok else 1,
        summary="",
        duration_seconds=0.1,
        skipped=skipped,
        skip_reason=f"{kind} not installed" if skipped else "",
    )


def _data(*, tests=(), quality=(), security=()) -> ReportData:
    return ReportData(
        project_root=Path("/p"),
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        environment=EnvironmentInfo(python="Python 3.13.0"),
        git=GitSnapshot(branch="main", commit="abc"),
        stats=ProjectStats(total_files=1, total_loc=1),
        detection=ProjectDetection(languages=["Python"]),
        test_results=list(tests),
        quality_results=list(quality),
        security_results=list(security),
    )


def test_a_fully_run_project_has_full_confidence() -> None:
    health = compute_health_score(
        _data(tests=[_result("pytest")], quality=[_result("ruff")])
    )

    assert health.checks_run == 2
    assert health.checks_skipped == []
    assert health.confidence == 1.0


def test_skipped_checks_lower_confidence_and_are_named() -> None:
    health = compute_health_score(
        _data(
            tests=[_result("pytest")],
            quality=[_result("ruff"), _result("mypy", skipped=True)],
            security=[
                _result("bandit", skipped=True),
                _result("pip-audit", skipped=True),
            ],
        )
    )

    assert health.checks_run == 2
    assert health.checks_skipped == ["bandit", "mypy", "pip-audit"]
    assert health.confidence == 0.4
    assert any("3 check(s) were skipped" in r for r in health.recommendations)
    assert any("`sarand --doctor`" in r for r in health.recommendations)


def test_an_unrequested_check_is_not_counted_as_skipped() -> None:
    health = compute_health_score(_data(tests=[_result("pytest")]))

    assert health.checks_skipped == []
    assert health.confidence == 1.0


def test_an_all_skipped_security_run_no_longer_earns_full_security_points() -> None:
    clean = compute_health_score(_data(security=[_result("bandit")]))
    nothing_ran = compute_health_score(
        _data(security=[_result("bandit", skipped=True)])
    )

    assert clean.breakdown["security"] == 15.0
    assert nothing_ran.breakdown["security"] == 8.0
    assert any("No security check could run" in r for r in nothing_ran.recommendations)


def test_some_security_checks_running_clean_still_earns_full_points() -> None:
    health = compute_health_score(
        _data(security=[_result("bandit"), _result("pip-audit", skipped=True)])
    )

    assert health.breakdown["security"] == 15.0


def test_a_skip_for_another_reason_is_not_blamed_on_a_missing_tool() -> None:
    other = CommandResult(
        kind="cargo deny check",
        returncode=0,
        summary="",
        duration_seconds=0.0,
        skipped=True,
        skip_reason="no deny.toml in the project",
    )

    health = compute_health_score(_data(security=[other]))

    assert health.checks_skipped == []


def test_the_reports_always_show_execution_coverage_and_never_call_it_confidence() -> (
    None
):
    """R13-B: the coverage line is permanent (a missing line reads as "nothing to
    report"), says "execution coverage", names what did not run, and never uses
    the word "confidence" for a measure of what ran."""
    complete = _data(tests=[_result("pytest")])
    complete.health = compute_health_score(complete)
    partial = _data(tests=[_result("pytest")], quality=[_result("ruff", skipped=True)])
    partial.health = compute_health_score(partial)

    for data in (complete, partial):
        for out in (markdown.render(data), text.render(data), html.render(data)):
            assert "execution coverage" in out.lower()
            # the risk rule keeps its legacy id; no other use of the word is allowed
            assert "confidence" not in out.replace("HEALTH-LOW-CONFIDENCE", "").lower()
    assert "execution coverage 50% (1 of 2 requested checks ran" in text.render(partial)
    assert "Not run: ruff (skipped" in markdown.render(partial)
    assert "execution coverage 100% (1 of 1 requested checks ran" in text.render(
        complete
    )
    assert "Execution coverage counts which requested checks ran" in markdown.render(
        complete
    )
