"""Kubernetes analyzer: `helm lint` on charts and `kustomize build` on overlays.

Matches only when `core/kubernetes.py` finds a Helm chart or a Kustomize
overlay (raw manifests alone give it nothing to run). It never applies
anything to a cluster:
`helm lint` and `kustomize build` only read files, and the rendered output of
`kustomize build` is written to a temporary file that is deleted, never
captured, because a rendered `Secret` must not end up in a report.

A check that cannot give a true answer on this machine is SKIPPED with its
reason instead of failing: a chart whose dependencies are not vendored, an
overlay that pulls a remote base (needs the network) or uses a `helmCharts`
generator, and any missing tool.

Schema validation is opt-in (round R10c, AGENTS.md section 5.85): only when the
environment variable SARAND_KUBECONFORM_SCHEMAS names a local directory of
Kubernetes JSON schemas (the layout of the kubernetes-json-schema project).
Each chart is then rendered by `helm template --output-dir` and each overlay
by `kustomize build` into a temporary directory that is deleted, and
`kubeconform` checks that output against the local schemas only: the network is
never used and the rendered manifests (a rendered `Secret` among them) are
never captured. Without the variable nothing changes. See docs/KUBERNETES.md.

آنالایزر Kubernetes: `helm lint` روی چارت‌ها و `kustomize build` روی
overlayها. فقط وقتی match می‌شود که `core/kubernetes.py` چارت یا overlay
پیدا کند. هرگز چیزی را روی کلاستر اعمال نمی‌کند، و خروجیِ رندرشده‌ی
`kustomize build` در یک فایل موقت نوشته و پاک می‌شود، چون یک `Secret`
رندرشده نباید به گزارش برسد. چکی که اینجا نمی‌تواند جواب درست بدهد (وابستگی
vendor نشده، base راه‌دور، `helmCharts`، ابزار نصب‌نشده) با دلیل SKIPPED
می‌شود، نه شکست.
اعتبارسنجی schema اختیاری است: فقط وقتی SARAND_KUBECONFORM_SCHEMAS به یک پوشه‌ی
محلی اشاره کند اجرا می‌شود، بدون شبکه و بدون ضبط خروجی رندرشده.
"""

from __future__ import annotations

import os
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


# Opt-in schema validation (AGENTS.md section 5.85). The variable names a local
# directory laid out like the kubernetes-json-schema project; nothing is
# downloaded. The optional version defaults to kubeconform's own ("master").
# اعتبارسنجی اختیاری: متغیر به یک پوشه‌ی محلی اشاره می‌کند؛ هیچ‌چیز دانلود نمی‌شود.
SCHEMAS_ENV = "SARAND_KUBECONFORM_SCHEMAS"
VERSION_ENV = "SARAND_KUBECONFORM_VERSION"
_SCHEMA_LAYOUT = (
    "{{ .NormalizedKubernetesVersion }}-standalone{{ .StrictSuffix }}"
    "/{{ .ResourceKind }}{{ .KindSuffix }}.json"
)
_SUMMARY = re.compile(
    r"Valid:\s*(\d+),\s*Invalid:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+)"
)


def configured_schemas() -> tuple[Path | None, str]:
    """The schema directory, or why there is none.

    `(None, "")` means the feature is off (variable unset or blank) and says
    nothing; `(None, reason)` means it was asked for but cannot work.
    """
    raw = os.environ.get(SCHEMAS_ENV, "").strip()
    if not raw:
        return None, ""
    path = Path(raw).expanduser()
    if not path.is_dir():
        return None, f"{SCHEMAS_ENV} is set but is not a directory ({raw})"
    if "{" in str(path) or "}" in str(path):
        return None, f"{SCHEMAS_ENV} must not contain a brace ({raw})"
    return path, ""


def schema_location(schemas: Path) -> str:
    """The `-schema-location` template for a local kubernetes-json-schema tree."""
    return f"{schemas.as_posix()}/{_SCHEMA_LAYOUT}"


def kubeconform_argv(schemas: Path, target: str) -> list[str]:
    argv = [
        "kubeconform",
        "-strict",
        "-summary",
        "-ignore-missing-schemas",
        "-schema-location",
        schema_location(schemas),
    ]
    version = os.environ.get(VERSION_ENV, "").strip()
    if version:
        argv += ["-kubernetes-version", version]
    argv.append(target)
    return argv


def judge_kubeconform(result: CommandResult) -> CommandResult:
    """Turn "nothing was actually checked" into a skip instead of a pass.

    `-ignore-missing-schemas` makes a resource without a schema count as
    skipped. If that is true of every resource, the schema directory is wrong
    or empty and a green check would be false assurance.
    اگر برای هیچ منبعی schema پیدا نشده باشد، نتیجه skipped است نه موفق.
    """
    if result.skipped or not result.passed:
        return result
    match = _SUMMARY.search(result.raw_output)
    if match is None:
        return result
    valid, invalid, errors, missing = map(int, match.groups())
    if valid == 0 and invalid == 0 and errors == 0 and missing > 0:
        return skipped(
            result.kind,
            f"no schema found for the {missing} rendered resource(s); "
            f"check the layout of {SCHEMAS_ENV}",
        )
    return result


async def _validate_chart(root: Path, chart_path: str, schemas: Path) -> CommandResult:
    """Render one chart into a temporary directory and check it; delete it."""
    kind = f"kubeconform {chart_path}"
    reason = helm_dependency_gap(root / chart_path)
    if reason:
        return skipped(kind, reason)
    with tempfile.TemporaryDirectory() as tmp:
        rendered = str(Path(tmp) / "rendered")
        render = await run_tool(
            root,
            f"helm template {chart_path}",
            ["helm", "template", "sarand-check", chart_path, "--output-dir", rendered],
        )
        if render.skipped:
            return skipped(kind, render.skip_reason)
        if not render.passed:
            return render
        # A passing render prints one line per written file; it is dropped.
        # خروجی رندر موفق (فهرست فایل‌های نوشته‌شده) دور ریخته می‌شود.
        check = await run_tool(root, kind, kubeconform_argv(schemas, rendered))
    return judge_kubeconform(check)


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
        schemas, problem = configured_schemas()
        for chart in info.helm_charts[:_MAX_PER_KIND]:
            kind = f"helm lint {chart.path}"
            reason = helm_dependency_gap(root / chart.path)
            if reason:
                results.append(skipped(kind, reason))
            else:
                results.append(await run_tool(root, kind, ["helm", "lint", chart.path]))
        if problem:
            results.append(skipped("kubeconform", problem))
        elif schemas is not None:
            for chart in info.helm_charts[:_MAX_PER_KIND]:
                results.append(await _validate_chart(root, chart.path, schemas))
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
                build = await run_tool(
                    root, kind, ["kustomize", "build", overlay.path, "-o", out]
                )
                results.append(build)
                if schemas is not None and build.passed:
                    check = await run_tool(
                        root,
                        f"kubeconform {overlay.path}",
                        kubeconform_argv(schemas, out),
                    )
                    results.append(judge_kubeconform(check))
        results.extend(_limit_note(info))
        return results

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
