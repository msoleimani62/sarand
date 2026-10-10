"""Kubernetes, second round (AGENTS.md section 5.60): raw manifests found by
content, and the analyzer that runs `helm lint` / `kustomize build`.

The analyzer is tested with the tool runner replaced, so these tests check
sarand's wiring (what is run, what is skipped and why), not the behaviour of
helm or kustomize themselves.

Kubernetes، دور دوم (بخش ۵.۶۰): مانیفست‌های خام و آنالایزر اجرای ابزارها.
ابزارها در تست‌ها جایگزین می‌شوند؛ آنچه سنجیده می‌شود سیم‌کشی sarand است.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from _helpers import write
from sarand.analyzers.kubernetes_analyzer import KubernetesAnalyzer
from sarand.core.components import detect_components
from sarand.core.kubernetes import detect_kubernetes
from sarand.models.results import (
    CommandResult,
    EnvironmentInfo,
    GitSnapshot,
    KubernetesInfo,
    KubernetesManifest,
    ProjectStats,
    ReportData,
)
from sarand.renderers import json_renderer, markdown
from sarand.utils.command import make_command_result

_DEPLOYMENT = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
---
apiVersion: v1
kind: Service
metadata:
  name: web
---
not: a resource
---
- a list
"""


def _chart(root: Path, rel: str, extra: str = "") -> None:
    write(root / rel / "Chart.yaml", f"name: {Path(rel).name}\nversion: 1.0.0\n{extra}")


# ---------------------------------------------------------------- raw scan --


def test_raw_manifests_are_found_by_content_and_documents_are_listed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "deploy" / "app.yaml", _DEPLOYMENT)
        info = detect_kubernetes(root)
        assert info is not None
        assert info.helm_charts == [] and info.kustomize_overlays == []
        assert [m.path for m in info.manifests] == ["deploy/app.yaml"]
        assert info.manifests[0].resources == ["Deployment/web", "Service/web"]
        assert info.total_manifest_files == 1


def test_files_that_are_not_manifests_are_ignored() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / ".github" / "workflows" / "ci.yml", "on: push\njobs: {}\n")
        write(root / "docker-compose.yml", "services:\n  a:\n    image: x\n")
        write(root / "k8s" / "kustomization.yaml", "resources:\n  - app.yaml\n")
        write(root / "k8s" / "values.yaml", "apiVersion: v1\nkind: Fake\n")
        write(root / "k8s" / "plain.yaml", "kind: Deployment\n")  # no apiVersion
        write(
            root / "k8s" / "kfile.yaml",
            "apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\n",
        )
        write(root / "k8s" / "templated.yaml", "name: {{ .Values.name }}\nkind: x\n")
        write(root / "k8s" / "big.yaml", _DEPLOYMENT + "# " + "x" * 600_000 + "\n")
        info = detect_kubernetes(root)
        assert info is not None  # the overlay is still found
        assert info.manifests == [] and info.total_manifest_files == 0


def test_a_charts_own_files_are_not_raw_manifests() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _chart(root, "charts/app")
        write(root / "charts" / "app" / "templates" / "deploy.yaml", _DEPLOYMENT)
        write(root / "charts" / "app" / "crds" / "crd.yaml", _DEPLOYMENT)
        write(root / "deploy" / "extra.yaml", _DEPLOYMENT)
        info = detect_kubernetes(root)
        assert info is not None
        assert [c.path for c in info.helm_charts] == ["charts/app"]
        assert [m.path for m in info.manifests] == ["deploy/extra.yaml"]


def test_a_project_without_kubernetes_is_still_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", "{}")
        write(root / "config.yaml", "name: demo\n")
        assert detect_kubernetes(root) is None


def test_the_manifest_cap_keeps_the_true_total() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for index in range(105):
            write(root / "m" / f"r{index:03d}.yaml", _DEPLOYMENT)
        info = detect_kubernetes(root)
        assert info is not None
        assert len(info.manifests) == 100
        assert info.total_manifest_files == 105


def test_the_manifest_scan_can_be_skipped() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _chart(root, "chart")
        write(root / "deploy" / "app.yaml", _DEPLOYMENT)
        light = detect_kubernetes(root, manifests=False)
        assert light is not None and light.manifests == []
        assert len(light.helm_charts) == 1


def test_raw_manifests_alone_do_not_make_a_project_hybrid() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pyproject.toml", '[project]\nname = "x"\n')
        write(root / "deploy" / "app.yaml", _DEPLOYMENT)
        info = detect_kubernetes(root)
        assert info is not None
        assert detect_components(root, info, None, None) is None


# -------------------------------------------------------------- rendering --


def _data(kubernetes: KubernetesInfo) -> ReportData:
    return ReportData(
        project_root=Path("project"),
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        environment=EnvironmentInfo(),
        git=GitSnapshot(),
        stats=ProjectStats(),
        kubernetes=kubernetes,
    )


def test_markdown_lists_raw_manifests_and_says_what_is_not_shown() -> None:
    info = KubernetesInfo(
        manifests=[
            KubernetesManifest("a.yaml", [f"Pod/p{i}" for i in range(8)]),
            KubernetesManifest("b.yaml", ["Service/s"]),
        ],
        total_manifest_files=5,
    )
    rendered = markdown.render(_data(info), include_source=False)
    assert "### Raw manifests" in rendered
    shown = ", ".join(f"Pod/p{i}" for i in range(6))
    assert f"| `a.yaml` | {shown} (+2 more) |" in rendered
    assert "| `b.yaml` | Service/s |" in rendered
    assert "3 more manifest file(s) not listed" in rendered


