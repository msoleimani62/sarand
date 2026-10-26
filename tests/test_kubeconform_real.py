"""Real helm and kubeconform against a tiny local schema directory (R10c).

Runs only when SARAND_REAL_KUBECONFORM is set (the CI job `kube` sets it), so a
normal `pytest` skips it visibly. It proves what the mocked tests cannot: the
flags, the schema layout and the summary format match the real binaries.

اجرای واقعی helm و kubeconform؛ فقط وقتی SARAND_REAL_KUBECONFORM تنظیم باشد.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest
import yaml
from _helpers import write
from sarand.analyzers import kubernetes_analyzer as k8s
from sarand.analyzers.kubernetes_analyzer import KubernetesAnalyzer
from sarand.models.results import CommandResult

_CI = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"
_SCHEMA = {
    "type": "object",
    "required": ["apiVersion", "kind"],
    "properties": {
        "apiVersion": {"type": "string"},
        "kind": {"type": "string"},
        "metadata": {"type": "object"},
        "data": {"type": "object", "additionalProperties": {"type": "string"}},
    },
}


def _require() -> None:
    if not os.environ.get("SARAND_REAL_KUBECONFORM"):
        pytest.skip("SARAND_REAL_KUBECONFORM is not set; see the CI job `kube`")


def _chart(root: Path, value: str) -> None:
    write(
        root / "charts" / "demo" / "Chart.yaml",
        "apiVersion: v2\nname: demo\nversion: 0.1.0\n",
    )
    write(
        root / "charts" / "demo" / "templates" / "cm.yaml",
        f"apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: demo\ndata:\n  key: {value}\n",
    )


def _schemas(root: Path) -> Path:
    folder = root / "schemas"
    write(
        folder / "master-standalone-strict" / "configmap-v1.json", json.dumps(_SCHEMA)
    )
    return folder


def _verdict(root: Path, schemas: Path) -> CommandResult:
    env = {k8s.SCHEMAS_ENV: str(schemas)}
    with mock.patch.dict(os.environ, env):
        results = asyncio.run(KubernetesAnalyzer().run_quality(root))
    return next(r for r in results if r.kind == "kubeconform charts/demo")


def test_a_valid_chart_passes_against_the_local_schema() -> None:
    _require()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _chart(root, '"text"')
        verdict = _verdict(root, _schemas(root))
        assert verdict.passed, (verdict.raw_output, verdict.skip_reason)


def test_an_invalid_chart_fails_and_says_why() -> None:
    _require()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _chart(root, "5")
        verdict = _verdict(root, _schemas(root))
        assert not verdict.passed and not verdict.skipped, verdict.raw_output
        assert verdict.raw_output


def test_an_empty_schema_directory_is_skipped_not_a_pass() -> None:
    _require()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _chart(root, '"text"')
        empty = root / "empty"
        empty.mkdir()
        verdict = _verdict(root, empty)
        assert verdict.skipped, verdict.raw_output
        assert "no schema found" in verdict.skip_reason


def test_ci_has_a_kube_job_that_sets_the_switch() -> None:
    steps = yaml.safe_load(_CI.read_text(encoding="utf-8"))["jobs"]["kube"]["steps"]
    switched = [s for s in steps if "SARAND_REAL_KUBECONFORM" in s.get("env", {})]
    assert switched
    assert all(s.get("continue-on-error") is not True for s in switched)


def test_the_ci_installer_pins_a_kubeconform_version() -> None:
    script = _CI.parent.parent.parent / "scripts" / "ci_install_kubeconform.sh"
    text = script.read_text(encoding="utf-8")
    assert 'version="v0.' in text
    assert "kubeconform@${version}" in text
    ci = _CI.read_text(encoding="utf-8")
    assert "bash scripts/ci_install_kubeconform.sh" in ci
