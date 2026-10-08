"""Regression tests for backlog status follow-up 2 -- nested packages whose
analyzer also matches the root (Node.js, Go, Rust). See AGENTS.md section
5.52 and the "Nested packages" paragraph of `core/per_component.py`."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from unittest import mock

from _helpers import write
from sarand.analyzers.node_analyzer import NodeAnalyzer
from sarand.analyzers.registry import builtin_analyzers, matching_analyzers
from sarand.core.components import detect_components
from sarand.core.compose import detect_compose
from sarand.core.per_component import (
    ComponentPlan,
    ComponentTarget,
    plan_component_runs,
    run_component_quality,
    run_component_security,
    run_component_tests,
)
from sarand.core.workspace import detect_workspace
from sarand.models.results import CommandResult

_COMPOSE = "services:\n  app:\n    build: .\n"
_ALL = frozenset({"tests", "quality", "security"})


def _pkg(name: str, **extra: object) -> str:
    data: dict[str, object] = {"name": name, "scripts": {"test": f"echo {name}"}}
    data.update(extra)
    return json.dumps(data)


def _plan(root: Path) -> ComponentPlan:
    analyzers = builtin_analyzers()
    components = detect_components(root, None, detect_compose(root), None)
    return plan_component_runs(
        root,
        components,
        analyzers,
        matching_analyzers(root, analyzers),
        detect_workspace(root),
    )


def _by_path(plan: ComponentPlan) -> dict[str, list[ComponentTarget]]:
    out: dict[str, list[ComponentTarget]] = {}
    for target in plan.targets:
        out.setdefault(target.path, []).append(target)
    return out


def _names(targets: list[ComponentTarget]) -> list[str]:
    return [a.name for t in targets for a in t.analyzers]


def _node_root(root: Path, **root_extra: object) -> None:
    write(root / "package.json", _pkg("root", **root_extra))
    write(root / "web" / "package.json", _pkg("web", dependencies={"react": "18"}))
    write(root / "api" / "package.json", _pkg("api", dependencies={"express": "4"}))
    write(
        root / "docker-compose.yml",
        "services:\n  web:\n    build: ./web\n  api:\n    build: ./api\n",
    )


def test_the_audited_gap_nested_node_packages_are_planned_with_a_node_root() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _node_root(root)
        by_path = _by_path(_plan(root))
        assert set(by_path) == {"api", "web"}
        for targets in by_path.values():
            assert _names(targets).count("Node.js") == 1
            node = next(t for t in targets if t.analyzers[0].name == "Node.js")
            assert node.phases == _ALL


def test_a_root_test_fan_out_drops_the_nested_node_test_phase() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _node_root(root, scripts={"test": "turbo run test"})
        for targets in _by_path(_plan(root)).values():
            node = next(t for t in targets if t.analyzers[0].name == "Node.js")
            assert node.phases == frozenset({"quality", "security"})


def test_a_root_lint_fan_out_or_eslint_config_drops_nested_node_linting() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _node_root(root, scripts={"test": "echo r", "lint": "pnpm -r lint"})
        for targets in _by_path(_plan(root)).values():
            node = next(t for t in targets if t.analyzers[0].name == "Node.js")
            assert node.phases == frozenset({"tests", "security"})
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _node_root(root)
        write(root / "eslint.config.js", "export default []\n")
        for targets in _by_path(_plan(root)).values():
            node = next(t for t in targets if t.analyzers[0].name == "Node.js")
            assert node.phases == frozenset({"tests", "security"})


def test_a_nested_go_module_is_planned_unless_the_root_has_go_work() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "go.mod", "module root\n")
        write(root / "tools" / "cli" / "go.mod", "module cli\n")
        write(root / "docker-compose.yml", _COMPOSE)
        by_path = _by_path(_plan(root))
        assert "Go" in _names(by_path["tools/cli"])
        write(root / "go.work", "go 1.22\nuse ./tools/cli\n")
        assert "tools/cli" not in _by_path(_plan(root))


def test_a_nested_cargo_crate_is_planned_unless_it_is_a_workspace_member() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Cargo.toml", '[package]\nname = "root"\nversion = "0.1.0"\n')
        write(root / "extras" / "tool" / "Cargo.toml", '[package]\nname = "t"\n')
        write(root / "docker-compose.yml", _COMPOSE)
        assert "Rust" in _names(_by_path(_plan(root))["extras/tool"])
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(
            root / "Cargo.toml",
            '[workspace]\nmembers = ["extras/*"]\n[package]\nname = "root"\n',
        )
        write(root / "extras" / "tool" / "Cargo.toml", '[package]\nname = "t"\n')
        write(root / "docker-compose.yml", _COMPOSE)
        assert "extras/tool" not in _by_path(_plan(root))


def test_python_stays_covered_by_the_root_run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pyproject.toml", '[project]\nname = "r"\nversion = "1"\n')
        write(root / "tools" / "app" / "pyproject.toml", '[project]\nname = "a"\n')
        write(root / "docker-compose.yml", _COMPOSE)
        assert "tools/app" not in _by_path(_plan(root))


def test_node_workspace_members_are_never_planned_a_second_time() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(
            root / "package.json",
            _pkg("root", workspaces=["apps/*"], private=True),
        )
        write(
            root / "apps" / "web" / "package.json",
            _pkg("web", dependencies={"react": "1"}),
        )
        write(
            root / "apps" / "api" / "package.json",
            _pkg("api", dependencies={"express": "4"}),
        )
        write(root / "docker-compose.yml", _COMPOSE)
        by_path = _by_path(_plan(root))
        for path in ("apps/web", "apps/api"):
            node_targets = [
                t
                for t in by_path[path]
                if any(a.name == "Node.js" for a in t.analyzers)
            ]
            assert len(node_targets) == 1
            assert node_targets[0].phases == frozenset({"tests", "quality"})


def test_a_pnpm_only_hybrid_never_gives_members_the_security_phase() -> None:
    """Regression for a quirk of the workspace round: with no root
    package.json the Node analyzer did not match the root, so the hybrid
    plan added it with every phase and the merge unioned `security` into the
    member target."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pnpm-workspace.yaml", "packages:\n  - 'apps/*'\n")
        write(
            root / "apps" / "web" / "package.json",
            _pkg("web", dependencies={"react": "1"}),
        )
        write(
            root / "apps" / "api" / "package.json",
            _pkg("api", dependencies={"express": "4"}),
        )
        for targets in _by_path(_plan(root)).values():
            for target in targets:
                if any(a.name == "Node.js" for a in target.analyzers):
                    assert "security" not in target.phases


