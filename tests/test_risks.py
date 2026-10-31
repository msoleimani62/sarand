"""Regression tests for Quick Context R11b: the nine-rule risk list
(`core/risks.py`) and the architecture block (`core/architecture.py`),
docs/QUICK_CONTEXT_DESIGN.md sections 6.1-6.3.

Every rule has three tests (fires, stays quiet, data absent), as the design
requires. Dependency-free like the other tests (no `import pytest`).
تست‌های رگرسیون R11b: ریسک‌های نُه‌قاعده‌ای و بلوک معماری؛ هر قاعده سه تست دارد.
"""

from __future__ import annotations

import copy
import json
import tempfile
from collections.abc import Callable
from dataclasses import asdict
from html import escape
from pathlib import Path

from _golden_fixtures import FIXTURES
from sarand.core.architecture import build_architecture, l3_lines
from sarand.core.risks import (
    CHECKS_SKIPPED_MIN,
    CONFIDENCE_MIN,
    DISPLAY_CAP,
    LARGE_FILE_BYTES,
    RULES,
    TODO_CLUSTER_MIN,
    evaluate_risks,
)
from sarand.models.results import (
    CommandResult,
    Component,
    ComponentsInfo,
    ComposeFile,
    ComposeInfo,
    ComposeService,
    GitSnapshot,
    HealthScore,
    HelmChart,
    KubernetesInfo,
    KustomizeOverlay,
    ReportData,
    SecretFinding,
    TodoItem,
    WorkspaceInfo,
    WorkspaceMember,
)
from sarand.renderers import html, json_renderer, markdown, text


