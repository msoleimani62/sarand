"""Kubernetes/Helm/Kustomize artifact detection (backlog item 5,
"Kubernetes / Helm / Kustomize").

Evidence-first audit before any implementation: grepped the whole
`analyzers/` and `core/` trees for any existing k8s/helm/kustomize
awareness -- CONFIRMED gap, none exists. `YamlAnalyzer`
(`analyzers/yaml_analyzer.py`) is a plain format analyzer: it lints
top-level `.yaml`/`.yml` files with `yamllint` and never inspects
their content, so it has no idea whether a YAML file is a Kubernetes
manifest, a CI workflow, or anything else.

Scope for this round, following the same discipline item 8's Cargo-
only first pass used: **detection only**, and only for the two
ecosystems with an unambiguous, cheap-to-find marker file --

- **Helm chart** -- a directory containing `Chart.yaml` (the file
  that makes a directory a chart, by Helm's own definition; `name`/
  `version` are read from it).
- **Kustomize overlay** -- a directory containing `kustomization.yaml`
  or `kustomization.yml` (Kustomize's own required marker file).

**Deliberately deferred, not attempted this round:** raw Kubernetes
manifests (a bare `Deployment`/`Service`/etc. YAML has no fixed
filename -- finding them means reading and parsing the content of
every `.yaml`/`.yml` file in the project looking for `apiVersion` +
`kind`, a materially bigger and more expensive scan than a marker-file
check, and worth its own scoped round rather than folding in here).
Also deferred: any execution (`helm lint`, `helm template`,
`kubeconform`/`kubeval`, `kustomize build`) -- this round adds
*representation*, matching item 8's own "detection first, execution
later" split.

تشخیص artifactهای Kubernetes/Helm/Kustomize (آیتم ۵ backlog،
«Kubernetes / Helm / Kustomize»).

ممیزیِ evidence-first پیش از هر پیاده‌سازی: کل درخت‌های `analyzers/`
و `core/` برای هرگونه آگاهی از k8s/helm/kustomize grep شد -- شکاف
CONFIRMED، هیچ‌چیزی وجود ندارد. `YamlAnalyzer` یک آنالایزرِ فرمتِ
ساده است: فقط فایل‌های `.yaml`/`.yml` سطح‌بالا را با `yamllint` لینت
می‌کند و هرگز محتوایشان را بررسی نمی‌کند.

اسکوپِ این دور، با همان انضباطِ اسکوپِ فقط-Cargoِ آیتم ۸: **فقط
تشخیص**، و فقط برای دو اکوسیستمی که یک فایل‌نشانگرِ بی‌ابهام و
ارزان‌یاب دارند -- چارت Helm (پوشه‌ای با `Chart.yaml`) و overlay
Kustomize (پوشه‌ای با `kustomization.yaml`/`.yml`). مانیفست‌های خامِ
Kubernetes (بدون نام‌فایلِ ثابت) و هرگونه اجرا (`helm lint`،
`kustomize build`، ...) عمداً به دورِ بعدی موکول شده‌اند.
"""

from __future__ import annotations

from pathlib import Path

import yaml as _yaml

from sarand.models.results import HelmChart, KubernetesInfo, KustomizeOverlay

# Directories never worth walking into: build output, dependency
# caches, and VCS internals never contain a project's own charts or
# overlays, only ever third-party/generated content -- the same
# philosophy (and mostly the same list) as `core/sbom.py`'s syft
# exclude fix, and for the same reason: walking them costs real time
# and memory for zero signal.
# دایرکتوری‌هایی که هرگز ارزشِ ورود ندارند: خروجیِ build، کشِ
# وابستگی‌ها، و داخلیِ VCS هرگز چارت یا overlayِ خودِ پروژه را ندارند،
# فقط همیشه محتوای شخص‌ثالث/تولیدشده -- همان فلسفه (و بیشتر همان
# فهرست) اصلاحِ syft در `core/sbom.py`، و به همان دلیل: ورود به
# آن‌ها زمان و حافظه‌ی واقعی هزینه می‌کند برای سیگنالِ صفر.
_SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "target",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        "dist",
        "build",
    }
)

# How deep under the project root to look. Helm charts and Kustomize
# overlays are, in every real-world layout seen in the wild, within a
# few levels of the root (e.g. `charts/my-app/Chart.yaml`,
# `k8s/overlays/prod/kustomization.yaml`) -- unbounded recursion would
# cost real time for no realistic benefit.
# چقدر زیرِ ریشه‌ی پروژه عمیق شویم. چارت‌های Helm و overlayهای
# Kustomize، در هر چیدمانِ واقعیِ دیده‌شده، در فاصله‌ی چند سطح از ریشه
# هستند -- بازگشتِ نامحدود بدون فایده‌ی واقعی، زمانِ واقعی هزینه
# می‌کند.
_MAX_DEPTH = 5


def _walk(root: Path) -> list[Path]:
    """Every directory under `root`, pruning `_SKIP_DIRS` and anything
    past `_MAX_DEPTH`, without following symlinks (avoids cycles and
    escaping the project tree)."""
    dirs = [root]
    frontier = [(root, 0)]
    while frontier:
        current, depth = frontier.pop()
        if depth >= _MAX_DEPTH:
            continue
        try:
            children = [
                c for c in current.iterdir() if c.is_dir() and not c.is_symlink()
            ]
        except OSError:
            continue
        for child in children:
            if child.name in _SKIP_DIRS:
                continue
            dirs.append(child)
            frontier.append((child, depth + 1))
    return dirs


def _read_helm_chart(chart_dir: Path, chart_path: str) -> HelmChart:
    manifest = chart_dir / "Chart.yaml"
    name = chart_dir.name
    version = ""
    if _yaml is not None:
        try:
            data = _yaml.safe_load(manifest.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                name = str(data.get("name") or name)
                version = str(data.get("version") or "")
        except (OSError, _yaml.YAMLError):
            # Malformed Chart.yaml isn't this detector's job to report
            # -- fall back to the directory name and no version.
            # Chart.yaml بدشکل کار این تشخیص‌دهنده نیست که گزارش شود
            # -- به نامِ دایرکتوری و بدون نسخه برمی‌گردد.
            pass
    return HelmChart(path=chart_path, name=name, version=version)


def _relative_posix(path: Path, root: Path | None = None) -> str:
    if root is None:
        return path.name
    if path == root:
        return "."
    return path.relative_to(root).as_posix()


def detect_kubernetes(root: Path) -> KubernetesInfo | None:
    """Detect Helm charts and Kustomize overlays under `root`. Returns
    `None` when neither is found -- the common case for a project with
    no Kubernetes tooling at all.
    """
    helm_charts: list[HelmChart] = []
    kustomize_overlays: list[KustomizeOverlay] = []

    for directory in _walk(root):
        chart_manifest = directory / "Chart.yaml"
        if chart_manifest.is_file():
            chart_path = _relative_posix(directory, root)
            helm_charts.append(_read_helm_chart(directory, chart_path))

        for marker_name in ("kustomization.yaml", "kustomization.yml"):
            if (directory / marker_name).is_file():
                kustomize_overlays.append(
                    KustomizeOverlay(path=_relative_posix(directory, root))
                )
                break

    if not helm_charts and not kustomize_overlays:
        return None

    helm_charts.sort(key=lambda c: c.path)
    kustomize_overlays.sort(key=lambda o: o.path)
    return KubernetesInfo(
        helm_charts=helm_charts, kustomize_overlays=kustomize_overlays
    )
