"""Tests for sarand.core.health -- score boundaries and critical-failure detection.

Expected sums below are computed by hand from the exact weights in
core/health.py (tests=25, quality=20, security=15, git=10, code=15,
tooling<=10). If you change those weights, update these expectations
in the same commit -- this test exists specifically to catch silent
scoring drift.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sarand.core.health import compute_health_score
from sarand.models.results import (
    CommandResult,
    EnvironmentInfo,
    GitSnapshot,
    ProjectStats,
    ReportData,
)


def _base_report(**overrides: object) -> ReportData:
    defaults: dict[str, object] = {
        "project_root": Path("/tmp/fixture"),
        "generated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "environment": EnvironmentInfo(),
        "git": GitSnapshot(),
        "stats": ProjectStats(),
    }
    defaults.update(overrides)
    return ReportData(**defaults)  # type: ignore[arg-type]


def test_empty_report_scores_low_and_grade_f() -> None:
    data = _base_report()
    result = compute_health_score(data)
    assert result.score == 43.0
    assert result.grade == "F"
    assert result.breakdown["tests"] == 5.0
    assert result.breakdown["tooling"] == 0.0


def test_passing_tests_and_quality_score_grade_b() -> None:
    data = _base_report(
        test_results=[
            CommandResult(kind="pytest", returncode=0, summary="ok"),
            CommandResult(kind="cargo test", returncode=0, summary="ok"),
        ],
        quality_results=[
            CommandResult(kind="ruff check", returncode=0, summary="ok"),
            CommandResult(kind="ruff format", returncode=0, summary="ok"),
        ],
        environment=EnvironmentInfo(
            tool_versions={f"tool{i}": "1.0" for i in range(5)}
        ),
    )
    result = compute_health_score(data)
    assert result.score == 88.0
    assert result.grade == "B"


def test_adding_clean_security_pushes_to_grade_a() -> None:
    data = _base_report(
        test_results=[CommandResult(kind="pytest", returncode=0, summary="ok")],
        quality_results=[CommandResult(kind="ruff check", returncode=0, summary="ok")],
        security_results=[CommandResult(kind="pip-audit", returncode=0, summary="ok")],
        environment=EnvironmentInfo(
            tool_versions={f"tool{i}": "1.0" for i in range(5)}
        ),
    )
    result = compute_health_score(data)
    assert result.score == 95.0
    assert result.grade == "A"


def test_failing_test_is_flagged_as_critical() -> None:
    data = _base_report(
        test_results=[CommandResult(kind="pytest", returncode=1, summary="FAILED")],
    )
    result = compute_health_score(data)
    assert any("failed" in c.lower() for c in result.critical_failures)
    assert result.breakdown["tests"] == 0.0  # 25.0 * (0 passed / 1 total)


def test_skipped_tests_do_not_count_as_failures() -> None:
    """A skipped test (tool not installed) is not the same as a failing
    test -- it should not appear in critical_failures."""
    data = _base_report(
        test_results=[
            CommandResult(
                kind="pytest",
                returncode=127,
                summary="",
                skipped=True,
                skip_reason="pytest not found",
            )
        ],
    )
    result = compute_health_score(data)
    assert not any("failed" in c.lower() for c in result.critical_failures)


def test_broken_symlinks_are_critical() -> None:
    data = _base_report(stats=ProjectStats(broken_symlinks=["a", "b", "c"]))
    result = compute_health_score(data)
    assert any("broken symlinks" in c.lower() for c in result.critical_failures)


def test_dirty_git_reduces_git_score() -> None:
    clean = compute_health_score(_base_report(git=GitSnapshot(dirty=False)))
    dirty = compute_health_score(
        _base_report(git=GitSnapshot(dirty=True, status="M file.py"))
    )
    assert dirty.breakdown["git"] < clean.breakdown["git"]


def test_score_never_exceeds_100_or_drops_below_0() -> None:
    data = _base_report(
        test_results=[CommandResult(kind="pytest", returncode=0, summary="ok")],
        quality_results=[CommandResult(kind="ruff", returncode=0, summary="ok")],
        security_results=[CommandResult(kind="pip-audit", returncode=0, summary="ok")],
        environment=EnvironmentInfo(
            tool_versions={f"tool{i}": "1.0" for i in range(20)}
        ),
    )
    result = compute_health_score(data)
    assert 0.0 <= result.score <= 100.0


def test_secret_findings_are_always_critical() -> None:
    from sarand.models.results import SecretFinding

    clean = compute_health_score(_base_report())
    with_secret = compute_health_score(
        _base_report(
            secret_findings=[
                SecretFinding(
                    path="config.py", line_number=3, pattern_name="AWS Access Key ID"
                )
            ]
        )
    )
    assert with_secret.breakdown["code"] < clean.breakdown["code"]
    assert any("secret" in c.lower() for c in with_secret.critical_failures)
