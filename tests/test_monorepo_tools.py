"""Turborepo and Nx declared tasks, read statically (backlog item 1, round R12).

Detection rules, evidence rules, caps, broken files and the Markdown and JSON
output. Nothing here (or in the module) runs any tool.

تشخیص Turborepo و Nx به‌صورت ایستا: قواعد شاهد، سقف‌ها، فایل‌های خراب و خروجی
Markdown و JSON. هیچ ابزاری اجرا نمی‌شود.
"""

from __future__ import annotations

import ast
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from _helpers import write
from sarand.core import monorepo_tools
from sarand.core.monorepo_tools import detect_monorepo_tools
from sarand.models.results import (
    EnvironmentInfo,
    GitSnapshot,
    MonorepoToolInfo,
    ProjectStats,
    ReportData,
    WorkspaceInfo,
    WorkspaceMember,
)
from sarand.renderers import json_renderer, markdown


def _json(path: Path, value: object) -> None:
    write(path, json.dumps(value))


def _workspace(*paths: str) -> list[WorkspaceInfo]:
    members = [WorkspaceMember(path=path, name=path) for path in paths]
    return [WorkspaceInfo(kind="npm", members=members)]


def _only(tools: list[MonorepoToolInfo], kind: str) -> MonorepoToolInfo:
    found = [tool for tool in tools if tool.kind == kind]
    assert len(found) == 1, [tool.kind for tool in tools]
    return found[0]


# ---------------------------------------------------------------- Turborepo


def test_turbo_json_tasks_are_listed_in_declared_order() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _json(
            root / "turbo.json",
            {
                "tasks": {
                    "build": {
                        "dependsOn": ["^build"],
                        "outputs": ["dist/**", ".next/**"],
                    },
                    "dev": {"cache": False, "persistent": True},
                    "test": {"dependsOn": ["build"]},
                }
            },
        )
        tool = _only(detect_monorepo_tools(root, []), "turbo")
        assert tool.config_files == ["turbo.json"]
        assert [task.name for task in tool.tasks] == ["build", "dev", "test"]
        assert tool.tasks_total == 3
        assert tool.tasks[0].depends_on == ["^build"]
        assert tool.tasks[0].detail == "2 output pattern(s)"
        assert tool.tasks[1].detail == "cache off, persistent"
        assert "turbo.json declares tasks" in tool.evidence


def test_the_legacy_pipeline_key_is_read_and_said_so() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _json(root / "turbo.json", {"pipeline": {"build": {"dependsOn": ["^build"]}}})
        tool = _only(detect_monorepo_tools(root, []), "turbo")
        assert [task.name for task in tool.tasks] == ["build"]
        assert any("legacy `pipeline`" in note for note in tool.notes)


def test_an_unreadable_turbo_json_is_a_note_without_its_content() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "turbo.json", '{"tasks": SECRET_TOKEN_123 oops')
        tool = _only(detect_monorepo_tools(root, []), "turbo")
        assert tool.tasks == []
        assert any("is not valid JSON" in note for note in tool.notes)
        assert all("SECRET_TOKEN_123" not in note for note in tool.notes)


def test_turbo_json_without_tasks_or_pipeline_is_noted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _json(root / "turbo.json", {"$schema": "https://turbo.build/schema.json"})
        tool = _only(detect_monorepo_tools(root, []), "turbo")
        assert tool.tasks == []
        assert any("no `tasks` or `pipeline`" in note for note in tool.notes)


def test_a_json_array_is_not_a_turbo_config() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "turbo.json", "[1, 2]")
        tool = _only(detect_monorepo_tools(root, []), "turbo")
        assert any("is not a JSON object" in note for note in tool.notes)


def test_turbo_jsonc_is_recognised_but_not_parsed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "turbo.jsonc", '{ // comment\n "tasks": {"build": {}} }')
        tool = _only(detect_monorepo_tools(root, []), "turbo")
        assert tool.config_files == ["turbo.jsonc"]
        assert tool.tasks == []
        assert any("not parsed" in note for note in tool.notes)