def _complete() -> ReportData:
    """A report where every rule has its data and none fires."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "proj"
        root.mkdir()
        data = FIXTURES["minimal"](root)
    data.stats.total_files = 10
    data.git = GitSnapshot(branch="main", commit="abc1234")
    data.health = HealthScore(score=90.0, grade="A", confidence=1.0, checks_run=3)
    ok = CommandResult(kind="ok", returncode=0, summary="")
    data.test_results = [copy.copy(ok)]
    data.quality_results = [copy.copy(ok)]
    data.security_results = [copy.copy(ok)]
    return data


def _ids(data: ReportData) -> list[str]:
    return [r.rule_id for r in evaluate_risks(data).risks]


def _skipped(kind: str) -> CommandResult:
    return CommandResult(kind=kind, returncode=0, summary="", skipped=True)


def _fire_sec(d: ReportData) -> None:
    d.security_results = [CommandResult(kind="gitleaks", returncode=1, summary="x")]


def _fire_health(d: ReportData) -> None:
    assert d.health is not None
    d.health.critical_failures = ["tests failed"]


def _fire_secret(d: ReportData) -> None:
    d.secret_findings = [SecretFinding(path="a.py", line_number=1, pattern_name="K")]


def _fire_skipped(d: ReportData) -> None:
    d.quality_results = [_skipped(f"t{i}") for i in range(CHECKS_SKIPPED_MIN)]


def _fire_git(d: ReportData) -> None:
    d.git = GitSnapshot(branch="main", commit="abc", dirty=True)


def _fire_confidence(d: ReportData) -> None:
    assert d.health is not None
    d.health.confidence = CONFIDENCE_MIN - 0.01


def _fire_todo(d: ReportData) -> None:
    d.todos = [
        TodoItem(path="a.py", line_number=i, kind="TODO", content="x")
        for i in range(TODO_CLUSTER_MIN)
    ]


def _fire_large(d: ReportData) -> None:
    d.stats.largest_files = [("big.md", LARGE_FILE_BYTES)]


def _fire_dup(d: ReportData) -> None:
    d.stats.duplicate_files = [("abc", ["a.txt", "b.txt"])]


def _absent_sec(d: ReportData) -> None:
    d.security_results = []


def _absent_health(d: ReportData) -> None:
    d.health = None


def _absent_scan(d: ReportData) -> None:
    d.stats.total_files = 0


def _absent_results(d: ReportData) -> None:
    d.test_results = d.quality_results = d.security_results = []


def _absent_git(d: ReportData) -> None:
    d.git = GitSnapshot()


# rule id -> (make it fire, make its data absent)
_CASES: dict[str, tuple[Callable[[ReportData], None], Callable[[ReportData], None]]] = {
    "SEC-CHECK-FAILED": (_fire_sec, _absent_sec),
    "HEALTH-CRITICAL": (_fire_health, _absent_health),
    "SECRET-PATTERNS": (_fire_secret, _absent_scan),
    "CHECKS-SKIPPED": (_fire_skipped, _absent_results),
    "GIT-STATE": (_fire_git, _absent_git),
    "HEALTH-LOW-CONFIDENCE": (_fire_confidence, _absent_health),
    "TODO-CLUSTER": (_fire_todo, _absent_scan),
    "LARGE-FILE": (_fire_large, _absent_scan),
    "DUPLICATE-FILES": (_fire_dup, _absent_scan),
}


def test_there_are_exactly_nine_rules_with_unique_ids_and_fixed_fields() -> None:
    ids = [r.rule_id for r in RULES]
    assert len(ids) == 9 and len(set(ids)) == 9 and set(ids) == set(_CASES)
    for rule in RULES:
        assert rule.severity in {"high", "warning", "info"}
        assert rule.category and rule.limitations.strip()


def test_a_complete_clean_report_fires_nothing_and_evaluates_everything() -> None:
    report = evaluate_risks(_complete())
    assert report.risks == [] and report.rules_not_evaluated == []


def test_every_rule_fires_when_its_condition_holds() -> None:
    for rule_id, (fire, _) in _CASES.items():
        data = _complete()
        fire(data)
        assert rule_id in _ids(data), rule_id


def test_every_rule_stays_quiet_on_clean_data() -> None:
    for rule_id in _CASES:
        assert rule_id not in _ids(_complete()), rule_id


def test_every_rule_with_absent_data_is_listed_and_does_not_fire() -> None:
    for rule_id, (fire, absent) in _CASES.items():
        data = _complete()
        fire(data)
        absent(data)
        report = evaluate_risks(data)
        assert rule_id in report.rules_not_evaluated, rule_id
        assert rule_id not in [r.rule_id for r in report.risks], rule_id


def test_thresholds_are_inclusive_at_the_documented_boundary() -> None:
    data = _complete()
    data.todos = [
        TodoItem(path="a.py", line_number=i, kind="TODO", content="x")
        for i in range(TODO_CLUSTER_MIN - 1)
    ]
    assert "TODO-CLUSTER" not in _ids(data)
    data.stats.largest_files = [("b.md", LARGE_FILE_BYTES - 1)]
    assert "LARGE-FILE" not in _ids(data)
    data.quality_results = [_skipped(f"t{i}") for i in range(CHECKS_SKIPPED_MIN - 1)]
    assert "CHECKS-SKIPPED" not in _ids(data)
    assert data.health is not None
    data.health.confidence = CONFIDENCE_MIN
    assert "HEALTH-LOW-CONFIDENCE" not in _ids(data)


def test_largest_files_are_read_as_bytes() -> None:
    """Measured on a real report: the history documents are 81-100 KB."""
    assert LARGE_FILE_BYTES == 64 * 1024
    data = _complete()
    data.stats.largest_files = [("docs/h.md", 100100), ("README.md", 55988)]
    risk = next(r for r in evaluate_risks(data).risks if r.rule_id == "LARGE-FILE")
    assert "1 file(s) of at least 64 KiB" in risk.reason
    assert "(97 KiB)" in risk.reason


def test_fixture_only_secret_matches_do_not_fire_and_nothing_leaks() -> None:
    data = _complete()
    data.secret_findings = [
        SecretFinding(
            path="tests/t.py", line_number=3, pattern_name="K", is_test_fixture=True
        )
    ]
    assert "SECRET-PATTERNS" not in _ids(data)
    data.secret_findings.append(
        SecretFinding(path="src/secret_path.py", line_number=9, pattern_name="AWS")
    )
    risk = evaluate_risks(data).risks[0]
    blob = json.dumps(asdict(risk))
    assert "secret_path" not in blob and "AWS" not in blob and "9" not in risk.reason


def test_skipped_inconclusive_and_failed_are_distinguished() -> None:
    data = _complete()
    data.security_results = [
        _skipped("a"),
        CommandResult(kind="b", returncode=1, summary="", inconclusive_reason="net"),
    ]
    assert "SEC-CHECK-FAILED" not in _ids(data)


def test_order_is_severity_then_rule_id_and_evaluation_is_pure() -> None:
    data = _complete()
    for fire, _ in _CASES.values():
        fire(data)
    before = copy.deepcopy(data)
    first = evaluate_risks(data)
    assert first == evaluate_risks(data) and data == before
    keys = [
        ({"high": 0, "warning": 1, "info": 2}[r.severity], r.rule_id)
        for r in first.risks
    ]
    assert keys == sorted(keys) and len(first.risks) == 9


def test_evidence_refs_are_capped_and_name_report_fields() -> None:
    data = _complete()
    data.security_results = [
        CommandResult(kind=f"tool{i}", returncode=1, summary="") for i in range(9)
    ]
    risk = evaluate_risks(data).risks[0]
    assert len(risk.evidence_refs) == 6 and risk.evidence_refs[-1] == "(+4 more)"
    assert risk.evidence_refs[0] == "security_results[kind=tool0]"


def test_json_carries_architecture_and_risks_with_all_fields() -> None:
    data = _complete()
    _fire_sec(data)
    payload = json.loads(json_renderer.render(data))
    assert set(payload["architecture"]) == {
        "components",
        "workspaces",
        "entry_points",
        "compose",
        "kubernetes",
    }
    risk = payload["risks"]["risks"][0]
    assert set(risk) == {
        "rule_id",
        "category",
        "severity",
        "evidence_refs",
        "reason",
        "limitations",
    }
    assert payload["risks"]["rules_not_evaluated"] == []


def _all_firing() -> ReportData:
    data = _complete()
    for fire, _ in _CASES.values():
        fire(data)
    return data


def test_markdown_html_and_text_share_the_same_lines() -> None:
    data = _all_firing()
    lines = l3_lines(data)
    out_html = html.render(data)
    out_text = text.render(data)
    for line in lines:
        assert f"  {line}" in out_text
        assert escape(line) in out_html
    md = markdown.render(data)
    for risk in evaluate_risks(data).risks[:DISPLAY_CAP]:
        assert risk.rule_id in md and risk.limitations.replace("|", "\\|") in md


def test_display_is_capped_with_the_hidden_count_and_json_keeps_all() -> None:
    data = _all_firing()
    md = markdown.render(data)
    assert "(+1 more)" in md
    assert len(evaluate_risks(data).risks) == 9
    assert len(json.loads(json_renderer.render(data))["risks"]["risks"]) == 9


def test_each_fired_rules_limitation_appears_once() -> None:
    md = markdown.render(_all_firing())
    for rule in RULES[:DISPLAY_CAP]:
        assert md.count(f"{rule.rule_id}: {rule.limitations}") <= 1


def test_names_from_the_scan_are_escaped_in_html_and_markdown() -> None:
    data = _complete()
    data.todos = [
        TodoItem(path="<b>`x`|y.py", line_number=i, kind="TODO", content="z")
        for i in range(TODO_CLUSTER_MIN)
    ]
    assert (
        "<b>"
        not in html.render(data).split("Architecture and Risks")[1].split("</pre>")[0]
    )
    line = next(
        ln for ln in markdown.render(data).splitlines() if "TODO-CLUSTER (" in ln
    )
    assert "`" not in line and "\\|" in line


def test_not_evaluated_rules_are_named_in_every_renderer() -> None:
    data = _complete()
    data.health = None
    for out in (markdown.render(data), text.render(data), html.render(data)):
        assert "Rules not evaluated (2 of 9, data absent)" in out
        assert "HEALTH-CRITICAL, HEALTH-LOW-CONFIDENCE" in out


# --- architecture block ----------------------------------------------------


def test_components_list_roles_and_file_counts_from_included_files() -> None:
    data = _complete()
    data.included_files = [
        Path("frontend/a.js"),
        Path("frontend/b.js"),
        Path("backend/x.py"),
        Path("README.md"),
    ]
    data.components = ComponentsInfo(
        components=[
            Component(
                path="frontend",
                role="application",
                kind="frontend",
                languages=["JavaScript"],
            ),
            Component(path="backend", role="application"),
        ],
        total_components=2,
    )
    arch = build_architecture(data)
    assert arch.components == [
        "frontend (application, frontend; JavaScript) -- 2 file(s)",
        "backend (application) -- 1 file(s)",
    ]


def test_workspace_members_entry_points_compose_and_kubernetes_are_read() -> None:
    data = _complete()
    data.included_files = [Path("crates/a/lib.rs"), Path("crates/a/x.rs")]
    data.workspace = WorkspaceInfo(
        kind="Cargo workspace",
        members=[WorkspaceMember(path="crates/a", name="a")],
    )
    data.detection.entry_points = ["src/main.rs"]
    data.compose = ComposeInfo(
        files=[
            ComposeFile(
                path="compose.yaml",
                services=[
                    ComposeService(name="web", builds=True),
                    ComposeService(name="db", image="postgres:16"),
                ],
            )
        ]
    )
    data.kubernetes = KubernetesInfo(
        helm_charts=[HelmChart(path="deploy/chart", name="app", version="1.2.0")],
        kustomize_overlays=[KustomizeOverlay(path="deploy/overlays/prod")],
        total_manifest_files=3,
    )
    arch = build_architecture(data)
    assert arch.workspaces == ["Cargo workspace: 1 member(s): crates/a (2 file(s))"]
    assert arch.entry_points == ["src/main.rs"]
    assert arch.compose == ["compose.yaml: 2 service(s): web (build), db (postgres:16)"]
    assert arch.kubernetes == [
        "Helm: 1 chart(s): app 1.2.0",
        "Kustomize: 1 overlay(s): deploy/overlays/prod",
        "Raw manifests: 3 file(s)",
    ]


def test_nothing_is_inferred_from_directory_or_file_names() -> None:
    data = _complete()
    data.included_files = [
        Path("controllers/a.py"),
        Path("services/b.py"),
        Path("api/c.py"),
    ]
    assert build_architecture(data).is_empty()


def test_architecture_lists_are_capped_with_the_hidden_count() -> None:
    data = _complete()
    data.components = ComponentsInfo(
        components=[Component(path=f"c{i}", role="application") for i in range(15)],
        total_components=15,
    )
    data.detection.entry_points = [f"e{i}.py" for i in range(12)]
    arch = build_architecture(data)
    assert arch.components[-1] == "(+5 more)" and len(arch.components) == 11
    assert arch.entry_points[-1] == "(+4 more)" and len(arch.entry_points) == 9


def test_architecture_is_deterministic_and_does_not_mutate() -> None:
    data = _all_firing()
    data.detection.entry_points = ["b.py", "a.py"]
    before = copy.deepcopy(data)
    assert build_architecture(data) == build_architecture(data) and data == before
    assert build_architecture(data).entry_points == ["b.py", "a.py"]


def test_the_l3_section_stays_within_its_documented_worst_case() -> None:
    data = _all_firing()
    long = "x" * 300
    data.components = ComponentsInfo(
        components=[
            Component(path=long, role="application", kind=long, languages=[long])
            for _ in range(40)
        ],
        total_components=40,
    )
    data.workspace = WorkspaceInfo(
        kind=long, members=[WorkspaceMember(path=long, name=long) for _ in range(40)]
    )
    data.detection.entry_points = [long] * 40
    data.compose = ComposeInfo(
        files=[
            ComposeFile(
                path=long,
                services=[ComposeService(name=long, image=long) for _ in range(30)],
            )
            for _ in range(20)
        ]
    )
    data.kubernetes = KubernetesInfo(
        helm_charts=[HelmChart(path=long, name=long, version=long) for _ in range(20)],
        kustomize_overlays=[KustomizeOverlay(path=long) for _ in range(20)],
        total_manifest_files=999,
    )
    data.todos = [
        TodoItem(path=long, line_number=i, kind="TODO", content="") for i in range(30)
    ]
    data.stats.largest_files = [(long, 10**9)]
    section = "\n".join(l3_lines(data))
    # Measured 5615 bytes and 54 lines; the whole text report 84 lines.
    assert len(section.encode()) < 6500
    assert len(l3_lines(data)) < 70
    assert len(text.render(data).splitlines()) < 100
