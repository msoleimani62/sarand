"""R13-G: every format tells the same facts about one report.

One synthetic-but-real report (the `advisories` golden fixture: the frozen Ramz
v0.3.2 cargo audit and cargo deny output, a skipped check, a check the runner
could not execute and a passing one, everything derived by the real pipeline) is
rendered in Markdown, HTML, JSON, SARIF and text, and the tests compare what
each says, structurally where the format is structured. No renderer is allowed to
recompute a fact: the shared lists live in core/report_views.py.
R13-G: همه‌ی قالب‌ها یک واقعیت را می‌گویند؛ مقایسه‌ی ساختاری، نه فقط snapshot.
"""

from __future__ import annotations

import html as html_lib
import json
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from _golden_fixtures import FIXTURES
from sarand.core.finding_identity import advisory_finding_id, failure_id
from sarand.core.health import compute_health_score
from sarand.core.report_views import (
    check_state_rows,
    collect_issues,
    failure_rows,
)
from sarand.models.results import CommandResult, ReportData
from sarand.renderers import html, json_renderer, markdown, sarif, text

_STATES = {"passed", "failed", "skipped", "inconclusive", "unavailable", "unknown"}
_BADGE = {
    "passed": "PASS",
    "failed": "FAIL",
    "skipped": "SKIP",
    "inconclusive": "INCONCLUSIVE",
    "unavailable": "UNAVAILABLE",
    "unknown": "UNKNOWN",
}
_SARIF_LEVELS = {"none", "note", "warning", "error"}


@contextmanager
def _report() -> Iterator[ReportData]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "p"
        root.mkdir()
        yield FIXTURES["advisories"](root)


def _all(data: ReportData) -> dict[str, Any]:
    out: dict[str, Any] = {}
    out["md"] = markdown.render(data, include_source=False)
    out["html"] = html.render(data, include_source=False)
    out["json"] = json.loads(json_renderer.render(data, include_source=False))
    out["sarif"] = json.loads(sarif.render(data))
    out["txt"] = text.render(data, include_source=False)
    return out


def _plain_html(page: str) -> str:
    return html_lib.unescape(re.sub(r"<[^>]+>", " ", page))


def _md_bullets(page: str, heading: str) -> int:
    block = page.split(f"## {heading}\n", 1)[1].split("\n## ", 1)[0]
    return sum(1 for line in block.splitlines() if line.startswith("- **"))


def _sarif_advisory_results(log: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in log["runs"][0]["results"] if r["ruleId"].startswith("RUSTSEC")]


# --- the core counts agree --------------------------------------------------------


def test_every_format_lists_the_same_advisories() -> None:
    with _report() as data:
        out = _all(data)
        expected = sorted(a.id for a in data.advisories)
        assert len(expected) == 18
        assert sorted(a["id"] for a in out["json"]["advisories"]) == expected
        assert sorted(r["ruleId"] for r in _sarif_advisory_results(out["sarif"])) == (
            expected
        )
        for adv_id in expected:
            assert f"| {adv_id} |" in out["md"], adv_id
            assert f"<td>{adv_id}</td>" in out["html"], adv_id
        assert "18 advisory(ies)" in out["md"]
        assert "18 advisory(ies)" in _plain_html(out["html"])
        assert "Advisories: 18" in out["txt"]


def test_advisories_keep_severity_and_applicability_everywhere() -> None:
    with _report() as data:
        out = _all(data)
        assert {a["applicability"] for a in out["json"]["advisories"]} == {"unknown"}
        for result in _sarif_advisory_results(out["sarif"]):
            props = result["properties"]
            assert props["applicability"] == "unknown"
            assert props["severity"] is None
            assert result["level"] in _SARIF_LEVELS
        assert out["md"].count("| unknown |") == 18
        assert out["html"].count("<td>unknown</td>") == 18


