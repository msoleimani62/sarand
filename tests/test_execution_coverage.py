"""R13-B: execution coverage = executed / requested (core/execution_coverage.py).

The mandatory synthetic matrix of the R13 master prompt (14 cases), each checked
in the model, in the JSON report and in every human-readable renderer; plus the
legacy `confidence` field, which must keep its old arithmetic.
R13-B: ماتریس ۱۴حالتهٔ پرامپت، در مدل، JSON و رندرهای قابل‌خواندن.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from _golden_fixtures import FIXTURES
from sarand.constants import SENTINEL_NOT_FOUND, SENTINEL_OS_ERROR, SENTINEL_TIMEOUT
from sarand.core.execution_coverage import (
    NOTE,
    coverage_empty_groups,
    coverage_headline,
    coverage_lines,
    coverage_not_run,
    coverage_oneline,
    coverage_percent,
    summarize_coverage,
)
from sarand.core.health import compute_health_score
from sarand.models.results import CommandResult, HealthScore, ReportData
from sarand.renderers import html, json_renderer, markdown, text


def _p(kind: str = "ok") -> CommandResult:
    return CommandResult(kind=kind, returncode=0, summary="")


def _f(kind: str = "bad") -> CommandResult:
    return CommandResult(kind=kind, returncode=1, summary="", raw_output="boom")


def _s(kind: str = "skip", reason: str = "tool not installed") -> CommandResult:
    return CommandResult(
        kind=kind, returncode=0, summary="", skipped=True, skip_reason=reason
    )


def _i(kind: str = "inc", reason: str = "the network was unreachable") -> CommandResult:
    return CommandResult(
        kind=kind, returncode=0, summary="", inconclusive_reason=reason
    )


def _u(kind: str, rc: int, out: str) -> CommandResult:
    return CommandResult(kind=kind, returncode=rc, summary="", raw_output=out)


def _data(
    tests: list[CommandResult] | None = None,
    quality: list[CommandResult] | None = None,
    security: list[CommandResult] | None = None,
) -> ReportData:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "p"
        root.mkdir()
        data = FIXTURES["minimal"](root)
    data.test_results = tests or []
    data.quality_results = quality or []
    data.security_results = security or []
    data.health = compute_health_score(data)
    return data


def _health(data: ReportData) -> HealthScore:
    assert data.health is not None
    return data.health


def _json_health(data: ReportData) -> dict[str, object]:
    payload = json.loads(json_renderer.render(data, include_source=False))
    health = payload["health"]
    assert isinstance(health, dict)
    return health


def _agree_everywhere(data: ReportData) -> None:
    """The model, the JSON and every human-readable report say the same thing."""
    h = _health(data)
    j = _json_health(data)
    assert j["execution_coverage"] == h.execution_coverage
    assert j["checks_requested"] == h.checks_requested
    assert j["checks_executed"] == h.checks_executed
    assert [g["state"] for g in j["coverage_gaps"]] == [  # type: ignore[attr-defined]
        g.state for g in h.coverage_gaps
    ]
    headline = coverage_headline(h)
    for out in (markdown.render(data), text.render(data), html.render(data)):
        assert headline.removeprefix("execution coverage ") in out
        assert "confidence" not in out.replace("HEALTH-LOW-CONFIDENCE", "").lower()


# --- the 14 cases of the master prompt --------------------------------------


def test_case_1_every_check_executed_successfully() -> None:
    data = _data([_p("a")], [_p("b")], [_p("c")])
    h = _health(data)
    assert (h.execution_coverage, h.checks_executed, h.checks_requested) == (1.0, 3, 3)
    assert h.coverage_gaps == []
    _agree_everywhere(data)


def test_case_2_every_check_executed_with_findings_still_counts_as_executed() -> None:
    data = _data([_f("a")], [_f("b")], [_f("c")])
    h = _health(data)
    assert (h.execution_coverage, h.checks_executed) == (1.0, 3)
    _agree_everywhere(data)


def test_case_3_some_passed_and_some_failed() -> None:
    data = _data([_p("a"), _f("b")], [_p("c")], [_f("d")])
    assert _health(data).execution_coverage == 1.0
    _agree_everywhere(data)


def test_case_4_some_checks_skipped() -> None:
    data = _data([_p("a")], [_p("b"), _s("c")], [_s("d")])
    h = _health(data)
    assert (h.execution_coverage, h.checks_executed, h.checks_requested) == (0.5, 2, 4)
    assert [(g.kind, g.state) for g in h.coverage_gaps] == [
        ("c", "skipped"),
        ("d", "skipped"),
    ]
    assert (
        coverage_not_run(h)
        == "c (skipped: tool not installed), d (skipped: tool not installed)"
    )
    _agree_everywhere(data)


def test_case_5_some_checks_inconclusive() -> None:
    data = _data([_p("a")], [_i("b")], [])
    h = _health(data)
    assert h.execution_coverage == 0.5
    assert [(g.kind, g.state, g.reason) for g in h.coverage_gaps] == [
        ("b", "inconclusive", "the network was unreachable"),
    ]
    _agree_everywhere(data)


def test_case_6_some_checks_unavailable_timeout_not_found_and_os_error() -> None:
    data = _data(
        [_p("a")],
        [
            _u("b", 124, f"partial\n{SENTINEL_TIMEOUT}"),
            _u("c", 127, f"{SENTINEL_NOT_FOUND} c"),
        ],
        [_u("d", 1, f"{SENTINEL_OS_ERROR} denied")],
    )
    h = _health(data)
    assert (h.execution_coverage, h.checks_executed, h.checks_requested) == (0.25, 1, 4)
    assert [(g.kind, g.state, g.reason) for g in h.coverage_gaps] == [
        ("b", "unavailable", "timeout"),
        ("c", "unavailable", "tool_not_found"),
        ("d", "unavailable", "os_error"),
    ]
    _agree_everywhere(data)


def test_case_7_all_checks_skipped_is_zero_not_unavailable() -> None:
    data = _data([_s("a")], [_s("b")], [_s("c")])
    h = _health(data)
    assert h.execution_coverage == 0.0 and h.checks_requested == 3
    assert coverage_headline(h) == (
        "execution coverage 0% (0 of 3 requested checks ran to a verdict)"
    )
    _agree_everywhere(data)


def test_case_8_zero_expected_checks_has_no_percentage_never_100() -> None:
    data = _data()
    h = _health(data)
    assert h.execution_coverage is None and h.checks_requested == 0
    assert _json_health(data)["execution_coverage"] is None
    assert (
        coverage_headline(h)
        == "execution coverage not available (no check was requested)"
    )
    for out in (markdown.render(data), text.render(data), html.render(data)):
        assert "not available (no check was requested)" in out
        assert "execution coverage 100%" not in out.lower()
    assert h.confidence == 1.0  # the LEGACY value, deprecated and not displayed


def test_case_9_an_empty_repository_gives_the_same_unavailable_state() -> None:
    data = _data()
    assert data.stats.total_files >= 0
    h = _health(data)
    assert h.execution_coverage is None and h.coverage_gaps == []
    assert h.coverage_by_group == {
        "tests": {"requested": 0, "executed": 0},
        "quality": {"requested": 0, "executed": 0},
        "security": {"requested": 0, "executed": 0},
    }


def test_case_10_partial_analyzer_execution_names_the_groups_with_nothing_requested() -> (
    None
):
    data = _data(None, [_p("b")], [_p("c")])
    h = _health(data)
    assert h.execution_coverage == 1.0
    assert coverage_empty_groups(h) == ["tests"]
    assert "No check was requested in: tests" in coverage_lines(h)
    assert "No check was requested in: tests" in markdown.render(data)


def test_case_11_missing_result_records_are_not_invented() -> None:
    data = _data([_p("a")], None, None)
    h = _health(data)
    assert (h.checks_requested, h.checks_executed) == (1, 1)
    assert coverage_empty_groups(h) == ["quality", "security"]


def test_case_12_duplicate_records_count_one_by_one_and_differ_from_the_legacy_value() -> (
    None
):
    data = _data([_p("ruff"), _p("ruff")], [_s("mypy"), _s("mypy")], [])
    h = _health(data)
    assert (h.execution_coverage, h.checks_requested, h.checks_executed) == (0.5, 4, 2)
    # LEGACY arithmetic, unchanged: skipped kinds are counted once, ran per record
    assert h.confidence == round(2 / (2 + 1), 2)
    assert h.execution_coverage != h.confidence


def test_case_13_an_invalid_or_contradictory_record_is_unknown_and_visible() -> None:
    bad = CommandResult(
        kind="odd",
        returncode=0,
        summary="",
        skipped=True,
        skip_reason="s",
        inconclusive_reason="i",
    )
    data = _data([_p("a"), bad])
    h = _health(data)
    assert h.execution_coverage == 0.5
    assert [(g.kind, g.state) for g in h.coverage_gaps] == [("odd", "unknown")]
    assert "contradictory record" in h.coverage_gaps[0].reason
    _agree_everywhere(data)


def test_case_14_a_mixture_of_executed_skipped_inconclusive_and_unavailable() -> None:
    data = _data(
        [_p("a"), _f("b")],
        [_s("c"), _i("d")],
        [_u("e", 124, SENTINEL_TIMEOUT)],
    )
    h = _health(data)
    assert (h.execution_coverage, h.checks_executed, h.checks_requested) == (0.4, 2, 5)
    assert [g.state for g in h.coverage_gaps] == [
        "skipped",
        "inconclusive",
        "unavailable",
    ]
    assert h.coverage_by_group["quality"] == {"requested": 2, "executed": 0}
    _agree_everywhere(data)


# --- formula, rounding, wording, compatibility ---------------------------------


def test_the_fraction_is_rounded_to_four_places_and_the_percent_half_up() -> None:
    assert summarize_coverage([_p()] * 6 + [_s()] * 5, [], []).coverage == round(
        6 / 11, 4
    )
    assert coverage_percent(6 / 11) == 55
    assert coverage_percent(0.725) == 73 and coverage_percent(0.5) == 50
    assert coverage_percent(1.0) == 100 and coverage_percent(0.0) == 0


def test_the_summary_is_deterministic_and_does_not_touch_its_input() -> None:
    results = [_p("a"), _s("b"), _i("c")]
    before = [(r.kind, r.skipped, r.inconclusive_reason) for r in results]
    first = summarize_coverage(results, [], [])
    assert first == summarize_coverage(results, [], [])
    assert before == [(r.kind, r.skipped, r.inconclusive_reason) for r in results]


def test_the_not_run_list_is_capped_with_the_hidden_count() -> None:
    data = _data([_s(f"t{i}") for i in range(9)])
    text_ = coverage_not_run(_health(data))
    assert text_.count("(skipped") == 6 and text_.endswith("(+3 more)")


def test_the_oneline_and_the_lines_use_the_same_basis() -> None:
    h = _health(_data([_p("a"), _s("b")]))
    assert coverage_oneline(h).startswith(coverage_headline(h))
    assert coverage_lines(h)[-1] == NOTE
    assert (
        "not analytical" not in NOTE and "not measure how complete or correct" in NOTE
    )


def test_the_legacy_confidence_keeps_its_old_arithmetic_for_the_old_cases() -> None:
    full = _health(_data([_p("a")], [_p("b")], [_p("c")]))
    assert full.confidence == 1.0
    half = _health(_data([_p("a")], [_s("b")], []))
    assert half.confidence == 0.5
    assert _health(_data([_p("a")], [_i("b")], [])).confidence == 0.5


def test_json_keeps_the_deprecated_field_next_to_the_new_ones() -> None:
    j = _json_health(_data([_p("a")], [_s("b")], []))
    assert {
        "confidence",
        "execution_coverage",
        "checks_requested",
        "checks_executed",
        "coverage_by_group",
        "coverage_gaps",
    } <= set(j)
    assert j["confidence"] == 0.5 and j["execution_coverage"] == 0.5
