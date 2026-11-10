"""R13-H: the section 11.5 criteria, pinned on the frozen real Ramz v0.3.2 output.

The tool output here is real (tests/data/ramz_v0_3_2, see its README: Ramz
7252b1c with the local Cargo.lock change, produced by sarand 160c589). The checks
around it mirror the historical Ramz run: a passing test suite, three linters and
two security tools that fail, and the passing rest, all taken through the real
pipeline (classification, known issues, advisories, health, every renderer).
The historical report said: "Compilation or lint errors were detected", "confidence
100%", counted 8 BUG test comments as markers, and showed a security finding and a
license violation as one thing. These tests keep each of those fixed.
R13-H: معیارهای بخش ۱۱٫۵ روی خروجی واقعیِ منجمد Ramz.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from _golden_fixtures import FIXTURES
from sarand.core.advisories import collect_advisories
from sarand.core.failures import classify_failures, known_issue_entries
from sarand.core.health import compute_health_score
from sarand.core.markers import is_actionable
from sarand.core.report_views import collect_issues
from sarand.models.results import CommandResult, ReportData, TodoItem
from sarand.renderers import html, json_renderer, markdown, sarif, text
from sarand.utils.command import make_command_result

_DATA = Path(__file__).parent / "data" / "ramz_v0_3_2"
_BUG_COMMENT = "// this test reproduces the exact bug we found and fixed: the"


def _real(name: str) -> str:
    return (_DATA / name).read_text(encoding="utf-8")


def _ok(kind: str) -> CommandResult:
    return CommandResult(kind=kind, returncode=0, summary="ok")


def _ramz(with_bug_markers: bool = True) -> ReportData:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "ramz"
        root.mkdir()
        data = FIXTURES["minimal"](root)
    data.test_results = [_ok("cargo test")]
    data.quality_results = [
        _ok("cargo fmt --check"),
        _ok("cargo clippy"),
        make_command_result("actionlint", 1, _real("actionlint.txt"), 1.0),
        make_command_result("yamllint", 1, _real("yamllint.txt"), 1.0),
        _ok("taplo lint"),
        make_command_result("markdownlint", 1, _real("markdownlint_excerpt.txt"), 1.0),
    ]
    data.security_results = [
        make_command_result("cargo audit", 1, _real("cargo_audit.txt"), 1.0),
        make_command_result(
            "cargo deny check", 5, _real("cargo_deny_excerpt.txt"), 1.0
        ),
        _ok("gitleaks"),
        _ok("syft (SBOM)"),
        _ok("lockfile check"),
    ]
    data.failures = classify_failures(
        data.test_results, data.quality_results, data.security_results
    )
    entries = known_issue_entries(data.failures)
    data.known_issues = [text_ for _, text_ in entries]
    data.known_issue_ids = [fid for fid, _ in entries]
    data.advisories = collect_advisories(data.security_results)
    data.todos = (
        [
            TodoItem(
                path="core/src/resume.rs",
                line_number=n,
                kind="BUG",
                content=_BUG_COMMENT,
            )
            for n in (202, 221, 229)
        ]
        if with_bug_markers
        else []
    )
    data.health = compute_health_score(data)
    return data


def _every_format(data: ReportData) -> dict[str, str]:
    return {
        "md": markdown.render(data, include_source=False),
        "html": html.render(data, include_source=False),
        "json": json_renderer.render(data, include_source=False),
        "sarif": sarif.render(data),
        "txt": text.render(data, include_source=False),
    }


def test_three_linters_failing_is_never_called_a_compilation_failure() -> None:
    data = _ramz()
    categories = {f.tool: f.category for f in data.failures}
    for linter in ("actionlint", "yamllint", "markdownlint"):
        assert categories[linter] == "lint_failure", linter
    assert not any(f.category == "compilation_failure" for f in data.failures)
    for name, page in _every_format(data).items():
        assert "Compilation or lint errors were detected" not in page, name
        assert "Compilation errors were reported" not in page, name


def test_the_health_score_says_coverage_not_certainty() -> None:
    data = _ramz()
    assert data.health is not None
    assert data.health.execution_coverage == 1.0
    assert (data.health.checks_requested, data.health.checks_executed) == (12, 12)
    pages = _every_format(data)
    for name in ("md", "txt"):
        assert (
            "execution coverage 100% (12 of 12 requested checks ran to a verdict)"
            in (pages[name])
            or "Execution coverage:** 100% (12 of 12" in pages[name]
        ), name
        assert "confidence 100%" not in pages[name], name
    assert "does not measure how complete or correct the analysis is" in pages["md"]


def test_historical_bug_comments_are_shown_but_not_scored() -> None:
    with_markers, without = _ramz(True), _ramz(False)
    assert [is_actionable(t) for t in with_markers.todos] == [False, False, False]
    assert with_markers.health is not None and without.health is not None
    assert with_markers.health.breakdown["code"] == without.health.breakdown["code"]
    assert with_markers.health.score == without.health.score
    payload = json.loads(json_renderer.render(with_markers, include_source=False))
    assert {t["category"] for t in payload["todos"]} == {"historical"}
    sar = json.loads(sarif.render(with_markers))
    todo_results = [
        r for r in sar["runs"][0]["results"] if r["ruleId"].startswith("todo/")
    ]
    assert {r["properties"]["category"] for r in todo_results} == {"historical"}
    assert "3 historical" in markdown.render(with_markers, include_source=False)


def test_a_security_finding_a_policy_violation_and_a_tool_failure_stay_apart() -> None:
    data = _ramz()
    assert data.health is not None
    critical = data.health.critical_failures
    assert len(critical) == 2
    assert critical[0].startswith("Security finding reported by cargo audit")
    assert "exploitability is not assessed" in critical[0]
    assert critical[1].startswith("Dependency policy violation reported by cargo deny")
    assert critical[1].endswith("not a vulnerability.")
    kinds = {f.category for f in data.failures if f.group == "security"}
    assert kinds == {"security_finding_detected", "dependency_policy_failure"}
    assert "security_tool_failure" not in kinds
    # no advisory is declared exploitable, none gets an invented severity
    assert {a.applicability for a in data.advisories} == {"unknown"}
    assert {a.severity for a in data.advisories} == {None}
    assert len(data.advisories) == 18


def test_counts_agree_in_markdown_json_and_sarif() -> None:
    data = _ramz()
    pages = _every_format(data)
    payload = json.loads(pages["json"])
    log = json.loads(pages["sarif"])
    results = log["runs"][0]["results"]
    view = collect_issues(data)
    advisories = [r for r in results if r["ruleId"].startswith("RUSTSEC")]
    tool = [r for r in results if r["ruleId"].startswith("tool-output")]
    assert len(advisories) == len(payload["advisories"]) == len(data.advisories) == 18
    assert len(tool) == len(view.errors) + len(view.warnings)
    assert pages["md"].count("| RUSTSEC-") == 18
    assert payload["health"]["critical_failures"] == data.health.critical_failures  # type: ignore[union-attr]
    assert (
        payload["health"]["critical_ids"]
        == log["runs"][0]["properties"]["sarand"]["health"]["criticalFindingIds"]
    )
    states = [
        r["state"]
        for k in ("test_results", "quality_results", "security_results")
        for r in payload[k]
    ]
    assert states.count("failed") == 5 and states.count("passed") == 7
    sar_states = [
        c["state"] for c in log["runs"][0]["properties"]["sarand"]["checkStates"]
    ]
    assert sar_states == states
    # the same fact told twice (a health critical failure and a known issue) is
    # one critical finding in Quick Context
    qc = payload["quick_context"]["critical_findings"]
    assert (
        len(qc) == 2 and len(set(payload["quick_context"]["critical_finding_ids"])) == 2
    )


def test_the_health_formula_decides_the_score_not_the_classification() -> None:
    """Classification changes text and counts, never the points: the same results
    score the same whether or not they are classified (weights are untouched)."""
    data = _ramz()
    assert data.health is not None
    before = dict(data.health.breakdown)
    data.failures = []
    data.known_issues = []
    data.known_issue_ids = []
    data.advisories = []
    again = compute_health_score(data)
    assert again.breakdown == before
    assert again.score == data.health.score