def test_a_turbo_dependency_or_script_alone_is_not_enough() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _json(
            root / "package.json",
            {
                "scripts": {"build": "turbo run build"},
                "devDependencies": {"turbo": "^2"},
            },
        )
        assert detect_monorepo_tools(root, _workspace("packages/a")) == []


def test_a_turbo_dependency_is_extra_evidence_next_to_the_config() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _json(root / "turbo.json", {"tasks": {"build": {}}})
        _json(root / "package.json", {"devDependencies": {"turbo": "^2"}})
        tool = _only(detect_monorepo_tools(root, []), "turbo")
        assert "package.json depends on turbo" in tool.evidence


def test_package_level_turbo_json_files_are_counted_not_read() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _json(root / "turbo.json", {"tasks": {"build": {}}})
        _json(root / "packages" / "a" / "turbo.json", {"extends": ["//"]})
        _json(root / "packages" / "b" / "turbo.json", {"extends": ["//"]})
        tool = _only(
            detect_monorepo_tools(root, _workspace("packages/a", "packages/b")), "turbo"
        )
        assert any("2 package-level turbo.json" in note for note in tool.notes)
        assert [task.name for task in tool.tasks] == ["build"]


def test_tasks_beyond_the_cap_are_counted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        total = monorepo_tools.MAX_TASKS + 5
        _json(root / "turbo.json", {"tasks": {f"t{i}": {} for i in range(total)}})
        tool = _only(detect_monorepo_tools(root, []), "turbo")
        assert len(tool.tasks) == monorepo_tools.MAX_TASKS
        assert tool.tasks_total == total


def test_an_oversized_turbo_json_is_not_read() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        big = {"tasks": {"build": {"outputs": ["x" * 1000] * 1500}}}
        _json(root / "turbo.json", big)
        assert (root / "turbo.json").stat().st_size > 1024 * 1024
        tool = _only(detect_monorepo_tools(root, []), "turbo")
        assert tool.tasks == []
        assert any("too large" in note for note in tool.notes)


# ----------------------------------------------------------------------- Nx


def test_nx_json_with_target_defaults_and_plugins() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _json(
            root / "nx.json",
            {
                "targetDefaults": {
                    "build": {"dependsOn": ["^build"], "cache": True},
                    "test": {
                        "dependsOn": [{"projects": "self", "target": "build"}],
                        "executor": "@nx/jest:jest",
                    },
                },
                "plugins": [{"plugin": "@nx/vite"}, "@nx/eslint"],
            },
        )
        tool = _only(detect_monorepo_tools(root, []), "nx")
        assert [task.name for task in tool.tasks] == ["build", "test"]
        assert tool.tasks[0].depends_on == ["^build"]
        assert tool.tasks[0].detail == "cache on"
        assert tool.tasks[1].depends_on == ['{"projects":"self","target":"build"}']
        assert tool.tasks[1].detail == "executor @nx/jest:jest"
        assert any(
            "2 plugin(s) declared (@nx/vite, @nx/eslint)" in n for n in tool.notes
        )
        assert any("infer" in note and "not shown" in note for note in tool.notes)


def test_the_inference_limit_is_always_stated_for_nx() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _json(root / "nx.json", {})
        tool = _only(detect_monorepo_tools(root, []), "nx")
        assert any("targets that Nx plugins infer" in note for note in tool.notes)


def test_project_json_files_become_declared_projects() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _json(root / "nx.json", {})
        _json(
            root / "apps" / "web" / "project.json",
            {
                "name": "web",
                "targets": {
                    "build": {"executor": "@nx/vite:build", "dependsOn": ["^build"]},
                    "serve": {"command": "vite"},
                },
            },
        )
        _json(root / "libs" / "ui" / "project.json", {"targets": {}})
        tool = _only(detect_monorepo_tools(root, []), "nx")
        assert [p.path for p in tool.projects] == ["apps/web", "libs/ui"]
        web, ui = tool.projects
        assert (web.name, web.name_declared) == ("web", True)
        assert [t.name for t in web.targets] == ["build", "serve"]
        assert web.targets[0].detail == "executor @nx/vite:build"
        assert web.targets[1].detail == "command"
        assert (ui.name, ui.name_declared) == ("ui", False)
        assert "2 project.json file(s)" in tool.evidence