def test_not_hybrid_now_plans_nested_non_recursive_packages() -> None:
    """Pinned the gap before 5.55 (`== ()`); see
    tests/test_nested_non_hybrid.py for the full set."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", _pkg("root"))
        write(root / "sub" / "package.json", _pkg("sub"))
        assert {t.path for t in _plan(root).targets} == {"sub"}


def test_each_analyzer_runs_once_per_phase_and_directory() -> None:
    calls: list[str] = []

    async def fake_tests(self: NodeAnalyzer, root: Path) -> CommandResult | None:
        calls.append(f"tests:{root.name}")
        return CommandResult(kind="npm test", returncode=0, summary="")

    async def fake_quality(self: NodeAnalyzer, root: Path) -> list[CommandResult]:
        calls.append(f"quality:{root.name}")
        return []

    async def fake_security(self: NodeAnalyzer, root: Path) -> list[CommandResult]:
        calls.append(f"security:{root.name}")
        return []

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _node_root(root)
        plan = _plan(root)
        with (
            mock.patch.object(NodeAnalyzer, "run_tests", fake_tests),
            mock.patch.object(NodeAnalyzer, "run_quality", fake_quality),
            mock.patch.object(NodeAnalyzer, "run_security", fake_security),
        ):
            results = asyncio.run(run_component_tests(plan))
            asyncio.run(run_component_quality(plan))
            asyncio.run(run_component_security(plan))
    assert sorted(r.kind for r in results) == ["api: npm test", "web: npm test"]
    assert sorted(calls) == [
        "quality:api",
        "quality:web",
        "security:api",
        "security:web",
        "tests:api",
        "tests:web",
    ]


def test_the_directory_cap_counts_directories_not_targets() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", _pkg("root"))
        write(root / "docker-compose.yml", _COMPOSE)
        for i in range(10):
            write(
                root / f"s{i:02d}" / "package.json",
                _pkg(f"s{i}", dependencies={"react" if i % 2 else "express": "1"}),
            )
        plan = _plan(root)
        assert len({t.path for t in plan.targets}) == 8 and plan.omitted == 2
