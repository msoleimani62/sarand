"""R13-D: one reading of a check's state for health, risks, Quick Context,
package summary and the status badges (core/check_states.py).

Covers every state, the CHECKS-SKIPPED threshold boundary (3), the guarantee that
a check with no verdict is never reported as a security finding, and a static
check that no consumer keeps a reading of its own. Dependency-free.
R13-D: یک منبع حقیقت برای وضعیت چک؛ همه‌ی حالت‌ها و مرز آستانه‌ی ۳.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from _golden_fixtures import FIXTURES
from sarand.constants import SENTINEL_NOT_FOUND, SENTINEL_TIMEOUT
from sarand.core.check_states import (
    NO_VERDICT_STATES,
    STATE_FAILED,
    STATE_INCONCLUSIVE,
    STATE_PASSED,
    STATE_SKIPPED,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    check_state,
    has_no_verdict,
)
from sarand.core.health import compute_health_score
from sarand.core.package_summary import summarize_packages
from sarand.core.quick_context import build_quick_context
from sarand.core.risks import CHECKS_SKIPPED_MIN, evaluate_risks
from sarand.models.results import CommandResult, HealthScore, ReportData
from sarand.renderers import html, markdown

_CORE = Path(__file__).resolve().parent.parent / "python" / "sarand" / "core"


def _mk(state: str, kind: str = "tool") -> CommandResult:
    if state == STATE_PASSED:
        return CommandResult(kind=kind, returncode=0, summary="ok")
    if state == STATE_FAILED:
        return CommandResult(kind=kind, returncode=1, summary="bad", raw_output="bad")
    if state == STATE_SKIPPED:
        return CommandResult(
            kind=kind, returncode=0, summary="", skipped=True, skip_reason="no tool"
        )
    if state == STATE_INCONCLUSIVE:
        return CommandResult(
            kind=kind, returncode=0, summary="", inconclusive_reason="offline"
        )
    if state == STATE_UNAVAILABLE:
        return CommandResult(
            kind=kind, returncode=124, summary="", raw_output=SENTINEL_TIMEOUT
        )
    return CommandResult(
        kind=kind,
        returncode=0,
        summary="",
        skipped=True,
        skip_reason="x",
        inconclusive_reason="y",
    )


def _data(**groups: list[CommandResult]) -> ReportData:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "p"
        root.mkdir()
        data = FIXTURES["minimal"](root)
    data.test_results = groups.get("tests", [])
    data.quality_results = groups.get("quality", [])
    data.security_results = groups.get("security", [])
    data.health = compute_health_score(data)
    return data


def _fired(data: ReportData) -> dict[str, str]:
    return {r.rule_id: r.reason for r in evaluate_risks(data).risks}


STATES = (
    STATE_PASSED,
    STATE_FAILED,
    STATE_SKIPPED,
    STATE_INCONCLUSIVE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)


# --- the state function ---------------------------------------------------------


def test_every_state_is_produced_by_exactly_one_record_shape() -> None:
    assert [check_state(_mk(s)) for s in STATES] == list(STATES)


def test_no_verdict_states_are_every_state_but_passed_and_failed() -> None:
    assert set(NO_VERDICT_STATES) == set(STATES) - {STATE_PASSED, STATE_FAILED}
    for s in STATES:
        assert has_no_verdict(_mk(s)) == (s in NO_VERDICT_STATES)


# --- health ----------------------------------------------------------------------


def test_health_counts_a_state_as_ran_only_when_it_has_a_verdict() -> None:
    for s in STATES:
        health = compute_health_score(_data(tests=[_mk(s)]))
        assert health.breakdown["tooling"] == (
            15.0 if s in (STATE_PASSED, STATE_FAILED) else 0.0
        ), s


def _scores(health: HealthScore) -> tuple[float, float, float]:
    return (
        health.breakdown["tests"],
        health.breakdown["quality"],
        health.breakdown["security"],
    )


def test_a_test_suite_that_timed_out_is_not_called_a_failed_suite() -> None:
    health = compute_health_score(_data(tests=[_mk(STATE_UNAVAILABLE, "pytest")]))
    assert "One or more test suites failed." not in health.critical_failures
    assert "Fix failing tests before release." not in health.recommendations
    assert health.critical_failures == [
        "Test check could not run (pytest); it gave no verdict and earns no points."
    ]
    assert any(
        r.startswith("Test check could not run (pytest: timed out)")
        for r in health.recommendations
    )


def test_a_timeout_never_scores_better_than_the_same_suite_failing() -> None:
    passed = _mk(STATE_PASSED, "pytest")
    timeout = compute_health_score(_data(tests=[passed, _mk(STATE_UNAVAILABLE, "b")]))
    failing = compute_health_score(_data(tests=[passed, _mk(STATE_FAILED, "b")]))
    clean = compute_health_score(_data(tests=[passed, _mk(STATE_PASSED, "b")]))
    assert timeout.breakdown["tests"] == failing.breakdown["tests"] == 12.5
    assert timeout.breakdown["tests"] < clean.breakdown["tests"] == 25.0
    assert timeout.score < clean.score
    assert timeout.score <= failing.score


def test_a_timeout_in_quality_earns_no_points_and_is_not_a_lint_failure() -> None:
    passed = _mk(STATE_PASSED, "mypy")
    timeout = compute_health_score(
        _data(quality=[passed, _mk(STATE_UNAVAILABLE, "ruff")])
    )
    failing = compute_health_score(_data(quality=[passed, _mk(STATE_FAILED, "ruff")]))
    assert timeout.breakdown["quality"] == failing.breakdown["quality"] == 10.0
    assert not any("lint / format" in r for r in timeout.recommendations)
    assert any("lint / format" in r for r in failing.recommendations)


def test_a_real_test_failure_still_fails_next_to_a_timeout() -> None:
    health = compute_health_score(
        _data(tests=[_mk(STATE_FAILED, "a"), _mk(STATE_UNAVAILABLE, "b")])
    )
    assert "One or more test suites failed." in health.critical_failures
    assert health.breakdown["tests"] == 0.0
    assert any(
        c.startswith("Test check could not run") for c in health.critical_failures
    )


def test_a_quality_tool_not_found_is_not_a_lint_failure() -> None:
    missing = CommandResult(
        kind="ruff check",
        returncode=127,
        summary="",
        raw_output=f"{SENTINEL_NOT_FOUND} ruff",
    )
    health = compute_health_score(_data(quality=[missing, _mk(STATE_PASSED, "mypy")]))
    assert health.breakdown["quality"] == 10.0
    assert not any("lint / format" in r for r in health.recommendations)
    assert any(
        r.startswith("Quality check could not run") for r in health.recommendations
    )


def test_a_security_timeout_never_earns_the_clean_score() -> None:
    clean = compute_health_score(_data(security=[_mk(STATE_PASSED, "pip-audit")]))
    beside = compute_health_score(
        _data(
            security=[
                _mk(STATE_PASSED, "pip-audit"),
                _mk(STATE_UNAVAILABLE, "cargo audit"),
            ]
        )
    )
    assert clean.breakdown["security"] == 15.0
    assert beside.breakdown["security"] == 8.0
    assert beside.critical_failures == []
    assert any("earns no points" in r for r in beside.recommendations)


def test_a_security_failure_still_scores_lowest_next_to_a_timeout() -> None:
    health = compute_health_score(
        _data(
            security=[
                _mk(STATE_FAILED, "pip-audit"),
                _mk(STATE_UNAVAILABLE, "cargo audit"),
            ]
        )
    )
    assert health.breakdown["security"] == 5.0


def test_skipped_and_inconclusive_keep_their_scoring_from_before() -> None:
    passed = _mk(STATE_PASSED, "pytest")
    for state in (STATE_SKIPPED, STATE_INCONCLUSIVE):
        health = compute_health_score(_data(tests=[passed, _mk(state, "b")]))
        assert health.breakdown["tests"] == 25.0, state


def test_the_legacy_fields_keep_their_old_arithmetic() -> None:
    not_installed = CommandResult(
        kind="b", returncode=0, summary="", skipped=True, skip_reason="not installed"
    )
    health = compute_health_score(
        _data(tests=[_mk(STATE_UNAVAILABLE, "a"), not_installed])
    )
    assert health.checks_run == 1
    assert health.checks_skipped == ["b"]
    assert health.confidence == 0.5


def test_no_verdict_state_is_never_a_security_finding_or_policy_violation() -> None:
    for s in NO_VERDICT_STATES:
        health = compute_health_score(_data(security=[_mk(s, "cargo audit")]))
        assert health.critical_failures == [], s
        assert health.breakdown["security"] == 8.0, s


# --- risks: CHECKS-SKIPPED and its threshold ----------------------------------------


def test_the_threshold_is_unchanged() -> None:
    assert CHECKS_SKIPPED_MIN == 3


def test_each_no_verdict_state_alone_fires_at_the_threshold_and_not_below() -> None:
    for s in NO_VERDICT_STATES:
        below = _data(quality=[_mk(s, f"t{i}") for i in range(CHECKS_SKIPPED_MIN - 1)])
        at = _data(quality=[_mk(s, f"t{i}") for i in range(CHECKS_SKIPPED_MIN)])
        assert "CHECKS-SKIPPED" not in _fired(below), s
        assert "CHECKS-SKIPPED" in _fired(at), s


def test_a_mix_of_states_adds_up_across_groups() -> None:
    data = _data(
        tests=[_mk(STATE_SKIPPED, "a")],
        quality=[_mk(STATE_INCONCLUSIVE, "b")],
        security=[_mk(STATE_UNAVAILABLE, "c")],
    )
    reason = _fired(data)["CHECKS-SKIPPED"]
    assert reason.startswith("3 of 3 checks gave no verdict")
    assert (
        "1 skipped" in reason
        and "1 inconclusive" in reason
        and "1 unavailable" in reason
    )
    assert f"threshold {CHECKS_SKIPPED_MIN}" in reason


def test_passed_and_failed_checks_never_count_toward_the_threshold() -> None:
    data = _data(
        quality=[
            _mk(STATE_PASSED, "a"),
            _mk(STATE_FAILED, "b"),
            _mk(STATE_PASSED, "c"),
        ],
        security=[_mk(STATE_SKIPPED, "d"), _mk(STATE_SKIPPED, "e")],
    )
    assert "CHECKS-SKIPPED" not in _fired(data)


def test_the_security_risk_fires_only_for_the_failed_state() -> None:
    for s in STATES:
        fired = _fired(_data(security=[_mk(s, "cargo audit")]))
        assert ("SEC-CHECK-FAILED" in fired) == (s == STATE_FAILED), s


# --- Quick Context, package summary, badges -------------------------------------------


def test_quick_context_names_each_no_verdict_state_apart_and_not_as_failed() -> None:
    data = _data(
        tests=[_mk(STATE_UNAVAILABLE, "pytest")],
        quality=[_mk(STATE_SKIPPED, "ruff"), _mk(STATE_UNKNOWN, "odd")],
        security=[_mk(STATE_INCONCLUSIVE, "cargo audit")],
    )
    risks = build_quick_context(data).risks
    joined = "\n".join(risks)
    assert "could not run" in joined and "pytest" in joined
    assert "skipped" in joined and "contradictory record" in joined
    assert "could not finish" in joined
    assert "failed" not in joined


def test_package_summary_counts_no_verdict_with_the_skipped() -> None:
    results = [_mk(s, "web: tool") for s in STATES]
    summary = next(
        x for x in summarize_packages(["web"], results, [], []) if x.package == "web"
    )
    phase = summary.tests
    assert (phase.passed, phase.failed, phase.skipped) == (1, 1, 4)


def test_both_badges_name_every_state() -> None:
    expected = {
        STATE_PASSED: "PASS",
        STATE_FAILED: "FAIL",
        STATE_SKIPPED: "SKIP",
        STATE_INCONCLUSIVE: "INCONCLUSIVE",
        STATE_UNAVAILABLE: "UNAVAILABLE",
        STATE_UNKNOWN: "UNKNOWN",
    }
    for s, text in expected.items():
        assert markdown._status_badge(_mk(s)) == text
        assert f">{text}<" in html._status_badge_html(_mk(s))


def test_markdown_explains_an_unavailable_check_and_does_not_call_it_a_failure() -> (
    None
):
    data = _data(security=[_mk(STATE_UNAVAILABLE, "cargo audit")])
    output = markdown.render(data, include_source=False)
    assert "### cargo audit [UNAVAILABLE]" in output
    assert "*Unavailable:* the runner could not run this tool (timeout)" in output


# --- one source of truth ----------------------------------------------------------------

_RAW = re.compile(
    r"\.skipped\b|\.inconclusive\b|\.inconclusive_reason\b|execution_cause\("
)


def test_no_consumer_reads_the_raw_state_flags_itself() -> None:
    for name in ("health.py", "risks.py", "quick_context.py", "package_summary.py"):
        code = (_CORE / name).read_text(encoding="utf-8")
        lines = [
            line
            for line in code.splitlines()
            if _RAW.search(line) and not line.lstrip().startswith(("#", '"', "`"))
        ]
        assert lines == [], (name, lines)
