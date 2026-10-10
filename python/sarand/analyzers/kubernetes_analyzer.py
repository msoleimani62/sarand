"""Kubernetes analyzer: `helm lint` on charts and `kustomize build` on overlays.

Matches only when `core/kubernetes.py` finds a Helm chart or a Kustomize
overlay (raw manifests alone give it nothing to run: validating them needs
schemas that `kubeconform` downloads, a network check this analyzer does not
perform -- AGENTS.md section 5.60). It never applies anything to a cluster:
`helm lint` and `kustomize build` only read files, and the rendered output of
`kustomize build` is written to a temporary file that is deleted, never
captured, because a rendered `Secret` must not end up in a report.

A check that cannot give a true answer on this machine is SKIPPED with its
reason instead of failing: a chart whose dependencies are not vendored, an
overlay that pulls a remote base (needs the network) or uses a `helmCharts`
generator, and any missing tool.

آنالایزر Kubernetes: `helm lint` روی چارت‌ها و `kustomize build` روی
overlayها. فقط وقتی match می‌شود که `core/kubernetes.py` چارت یا overlay
پیدا کند. هرگز چیزی را روی کلاستر اعمال نمی‌کند، و خروجیِ رندرشده‌ی
`kustomize build` در یک فایل موقت نوشته و پاک می‌شود، چون یک `Secret`
رندرشده نباید به گزارش برسد. چکی که اینجا نمی‌تواند جواب درست بدهد (وابستگی
vendor نشده، base راه‌دور، `helmCharts`، ابزار نصب‌نشده) با دلیل SKIPPED
می‌شود، نه شکست.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import yaml as _yaml

from sarand.analyzers._tooling import read_text_safely, run_tool, skipped
from sarand.core.kubernetes import detect_kubernetes
from sarand.models.results import CommandResult, KubernetesInfo

# At most this many charts and this many overlays are checked per run; the
# rest are named in one skipped result, never silently dropped.
# حداکثر تعداد چارت و overlay در هر اجرا؛ بقیه در یک نتیجه‌ی skipped نام برده می‌شوند.
_MAX_PER_KIND = 8

# A kustomize resource that is not a local path: a URL, an scp-style git
# address, or `host.tld/org/repo//path` (kustomize's own shorthand).
_REMOTE = re.compile(
    r"^(?:[A-Za-z][A-Za-z0-9+.-]*://|git@|[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+[/:])"
)


def _load_yaml_dict(path: Path) -> dict[str, object]:
    try:
        data = _yaml.safe_load(read_text_safely(path))
    except _yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def helm_dependency_gap(chart_dir: Path) -> str:
    """Why `helm lint` cannot answer for this chart, or "" when it can: its
    `Chart.yaml` lists dependencies that are not in `charts/`."""
    dependencies = _load_yaml_dict(chart_dir / "Chart.yaml").get("dependencies")
    if not isinstance(dependencies, list) or not dependencies:
        return ""
    vendored: list[str] = []
    try:
        vendored = [entry.name for entry in (chart_dir / "charts").iterdir()]
    except OSError:
        pass
    missing = []
    for dependency in dependencies:
        name = dependency.get("name") if isinstance(dependency, dict) else None
        if not isinstance(name, str) or not name:
            continue
        if not any(item == name or item.startswith(f"{name}-") for item in vendored):
            missing.append(name)
    if not missing:
        return ""
    return (
        f"chart dependencies not vendored ({', '.join(sorted(missing))}); "
        f"run `helm dependency build {chart_dir.name}` first"
    )


def kustomize_gap(overlay_dir: Path) -> str:
    """Why `kustomize build` cannot answer here, or "" when it can: a remote
    base (needs the network) or a `helmCharts` generator (needs helm and the
    chart repository)."""
    data = _load_yaml_dict(
        overlay_dir / "kustomization.yaml"
        if (overlay_dir / "kustomization.yaml").is_file()
        else overlay_dir / "kustomization.yml"
    )
    if data.get("helmCharts"):
        return "uses a helmCharts generator (needs helm and the chart repository)"
    for key in ("resources", "bases", "components"):
        entries = data.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if (
                isinstance(entry, str)
                and not (overlay_dir / entry).exists()
                and _REMOTE.match(entry)
            ):
                return f"references a remote base ({entry}); needs the network"
    return ""


def _limit_note(info: KubernetesInfo) -> list[CommandResult]:
    hidden_charts = max(0, len(info.helm_charts) - _MAX_PER_KIND)
    hidden_overlays = max(0, len(info.kustomize_overlays) - _MAX_PER_KIND)
    if not (hidden_charts or hidden_overlays):
        return []
    parts = []
    if hidden_charts:
        parts.append(f"{hidden_charts} Helm chart(s)")
    if hidden_overlays:
        parts.append(f"{hidden_overlays} Kustomize overlay(s)")
    return [
        skipped(
            "kubernetes",
            f"{' and '.join(parts)} not checked (limit {_MAX_PER_KIND} of each kind)",
        )
    ]


class KubernetesAnalyzer:
    name = "Kubernetes"

    @staticmethod
    def _artifacts(root: Path) -> KubernetesInfo | None:
        info = detect_kubernetes(root, manifests=False)
        if info is None or not (info.helm_charts or info.kustomize_overlays):
            return None
        return info

    def matches(self, root: Path) -> bool:
        return self._artifacts(root) is not None

    def entry_points(self, root: Path) -> list[str]:
        info = self._artifacts(root)
        if info is None:
            return []
        found = [f"{c.path}/Chart.yaml" for c in info.helm_charts]
        for overlay in info.kustomize_overlays:
            marker = "kustomization.yaml"
            if not (root / overlay.path / marker).is_file():
                marker = "kustomization.yml"
            found.append(f"{overlay.path}/{marker}")
        return [item.removeprefix("./") for item in found]

    async def run_tests(self, root: Path) -> CommandResult | None:
        return None

    async def run_quality(self, root: Path) -> list[CommandResult]:
        info = self._artifacts(root)
        if info is None:
            return []
        results: list[CommandResult] = []
        for chart in info.helm_charts[:_MAX_PER_KIND]:
            kind = f"helm lint {chart.path}"
            reason = helm_dependency_gap(root / chart.path)
            if reason:
                results.append(skipped(kind, reason))
            else:
                results.append(await run_tool(root, kind, ["helm", "lint", chart.path]))
        for overlay in info.kustomize_overlays[:_MAX_PER_KIND]:
            kind = f"kustomize build {overlay.path}"
            reason = kustomize_gap(root / overlay.path)
            if reason:
                results.append(skipped(kind, reason))
                continue
            # The rendered manifests go to a temporary file that is removed
            # with the directory: only errors reach the report (a rendered
            # Secret must never be captured).
            # خروجی رندرشده در فایل موقت می‌رود و پاک می‌شود؛ فقط خطاها گزارش می‌شوند.
            with tempfile.TemporaryDirectory() as tmp:
                out = str(Path(tmp) / "rendered.yaml")
                results.append(
                    await run_tool(
                        root, kind, ["kustomize", "build", overlay.path, "-o", out]
                    )
                )
        results.extend(_limit_note(info))
        return results

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
