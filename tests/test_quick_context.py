"""Regression tests for backlog item 12 (Quick Context, L2) -- see
AGENTS.md section 5.43 and `core/quick_context.py`'s module docstring
for the audit, the budget and the "nothing invented" rule.
"""

from __future__ import annotations

import copy
import json
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from _golden_fixtures import FIXTURES
from sarand.core.ai_summary import generate_ai_summary, suggest_reading_order
from sarand.core.quick_context import build_quick_context
from sarand.models.results import (
    CommandResult,
    Component,
    ComponentsInfo,
    HealthScore,
    Issue,
    ReportData,
    SecretFinding,
)
from sarand.renderers import json_renderer, markdown


@contextmanager
def _fixture(name: str) -> Iterator[ReportData]:
    """A golden fixture built under a temporary project root."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / f"{name}-project"
        root.mkdir()
        yield FIXTURES[name](root)


def test_it_is_deterministic_and_never_mutates_the_report() -> None:
    for name in FIXTURES:
        with _fixture(name) as data:
            before = copy.deepcopy(data)
            first = build_quick_context(data)
            assert first == build_quick_context(data)
            assert data == before
            assert markdown.render(data) == markdown.render(copy.deepcopy(data))


def test_it_does_not_change_the_l1_summary_or_any_analysis_result() -> None:
    with _fixture("hybrid") as data:
        summary = generate_ai_summary(data)
        results = copy.deepcopy((data.test_results, data.health, data.known_issues))
        build_quick_context(data)
        markdown.render(data)
        assert generate_ai_summary(data) == summary
        assert (data.test_results, data.health, data.known_issues) == results


def test_checks_carry_their_status() -> None:
    with _fixture("hybrid") as data:
        data.test_results = [
            CommandResult(kind="pytest", returncode=0, summary="ok"),
            CommandResult(kind="cargo test", returncode=1, summary="bad"),
            CommandResult(
                kind="go test", returncode=0, summary="", skipped=True, skip_reason="x"
            ),
        ]
        data.quality_results = []
        data.security_results = []
        qc = build_quick_context(data)
        assert qc.tests == ["pytest: passed", "cargo test: failed", "go test: skipped"]
        assert any("1 check(s) failed: cargo test" in r for r in qc.risks)
        assert any("skipped" in r and "go test" in r for r in qc.risks)


def test_critical_findings_and_risks_surface_the_important_things() -> None:
    with _fixture("minimal") as data:
        data.health = HealthScore(
            score=40.0,
            grade="F",
            critical_failures=["tests are failing"],
            confidence=0.5,
        )
        data.known_issues = ["Linker 'cc' not found"]
        data.git.dirty = True
        data.git.behind = 3
        data.test_results = [
            CommandResult(
                kind="pytest",
                returncode=1,
                summary="",
                errors=[Issue(source="pytest", message="boom", severity="error")],
            )
        ]
        qc = build_quick_context(data)
        assert qc.critical_findings == ["tests are failing", "Linker 'cc' not found"]
        assert "confidence 50%" in qc.health and "grade F" in qc.health
        joined = " | ".join(qc.risks)
        assert "uncommitted changes" in joined
        assert "3 commit(s) behind" in joined
        assert "1 error(s) and 0 warning(s)" in joined


def test_secret_findings_are_counted_but_never_named() -> None:
    with _fixture("minimal") as data:
        data.secret_findings = [
            SecretFinding(path="config/prod.env", line_number=3, pattern_name="aws key")
        ]
        qc = build_quick_context(data)
        assert any("1 potential secret(s) found" in r for r in qc.risks)
        assert "prod.env" not in json.dumps(asdict(qc))


def test_structure_comes_from_the_top_level_of_the_tree() -> None:
    with _fixture("minimal") as data:
        data.tree_text = "proj/\n├── src/\n│   └── a.py\n├── docs/\n└── README.md\n"
        assert build_quick_context(data).structure == [
            "src/",
            "docs/",
            "(1 top-level file(s))",
        ]


def test_components_are_listed_application_first_when_hybrid() -> None:
    with _fixture("minimal") as data:
        data.components = ComponentsInfo(
            components=[
                Component(
                    path="docker-compose.yml", role="infrastructure", kind="compose"
                ),
                Component(path="backend", role="application", kind="backend"),
            ],
            total_components=2,
        )
        assert build_quick_context(data).components == [
            "backend (application, backend)",
            "docker-compose.yml (infrastructure, compose)",
        ]


def test_worst_case_stays_within_the_documented_budget() -> None:
    with _fixture("hybrid") as data:
        long = "x" * 500
        data.known_issues = [long] * 40
        data.health = HealthScore(critical_failures=[long] * 40, confidence=0.1)
        data.test_results = [
            CommandResult(kind=long, returncode=1, summary="", errors=[], warnings=[])
            for _ in range(60)
        ]
        data.quality_results = list(data.test_results)
        data.security_results = list(data.test_results)
        data.suggested_reading_order = [long] * 100
        data.tree_text = "p/\n" + "".join(f"├── {long}\n" for _ in range(100))
        data.components = ComponentsInfo(
            components=[
                Component(path=long, role="application", kind=long) for _ in range(60)
            ],
            total_components=60,
        )
        section = markdown.render(data).split("## Detected Project")[0]
        quick = section.split("## Quick Context")[1]
        assert len(quick) < 9000
        qc = build_quick_context(data)
        assert qc.tests[-1] == "(+48 more)"
        assert len(qc.reading_order) == 10
        assert all(len(item) <= 120 for item in qc.critical_findings)


def test_markdown_puts_quick_context_first_with_every_field() -> None:
    for name in FIXTURES:
        with _fixture(name) as data:
            out = markdown.render(data)
        assert out.index("## Quick Context") < out.index("## Detected Project")
        assert out.index("## Quick Context") < out.index("## Environment")
        block = out.split("## Quick Context")[1].split("\n## ")[0]
        for label in ("Project", "Structure", "Tests", "Quality", "Security"):
            assert f"- **{label}:**" in block
        assert "- **Critical findings:**" in block and "- **Risks:**" in block
        assert ("- **Health:**" in block) == (data.health is not None)


def test_json_exposes_the_same_block_near_the_top() -> None:
    with _fixture("hybrid") as data:
        payload = json.loads(json_renderer.render(data))
        assert list(payload)[:2] == ["project_root", "quick_context"]
        assert payload["quick_context"] == json.loads(
            json.dumps(asdict(build_quick_context(data)))
        )


def test_reading_order_puts_entry_points_before_plugins_docs_and_tests() -> None:
    """The audit scenario on the real report: alphabetical analyzer
    plugins, docs files and a test file used to crowd out cli.py."""
    root = Path("/p")
    included = (
        [Path(f"python/sarand/analyzers/{n}_analyzer.py") for n in "abcdef"]
        + [Path(f"docs/guide{i}.md") for i in range(4)]
        + [
            Path("python/sarand/cli.py"),
            Path("python/sarand/core/health.py"),
            Path("tests/test_analyzers.py"),
            Path("tests/golden/README.md"),
            Path("README.md"),
            Path("pyproject.toml"),
        ]
    )
    order = suggest_reading_order(root, included)
    assert order[:2] == ["README.md", "pyproject.toml"]
    assert order[2:4] == ["python/sarand/cli.py", "python/sarand/core/health.py"]
    assert order[4] == "docs/guide0.md"
    assert order.index("python/sarand/analyzers/a_analyzer.py") > order.index(
        "docs/guide3.md"
    )
    assert order.index("docs/guide0.md") < order.index("tests/test_analyzers.py")
    assert order.index("tests/golden/README.md") > order.index("docs/guide3.md")
    assert order == suggest_reading_order(root, list(reversed(included)))