def test_project_json_without_nx_json_is_not_enough() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _json(root / "apps" / "web" / "project.json", {"name": "web", "targets": {}})
        _json(root / "package.json", {"devDependencies": {"nx": "^19"}})
        assert detect_monorepo_tools(root, []) == []


def test_an_unreadable_nx_json_is_still_nx_with_a_note() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "nx.json", "{ not json")
        tool = _only(detect_monorepo_tools(root, []), "nx")
        assert tool.tasks == []
        assert any("nx.json is not valid JSON" in note for note in tool.notes)


def test_a_broken_project_json_is_counted_and_skipped() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _json(root / "nx.json", {})
        write(root / "apps" / "a" / "project.json", "{ broken")
        _json(root / "apps" / "b" / "project.json", {"name": "b"})
        tool = _only(detect_monorepo_tools(root, []), "nx")
        assert [p.path for p in tool.projects] == ["apps/b"]
        assert any("1 project.json file(s) could not be read" in n for n in tool.notes)


def test_an_explicit_nx_block_in_a_member_package_json_is_a_project() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _json(root / "nx.json", {})
        _json(
            root / "packages" / "api" / "package.json",
            {"name": "@acme/api", "nx": {"targets": {"build": {"command": "tsc"}}}},
        )
        _json(root / "packages" / "plain" / "package.json", {"name": "@acme/plain"})
        tool = _only(
            detect_monorepo_tools(root, _workspace("packages/api", "packages/plain")),
            "nx",
        )
        assert [(p.path, p.name) for p in tool.projects] == [
            ("packages/api", "@acme/api")
        ]


def test_a_member_with_project_json_is_not_listed_twice() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _json(root / "nx.json", {})
        _json(root / "packages" / "api" / "project.json", {"name": "api"})
        _json(
            root / "packages" / "api" / "package.json",
            {"name": "@acme/api", "nx": {"targets": {"build": {}}}},
        )
        tool = _only(detect_monorepo_tools(root, _workspace("packages/api")), "nx")
        assert [p.path for p in tool.projects] == ["packages/api"]


def test_projects_and_targets_beyond_the_caps_are_counted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _json(root / "nx.json", {})
        total = monorepo_tools.MAX_PROJECTS + 5
        many: dict[str, dict[str, object]] = {
            f"t{i}": {} for i in range(monorepo_tools.MAX_TARGETS_PER_PROJECT + 3)
        }
        for index in range(total):
            _json(
                root / "apps" / f"app{index:03d}" / "project.json",
                {"name": f"app{index:03d}", "targets": many},
            )
        tool = _only(detect_monorepo_tools(root, []), "nx")
        assert len(tool.projects) == monorepo_tools.MAX_PROJECTS
        assert tool.projects_total == total
        first = tool.projects[0]
        assert len(first.targets) == monorepo_tools.MAX_TARGETS_PER_PROJECT
        assert first.targets_total == monorepo_tools.MAX_TARGETS_PER_PROJECT + 3


def test_ignored_directories_and_symlinks_are_not_searched() -> None:
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
        root = Path(tmp)
        _json(root / "nx.json", {})
        _json(root / "node_modules" / "dep" / "project.json", {"name": "dep"})
        _json(root / ".hidden" / "project.json", {"name": "hidden"})
        _json(Path(outside) / "project.json", {"name": "outside"})
        try:
            (root / "link").symlink_to(outside, target_is_directory=True)
        except OSError:
            pass
        _json(root / "apps" / "real" / "project.json", {"name": "real"})
        tool = _only(detect_monorepo_tools(root, []), "nx")
        assert [p.name for p in tool.projects] == ["real"]


