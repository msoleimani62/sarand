"""Regression tests for backlog item 6 (Docker Compose, detection-only
first scope) -- see AGENTS.md section 5.38 and `core/compose.py`'s
module docstring for the audit and design rationale.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from _helpers import write
from sarand.core.compose import detect_compose
from sarand.models.results import (
    ComposeFile,
    ComposeInfo,
    ComposeService,
    EnvironmentInfo,
    GitSnapshot,
    ProjectStats,
    ReportData,
)
from sarand.renderers import json_renderer, markdown

_BASIC = (
    "services:\n"
    "  web:\n"
    "    image: nginx:1.27\n"
    "  api:\n"
    "    build: ./api\n"
    "  db:\n"
    "    image: postgres:16\n"
    "    build:\n"
    "      context: ./db\n"
)


def test_project_without_compose_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "app.py", "print('hi')\n")
        write(root / "config.yaml", "services:\n  web:\n    image: x\n")
        assert detect_compose(root) is None


def test_services_are_read_with_image_and_build_flag_in_file_order() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "docker-compose.yml", _BASIC)
        info = detect_compose(root)
        assert info is not None
        assert [f.path for f in info.files] == ["docker-compose.yml"]
        assert [(s.name, s.image, s.builds) for s in info.files[0].services] == [
            ("web", "nginx:1.27", False),
            ("api", "", True),
            ("db", "postgres:16", True),
        ]


def test_all_supported_names_are_found() -> None:
    names = [
        "compose.yaml",
        "compose.yml",
        "docker-compose.yaml",
        "docker-compose.yml",
        "docker-compose.override.yml",
        "compose.prod.yaml",
    ]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name in names:
            write(root / name, "services: {}\n")
        info = detect_compose(root)
        assert info is not None
        assert [f.path for f in info.files] == sorted(names)


def test_lookalike_names_are_not_matched() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name in (
            "my-compose.yml",
            "compose.yml.bak",
            "docker-compose.json",
            "docker_compose.yml",
            "composer.yaml",
        ):
            write(root / name, "services: {}\n")
        assert detect_compose(root) is None


def test_nested_compose_file_gets_a_posix_relative_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "deploy" / "prod" / "compose.yaml", "services: {}\n")
        info = detect_compose(root)
        assert info is not None
        assert [f.path for f in info.files] == ["deploy/prod/compose.yaml"]


def test_build_and_dependency_directories_are_never_searched() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for skipped in (".venv", "target", "node_modules", ".git"):
            write(root / skipped / "vendored" / "compose.yaml", "services: {}\n")
        assert detect_compose(root) is None


def test_search_depth_is_bounded() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "a" / "b" / "c" / "d" / "e" / "compose.yaml", "services: {}\n")
        assert detect_compose(root) is not None
        write(root / "a" / "b" / "c" / "d" / "e" / "f" / "compose.yaml", "")
        info = detect_compose(root)
        assert info is not None
        assert len(info.files) == 1


def test_malformed_file_is_reported_with_no_services_instead_of_crashing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "compose.yaml", "this: is: not: valid: yaml: [")
        info = detect_compose(root)
        assert info is not None
        assert [(f.path, f.services) for f in info.files] == [("compose.yaml", [])]


def test_odd_but_valid_shapes_do_not_crash() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "a" / "compose.yaml", "- just\n- a list\n")
        write(root / "b" / "compose.yaml", "services: [web]\n")
        write(root / "c" / "compose.yaml", "services:\n  web:\n  cache: ~\n")
        write(root / "d" / "compose.yaml", "services:\n  web:\n    image: 5\n")
        info = detect_compose(root)
        assert info is not None
        by_path = {f.path: f.services for f in info.files}
        assert by_path["a/compose.yaml"] == []
        assert by_path["b/compose.yaml"] == []
        assert [s.name for s in by_path["c/compose.yaml"]] == ["web", "cache"]
        assert by_path["d/compose.yaml"] == [ComposeService(name="web")]


def test_undecodable_file_does_not_crash() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "compose.yaml").write_bytes(b"services:\n  web:\n    image: \xff\xfe\n")
        info = detect_compose(root)
        assert info is not None
        assert info.files[0].services == []


def _minimal_report_data(root: Path, compose: ComposeInfo | None) -> ReportData:
    return ReportData(
        project_root=root,
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        environment=EnvironmentInfo(),
        git=GitSnapshot(),
        stats=ProjectStats(),
        compose=compose,
    )


def _sample_info() -> ComposeInfo:
    return ComposeInfo(
        files=[
            ComposeFile(
                path="compose.yaml",
                services=[
                    ComposeService(name="web", image="nginx:1.27"),
                    ComposeService(name="api", builds=True),
                ],
            ),
            ComposeFile(path="broken/compose.yaml"),
        ]
    )


def test_markdown_has_no_compose_section_when_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = _minimal_report_data(Path(tmp), compose=None)
        assert "## Docker Compose" not in markdown.render(data, include_source=False)


def test_markdown_renders_services_and_empty_files() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = _minimal_report_data(Path(tmp), compose=_sample_info())
        rendered = markdown.render(data, include_source=False)
        assert "## Docker Compose" in rendered
        assert "### `compose.yaml`" in rendered
        assert "| web | nginx:1.27 | - |" in rendered
        assert "| api | - | yes |" in rendered
        assert "### `broken/compose.yaml`" in rendered
        assert "_No services found._" in rendered


def test_json_has_no_compose_key_when_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = _minimal_report_data(Path(tmp), compose=None)
        payload = json.loads(json_renderer.render(data, include_source=False))
        assert "compose" not in payload


def test_json_renders_compose_key_when_present() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = _minimal_report_data(Path(tmp), compose=_sample_info())
        payload = json.loads(json_renderer.render(data, include_source=False))
        assert payload["compose"] == {
            "files": [
                {
                    "path": "compose.yaml",
                    "services": [
                        {"name": "web", "image": "nginx:1.27", "builds": False},
                        {"name": "api", "image": "", "builds": True},
                    ],
                },
                {"path": "broken/compose.yaml", "services": []},
            ]
        }
