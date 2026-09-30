"""Regression tests for backlog item 11 (Hybrid project model,
representation-only first scope) -- see AGENTS.md section 5.40 and
`core/components.py`'s module docstring for the audit and rationale.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from _helpers import write
from sarand.core.components import detect_components
from sarand.core.compose import detect_compose
from sarand.core.kubernetes import detect_kubernetes
from sarand.core.makefile import detect_makefiles
from sarand.models.results import (
    Component,
    ComponentLink,
    ComponentsInfo,
    EnvironmentInfo,
    GitSnapshot,
    ProjectStats,
    ReportData,
)
from sarand.renderers import json_renderer, markdown

_COMPOSE = (
    "services:\n"
    "  api:\n"
    "    build: ./backend\n"
    "  web:\n"
    "    build:\n"
    "      context: ./frontend\n"
    "  db:\n"
    "    image: postgres:16\n"
    "  ext:\n"
    "    build: https://github.com/example/repo.git\n"
    "  up:\n"
    "    build: ../elsewhere\n"
)


def build_hybrid(root: Path) -> None:
    """The hybrid fixture from the item-11 audit."""
    write(
        root / "backend" / "pyproject.toml",
        '[project]\nname = "api"\nversion = "0.1"\ndependencies = ["FastAPI>=0.100"]\n',
    )
    write(root / "backend" / "app" / "main.py", "print(1)\n")
    write(
        root / "frontend" / "package.json",
        '{"name": "web", "dependencies": {"react": "18", "vite": "5"}}',
    )
    write(root / "frontend" / "src" / "index.js", "console.log(1)\n")
    write(root / "docker-compose.yml", _COMPOSE)
    write(root / ".github" / "workflows" / "ci.yml", "name: CI\non: push\n")
    write(root / "Makefile", "all:\n\techo\n")
    write(root / "deploy" / "k8s" / "kustomization.yaml", "resources: []\n")
    write(root / "docs" / "index.md", "# Docs\n")


def _detect(root: Path) -> ComponentsInfo | None:
    return detect_components(
        root,
        detect_kubernetes(root),
        detect_compose(root),
        detect_makefiles(root),
    )


def _by_key(info: ComponentsInfo) -> dict[tuple[str, str], Component]:
    return {(c.path, c.role): c for c in info.components}


def test_hybrid_fixture_components_are_distinguishable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build_hybrid(root)
        info = _detect(root)
        assert info is not None
        comps = _by_key(info)
        backend = comps[("backend", "application")]
        assert (backend.kind, backend.languages) == ("backend", ["Python"])
        frontend = comps[("frontend", "application")]
        assert (frontend.kind, frontend.languages) == ("frontend", ["Node.js"])
        assert comps[("docker-compose.yml", "infrastructure")].kind == "compose"
        assert comps[("deploy/k8s", "infrastructure")].kind == "kustomize"
        assert comps[(".github/workflows", "ci")].kind == "github-actions"
        assert comps[("docs", "documentation")].evidence == ["docs/"]
        assert comps[("Makefile", "configuration")].kind == "make"
        roles = [c.role for c in info.components]
        assert roles == sorted(
            roles,
            key=[
                "application",
                "infrastructure",
                "ci",
                "documentation",
                "configuration",
            ].index,
        )


def test_compose_build_contexts_become_relationships_only_when_resolvable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build_hybrid(root)
        info = _detect(root)
        assert info is not None
        assert [(k.source, k.target, k.relation) for k in info.links] == [
            ("docker-compose.yml", "backend", "builds"),
            ("docker-compose.yml", "frontend", "builds"),
        ]
        assert info.links[0].evidence == "service 'api' build context"
        assert info.total_links == 2


def test_compose_in_subdirectory_resolves_context_relative_to_itself() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(
            root / "services" / "api" / "package.json",
            '{"dependencies": {"express": "4"}}',
        )
        write(root / "app" / "package.json", '{"dependencies": {"react": "18"}}')
        write(
            root / "deploy" / "compose.yaml",
            "services:\n  api:\n    build: ../services/api\n  web:\n    build: ../app\n",
        )
        info = _detect(root)
        assert info is not None
        assert [(k.target) for k in info.links] == ["app", "services/api"]


def test_plain_project_is_not_hybrid_and_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pyproject.toml", '[project]\nname = "x"\nversion = "1"\n')
        write(root / "Dockerfile", "FROM python:3\n")
        write(root / ".github" / "workflows" / "ci.yml", "name: CI\n")
        write(root / "docs" / "index.md", "# d\n")
        write(root / "Makefile", "all:\n")
        assert _detect(root) is None


def test_same_kind_workspace_members_are_not_hybrid() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Cargo.toml", "[workspace]\nmembers = ['a', 'b']\n")
        write(root / "a" / "Cargo.toml", '[package]\nname = "a"\n')
        write(root / "b" / "Cargo.toml", '[package]\nname = "b"\n')
        assert _detect(root) is None


def test_application_plus_compose_is_hybrid() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "go.mod", "module x\n")
        write(root / "compose.yaml", "services:\n  app:\n    build: .\n")
        info = _detect(root)
        assert info is not None
        assert [(k.source, k.target) for k in info.links] == [("compose.yaml", ".")]


def test_two_languages_are_hybrid_without_any_infrastructure() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "server" / "go.mod", "module x\n")
        write(root / "client" / "Gemfile", "source 'https://rubygems.org'\n")
        info = _detect(root)
        assert info is not None
        assert {(c.path, tuple(c.languages)) for c in info.components} == {
            ("server", ("Go",)),
            ("client", ("Ruby",)),
        }


def test_frontend_and_backend_hints_need_unambiguous_dependencies() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(
            root / "both" / "package.json",
            '{"dependencies": {"next": "1", "express": "4"}}',
        )
        write(root / "none" / "package.json", '{"dependencies": {"lodash": "4"}}')
        write(root / "broken" / "package.json", "{not json")
        write(root / "py" / "requirements.txt", "# c\nDjango==5.0\n")
        write(root / "py" / "app.py", "x = 1\n")
        write(
            root / "py2" / "pyproject.toml", "[tool.poetry.dependencies]\nflask = '*'\n"
        )
        info = _detect(root)
        assert info is not None
        kinds = {c.path: c.kind for c in info.components if c.role == "application"}
        assert kinds["both"] == ""
        assert kinds["none"] == ""
        assert kinds["broken"] == ""
        assert kinds["py2"] == "backend"


def test_weak_marker_alone_is_not_a_component_below_the_root() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "docs" / "requirements.txt", "sphinx\n")
        write(root / "a" / "go.mod", "module a\n")
        write(root / "b" / "Gemfile", "x\n")
        info = _detect(root)
        assert info is not None
        assert "docs" not in {
            c.path for c in info.components if c.role == "application"
        }


def test_fixture_vendor_and_dependency_dirs_are_never_components() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "a" / "go.mod", "module a\n")
        write(root / "b" / "Gemfile", "x\n")
        for skipped in ("node_modules", "tests", "examples", "vendor", ".venv"):
            write(root / skipped / "pkg" / "package.json", "{}")
        info = _detect(root)
        assert info is not None
        assert {c.path for c in info.components} == {"a", "b"}


def test_search_depth_is_bounded() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "a" / "b" / "c" / "deep" / "go.mod", "module d\n")
        write(root / "a" / "b" / "c" / "go.mod", "module c\n")
        write(root / "x" / "Gemfile", "x\n")
        info = _detect(root)
        assert info is not None
        paths = {c.path for c in info.components}
        assert "a/b/c" in paths
        assert "a/b/c/deep" not in paths


def test_terraform_and_dockerfile_directories_are_infrastructure() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "app" / "go.mod", "module a\n")
        write(root / "app" / "Dockerfile", "FROM scratch\n")
        write(root / "infra" / "main.tf", 'resource "x" "y" {}\n')
        info = _detect(root)
        assert info is not None
        comps = _by_key(info)
        assert comps[("infra", "infrastructure")].kind == "terraform"
        assert comps[("app", "infrastructure")].kind == "container"


def test_component_cap_keeps_true_totals() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for i in range(60):
            write(root / f"svc{i:02d}" / "go.mod", "module m\n")
        write(root / "web" / "Gemfile", "x\n")
        info = _detect(root)
        assert info is not None
        assert info.total_components == 61
        assert len(info.components) == 50


def test_malformed_compose_and_unreadable_manifests_do_not_crash() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "a" / "go.mod", "module a\n")
        write(root / "compose.yaml", "services: [broken")
        (root / "b").mkdir()
        (root / "b" / "package.json").write_bytes(b"\xff\xfe\x00")
        info = _detect(root)
        assert info is not None
        assert info.links == []


def test_detection_adds_no_findings_and_is_deterministic() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build_hybrid(root)
        first = _detect(root)
        second = _detect(root)
        assert first == second
        assert not hasattr(first, "issues")
        assert not hasattr(first, "known_issues")


def _data(root: Path, components: ComponentsInfo | None) -> ReportData:
    return ReportData(
        project_root=root,
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        environment=EnvironmentInfo(),
        git=GitSnapshot(),
        stats=ProjectStats(),
        components=components,
    )


def _sample() -> ComponentsInfo:
    return ComponentsInfo(
        components=[
            Component(
                path="backend",
                role="application",
                kind="backend",
                languages=["Python"],
                evidence=["pyproject.toml"],
            ),
            Component(path="docs", role="documentation"),
        ],
        links=[
            ComponentLink(
                source="compose.yaml",
                target="backend",
                relation="builds",
                evidence="service 'api' build context",
            )
        ],
        total_components=3,
        total_links=2,
    )


def test_markdown_has_no_components_section_when_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        rendered = markdown.render(_data(Path(tmp), None), include_source=False)
        assert "## Project Components" not in rendered


def test_markdown_renders_table_relationships_and_truncation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        rendered = markdown.render(_data(Path(tmp), _sample()), include_source=False)
        assert "## Project Components" in rendered
        assert (
            "| `backend` | application | backend | Python | `pyproject.toml` |"
            in rendered
        )
        assert "| `docs` | documentation | - | - | - |" in rendered
        assert "_1 more component(s) not shown._" in rendered
        assert (
            "- `compose.yaml` builds `backend` (service 'api' build context)"
            in rendered
        )
        assert "_1 more relationship(s) not shown._" in rendered
        assert rendered.index("## Project Components") < rendered.index(
            "## Environment"
        )


def test_json_has_no_components_key_when_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        payload = json.loads(
            json_renderer.render(_data(Path(tmp), None), include_source=False)
        )
        assert "components" not in payload


def test_json_renders_components_key_when_present() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        payload = json.loads(
            json_renderer.render(_data(Path(tmp), _sample()), include_source=False)
        )
        block = payload["components"]
        assert (block["total_components"], block["total_links"]) == (3, 2)
        assert block["components"][0] == {
            "path": "backend",
            "role": "application",
            "kind": "backend",
            "languages": ["Python"],
            "evidence": ["pyproject.toml"],
        }
        assert block["links"][0]["relation"] == "builds"
