"""Regression tests for backlog follow-up 1 (npm / Yarn / pnpm workspaces)
-- see AGENTS.md section 5.50, `core/node_workspace.py` and the Node
section of `core/per_component.py` for the audit, the scope and the
duplicate-prevention rules these tests pin.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from _helpers import write
from sarand.analyzers.node_analyzer import NodeAnalyzer
from sarand.analyzers.registry import builtin_analyzers, matching_analyzers
from sarand.core.components import detect_components
from sarand.core.health import compute_health_score
from sarand.core.node_workspace import detect_node_workspace, root_script_cascades
from sarand.core.per_component import (
    ComponentPlan,
    plan_component_runs,
    run_component_quality,
    run_component_security,
    run_component_tests,
)
from sarand.core.workspace import detect_workspace
from sarand.models.results import (
    CommandResult,
    EnvironmentInfo,
    GitSnapshot,
    ProjectStats,
    ReportData,
    WorkspaceInfo,
    WorkspaceMember,
)
from sarand.renderers import json_renderer, markdown


def _pkg(name: str, **extra: object) -> str:
    data: dict[str, object] = {"name": name, "scripts": {"test": f"echo {name}"}}
    data.update(extra)
    return json.dumps(data)


def build_npm(root: Path) -> None:
    write(root / "package.json", _pkg("root", private=True, workspaces=["packages/*"]))
    for name in ("a", "b"):
        write(root / "packages" / name / "package.json", _pkg(name))


def _members(root: Path) -> list[str]:
    info = detect_node_workspace(root)
    assert info is not None
    return [m.path for m in info.members]


def test_npm_workspaces_array_form() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build_npm(root)
        info = detect_node_workspace(root)
        assert info is not None and info.kind == "npm"
        assert [(m.path, m.name) for m in info.members] == [
            ("packages/a", "a"),
            ("packages/b", "b"),
        ]


def test_yarn_workspaces_object_form_and_kind_detection() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", _pkg("r", workspaces={"packages": ["pk/*"]}))
        write(root / "pk" / "x" / "package.json", _pkg("x"))
        assert detect_node_workspace(root).kind == "npm"  # type: ignore[union-attr]
        write(root / "yarn.lock", "")
        assert detect_node_workspace(root).kind == "yarn"  # type: ignore[union-attr]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(
            root / "package.json",
            _pkg("r", workspaces=["pk/*"], packageManager="yarn@4.1.0"),
        )
        write(root / "pk" / "x" / "package.json", _pkg("x"))
        assert detect_node_workspace(root).kind == "yarn"  # type: ignore[union-attr]


def test_pnpm_workspace_file_with_and_without_a_root_package_json() -> None:
    for with_root in (True, False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "pnpm-workspace.yaml", "packages:\n  - 'packages/*'\n")
            if with_root:
                write(root / "package.json", _pkg("root"))
            write(root / "packages" / "a" / "package.json", _pkg("a"))
            info = detect_node_workspace(root)
            assert info is not None and info.kind == "pnpm"
            assert [m.path for m in info.members] == ["packages/a"]


def test_pnpm_wins_when_both_declarations_exist() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pnpm-workspace.yaml", "packages:\n  - 'apps/*'\n")
        write(root / "package.json", _pkg("r", workspaces=["packages/*"]))
        write(root / "apps" / "w" / "package.json", _pkg("w"))
        write(root / "packages" / "p" / "package.json", _pkg("p"))
        assert _members(root) == ["apps/w"]


def test_negated_patterns_exclude_members_and_are_reported() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(
            root / "pnpm-workspace.yaml",
            "packages:\n  - 'packages/*'\n  - '!packages/legacy'\n",
        )
        for name in ("a", "legacy"):
            write(root / "packages" / name / "package.json", _pkg(name))
        info = detect_node_workspace(root)
        assert info is not None
        assert [m.path for m in info.members] == ["packages/a"]
        assert info.exclude_patterns == ["packages/legacy"]


def test_double_star_patterns_reach_nested_packages() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", _pkg("r", workspaces=["libs/**"]))
        write(root / "libs" / "a" / "package.json", _pkg("a"))
        write(root / "libs" / "grp" / "b" / "package.json", _pkg("b"))
        write(root / "other" / "c" / "package.json", _pkg("c"))
        assert _members(root) == ["libs/a", "libs/grp/b"]


def test_literal_paths_and_dot_slash_prefixes_work() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", _pkg("r", workspaces=["./tools/cli/", "docs"]))
        write(root / "tools" / "cli" / "package.json", _pkg("cli"))
        write(root / "docs" / "package.json", _pkg("docs"))
        assert _members(root) == ["docs", "tools/cli"]


def test_node_modules_and_build_dirs_are_never_members() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", _pkg("r", workspaces=["packages/**"]))
        write(root / "packages" / "a" / "package.json", _pkg("a"))
        write(root / "packages" / "a" / "node_modules" / "dep" / "package.json", "{}")
        write(root / "packages" / "dist" / "package.json", "{}")
        assert _members(root) == ["packages/a"]


def test_directories_without_a_package_json_are_not_members() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", _pkg("r", workspaces=["packages/*"]))
        write(root / "packages" / "a" / "package.json", _pkg("a"))
        write(root / "packages" / "empty" / "readme.md", "x")
        assert _members(root) == ["packages/a"]


def test_the_root_is_not_a_member_and_a_nameless_package_uses_its_dir() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", _pkg("r", workspaces=["."]))
        write(root / "packages" / "z" / "package.json", "{}")
        assert _members(root) == []
        write(root / "package.json", _pkg("r", workspaces=["packages/*"]))
        info = detect_node_workspace(root)
        assert info is not None and info.members[0].name == "z"


def test_not_a_workspace_returns_none() -> None:
    cases = [
        None,
        "{not json",
        "[]",
        json.dumps({"name": "x"}),
        json.dumps({"workspaces": []}),
        json.dumps({"workspaces": "packages/*"}),
        json.dumps({"workspaces": [1, None]}),
    ]
    for body in cases:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            if body is not None:
                write(root / "package.json", body)
            assert detect_node_workspace(root) is None, body
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pnpm-workspace.yaml", "packages: [unclosed")
        assert detect_node_workspace(root) is None
        write(root / "pnpm-workspace.yaml", "- just\n- a list\n")
        assert detect_node_workspace(root) is None


def test_cargo_is_detected_first_when_both_models_exist() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build_npm(root)
        write(root / "Cargo.toml", "[workspace]\nmembers = ['crates/*']\n")
        write(root / "crates" / "c" / "Cargo.toml", '[package]\nname = "c"\n')
        info = detect_workspace(root)
        assert info is not None and info.kind == "cargo"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build_npm(root)
        info = detect_workspace(root)
        assert info is not None and info.kind == "npm"


def test_cascade_recognition_table() -> None:
    cascades = [
        "npm test --workspaces",
        "npm run test -ws",
        "npm run test --workspace=packages/a",
        "pnpm -r test",
        "pnpm run --recursive test",
        "pnpm --filter ./packages/* test",
        "yarn workspaces foreach run test",
        "turbo run test",
        "nx run-many -t test",
        "lerna run test",
    ]
    plain = ["jest", "vitest run", "pnpm -w test", "echo nxfoo", "node scripts/test.js"]
    for body in cascades + plain:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "package.json", json.dumps({"scripts": {"test": body}}))
            assert root_script_cascades(root, "test") is (body in cascades), body
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert root_script_cascades(root, "test") is False
        write(root / "package.json", json.dumps({"scripts": {"test": 5}}))
        assert root_script_cascades(root, "test") is False
        assert root_script_cascades(root, "lint") is False


def _plan(root: Path, workspace: WorkspaceInfo | None) -> ComponentPlan:
    analyzers = builtin_analyzers()
    return plan_component_runs(
        root, None, analyzers, matching_analyzers(root, analyzers), workspace
    )


def test_members_are_planned_with_tests_and_quality_but_never_security() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build_npm(root)
        plan = _plan(root, detect_workspace(root))
        assert [t.path for t in plan.targets] == ["packages/a", "packages/b"]
        for target in plan.targets:
            assert [a.name for a in target.analyzers] == ["Node.js"]
            assert target.phases == frozenset({"tests", "quality"})


def test_a_root_test_script_that_fans_out_drops_the_test_phase_only() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build_npm(root)
        write(
            root / "package.json",
            _pkg(
                "root",
                workspaces=["packages/*"],
                scripts={"test": "npm test --workspaces"},
            ),
        )
        plan = _plan(root, detect_workspace(root))
        assert {t.phases for t in plan.targets} == {frozenset({"quality"})}


def test_a_root_eslint_config_or_lint_fan_out_drops_member_linting() -> None:
    for extra in ({"eslint.config.js": "export default []\n"}, None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build_npm(root)
            if extra:
                for name, body in extra.items():
                    write(root / name, body)
            else:
                write(
                    root / "package.json",
                    _pkg(
                        "root",
                        workspaces=["packages/*"],
                        scripts={"test": "echo r", "lint": "pnpm -r lint"},
                    ),
                )
            plan = _plan(root, detect_workspace(root))
            assert {t.phases for t in plan.targets} == {frozenset({"tests"})}


def test_nothing_is_planned_when_the_root_fans_out_both_phases() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build_npm(root)
        write(
            root / "package.json",
            _pkg(
                "root",
                workspaces=["packages/*"],
                scripts={"test": "turbo run test", "lint": "turbo run lint"},
            ),
        )
        assert _plan(root, detect_workspace(root)).targets == ()


def test_non_node_or_missing_workspaces_plan_nothing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build_npm(root)
        cargo = WorkspaceInfo(
            kind="cargo", members=[WorkspaceMember("packages/a", "a")]
        )
        # Workspace info that does not describe these packages: they are no
        # members, so none may get member runs (members never get `security`);
        # since 5.55 they are planned as standalone nested packages instead.
        for workspace in (cargo, None):
            for target in _plan(root, workspace).targets:
                assert "security" in target.phases
        analyzers = [a for a in builtin_analyzers() if not isinstance(a, NodeAnalyzer)]
        plan = plan_component_runs(root, None, analyzers, [], detect_workspace(root))
        assert plan.targets == ()


def test_the_environment_switch_disables_member_runs_too() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build_npm(root)
        workspace = detect_workspace(root)
        with mock.patch.dict(os.environ, {"SARAND_NO_COMPONENTS": "1"}):
            assert _plan(root, workspace).targets == ()


def test_more_than_twenty_members_are_capped_with_the_true_count_reported() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", _pkg("r", workspaces=["packages/*"]))
        for i in range(25):
            write(root / "packages" / f"p{i:02d}" / "package.json", _pkg(f"p{i}"))
        plan = _plan(root, detect_workspace(root))
        assert len(plan.targets) == 20 and plan.omitted_members == 5
        notes = asyncio.run(run_component_tests(plan))
        assert notes[-1].skipped
        assert "5 more workspace member(s) not analysed (limit 20)" in (
            notes[-1].skip_reason
        )


def test_a_member_that_is_also_a_hybrid_component_runs_each_analyzer_once() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pnpm-workspace.yaml", "packages:\n  - 'apps/*'\n")
        write(
            root / "apps" / "web" / "package.json",
            _pkg("web", dependencies={"react": "18"}),
        )
        write(
            root / "apps" / "api" / "package.json",
            _pkg("api", dependencies={"express": "4"}),
        )
        analyzers = builtin_analyzers()
        active = matching_analyzers(root, analyzers)
        components = detect_components(root)
        assert components is not None
        plan = plan_component_runs(
            root, components, analyzers, active, detect_workspace(root)
        )
        names: dict[str, list[str]] = {}
        node_phases: dict[str, set[str]] = {}
        for target in plan.targets:
            names.setdefault(target.path, []).extend(a.name for a in target.analyzers)
            if any(a.name == "Node.js" for a in target.analyzers):
                node_phases.setdefault(target.path, set()).update(target.phases)
        assert set(names) == {"apps/api", "apps/web"}
        for path, found in names.items():
            assert found.count("Node.js") == 1
            assert node_phases[path] == {"tests", "quality"}


def _fake_result(kind: str, code: int = 0) -> CommandResult:
    return CommandResult(kind=kind, returncode=code, summary="")


def test_member_runs_are_labelled_and_the_security_phase_is_never_called() -> None:
    calls: list[str] = []

    async def fake_tests(self: NodeAnalyzer, root: Path) -> CommandResult | None:
        calls.append(f"tests:{root.name}")
        return _fake_result("npm test")

    async def fake_quality(self: NodeAnalyzer, root: Path) -> list[CommandResult]:
        calls.append(f"quality:{root.name}")
        return [_fake_result("npm run lint")]

    async def fake_security(self: NodeAnalyzer, root: Path) -> list[CommandResult]:
        calls.append(f"security:{root.name}")
        return [_fake_result("npm audit")]

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build_npm(root)
        plan = _plan(root, detect_workspace(root))
        with (
            mock.patch.object(NodeAnalyzer, "run_tests", fake_tests),
            mock.patch.object(NodeAnalyzer, "run_quality", fake_quality),
            mock.patch.object(NodeAnalyzer, "run_security", fake_security),
        ):
            tests = asyncio.run(run_component_tests(plan))
            quality = asyncio.run(run_component_quality(plan))
            security = asyncio.run(run_component_security(plan))
    assert [r.kind for r in tests] == ["packages/a: npm test", "packages/b: npm test"]
    assert [r.kind for r in quality] == [
        "packages/a: npm run lint",
        "packages/b: npm run lint",
    ]
    assert security == []
    assert not any(c.startswith("security:") for c in calls)
    assert calls.count("tests:a") == 1 and calls.count("quality:b") == 1


def test_the_audited_gap_is_closed_on_real_analyzers_for_every_model() -> None:
    """Before: workspace None, only the root ran. After: every member is
    planned for the Node.js analyzer and nothing that matched the root is
    repeated."""
    builders = {
        "npm": build_npm,
        "pnpm": lambda r: (
            write(r / "package.json", _pkg("root")),
            write(r / "pnpm-workspace.yaml", "packages:\n  - 'packages/*'\n"),
            [write(r / "packages" / n / "package.json", _pkg(n)) for n in "ab"],
        ),
        "pnpm-only": lambda r: (
            write(r / "pnpm-workspace.yaml", "packages:\n  - 'packages/*'\n"),
            [write(r / "packages" / n / "package.json", _pkg(n)) for n in "ab"],
        ),
    }
    for model, build in builders.items():
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root)
            analyzers = builtin_analyzers()
            plan = plan_component_runs(
                root,
                None,
                analyzers,
                matching_analyzers(root, analyzers),
                detect_workspace(root),
            )
            assert [t.path for t in plan.targets] == ["packages/a", "packages/b"], model
            for target in plan.targets:
                assert [a.name for a in target.analyzers] == ["Node.js"], model


def _report(root: Path, workspace: WorkspaceInfo | None) -> ReportData:
    return ReportData(
        project_root=root,
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        environment=EnvironmentInfo(),
        git=GitSnapshot(),
        stats=ProjectStats(),
        workspace=workspace,
    )


def test_health_counts_each_check_once_in_one_repository_score() -> None:
    """Aggregation rule: member results join the same flat lists as the
    root's, each counted once; one repository-level score, no per-workspace
    score. A failing member suite lowers the shared ratio."""
    with tempfile.TemporaryDirectory() as tmp:
        data = _report(Path(tmp), None)
        data.test_results = [_fake_result("npm test"), _fake_result("a: npm test")]
        clean = compute_health_score(data).breakdown["tests"]
        data.test_results = [_fake_result("npm test"), _fake_result("a: npm test", 1)]
        failed = compute_health_score(data)
        assert clean == 25.0 and failed.breakdown["tests"] == 12.5
        assert any("test suites failed" in c for c in failed.critical_failures)


def test_reports_show_the_workspace_kind_and_members() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build_npm(root)
        data = _report(root, detect_workspace(root))
        rendered = markdown.render(data, include_source=False)
        assert "- **Kind:** npm" in rendered and "| a | `packages/a` |" in rendered
        payload = json.loads(json_renderer.render(data, include_source=False))
        assert payload["workspace"]["kind"] == "npm"
        assert [m["path"] for m in payload["workspace"]["members"]] == [
            "packages/a",
            "packages/b",
        ]
