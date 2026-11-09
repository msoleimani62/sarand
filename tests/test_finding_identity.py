"""R13-F: one underlying problem has one stable id, and the report ties the places
that tell it together without guessing from similar words.

Evidence behind the tests: the real Ramz v0.3.2 outputs frozen in
tests/data/ramz_v0_3_2. Every behaviour has a true-duplicate case and a
similar-but-distinct case. Dependency-free like the other tests.
R13-F: هر مشکل یک شناسه‌ی پایدار دارد؛ شباهت متن معیار یکی‌بودن نیست.
"""

from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

from _golden_fixtures import FIXTURES
from sarand.constants import (
    FAILURE_DEPENDENCY_POLICY,
    FAILURE_SECURITY_FINDING,
    FAILURE_SECURITY_TOOL,
)
from sarand.core.failures import (
    classify_failures,
    known_issue_entries,
    known_issues_from_failures,
)
from sarand.core.finding_identity import (
    condition_id,
    failure_id,
    finding_id,
    kind_of,
    unique_ids,
)
from sarand.core.health import compute_health_score
from sarand.core.quick_context import build_quick_context
from sarand.core.risks import evaluate_risks
from sarand.models.results import CommandResult, Failure, HealthScore, ReportData
from sarand.renderers import json_renderer
from sarand.utils.command import make_command_result

_DATA = Path(__file__).parent / "data" / "ramz_v0_3_2"
_AUDIT = (_DATA / "cargo_audit.txt").read_text(encoding="utf-8")
_DENY = (_DATA / "cargo_deny_excerpt.txt").read_text(encoding="utf-8")


def _audit(kind: str = "cargo audit") -> CommandResult:
    return make_command_result(kind, 1, _AUDIT, 1.0)


def _data(security: list[CommandResult]) -> ReportData:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "p"
        root.mkdir()
        data = FIXTURES["minimal"](root)
    data.test_results = []
    data.quality_results = []
    data.security_results = security
    data.failures = classify_failures([], [], security)
    entries = known_issue_entries(data.failures)
    data.known_issues = [text for _, text in entries]
    data.known_issue_ids = [fid for fid, _ in entries]
    data.health = compute_health_score(data)
    return data


# --- the id itself --------------------------------------------------------------


def test_an_id_is_readable_stable_and_independent_of_order() -> None:
    a = condition_id(FAILURE_SECURITY_FINDING, ["cargo deny", "cargo audit"])
    b = condition_id(
        FAILURE_SECURITY_FINDING, ["cargo audit", "cargo deny", "cargo audit"]
    )
    assert a == b
    assert kind_of(a) == FAILURE_SECURITY_FINDING
    assert len(a.split(":")[1]) == 12
    assert finding_id("x", "a") == finding_id("x", " a ")


def test_similar_but_distinct_conditions_keep_distinct_ids() -> None:
    audit = condition_id(FAILURE_SECURITY_FINDING, ["cargo audit"])
    deny = condition_id(FAILURE_SECURITY_FINDING, ["cargo deny"])
    both = condition_id(FAILURE_SECURITY_FINDING, ["cargo audit", "cargo deny"])
    other_kind = condition_id(FAILURE_DEPENDENCY_POLICY, ["cargo audit"])
    assert len({audit, deny, both, other_kind}) == 4
    # a separator inside a part cannot make two different tuples collide
    assert finding_id("k", "a", "bc") != finding_id("k", "ab", "c")


def test_a_failure_id_uses_structure_not_evidence() -> None:
    base = Failure(tool="ruff", group="quality", category="lint_failure", subject="x")
    same = Failure(
        tool="ruff",
        group="quality",
        category="lint_failure",
        subject="x",
        returncode=9,
        summary="other words",
        signals=("s",),
    )
    other_subject = Failure(
        tool="ruff", group="quality", category="lint_failure", subject="y"
    )
    other_group = Failure(
        tool="ruff", group="security", category="lint_failure", subject="x"
    )
    assert failure_id(base) == failure_id(same)
    assert (
        len({failure_id(base), failure_id(other_subject), failure_id(other_group)}) == 3
    )


def test_unique_ids_keeps_first_seen_order_and_drops_empty() -> None:
    assert unique_ids(["b", "", "a", "b"]) == ["b", "a"]


# --- health critical failures and known issues ----------------------------------


def test_health_ids_match_the_texts_one_to_one() -> None:
    data = _data([_audit()])
    assert data.health is not None
    assert len(data.health.critical_ids) == len(data.health.critical_failures) == 1
    assert kind_of(data.health.critical_ids[0]) == FAILURE_SECURITY_FINDING


def test_the_same_condition_has_one_id_in_health_and_known_issues() -> None:
    data = _data([_audit()])
    assert data.health is not None
    assert data.health.critical_ids[0] in data.known_issue_ids


def test_a_condition_is_never_added_twice_to_the_critical_list() -> None:
    results = [_audit(), _audit()]
    data = _data(results)
    assert data.health is not None
    assert len(data.health.critical_failures) == len(set(data.health.critical_ids))


def test_two_tools_failing_differently_are_two_critical_failures() -> None:
    licenses = "error[rejected]: failed to satisfy license requirements\n   ┌─ Cargo.lock:3:1\n"
    deny = make_command_result("cargo deny check", 4, licenses, 1.0)
    data = _data([_audit(), deny])
    assert data.health is not None
    kinds = sorted(kind_of(i) for i in data.health.critical_ids)
    assert kinds == [FAILURE_DEPENDENCY_POLICY, FAILURE_SECURITY_FINDING]
    assert len(data.health.critical_failures) == 2