def test_deep_project_json_files_beyond_the_depth_are_not_read() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _json(root / "nx.json", {})
        deep = root.joinpath(*[f"d{i}" for i in range(monorepo_tools._MAX_DEPTH + 2)])
        _json(deep / "project.json", {"name": "too-deep"})
        assert _only(detect_monorepo_tools(root, []), "nx").projects == []


# --------------------------------------------------------------- both / none


def test_nothing_is_reported_without_a_config_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert detect_monorepo_tools(Path(tmp), []) == []


def test_a_repository_with_both_lists_turbo_first_then_nx() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _json(root / "turbo.json", {"tasks": {"build": {}}})
        _json(root / "nx.json", {})
        assert [t.kind for t in detect_monorepo_tools(root, [])] == ["turbo", "nx"]


def test_the_module_never_runs_anything() -> None:
    tree = ast.parse(Path(monorepo_tools.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
            used.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
    assert not imported & {"subprocess", "shlex", "pty"}
    assert not used & {"run_cmd", "run_cmd_async", "run_tool", "system", "Popen"}


# ------------------------------------------------------------------ reports


def _data(root: Path, tools: list[MonorepoToolInfo]) -> ReportData:
    return ReportData(
        project_root=root,
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        environment=EnvironmentInfo(),
        git=GitSnapshot(),
        stats=ProjectStats(),
        monorepo_tools=tools,
    )


def _both(root: Path) -> list[MonorepoToolInfo]:
    _json(root / "turbo.json", {"tasks": {"build": {"dependsOn": ["^build"]}}})
    _json(root / "nx.json", {"targetDefaults": {"test": {}}})
    _json(root / "apps" / "web" / "project.json", {"name": "web", "targets": {"b": {}}})
    return detect_monorepo_tools(root, [])


def test_markdown_has_no_section_without_tools() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        text = markdown.render(_data(Path(tmp), []), include_source=False)
        assert "Monorepo tooling" not in text


def test_markdown_lists_tasks_projects_and_the_static_statement() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        text = markdown.render(_data(root, _both(root)), include_source=False)
        assert "## Monorepo tooling" in text
        assert "nothing was executed" in text
        assert "### Turborepo" in text and "### Nx" in text
        assert "| `build` | `^build` | - |" in text
        assert "Target defaults (1):" in text
        assert "- `apps/web` -- `web`: b" in text
        assert "targets that Nx plugins infer" in text


def test_markdown_cells_are_safe_for_names_with_pipes_and_backticks() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _json(root / "turbo.json", {"tasks": {"a|b`c": {"dependsOn": ["x|y"]}}})
        text = markdown.render(
            _data(root, detect_monorepo_tools(root, [])), include_source=False
        )
        assert "| `a\\|b'c` | `x\\|y` | - |" in text


def test_markdown_says_how_many_tasks_were_left_out() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        total = monorepo_tools.MAX_TASKS + 3
        _json(root / "turbo.json", {"tasks": {f"t{i}": {} for i in range(total)}})
        text = markdown.render(
            _data(root, detect_monorepo_tools(root, [])), include_source=False
        )
        assert f"Declared tasks ({total}):" in text
        assert "(+3 more not shown)" in text


def test_json_has_no_key_without_tools() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        payload = json.loads(
            json_renderer.render(_data(Path(tmp), []), include_source=False)
        )
        assert "monorepo_tools" not in payload


def test_json_carries_the_same_facts_as_markdown() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tools = _both(root)
        payload = json.loads(
            json_renderer.render(_data(root, tools), include_source=False)
        )
        listed = payload["monorepo_tools"]
        assert [tool["kind"] for tool in listed] == ["turbo", "nx"]
        assert listed[0]["tasks"][0] == {
            "name": "build",
            "depends_on": ["^build"],
            "detail": "",
        }
        assert listed[0]["tasks_total"] == 1
        assert listed[1]["projects"][0]["path"] == "apps/web"
        assert listed[1]["projects_total"] == 1
        assert listed[1]["projects"][0]["targets"][0]["name"] == "b"
