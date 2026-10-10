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

**Deferred in round one (raw manifests were added in round two and the
execution lives in `analyzers/kubernetes_analyzer.py`, AGENTS.md section
5.60):** raw Kubernetes
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

from sarand.models.results import (
    HelmChart,
    KubernetesInfo,
    KubernetesManifest,
    KustomizeOverlay,
)

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


# Raw manifests: a YAML file whose documents carry `apiVersion` and `kind`.
# The scan is bounded on three axes (files read, bytes read, size of one
# file) so a large repository cannot make it slow, and a chart's own files
# (templates are not valid YAML, `crds/` belong to the chart) are left to the
# chart. A directory symlink is never entered and a file symlink never read.
# مانیفست خام: فایل YAML که سندهایش `apiVersion` و `kind` دارند. اسکن در سه
# محور محدود است و فایل‌های خودِ چارت به چارت واگذار می‌شود.
_MANIFEST_SUFFIXES = (".yaml", ".yml")
_NOT_MANIFESTS = frozenset(
    {
        "kustomization.yaml",
        "kustomization.yml",
        "chart.yaml",
        "chart.lock",
        "values.yaml",
        "values.yml",
    }
)
_MAX_YAML_FILES = 500
_MAX_FILE_BYTES = 512 * 1024
_MAX_SCAN_BYTES = 8 * 1024 * 1024
_MAX_MANIFEST_FILES = 100
_MAX_RESOURCES_PER_FILE = 50


def _resources_in(text: str) -> list[str]:
    """`Kind/name` of every Kubernetes resource document in `text`."""
    if "apiVersion" not in text or "kind" not in text:
        return []
    try:
        documents = list(_yaml.safe_load_all(text))
    except (_yaml.YAMLError, ValueError, RecursionError):
        # Not YAML (a Helm or Jinja template, say): not a manifest.
        # YAML نیست (مثلاً قالب Helm یا Jinja): مانیفست هم نیست.
        return []
    found: list[str] = []
    for document in documents:
        if not isinstance(document, dict):
            continue
        api_version = document.get("apiVersion")
        kind = document.get("kind")
        if not isinstance(api_version, str) or not isinstance(kind, str) or not kind:
            continue
        # A kustomization file under another name is not a resource.
        if api_version.startswith("kustomize.config.k8s.io/"):
            continue
        metadata = document.get("metadata")
        name = metadata.get("name") if isinstance(metadata, dict) else None
        found.append(f"{kind}/{name}" if isinstance(name, str) and name else kind)
    return found


def _scan_manifests(
    root: Path, directories: list[Path], chart_dirs: list[Path]
) -> tuple[list[KubernetesManifest], int]:
    """Raw manifest files under `root`, and how many exist (uncapped)."""
    manifests: list[KubernetesManifest] = []
    total = 0
    files_read = 0
    bytes_read = 0
    for directory in sorted(directories, key=lambda d: _relative_posix(d, root)):
        if any(
            chart == directory or chart in directory.parents for chart in chart_dirs
        ):
            continue
        try:
            names = sorted(
                e.name
                for e in directory.iterdir()
                if e.name.lower().endswith(_MANIFEST_SUFFIXES)
                and e.is_file()
                and not e.is_symlink()
            )
        except OSError:
            continue
        for name in names:
            if name.lower() in _NOT_MANIFESTS:
                continue
            if files_read >= _MAX_YAML_FILES or bytes_read >= _MAX_SCAN_BYTES:
                return manifests, total
            path = directory / name
            try:
                size = path.stat().st_size
                if size > _MAX_FILE_BYTES:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            files_read += 1
            bytes_read += size
            resources = _resources_in(text)
            if not resources:
                continue
            total += 1
            if len(manifests) < _MAX_MANIFEST_FILES:
                manifests.append(
                    KubernetesManifest(
                        path=_relative_posix(path, root),
                        resources=resources[:_MAX_RESOURCES_PER_FILE],
                    )
                )
    return manifests, total


def detect_kubernetes(root: Path, *, manifests: bool = True) -> KubernetesInfo | None:
    """Detect Helm charts, Kustomize overlays and (unless `manifests` is
    False) raw manifests under `root`. Returns `None` when none is found --
    the common case for a project with no Kubernetes tooling at all.
    `manifests=False` is the cheap form `KubernetesAnalyzer.matches` uses.
    """
    helm_charts: list[HelmChart] = []
    kustomize_overlays: list[KustomizeOverlay] = []

    directories = _walk(root)
    for directory in directories:
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

    raw: list[KubernetesManifest] = []
    raw_total = 0
    if manifests:
        chart_dirs = [root / c.path for c in helm_charts]
        raw, raw_total = _scan_manifests(root, directories, chart_dirs)

    if not helm_charts and not kustomize_overlays and not raw:
        return None

    helm_charts.sort(key=lambda c: c.path)
    kustomize_overlays.sort(key=lambda o: o.path)
    return KubernetesInfo(
        helm_charts=helm_charts,
        kustomize_overlays=kustomize_overlays,
        manifests=raw,
        total_manifest_files=raw_total,
    )