def test_json_has_manifests_only_when_there_are_any() -> None:
    bare = json.loads(
        json_renderer.render(_data(KubernetesInfo()), include_source=False)
    )
    assert "manifests" not in bare["kubernetes"]
    full = json.loads(
        json_renderer.render(
            _data(
                KubernetesInfo(
                    manifests=[KubernetesManifest("a.yaml", ["Pod/p"])],
                    total_manifest_files=1,
                )
            ),
            include_source=False,
        )
    )
    assert full["kubernetes"]["manifests"] == [
        {"path": "a.yaml", "resources": ["Pod/p"]}
    ]
    assert full["kubernetes"]["total_manifest_files"] == 1


# --------------------------------------------------------------- analyzer --


def _run(coro):
    return asyncio.run(coro)


def _quality(root: Path) -> tuple[list[CommandResult], list[list[str]]]:
    """Run the analyzer with a fake tool runner; return results and argvs."""
    calls: list[list[str]] = []

    async def fake_run_tool(_root, kind, argv):
        calls.append(list(argv))
        return make_command_result(kind, 0, "ok", 0.0)

    with mock.patch("sarand.analyzers.kubernetes_analyzer.run_tool", fake_run_tool):
        results = _run(KubernetesAnalyzer().run_quality(root))
    return results, calls


def test_the_analyzer_matches_charts_and_overlays_but_not_raw_manifests() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "deploy" / "app.yaml", _DEPLOYMENT)
        assert KubernetesAnalyzer().matches(root) is False
        _chart(root, "charts/app")
        assert KubernetesAnalyzer().matches(root) is True


def test_entry_points_name_the_marker_files() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _chart(root, ".")
        write(root / "k8s" / "kustomization.yml", "resources: []\n")
        assert KubernetesAnalyzer().entry_points(root) == [
            "Chart.yaml",
            "k8s/kustomization.yml",
        ]


def test_charts_and_overlays_are_checked_with_the_right_commands() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _chart(root, "charts/app")
        write(root / "k8s" / "kustomization.yaml", "resources: []\n")
        results, calls = _quality(root)
        assert [r.kind for r in results] == [
            "helm lint charts/app",
            "kustomize build k8s",
        ]
        assert calls[0] == ["helm", "lint", "charts/app"]
        assert calls[1][:3] == ["kustomize", "build", "k8s"]
        assert calls[1][3] == "-o"
        # The rendered manifests went to a temporary file that is gone.
        assert not Path(calls[1][4]).exists()


def test_the_analyzer_runs_no_tests_and_no_security_checks() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _chart(root, "chart")
        assert _run(KubernetesAnalyzer().run_tests(root)) is None
        assert _run(KubernetesAnalyzer().run_security(root)) == []


def test_a_chart_with_unbuilt_dependencies_is_skipped_with_the_reason() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        dep = "dependencies:\n  - name: redis\n    version: 1.0.0\n"
        _chart(root, "charts/app", dep)
        results, calls = _quality(root)
        assert calls == []
        assert results[0].skipped
        assert "not vendored (redis)" in results[0].skip_reason
        assert "helm dependency build" in results[0].skip_reason


def test_a_chart_with_vendored_dependencies_is_linted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        dep = "dependencies:\n  - name: redis\n    version: 1.0.0\n"
        _chart(root, "charts/app", dep)
        write(root / "charts" / "app" / "charts" / "redis-1.0.0.tgz", "x")
        results, calls = _quality(root)
        assert calls == [["helm", "lint", "charts/app"]]
        assert not results[0].skipped


def test_overlays_that_need_the_network_or_helm_are_skipped() -> None:
    cases = {
        "https": "resources:\n  - https://example.com/base.yaml\n",
        "shorthand": "resources:\n  - github.com/org/repo//base?ref=v1\n",
        "scp": "bases:\n  - git@github.com:org/repo.git//base\n",
        "helm": "helmCharts:\n  - name: x\n    repo: https://example.com\n",
    }
    for label, body in cases.items():
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "k8s" / "kustomization.yaml", body)
            results, calls = _quality(root)
            assert calls == [], label
            assert results[0].skipped, label


def test_a_local_base_is_not_treated_as_remote() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "base" / "kustomization.yaml", "resources: []\n")
        write(
            root / "overlays" / "prod" / "kustomization.yaml",
            "resources:\n  - ../../base\n  - extra.example.yaml\n",
        )
        write(root / "overlays" / "prod" / "extra.example.yaml", "x: 1\n")
        results, calls = _quality(root)
        assert len(calls) == 2  # base and prod, nothing skipped
        assert not any(r.skipped for r in results)


def test_more_charts_than_the_limit_are_counted_in_one_note() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for index in range(10):
            _chart(root, f"charts/c{index:02d}")
        results, calls = _quality(root)
        assert len(calls) == 8
        note = results[-1]
        assert note.kind == "kubernetes" and note.skipped
        assert "2 Helm chart(s) not checked" in note.skip_reason


def test_a_missing_tool_is_a_skipped_result_not_a_failure() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _chart(root, "chart")
        write(root / "k8s" / "kustomization.yaml", "resources: []\n")
        with mock.patch("sarand.analyzers._tooling.shutil.which", return_value=None):
            results = _run(KubernetesAnalyzer().run_quality(root))
        assert [r.skip_reason for r in results] == [
            "helm not installed",
            "kustomize not installed",
        ]