def test_sarif_advisory_level_matches_the_advisory_kind() -> None:
    with _report() as data:
        log = json.loads(sarif.render(data))
        kinds = {a.id: a.kind for a in data.advisories}
        for result in _sarif_advisory_results(log):
            expected = (
                "note"
                if kinds[result["ruleId"]] in ("unmaintained", "notice", "yanked")
                else "warning"
            )
            assert result["level"] == expected, result["ruleId"]


def test_failures_have_the_same_ids_in_every_format() -> None:
    with _report() as data:
        out = _all(data)
        ids = [failure_id(f) for f in data.failures]
        assert len(ids) == 4 and len(set(ids)) == 4
        assert [f["id"] for f in out["json"]["failures"]] == ids
        assert [
            f["id"] for f in out["sarif"]["runs"][0]["properties"]["sarand"]["failures"]
        ] == ids
        for fid in ids:
            assert f"`{fid}`" in out["md"], fid
            assert f"<td>{fid}</td>" in out["html"], fid
        assert "Failures: 4 classified" in out["txt"]


def test_failure_rows_are_the_single_source_of_the_tables() -> None:
    with _report() as data:
        rows = failure_rows(data)
        assert len(rows) == len(data.failures)
        assert _md_failure_rows(data) == len(rows)


def _md_failure_rows(data: ReportData) -> int:
    page = markdown.render(data, include_source=False)
    block = page.split("## Failure classification")[1].split("\n## ")[0]
    return sum(
        1 for line in block.splitlines() if line.startswith("| ") and "`" in line
    )


def test_critical_failures_and_known_issues_agree() -> None:
    with _report() as data:
        out = _all(data)
        assert data.health is not None
        crit = data.health.critical_failures
        assert out["json"]["health"]["critical_failures"] == crit
        for line in crit:
            assert f"- {line}" in out["md"]
            assert html_lib.escape(line) in out["html"]
        assert out["json"]["health"]["critical_ids"] == data.health.critical_ids
        sar = out["sarif"]["runs"][0]["properties"]["sarand"]["health"]
        assert sar["criticalFindingIds"] == data.health.critical_ids
        # Quick Context never has more critical lines than the report knows
        qc = out["json"]["quick_context"]["critical_findings"]
        assert len(qc) <= len(crit) + len(data.known_issues)
        assert out["json"]["known_issues"] == data.known_issues
        assert out["json"]["known_issue_ids"] == data.known_issue_ids
        for issue in data.known_issues:
            assert f"- {issue}" in out["md"]
            assert html_lib.escape(issue) in out["html"]


def test_one_condition_is_one_critical_line_in_quick_context() -> None:
    with _report() as data:
        qc = json.loads(json_renderer.render(data, include_source=False))[
            "quick_context"
        ]
        assert len(qc["critical_findings"]) == len(set(qc["critical_finding_ids"]))
        assert len(qc["critical_findings"]) == len(data.health.critical_failures)  # type: ignore[union-attr]


def test_a_check_that_could_not_run_is_not_a_known_issue_or_a_critical_line() -> None:
    with _report() as data:
        out = _all(data)
        # it is still a classified failure with its cause ...
        rows = {row[0]: row for row in failure_rows(data)}
        assert rows["ruff check"][3] == "tool_not_found"
        # ... but it gave no verdict, so it is not "a tool that failed" anywhere
        assert not any("ruff check" in text for text in data.known_issues)
        qc = out["json"]["quick_context"]["critical_findings"]
        assert not any("ruff check" in line for line in qc)
        assert not any("not classified" in line for line in qc)
        # and it stays visible as a gap
        assert any(
            "ruff check" in line for line in out["json"]["quick_context"]["risks"]
        )


# --- check states and coverage ----------------------------------------------------


