"""Regression tests for per-component analyzer runs in hybrid projects
-- see AGENTS.md section 5.42 and `core/per_component.py`'s module
docstring for the audit, design and the no-duplicate-findings rule.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from _helpers import write
from sarand.analyzers.registry import builtin_analyzers, matching_analyzers
from sarand.core.components import detect_components
from sarand.core.compose import detect_compose
from sarand.core.kubernetes import detect_kubernetes
from sarand.core.makefile import detect_makefiles
from sarand.core.per_component import (
    ComponentPlan,
    ComponentTarget,
    plan_component_runs,
    run_component_quality,
    run_component_security,
    run_component_tests,
)
from sarand.models.results import (
    CommandResult,
    Component,
    ComponentsInfo,
    Issue,
)
from test_components import build_hybrid


class FakeAnalyzer:
    """Matches a directory that contains `marker`; records where it ran."""

    def __init__(self, name: str, marker: str) -> None:
        self.name = name
        self.marker = marker
        self.ran_in: list[Path] = []

    def matches(self, root: Path) -> bool:
        return (root / self.marker).exists()

    def entry_points(self, root: Path) -> list[str]:
        return []

    async def run_tests(self, root: Path) -> CommandResult | None:
        self.ran_in.append(root)
        return CommandResult(
            kind=f"{self.name}-test",
            returncode=1,
            summary="boom",
            raw_output="boom",
            errors=[
                Issue(source=f"{self.name}-test", message="failed", severity="error")
            ],
        )

    async def run_quality(self, root: Path) -> list[CommandResult]:
        self.ran_in.append(root)
        return [CommandResult(kind=f"{self.name}-lint", returncode=0, summary="ok")]

    async def run_security(self, root: Path) -> list[CommandResult]:
        self.ran_in.append(root)
        return [CommandResult(kind=f"{self.name}-audit", returncode=0, summary="ok")]


def _info(*paths: str, role: str = "application") -> ComponentsInfo:
    comps = [Component(path=p, role=role) for p in paths]
    return ComponentsInfo(components=comps, total_components=len(comps))


def test_non_hybrid_project_gets_an_empty_plan() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        plan = plan_component_runs(Path(tmp), None, [FakeAnalyzer("A", "a.txt")], [])
        assert plan == ComponentPlan()


def test_analyzer_matching_the_root_is_never_rerun_inside_a_component() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "a.txt")
        write(root / "backend" / "a.txt")
        write(root / "backend" / "b.txt")
        at_root = FakeAnalyzer("A", "a.txt")
        only_below = FakeAnalyzer("B", "b.txt")
        plan = plan_component_runs(
            root, _info("backend"), [at_root, only_below], [at_root]
        )
        assert [(t.path, [a.name for a in t.analyzers]) for t in plan.targets] == [
            ("backend", ["B"])
        ]


def test_only_application_components_below_the_root_are_planned() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "x.txt")
        write(root / "infra" / "x.txt")
        analyzer = FakeAnalyzer("X", "x.txt")
        infra_only = _info("infra", role="infrastructure")
        assert plan_component_runs(root, infra_only, [analyzer], []).targets == ()
        root_app = _info(".")
        assert plan_component_runs(root, root_app, [analyzer], []).targets == ()


def test_outermost_component_wins_for_nested_components() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "a" / "m.txt")
        write(root / "a" / "b" / "m.txt")
        write(root / "a" / "b" / "n.txt")
        m = FakeAnalyzer("M", "m.txt")
        n = FakeAnalyzer("N", "n.txt")
        plan = plan_component_runs(root, _info("a", "a/b"), [m, n], [])
        assert [(t.path, [x.name for x in t.analyzers]) for t in plan.targets] == [
            ("a", ["M"]),
            ("a/b", ["N"]),
        ]


def test_a_sibling_component_is_not_treated_as_nested() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "app" / "m.txt")
        write(root / "app2" / "m.txt")
        m = FakeAnalyzer("M", "m.txt")
        plan = plan_component_runs(root, _info("app", "app2"), [m], [])
        assert [t.path for t in plan.targets] == ["app", "app2"]


def test_component_cap_reports_the_omitted_count() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        names = [f"c{i:02d}" for i in range(11)]
        for n in names:
            write(root / n / "m.txt")
        plan = plan_component_runs(
            root, _info(*names), [FakeAnalyzer("M", "m.txt")], []
        )
        assert len(plan.targets) == 8
        assert plan.omitted == 3
        note = asyncio.run(run_component_tests(plan))[-1]
        assert note.skipped and "3 more component(s) not analysed" in note.skip_reason


def test_environment_variable_disables_everything() -> None:
    import os

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "backend" / "m.txt")
        os.environ["SARAND_NO_COMPONENTS"] = "1"
        try:
            plan = plan_component_runs(
                root, _info("backend"), [FakeAnalyzer("M", "m.txt")], []
            )
        finally:
            del os.environ["SARAND_NO_COMPONENTS"]
        assert plan.targets == ()


def test_a_crashing_matches_is_skipped_not_fatal() -> None:
    class Broken(FakeAnalyzer):
        def matches(self, root: Path) -> bool:
            raise RuntimeError("plugin bug")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "backend" / "m.txt")
        good = FakeAnalyzer("M", "m.txt")
        plan = plan_component_runs(
            root, _info("backend"), [Broken("X", "m.txt"), good], []
        )
        assert [a.name for a in plan.targets[0].analyzers] == ["M"]


def test_results_run_in_the_component_directory_and_are_labelled() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "backend" / "m.txt")
        analyzer = FakeAnalyzer("M", "m.txt")
        plan = plan_component_runs(root, _info("backend"), [analyzer], [])

        tests = asyncio.run(run_component_tests(plan))
        quality = asyncio.run(run_component_quality(plan))
        security = asyncio.run(run_component_security(plan))

        assert analyzer.ran_in == [root / "backend"] * 3
        assert [r.kind for r in tests] == ["backend: M-test"]
        assert [r.kind for r in quality] == ["backend: M-lint"]
        assert [r.kind for r in security] == ["backend: M-audit"]
        assert [i.source for i in tests[0].errors] == ["backend: M-test"]
        assert tests[0].returncode == 1 and not tests[0].passed


def test_two_components_with_the_same_analyzer_are_attributed_separately() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "one" / "m.txt")
        write(root / "two" / "m.txt")
        analyzer = FakeAnalyzer("M", "m.txt")
        plan = plan_component_runs(root, _info("one", "two"), [analyzer], [])
        kinds = [r.kind for r in asyncio.run(run_component_tests(plan))]
        assert kinds == ["one: M-test", "two: M-test"]


def test_empty_plan_runs_nothing_and_returns_nothing() -> None:
    assert asyncio.run(run_component_tests(ComponentPlan())) == []
    assert asyncio.run(run_component_quality(ComponentPlan())) == []
    assert asyncio.run(run_component_security(ComponentPlan())) == []


def test_relabelling_does_not_mutate_the_original_result() -> None:
    analyzer = FakeAnalyzer("M", "m.txt")
    original = asyncio.run(analyzer.run_tests(Path(".")))
    assert original is not None
    target = ComponentTarget("svc", Path("."), (analyzer,))
    asyncio.run(run_component_tests(ComponentPlan(targets=(target,))))
    assert original.kind == "M-test"
    assert original.errors[0].source == "M-test"


def test_real_analyzers_on_the_hybrid_fixture_close_the_audited_gap() -> None:
    """The exact scenario from the item-11 audit: before this change only
    GitHub Actions / YAML / Markdown ran; now Python and Node.js run in
    their own components, and nothing that matched the root runs twice."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build_hybrid(root)
        components = detect_components(
            root,
            detect_kubernetes(root),
            detect_compose(root),
            detect_makefiles(root),
        )
        analyzers = builtin_analyzers()
        active = matching_analyzers(root, analyzers)
        active_names = {a.name for a in active}
        assert "Python" not in active_names and "Node.js" not in active_names

        plan = plan_component_runs(root, components, analyzers, active)
        by_path = {t.path: {a.name for a in t.analyzers} for t in plan.targets}
        assert "Python" in by_path["backend"]
        assert "Node.js" in by_path["frontend"]
        for names in by_path.values():
            assert not (names & active_names)
