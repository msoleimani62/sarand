"""Every workspace of a repository is modelled (AGENTS.md section 5.58).

A repository with both a Cargo and a Node workspace used to record only the
first (`cargo`): the report listed one workspace and the planner treated the
Node members as stray nested packages with a per-member `npm audit`.

مدل‌کردن همه‌ی workspaceهای مخزن (بخش ۵.۵۸ AGENTS.md).
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from _helpers import write
from sarand.analyzers.registry import builtin_analyzers, matching_analyzers
from sarand.core.components import detect_components
from sarand.core.per_component import ComponentPlan, plan_component_runs
from sarand.core.workspace import detect_workspace, detect_workspaces
from sarand.models.results import (
    EnvironmentInfo,
    GitSnapshot,
    ProjectStats,
    ReportData,
    WorkspaceInfo,
    WorkspaceMember,
)
from sarand.renderers import json_renderer, markdown


def _pkg(name: str, **extra: object) -> str:
    data: dict[str, object] = {
        "name": name,
        "scripts": {"test": f"echo {name}", "lint": "echo lint"},
    }
    data.update(extra)
    return json.dumps(data)


def _build_both(root: Path, **root_pkg: object) -> None:
    write(
        root / "Cargo.toml",
        '[workspace]\nmembers = ["crates/*"]\n[package]\nname = "root"\nversion = "0.1.0"\n',
    )
    write(root / "crates" / "x" / "Cargo.toml", '[package]\nname = "x"\n')
    write(root / "package.json", _pkg("root", workspaces=["packages/*"], **root_pkg))
    write(root / "packages" / "a" / "package.json", _pkg("a"))
    write(root / "packages" / "b" / "package.json", _pkg("b"))
    write(root / "tools" / "cli" / "package.json", _pkg("cli"))


def _plan(root: Path, workspace: object) -> ComponentPlan:
    analyzers = builtin_analyzers()
    return plan_component_runs(
        root,
        detect_components(root, None, None, None),
        analyzers,
        matching_analyzers(root, analyzers),
        workspace,  # type: ignore[arg-type]
    )


def _by_path(plan: ComponentPlan) -> dict[str, list[tuple[str, frozenset[str]]]]:
    out: dict[str, list[tuple[str, frozenset[str]]]] = {}
    for target in plan.targets:
        out.setdefault(target.path, []).extend(
            (a.name, target.phases) for a in target.analyzers
        )
    return out


def test_both_workspaces_are_detected_in_order() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _build_both(root)
        found = detect_workspaces(root)
        assert [w.kind for w in found] == ["cargo", "npm"]
        assert [m.path for m in found[1].members] == ["packages/a", "packages/b"]
        first = detect_workspace(root)
        assert first is not None and first.kind == "cargo"


def test_one_or_no_workspace_is_unchanged() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert detect_workspaces(root) == []
        assert detect_workspace(root) is None
        write(root / "package.json", _pkg("root", workspaces=["packages/*"]))
        write(root / "packages" / "a" / "package.json", _pkg("a"))
        assert [w.kind for w in detect_workspaces(root)] == ["npm"]


def test_node_members_are_planned_as_members_not_as_stray_packages() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _build_both(root)
        planned = _by_path(_plan(root, detect_workspaces(root)))
        for member in ("packages/a", "packages/b"):
            # Exactly one Node.js run, tests and quality only: no npm audit.
            assert planned[member] == [("Node.js", frozenset({"tests", "quality"}))]
        # A standalone package keeps the security phase (own lockfile).
        assert ("Node.js", frozenset({"tests", "quality", "security"})) in planned[
            "tools/cli"
        ]
        # Cargo members are covered by `cargo test --all`.
        assert "crates/x" not in planned


def test_the_audited_gap_is_visible_with_only_the_first_workspace() -> None:
    """Documents the before-state: handing the planner just the Cargo
    workspace (the old behaviour) makes the Node members look stray."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _build_both(root)
        old = _by_path(_plan(root, detect_workspace(root)))
        assert ("Node.js", frozenset({"tests", "quality", "security"})) in old[
            "packages/a"
        ]


def test_a_list_and_a_single_workspace_plan_identically() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", _pkg("root", workspaces=["packages/*"]))
        write(root / "packages" / "a" / "package.json", _pkg("a"))
        single = detect_workspace(root)
        assert single is not None
        assert _by_path(_plan(root, single)) == _by_path(_plan(root, [single]))


def test_the_order_of_the_workspaces_does_not_matter() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _build_both(root)
        found = detect_workspaces(root)
        assert _by_path(_plan(root, found)) == _by_path(_plan(root, found[::-1]))


def test_a_root_script_that_fans_out_still_drops_the_member_phase() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _build_both(root, scripts={"test": "npm test --workspaces", "lint": "echo l"})
        planned = _by_path(_plan(root, detect_workspaces(root)))
        assert planned["packages/a"] == [("Node.js", frozenset({"quality"}))]


def test_a_cargo_only_workspace_is_unchanged() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Cargo.toml", '[workspace]\nmembers = ["crates/*"]\n')
        write(root / "crates" / "x" / "Cargo.toml", '[package]\nname = "x"\n')
        assert _by_path(_plan(root, detect_workspaces(root))) == {}


def _data(root: Path, *workspaces: WorkspaceInfo) -> ReportData:
    return ReportData(
        project_root=root,
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        environment=EnvironmentInfo(),
        git=GitSnapshot(),
        stats=ProjectStats(),
        workspace=workspaces[0] if workspaces else None,
        extra_workspaces=list(workspaces[1:]),
    )


def _cargo() -> WorkspaceInfo:
    return WorkspaceInfo(kind="cargo", members=[WorkspaceMember("crates/x", "x")])


def _npm() -> WorkspaceInfo:
    return WorkspaceInfo(kind="npm", members=[WorkspaceMember("packages/a", "a")])


def test_all_workspaces_lists_the_first_then_the_rest() -> None:
    root = Path("project")
    assert _data(root).all_workspaces == []
    assert [w.kind for w in _data(root, _cargo()).all_workspaces] == ["cargo"]
    assert [w.kind for w in _data(root, _cargo(), _npm()).all_workspaces] == [
        "cargo",
        "npm",
    ]


def test_markdown_keeps_the_plain_heading_for_one_workspace() -> None:
    rendered = markdown.render(_data(Path("project"), _cargo()), include_source=False)
    assert "## Workspace\n" in rendered
    assert "## Workspace (" not in rendered


def test_markdown_names_each_workspace_when_there_are_several() -> None:
    rendered = markdown.render(
        _data(Path("project"), _cargo(), _npm()), include_source=False
    )
    assert "## Workspace (cargo)" in rendered
    assert "## Workspace (npm)" in rendered
    assert "| x | `crates/x` |" in rendered
    assert "| a | `packages/a` |" in rendered


def test_json_gets_a_workspaces_list_only_for_several() -> None:
    one = json.loads(
        json_renderer.render(_data(Path("project"), _cargo()), include_source=False)
    )
    assert "workspaces" not in one and one["workspace"]["kind"] == "cargo"
    many = json.loads(
        json_renderer.render(
            _data(Path("project"), _cargo(), _npm()), include_source=False
        )
    )
    assert many["workspace"] == many["workspaces"][0]
    assert [w["kind"] for w in many["workspaces"]] == ["cargo", "npm"]
    none = json.loads(
        json_renderer.render(_data(Path("project")), include_source=False)
    )
    assert "workspace" not in none and "workspaces" not in none
