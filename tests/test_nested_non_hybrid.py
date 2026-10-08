"""Regression tests for the nested-package gap of non-hybrid projects (AGENTS.md
section 5.55, the "Non-hybrid projects" paragraph of `core/per_component.py`).

A project that is not hybrid (one package kind, no compose / Kubernetes /
Terraform) used to get no nested runs: `detect_components` returned None, so
the planner had nothing to plan. Node.js, Go and Rust packages below the root
were never tested, linted or audited.

تست‌های شکاف بسته‌های تو در تو در پروژه‌های غیرهیبرید (بخش ۵.۵۵ AGENTS.md).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

from _helpers import write
from sarand.analyzers.registry import builtin_analyzers, matching_analyzers
from sarand.core.components import detect_components
from sarand.core.per_component import ComponentPlan, plan_component_runs
from sarand.core.workspace import detect_workspace

_ALL = frozenset({"tests", "quality", "security"})


def _pkg(name: str, **extra: object) -> str:
    data: dict[str, object] = {"name": name, "scripts": {"test": f"echo {name}"}}
    data.update(extra)
    return json.dumps(data)


def _plan(root: Path) -> ComponentPlan:
    analyzers = builtin_analyzers()
    return plan_component_runs(
        root,
        detect_components(root, None, None, None),
        analyzers,
        matching_analyzers(root, analyzers),
        detect_workspace(root),
    )


def _names(plan: ComponentPlan, path: str) -> list[str]:
    return [a.name for t in plan.targets if t.path == path for a in t.analyzers]


def _paths(plan: ComponentPlan) -> set[str]:
    return {t.path for t in plan.targets}


def test_a_node_root_with_a_standalone_nested_package_is_planned() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", _pkg("root"))
        write(root / "tools" / "cli" / "package.json", _pkg("cli"))
        # The premise of the audited gap: this is not a hybrid project.
        assert detect_components(root, None, None, None) is None
        plan = _plan(root)
        assert _paths(plan) == {"tools/cli"}
        assert _names(plan, "tools/cli") == ["Node.js"]
        node = plan.targets[0]
        assert node.phases == _ALL


def test_a_go_root_with_a_nested_module_is_planned_unless_go_work() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "go.mod", "module root\n")
        write(root / "tools" / "cli" / "go.mod", "module cli\n")
        assert _names(_plan(root), "tools/cli") == ["Go"]
        write(root / "go.work", "go 1.22\nuse ./tools/cli\n")
        assert _paths(_plan(root)) == set()


def test_a_rust_root_with_a_nested_crate_is_planned_unless_a_member() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Cargo.toml", '[package]\nname = "root"\nversion = "0.1.0"\n')
        write(root / "extras" / "tool" / "Cargo.toml", '[package]\nname = "t"\n')
        assert _names(_plan(root), "extras/tool") == ["Rust"]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(
            root / "Cargo.toml",
            '[workspace]\nmembers = ["extras/*"]\n[package]\nname = "root"\n',
        )
        write(root / "extras" / "tool" / "Cargo.toml", '[package]\nname = "t"\n')
        assert _paths(_plan(root)) == set()


def test_node_workspace_members_are_not_planned_twice() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", _pkg("root", workspaces=["packages/*"]))
        write(root / "packages" / "a" / "package.json", _pkg("a"))
        write(root / "tools" / "cli" / "package.json", _pkg("cli"))
        plan = _plan(root)
        by_dir = {t.path: t for t in plan.targets}
        # The member keeps its single, workspace-restricted target ...
        assert [t.path for t in plan.targets].count("packages/a") == 1
        assert by_dir["packages/a"].phases <= frozenset({"tests", "quality"})
        # ... and the standalone package is planned with the nested phases.
        assert "security" in by_dir["tools/cli"].phases


def test_a_root_without_a_marker_still_runs_every_nested_node_package() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Makefile", "all:\n\techo hi\n")
        write(root / "web" / "package.json", _pkg("web"))
        write(root / "admin" / "package.json", _pkg("admin"))
        assert detect_components(root, None, None, None) is None
        plan = _plan(root)
        assert _paths(plan) == {"web", "admin"}
        # Only the three non-recursive analyzers: no JSON / YAML extras.
        assert _names(plan, "web") == ["Node.js"]
        assert _names(plan, "admin") == ["Node.js"]


def test_root_fan_out_and_eslint_rules_apply_to_nested_packages_too() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(
            root / "package.json",
            _pkg("root", scripts={"test": "turbo run test", "lint": "echo l"}),
        )
        write(root / "tools" / "cli" / "package.json", _pkg("cli"))
        node = _plan(root).targets[0]
        assert "tests" not in node.phases
        assert "security" in node.phases


def test_example_test_and_fixture_directories_are_never_planned() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", _pkg("root"))
        for sub in ("examples", "fixtures", "tests", "vendor"):
            write(root / sub / "demo" / "package.json", _pkg("demo"))
        write(root / "node_modules" / "x" / "package.json", _pkg("x"))
        assert _paths(_plan(root)) == set()


def test_python_stays_covered_by_the_root_run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pyproject.toml", '[project]\nname = "root"\n')
        write(root / "tools" / "x" / "pyproject.toml", '[project]\nname = "x"\n')
        assert _paths(_plan(root)) == set()


def test_a_plain_project_without_nested_packages_has_an_empty_plan() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", _pkg("root"))
        write(root / "src" / "index.js", "console.log(1)\n")
        plan = _plan(root)
        assert plan.targets == ()
        assert plan.omitted == 0


def test_the_cap_applies_and_the_rest_is_counted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", _pkg("root"))
        for index in range(10):
            write(root / "pkgs" / f"p{index:02d}" / "package.json", _pkg(f"p{index}"))
        plan = _plan(root)
        assert len(_paths(plan)) == 8
        assert plan.omitted == 2


def test_the_escape_hatch_disables_nested_runs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", _pkg("root"))
        write(root / "tools" / "cli" / "package.json", _pkg("cli"))
        with mock.patch.dict(os.environ, {"SARAND_NO_COMPONENTS": "1"}):
            assert _plan(root).targets == ()