def test_every_check_has_the_same_state_in_every_format() -> None:
    with _report() as data:
        out = _all(data)
        rows = check_state_rows(data)
        assert {state for _, _, state in rows} == {
            "passed",
            "failed",
            "skipped",
            "unavailable",
        }
        for group, key in (
            ("tests", "test_results"),
            ("quality", "quality_results"),
            ("security", "security_results"),
        ):
            json_states = [(r["kind"], r["state"]) for r in out["json"][key]]
            assert json_states == [(k, s) for g, k, s in rows if g == group]
        sarif_states = out["sarif"]["runs"][0]["properties"]["sarand"]["checkStates"]
        assert [(c["group"], c["check"], c["state"]) for c in sarif_states] == rows
        for _, kind, state in rows:
            assert f"### {kind} [{_BADGE[state]}]" in out["md"], (kind, state)
            assert re.search(
                rf"{re.escape(kind)}\s*<span class=\"badge[^>]*>{_BADGE[state]}<",
                out["html"],
            ), (kind, state)
        assert {s for _, _, s in rows} <= _STATES


def test_a_skipped_or_unavailable_check_is_never_shown_as_passed() -> None:
    with _report() as data:
        out = _all(data)
        states = {kind: state for _, kind, state in check_state_rows(data)}
        assert states["cargo clippy"] == "skipped"
        assert states["ruff check"] == "unavailable"
        sar = {
            c["check"]: c["state"]
            for c in out["sarif"]["runs"][0]["properties"]["sarand"]["checkStates"]
        }
        assert sar["cargo clippy"] == "skipped" and sar["ruff check"] == "unavailable"
        gaps = out["json"]["health"]["coverage_gaps"]
        assert {(g["kind"], g["state"]) for g in gaps} == {
            ("cargo clippy", "skipped"),
            ("ruff check", "unavailable"),
        }


def test_coverage_is_the_same_number_everywhere() -> None:
    with _report() as data:
        out = _all(data)
        assert data.health is not None
        health = data.health
        assert out["json"]["health"]["execution_coverage"] == health.execution_coverage
        sar = out["sarif"]["runs"][0]["properties"]["sarand"]["health"]
        assert sar["executionCoverage"] == health.execution_coverage
        assert sar["checksRequested"] == health.checks_requested
        assert sar["checksExecuted"] == health.checks_executed
        assert sar["coverageByGroup"] == health.coverage_by_group
        percent = f"{round(health.execution_coverage * 100)}%"  # type: ignore[operator]
        assert percent in out["md"]
        assert percent in _plain_html(out["html"])
        assert percent in out["txt"]
        assert (sar["score"], sar["grade"]) == (health.score, health.grade)
        assert f"{health.score} / {health.max_score}" in out["md"]


def test_unknown_coverage_is_null_and_never_zero_or_full() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "p"
        root.mkdir()
        data = FIXTURES["minimal"](root)
        data.health = compute_health_score(data)
        out = _all(data)
        assert out["json"]["health"]["execution_coverage"] is None
        assert (
            out["sarif"]["runs"][0]["properties"]["sarand"]["health"][
                "executionCoverage"
            ]
            is None
        )
        assert "0%" not in out["md"] and "100%" not in out["md"]


def test_inconclusive_list_is_always_present_in_json() -> None:
    with _report() as data:
        payload = json.loads(json_renderer.render(data, include_source=False))
        assert payload["health"]["checks_inconclusive"] == []
        data.quality_results.append(
            CommandResult(
                kind="slow-lint",
                returncode=0,
                summary="",
                inconclusive_reason="output was cut off",
            )
        )
        data.health = compute_health_score(data)
        payload = json.loads(json_renderer.render(data, include_source=False))
        assert payload["health"]["checks_inconclusive"] == ["slow-lint"]
        assert payload["quality_results"][-1]["state"] == "inconclusive"


# --- no tool line is counted twice -------------------------------------------------