# --- Quick Context --------------------------------------------------------------


def test_quick_context_shows_one_condition_once_and_keeps_the_known_issue() -> None:
    data = _data([_audit()])
    assert data.known_issues, "the known issue exists in the report"
    qc = build_quick_context(data)
    assert len(qc.critical_findings) == 1
    assert qc.critical_findings[0].startswith("Security finding reported by")
    assert len(qc.critical_finding_ids) == 1
    assert qc.critical_finding_ids[0] == data.health.critical_ids[0]  # type: ignore[union-attr]
    # nothing is dropped from the report itself
    assert data.known_issues == known_issues_from_failures(data.failures)


def test_a_known_issue_of_a_different_condition_is_not_merged() -> None:
    data = _data([_audit()])
    assert data.health is not None
    data.known_issues.append("Linker 'cc' not found")
    data.known_issue_ids.append(finding_id(FAILURE_SECURITY_TOOL, "cargo audit"))
    qc = build_quick_context(data)
    assert len(qc.critical_findings) == 2
    assert qc.critical_findings[1] == "Linker 'cc' not found"


def test_without_ids_nothing_is_merged_even_if_the_text_is_identical() -> None:
    data = _data([])
    data.health = HealthScore(critical_failures=["same text"], critical_ids=[])
    data.known_issues = ["same text"]
    data.known_issue_ids = []
    qc = build_quick_context(data)
    assert qc.critical_findings == ["same text", "same text"]
    assert qc.critical_finding_ids == []


def test_identical_sentences_with_different_ids_stay_separate() -> None:
    data = _data([])
    data.health = HealthScore(
        critical_failures=["Problem found."],
        critical_ids=[finding_id("health", "a")],
    )
    data.known_issues = ["Problem found."]
    data.known_issue_ids = [finding_id("known", "b")]
    assert build_quick_context(data).critical_findings == [
        "Problem found.",
        "Problem found.",
    ]


def test_the_more_counter_counts_only_unique_known_issues() -> None:
    data = _data([])
    shared = finding_id("both", "x")
    data.health = HealthScore(critical_failures=["h"], critical_ids=[shared])
    data.known_issues = [f"k{i}" for i in range(8)] + ["dup"]
    data.known_issue_ids = [finding_id("k", str(i)) for i in range(8)] + [shared]
    qc = build_quick_context(data)
    assert qc.critical_findings[-1] == "(+3 more known issue(s))"
    assert "dup" not in qc.critical_findings


def test_quick_context_is_deterministic_and_does_not_mutate() -> None:
    data = _data([_audit()])
    before = copy.deepcopy(data)
    assert build_quick_context(data) == build_quick_context(data)
    assert data == before


# --- risks ----------------------------------------------------------------------


def test_health_critical_says_when_it_restates_the_failed_security_check() -> None:
    data = _data([_audit()])
    fired = {r.rule_id: r for r in evaluate_risks(data).risks}
    assert "SEC-CHECK-FAILED" in fired
    assert "restate the failed security check" in fired["HEALTH-CRITICAL"].reason
    assert fired["HEALTH-CRITICAL"].reason.startswith("1 critical failure(s)")


def test_health_critical_stays_plain_without_a_security_overlap() -> None:
    data = _data([])
    data.health = HealthScore(
        critical_failures=["tests failed"],
        critical_ids=[finding_id("test_suite_failed", "t")],
    )
    fired = {r.rule_id: r for r in evaluate_risks(data).risks}
    assert (
        fired["HEALTH-CRITICAL"].reason == "1 critical failure(s) in the health score"
    )


def test_health_critical_counts_distinct_ids_not_entries() -> None:
    data = _data([])
    same = finding_id("k", "a")
    data.health = HealthScore(
        critical_failures=["a", "a again"], critical_ids=[same, same]
    )
    fired = {r.rule_id: r for r in evaluate_risks(data).risks}
    assert (
        fired["HEALTH-CRITICAL"].reason == "1 critical failure(s) in the health score"
    )


# --- serialization --------------------------------------------------------------


def test_ids_survive_json_and_are_the_same_on_every_run() -> None:
    first = json.loads(json_renderer.render(_data([_audit()]), include_source=False))
    second = json.loads(json_renderer.render(_data([_audit()]), include_source=False))
    assert first["schema_version"] == "1.5"
    assert first["health"]["critical_ids"] == second["health"]["critical_ids"]
    assert first["known_issue_ids"] == second["known_issue_ids"]
    assert (
        first["quick_context"]["critical_finding_ids"]
        == (second["quick_context"]["critical_finding_ids"])
    )
    ids = [f["id"] for f in first["failures"]]
    assert ids == [f["id"] for f in second["failures"]]
    assert all(
        i.split(":")[0] == f["category"]
        for i, f in zip(ids, first["failures"], strict=True)
    )
    assert first["health"]["critical_ids"][0] in first["known_issue_ids"]


def test_a_report_without_failures_gets_no_id_keys() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "p"
        root.mkdir()
        data = FIXTURES["minimal"](root)
    payload = json.loads(json_renderer.render(data, include_source=False))
    assert "known_issue_ids" not in payload
    assert "failures" not in payload
    assert "critical_ids" not in (payload["health"] or {})
