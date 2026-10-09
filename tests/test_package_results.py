"""Per-package results (AGENTS.md section 5.59): the summary counts, the
Markdown table and the JSON key, and that an ordinary report is unchanged.

نتایج هر بسته (بخش ۵.۵۹): شمارش، جدول Markdown و کلید JSON.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sarand.core.package_summary import (
    ROOT_PACKAGE,
    PackageSummary,
    PhaseCount,
    summarize_packages,
)
from sarand.models.results import (
    CommandResult,
    EnvironmentInfo,
    GitSnapshot,
    ProjectStats,
    ReportData,
)
from sarand.renderers import json_renderer, markdown


def _ok(kind: str) -> CommandResult:
    return CommandResult(kind=kind, returncode=0, summary="ok")


def _bad(kind: str) -> CommandResult:
    return CommandResult(kind=kind, returncode=1, summary="failed")


def _skipped(kind: str) -> CommandResult:
    return CommandResult(
        kind=kind, returncode=0, summary="", skipped=True, skip_reason="not installed"
    )


def _by_name(summaries: list[PackageSummary]) -> dict[str, PackageSummary]:
    return {s.package: s for s in summaries}


def test_no_packages_means_no_summary() -> None:
    assert summarize_packages([], [_ok("pytest")], [], []) == []
    assert summarize_packages([ROOT_PACKAGE], [_ok("pytest")], [], []) == []


def test_results_are_grouped_by_their_package_label() -> None:
    summaries = summarize_packages(
        ["packages/a", "packages/b"],
        [_ok("pytest"), _ok("packages/a: npm test"), _bad("packages/b: npm test")],
        [_ok("ruff"), _ok("packages/a: eslint")],
        [_skipped("packages/a: npm audit"), _ok("pip-audit")],
    )
    assert [s.package for s in summaries] == [".", "packages/a", "packages/b"]
    by = _by_name(summaries)
    assert by["."].tests == PhaseCount(passed=1)
    assert by["."].quality == PhaseCount(passed=1)
    assert by["."].security == PhaseCount(passed=1)
    assert by["packages/a"].tests == PhaseCount(passed=1)
    assert by["packages/a"].quality == PhaseCount(passed=1)
    assert by["packages/a"].security == PhaseCount(skipped=1)
    assert by["packages/b"].tests == PhaseCount(failed=1)
    assert by["packages/b"].failed == 1
    assert by["."].failed == 0


def test_the_longest_package_wins_and_unknown_labels_go_to_the_root() -> None:
    summaries = summarize_packages(
        ["packages/a", "packages/a/b"],
        [_ok("packages/a/b: npm test"), _bad("packages/a: npm test"), _ok("docker: x")],
        [],
        [],
    )
    by = _by_name(summaries)
    assert by["packages/a/b"].tests == PhaseCount(passed=1)
    assert by["packages/a"].tests == PhaseCount(failed=1)
    # "docker" is not a package of this run: it stays with the root.
    assert by["."].tests == PhaseCount(passed=1)


def test_a_package_with_no_results_has_empty_counts() -> None:
    summaries = summarize_packages(["packages/a"], [_ok("pytest")], [], [])
    assert _by_name(summaries)["packages/a"].tests == PhaseCount()
    assert _by_name(summaries)["packages/a"].tests.ran == 0


def test_duplicate_package_paths_are_listed_once() -> None:
    summaries = summarize_packages(["a", "a", "."], [], [], [])
    assert [s.package for s in summaries] == [".", "a"]


def _data(**kwargs: object) -> ReportData:
    return ReportData(
        project_root=Path("project"),
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        environment=EnvironmentInfo(),
        git=GitSnapshot(),
        stats=ProjectStats(),
        **kwargs,  # type: ignore[arg-type]
    )


def test_report_data_has_no_packages_by_default() -> None:
    assert _data().package_paths == []


def test_markdown_has_no_table_for_an_ordinary_project() -> None:
    rendered = markdown.render(
        _data(test_results=[_ok("pytest")]), include_source=False
    )
    assert "## Package results" not in rendered


def test_markdown_table_lists_every_package_with_counts() -> None:
    rendered = markdown.render(
        _data(
            package_paths=["packages/a", "tools/cli"],
            test_results=[
                _ok("pytest"),
                _ok("packages/a: npm test"),
                _bad("tools/cli: npm test"),
            ],
            quality_results=[_ok("ruff")],
            security_results=[_skipped("packages/a: npm audit")],
        ),
        include_source=False,
    )
    assert "## Package results" in rendered
    assert "| Package | Tests | Quality | Security |" in rendered
    assert "| `.` (root) | 1/1 | 1/1 | - |" in rendered
    assert "| `packages/a` | 1/1 | - | skipped |" in rendered
    assert "| `tools/cli` | 0/1 failed | - | - |" in rendered
    # The table comes before the detailed results.
    assert rendered.index("## Package results") < rendered.index("## Test results")


def test_json_has_package_results_only_when_there_are_packages() -> None:
    plain = json.loads(json_renderer.render(_data(), include_source=False))
    assert "package_results" not in plain
    rich = json.loads(
        json_renderer.render(
            _data(
                package_paths=["packages/a"],
                test_results=[_ok("pytest"), _bad("packages/a: npm test")],
            ),
            include_source=False,
        )
    )
    rows = {r["package"]: r for r in rich["package_results"]}
    assert list(rows) == [".", "packages/a"]
    assert rows["."]["tests"] == {"passed": 1, "failed": 0, "skipped": 0}
    assert rows["packages/a"]["tests"] == {"passed": 0, "failed": 1, "skipped": 0}
    assert rows["packages/a"]["security"] == {"passed": 0, "failed": 0, "skipped": 0}