def test_advisory_lines_are_not_listed_again_as_tool_output() -> None:
    with _report() as data:
        view = collect_issues(data)
        assert view.in_advisories == 15  # 13 audit kind lines + 2 deny heads
        messages = [i.message for i in view.errors + view.warnings]
        assert not any(m.startswith("error[vulnerability]") for m in messages)
        assert not any(re.match(r"^Warning:\s+\w+$", m) for m in messages)
        # other lines of the same tools stay
        assert any(m.startswith("error[rejected]") for m in messages)
        assert any("5 vulnerabilities found" in m for m in messages)


def test_issue_counts_match_in_markdown_html_sarif_and_quick_context() -> None:
    with _report() as data:
        out = _all(data)
        view = collect_issues(data)
        tool_results = [
            r
            for r in out["sarif"]["runs"][0]["results"]
            if r["ruleId"].startswith("tool-output")
        ]
        assert len(tool_results) == len(view.errors) + len(view.warnings)
        assert _md_bullets(out["md"], "Errors detected") == len(view.errors)
        assert _md_bullets(out["md"], "Warnings detected") == len(view.warnings)
        assert f"Errors detected ({len(view.errors)})" in _plain_html(out["html"])
        assert f"Warnings detected ({len(view.warnings)})" in _plain_html(out["html"])
        risks = out["json"]["quick_context"]["risks"]
        assert (
            f"tools reported {len(view.errors)} error(s) and "
            f"{len(view.warnings)} warning(s)"
        ) in risks
        assert "restate a dependency advisory" in out["md"]
        assert "restate a dependency advisory" in _plain_html(out["html"])


def test_a_line_is_dropped_only_when_its_tool_produced_an_advisory() -> None:
    from sarand.core.advisories import is_advisory_line
    from sarand.models.results import Issue

    line = Issue(source="cargo deny check", message="error[vulnerability]: x")
    assert is_advisory_line(line, []) is False
    with _report() as data:
        assert is_advisory_line(line, data.advisories) is True
        other_tool = Issue(source="cargo outdated", message="error[vulnerability]: x")
        assert is_advisory_line(other_tool, data.advisories) is False
        license_line = Issue(source="cargo deny check", message="error[rejected]: y")
        assert is_advisory_line(license_line, data.advisories) is False
        assert (
            is_advisory_line(
                Issue(source="cargo audit", message="error: 5 vulnerabilities found!"),
                data.advisories,
            )
            is False
        )


# --- SARIF stays a valid, honest SARIF --------------------------------------------


def test_sarif_is_structurally_valid_2_1_0() -> None:
    with _report() as data:
        log = json.loads(sarif.render(data))
        assert log["version"] == "2.1.0"
        assert log["$schema"].endswith("sarif-schema-2.1.0.json")
        (run,) = log["runs"]
        driver = run["tool"]["driver"]
        assert driver["name"] == "sarand" and driver["informationUri"].startswith(
            "https://"
        )
        rule_ids = [r["id"] for r in driver["rules"]]
        assert len(rule_ids) == len(set(rule_ids))
        for result in run["results"]:
            assert result["ruleId"] in rule_ids
            assert result["level"] in _SARIF_LEVELS
            assert (
                isinstance(result["message"]["text"], str) and result["message"]["text"]
            )
            for value in result.get("partialFingerprints", {}).values():
                assert isinstance(value, str) and value
            assert isinstance(result.get("properties", {}), dict)
        assert isinstance(run["properties"], dict)


def test_sarif_advisory_fingerprints_are_the_finding_ids_and_stable() -> None:
    with _report() as data:
        first = json.loads(sarif.render(data))
        second = json.loads(sarif.render(data))
        wanted = {advisory_finding_id(a) for a in data.advisories}
        got = {
            r["partialFingerprints"]["sarandFindingId/v1"]
            for r in _sarif_advisory_results(first)
        }
        assert got == wanted and len(got) == 18
        assert first == second


def test_every_format_is_deterministic() -> None:
    with _report() as data:
        assert _all(data) == _all(data)
