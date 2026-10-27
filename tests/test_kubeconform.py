"""Opt-in schema validation of rendered charts and overlays (backlog item 5, R10c).

The tool runner is replaced, so these tests check sarand's wiring (what is run,
in which order, what is kept and what is thrown away), not kubeconform or helm
themselves; the real binaries are exercised by `test_kubeconform_real.py` in CI.

اعتبارسنجی اختیاری schema برای چارت‌ها و overlayها؛ ابزارها جایگزین شده‌اند و
سیم‌کشی sarand سنجیده می‌شود.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from unittest import mock

from _helpers import write
from sarand.analyzers import kubernetes_analyzer as k8s
from sarand.analyzers.kubernetes_analyzer import KubernetesAnalyzer
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result

_OK_SUMMARY = (
    "Summary: 2 resources found in 1 file - Valid: 2, Invalid: 0, Errors: 0, Skipped: 0"
)
_NO_SCHEMA = (
    "Summary: 2 resources found in 1 file - Valid: 0, Invalid: 0, Errors: 0, Skipped: 2"
)
_INVALID = (
    "rendered/app/templates/cm.yaml - ConfigMap demo is invalid: data.key: got "
    "number, want string\n"
    "Summary: 1 resource found in 1 file - Valid: 0, Invalid: 1, Errors: 0, Skipped: 0"
)


def _project(root: Path, *, chart: bool = True, overlay: bool = False) -> None:
    if chart:
        write(root / "charts" / "app" / "Chart.yaml", "name: app\nversion: 0.1.0\n")
    if overlay:
        write(root / "overlays" / "prod" / "kustomization.yaml", "resources: []\n")


def _run(
    root: Path,
    env: dict[str, str],
    *,
    render: tuple[int, str] = (0, "wrote /tmp/x/app/templates/secret.yaml\n"),
    check: tuple[int, str] = (0, _OK_SUMMARY),
    build: tuple[int, str] = (0, ""),
) -> tuple[list[CommandResult], list[list[str]]]:
    calls: list[list[str]] = []

    async def fake_run_tool(
        _root: Path, kind: str, argv: Sequence[str]
    ) -> CommandResult:
        calls.append(list(argv))
        if argv[:2] == ["helm", "template"]:
            code, output = render
        elif argv[0] == "kubeconform":
            code, output = check
        elif argv[0] == "kustomize":
            code, output = build
        else:
            code, output = 0, "ok"
        return make_command_result(kind, code, output, 0.0)

    clean = {k: v for k, v in os.environ.items() if not k.startswith("SARAND_KUBE")}
    with (
        mock.patch.dict(os.environ, clean, clear=True),
        mock.patch.dict(os.environ, env),
        mock.patch("sarand.analyzers.kubernetes_analyzer.run_tool", fake_run_tool),
    ):
        results = asyncio.run(KubernetesAnalyzer().run_quality(root))
    return results, calls


def _kinds(results: list[CommandResult]) -> list[str]:
    return [result.kind for result in results]


def test_without_the_variable_nothing_new_runs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _project(root, overlay=True)
        results, calls = _run(root, {})
        assert _kinds(results) == [
            "helm lint charts/app",
            "kustomize build overlays/prod",
        ]
        assert all(argv[0] != "kubeconform" for argv in calls)
        assert all(argv[:2] != ["helm", "template"] for argv in calls)


def test_a_chart_is_rendered_to_a_directory_then_checked_against_local_schemas() -> (
    None
):
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as schemas:
        root = Path(tmp)
        _project(root)
        results, calls = _run(root, {k8s.SCHEMAS_ENV: schemas})
        template = next(c for c in calls if c[:2] == ["helm", "template"])
        check = next(c for c in calls if c[0] == "kubeconform")
        assert template[2:4] == ["sarand-check", "charts/app"]
        assert template[4] == "--output-dir"
        assert check[-1] == template[5]
        assert check[1:4] == ["-strict", "-summary", "-ignore-missing-schemas"]
        assert check[check.index("-schema-location") + 1] == (
            f"{Path(schemas).as_posix()}/{{{{ .NormalizedKubernetesVersion }}}}-standalone"
            "{{ .StrictSuffix }}/{{ .ResourceKind }}{{ .KindSuffix }}.json"
        )
        assert "-kubernetes-version" not in check
        assert _kinds(results) == ["helm lint charts/app", "kubeconform charts/app"]
        assert results[1].passed


def test_the_rendered_files_are_never_captured_and_the_directory_is_deleted() -> None:
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as schemas:
        root = Path(tmp)
        _project(root)
        results, calls = _run(root, {k8s.SCHEMAS_ENV: schemas})
        assert all("secret.yaml" not in result.raw_output for result in results)
        assert all("secret.yaml" not in result.summary for result in results)
        template = next(c for c in calls if c[:2] == ["helm", "template"])
        assert not Path(template[5]).exists()


def test_the_kubernetes_version_is_passed_when_given() -> None:
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as schemas:
        root = Path(tmp)
        _project(root)
        _, calls = _run(root, {k8s.SCHEMAS_ENV: schemas, k8s.VERSION_ENV: " 1.30.0 "})
        check = next(c for c in calls if c[0] == "kubeconform")
        assert check[check.index("-kubernetes-version") + 1] == "1.30.0"


def test_an_invalid_resource_is_a_failed_check_with_the_tool_message() -> None:
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as schemas:
        root = Path(tmp)
        _project(root)
        results, _ = _run(root, {k8s.SCHEMAS_ENV: schemas}, check=(1, _INVALID))
        verdict = results[-1]
        assert verdict.kind == "kubeconform charts/app"
        assert not verdict.passed and not verdict.skipped
        assert "want string" in verdict.raw_output


def test_a_failing_render_is_reported_and_kubeconform_is_not_run() -> None:
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as schemas:
        root = Path(tmp)
        _project(root)
        results, calls = _run(
            root, {k8s.SCHEMAS_ENV: schemas}, render=(1, "Error: template broke\n")
        )
        assert results[-1].kind == "helm template charts/app"
        assert not results[-1].passed
        assert all(argv[0] != "kubeconform" for argv in calls)


def test_no_schema_for_any_resource_is_skipped_not_a_false_pass() -> None:
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as schemas:
        root = Path(tmp)
        _project(root)
        results, _ = _run(root, {k8s.SCHEMAS_ENV: schemas}, check=(0, _NO_SCHEMA))
        verdict = results[-1]
        assert verdict.skipped
        assert "no schema found" in verdict.skip_reason
        assert k8s.SCHEMAS_ENV in verdict.skip_reason


def test_a_chart_with_unbuilt_dependencies_is_skipped_before_rendering() -> None:
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as schemas:
        root = Path(tmp)
        write(
            root / "charts" / "app" / "Chart.yaml",
            "name: app\nversion: 0.1.0\ndependencies:\n  - name: redis\n",
        )
        results, calls = _run(root, {k8s.SCHEMAS_ENV: schemas})
        assert results[-1].kind == "kubeconform charts/app"
        assert results[-1].skipped
        assert "not vendored" in results[-1].skip_reason
        assert all(argv[:2] != ["helm", "template"] for argv in calls)


def test_a_variable_that_is_not_a_directory_gives_one_skipped_result() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _project(root, overlay=True)
        results, calls = _run(root, {k8s.SCHEMAS_ENV: str(root / "missing")})
        notes = [result for result in results if result.kind == "kubeconform"]
        assert len(notes) == 1
        assert notes[0].skipped
        assert "not a directory" in notes[0].skip_reason
        assert all(argv[0] != "kubeconform" for argv in calls)


def test_a_brace_in_the_schema_path_is_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        braces = Path(tmp) / "{x}"
        braces.mkdir()
        path, problem = _configured(str(braces))
        assert path is None
        assert "brace" in problem


def _configured(value: str) -> tuple[Path | None, str]:
    with mock.patch.dict(os.environ, {k8s.SCHEMAS_ENV: value}):
        return k8s.configured_schemas()


def test_an_unset_or_blank_variable_means_off_and_says_nothing() -> None:
    assert _configured("") == (None, "")
    assert _configured("   ") == (None, "")


def test_a_kustomize_overlay_is_checked_after_a_successful_build() -> None:
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as schemas:
        root = Path(tmp)
        _project(root, chart=False, overlay=True)
        results, calls = _run(root, {k8s.SCHEMAS_ENV: schemas})
        assert _kinds(results) == [
            "kustomize build overlays/prod",
            "kubeconform overlays/prod",
        ]
        build = next(c for c in calls if c[0] == "kustomize")
        check = next(c for c in calls if c[0] == "kubeconform")
        assert check[-1] == build[build.index("-o") + 1]
        assert not Path(check[-1]).exists()


def test_a_failed_build_is_not_checked_with_kubeconform() -> None:
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as schemas:
        root = Path(tmp)
        _project(root, chart=False, overlay=True)
        results, calls = _run(
            root, {k8s.SCHEMAS_ENV: schemas}, build=(1, "Error: bad overlay\n")
        )
        assert _kinds(results) == ["kustomize build overlays/prod"]
        assert all(argv[0] != "kubeconform" for argv in calls)


def test_the_schema_layout_is_the_kubernetes_json_schema_layout() -> None:
    assert k8s.schema_location(Path("/s")) == (
        "/s/{{ .NormalizedKubernetesVersion }}-standalone{{ .StrictSuffix }}"
        "/{{ .ResourceKind }}{{ .KindSuffix }}.json"
    )
