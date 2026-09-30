"""Regression tests for backlog item 5 (Kubernetes / Helm / Kustomize,
detection-only first scope) -- see AGENTS.md section 5.36 and
`core/kubernetes.py`'s module docstring for the audit and design
rationale.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from _helpers import write
from sarand.core.kubernetes import detect_kubernetes
from sarand.models.results import (
    EnvironmentInfo,
    GitSnapshot,
    HelmChart,
    KubernetesInfo,
    KustomizeOverlay,
    ProjectStats,
    ReportData,
)
from sarand.renderers import json_renderer, markdown


def test_project_with_no_kubernetes_tooling_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "app.py", "print('hi')\n")
        write(root / "config.yaml", "key: value\n")
        assert detect_kubernetes(root) is None


def test_helm_chart_is_found_with_name_and_version() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(
            root / "charts" / "my-app" / "Chart.yaml",
            "apiVersion: v2\nname: my-app\nversion: 1.2.3\n",
        )
        info = detect_kubernetes(root)
        assert info is not None
        assert [(c.path, c.name, c.version) for c in info.helm_charts] == [
            ("charts/my-app", "my-app", "1.2.3")
        ]
        assert info.kustomize_overlays == []


def test_kustomize_overlay_is_found_for_both_extensions() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "base" / "kustomization.yaml", "resources: []\n")
        write(root / "overlays" / "prod" / "kustomization.yml", "resources: []\n")
        info = detect_kubernetes(root)
        assert info is not None
        assert [o.path for o in info.kustomize_overlays] == ["base", "overlays/prod"]
        assert info.helm_charts == []


def test_a_chart_at_the_project_root_has_path_dot() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Chart.yaml", "name: root-chart\nversion: 0.1.0\n")
        info = detect_kubernetes(root)
        assert info is not None
        assert [c.path for c in info.helm_charts] == ["."]


def test_build_and_dependency_directories_are_never_searched() -> None:
    """Same philosophy as `core/sbom.py`'s syft exclude fix (AGENTS.md
    5.34): `.venv`/`target`/`node_modules` etc. only ever contain
    third-party or generated content, never the project's own charts,
    and walking them costs real time for zero signal."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for skipped in (".venv", "target", "node_modules", ".git"):
            write(root / skipped / "vendored" / "Chart.yaml", "name: decoy\n")
            write(root / skipped / "vendored" / "kustomization.yaml", "resources: []\n")
        assert detect_kubernetes(root) is None


def test_malformed_chart_yaml_falls_back_to_dirname_instead_of_crashing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "broken-chart" / "Chart.yaml", "this: is: not: valid: yaml: [")
        info = detect_kubernetes(root)
        assert info is not None
        assert [(c.name, c.version) for c in info.helm_charts] == [("broken-chart", "")]


def _minimal_report_data(root: Path, kubernetes: KubernetesInfo | None) -> ReportData:
    return ReportData(
        project_root=root,
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        environment=EnvironmentInfo(),
        git=GitSnapshot(),
        stats=ProjectStats(),
        kubernetes=kubernetes,
    )


def test_markdown_has_no_kubernetes_section_when_none() -> None:
    """The whole point of only emitting a section when something was
    actually detected: an ordinary project's report must look exactly
    as it did before this feature existed."""
    with tempfile.TemporaryDirectory() as tmp:
        data = _minimal_report_data(Path(tmp), kubernetes=None)
        assert "## Kubernetes" not in markdown.render(data, include_source=False)


def test_markdown_renders_both_helm_and_kustomize_when_present() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        info = KubernetesInfo(
            helm_charts=[HelmChart(path="charts/app", name="app", version="1.0.0")],
            kustomize_overlays=[KustomizeOverlay(path="overlays/prod")],
        )
        data = _minimal_report_data(Path(tmp), kubernetes=info)
        rendered = markdown.render(data, include_source=False)
        assert "## Kubernetes" in rendered
        assert "| app | 1.0.0 | `charts/app` |" in rendered
        assert "- `overlays/prod`" in rendered


def test_json_has_no_kubernetes_key_when_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = _minimal_report_data(Path(tmp), kubernetes=None)
        payload = json.loads(json_renderer.render(data, include_source=False))
        assert "kubernetes" not in payload


def test_json_renders_kubernetes_key_when_present() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        info = KubernetesInfo(
            helm_charts=[HelmChart(path="charts/app", name="app", version="1.0.0")],
            kustomize_overlays=[KustomizeOverlay(path="overlays/prod")],
        )
        data = _minimal_report_data(Path(tmp), kubernetes=info)
        payload = json.loads(json_renderer.render(data, include_source=False))
        assert payload["kubernetes"] == {
            "helm_charts": [{"path": "charts/app", "name": "app", "version": "1.0.0"}],
            "kustomize_overlays": [{"path": "overlays/prod"}],
        }
