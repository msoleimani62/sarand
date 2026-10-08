"""Project component view for hybrid repositories (backlog item 11,
"Hybrid Project Model"), first scope: representation and context.

Evidence-first audit, run against a realistic hybrid fixture
(`backend/pyproject.toml` + `frontend/package.json` with React, a root
`docker-compose.yml` building both, `.github/workflows/ci.yml`, a
root `Makefile`, `deploy/k8s/kustomization.yaml`, `docs/`):

- `detect_project()` only inspects marker files in the project *root*
  and keeps one `primary_language`/`project_type`/`build_system` (first
  match wins). The fixture was reported as language "Generic", type
  "unknown", build system "make" -- neither Python nor Node.js was
  detected at all, because the only root marker was the `Makefile`.
- Analyzers are matched against the root too, so of ~40 analyzers only
  GitHub Actions, YAML and Markdown matched. Python and Node analyzers
  never ran: **no tests, quality or security checks for either real
  component.** (CONFIRMED, and a bigger gap than the representation
  one this round addresses -- recorded in BACKLOG_STATUS.md as its own
  follow-up; not fixed here.)
- Nothing expresses that the compose services build `backend/` and
  `frontend/`, or which directory is an application versus
  infrastructure versus CI.

Scope, per the backlog doc ("focus on representation and context, not
a universal software architecture detector"): a *view* over evidence
that is already cheap to read. It adds **no findings**, runs nothing,
and never changes `primary_language`, health, issues or any existing
report section. Roles are assigned only from concrete markers:

- **application** -- a directory with a language project marker
  (`PROJECT_MARKERS`, bounded 3 levels deep). `kind` is `frontend` /
  `backend` only when a declared dependency says so unambiguously
  (npm: react/vue/svelte/angular/next/... vs express/fastify/nest/...;
  Python: fastapi/django/flask/...); otherwise left empty -- never
  guessed from directory names.
- **infrastructure** -- Helm charts, Kustomize overlays and Compose
  files already found by `core/kubernetes.py` / `core/compose.py`,
  plus Terraform directories (`*.tf`) and Dockerfile directories.
- **ci** -- GitHub Actions, GitLab CI, Jenkins, CircleCI, Azure
  Pipelines markers at the root.
- **documentation** -- a root `docs/` directory with files in it.
- **configuration** -- Makefiles already found by `core/makefile.py`.

The one relationship represented: a Compose service whose `build:`
context points at a detected application directory ("builds").

The section is emitted only for a *hybrid* project: at least two
application components with different (languages, kind) signatures
(so a Cargo or npm workspace of same-kind members is not "hybrid"),
or an application together with Helm/Kustomize/Compose/Terraform
infrastructure. A plain project with a Dockerfile, CI and docs gets no
new section.

**Deliberately deferred:** running analyzers per component (the
execution gap above), database/service-role inference, relationships
beyond Compose builds, Nx/Turborepo/Bazel graphs, changing
`detect_project()`.

نمای اجزای پروژه برای مخزن‌های ترکیبی (آیتم ۱۱ backlog، «مدل پروژه‌ی
ترکیبی»)، اسکوپ اول: بازنمایی و زمینه.

ممیزی evidence-first روی یک fixture ترکیبیِ واقع‌بینانه نشان داد:
`detect_project()` فقط نشانگرهای ریشه را می‌بیند و یک زبان اصلی نگه
می‌دارد؛ fixture به‌صورت «Generic / unknown / make» گزارش شد و نه
Python تشخیص داده شد نه Node.js. آنالایزرها هم فقط روی ریشه match
می‌شوند، پس از حدود ۴۰ آنالایزر فقط GitHub Actions، YAML و Markdown
اجرا شدند: **برای هیچ‌کدام از اجزای واقعی تست/کیفیت/امنیت اجرا نشد**
(CONFIRMED، شکافی بزرگ‌تر از شکاف بازنمایی این دور؛ جداگانه در
BACKLOG_STATUS.md ثبت شده و اینجا حل نشده است).

اسکوپ: یک *نما* روی شواهدی که ارزان خوانده می‌شوند. هیچ finding
اضافه نمی‌کند، چیزی اجرا نمی‌کند و هیچ بخش موجودی را تغییر نمی‌دهد.
نقش‌ها فقط از نشانگرهای مشخص می‌آیند (application، infrastructure،
ci، documentation، configuration) و `kind` فقط وقتی پر می‌شود که
وابستگیِ اعلام‌شده بی‌ابهام باشد -- هرگز از نام پوشه حدس زده نمی‌شود.
تنها رابطه: سرویس Compose که context بیلدش به پوشه‌ی یک application
اشاره کند («builds»). بخش فقط برای پروژه‌ی *ترکیبی* ظاهر می‌شود.

عمداً به بعد موکول شد: اجرای آنالایزر برای هر جزء، استنتاج نقشِ
دیتابیس/سرویس، روابط فراتر از build در Compose، گراف Nx/Turborepo/
Bazel و تغییر `detect_project()`.
"""

from __future__ import annotations

import json
import posixpath
import re
import sys
from pathlib import Path

import yaml as _yaml

from sarand.constants import IGNORE_DIRS, PROJECT_MARKERS
from sarand.models.results import (
    Component,
    ComponentLink,
    ComponentsInfo,
    ComposeInfo,
    KubernetesInfo,
    MakefileInfo,
)

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10: same parser, packaged separately
    import tomli as tomllib

# Precision over recall: fixtures, vendored code and examples often
# carry their own manifests and would otherwise show up as components.
# دقت مهم‌تر از پوشش: fixtureها، کدِ vendor و نمونه‌ها مانیفست خودشان را
# دارند و در غیر این صورت به‌عنوان جزء ظاهر می‌شدند.
_SKIP_DIRS = IGNORE_DIRS | frozenset(
    {
        "tests",
        "test",
        "testdata",
        "fixtures",
        "examples",
        "example",
        "vendor",
        "third_party",
        "third-party",
    }
)

_MAX_DEPTH = 3
_MAX_COMPONENTS = 50
_MAX_LINKS = 100
_MAX_PARSE_BYTES = 1024 * 1024

# A directory holding only one of these is not treated as a component
# below the root (`docs/requirements.txt` for Sphinx is the classic
# false positive). At the root they still count: `detect_project()`
# already treats them as project markers there.
# پوشه‌ای که فقط یکی از این‌ها را دارد زیرِ ریشه جزء حساب نمی‌شود.
_WEAK_MARKERS = frozenset({"requirements.txt", "setup.cfg"})

_ROLE_ORDER = {
    "application": 0,
    "infrastructure": 1,
    "ci": 2,
    "documentation": 3,
    "configuration": 4,
}
_HYBRID_INFRA_KINDS = frozenset({"helm", "kustomize", "compose", "terraform"})

_NODE_FRONTEND = frozenset(
    {
        "react",
        "react-dom",
        "vue",
        "svelte",
        "@sveltejs/kit",
        "@angular/core",
        "next",
        "nuxt",
        "solid-js",
        "preact",
        "astro",
        "gatsby",
        "lit",
    }
)
_NODE_BACKEND = frozenset(
    {"express", "fastify", "koa", "@nestjs/core", "hapi", "@hapi/hapi", "restify"}
)
_PY_BACKEND = frozenset(
    {
        "fastapi",
        "django",
        "flask",
        "starlette",
        "aiohttp",
        "tornado",
        "sanic",
        "litestar",
        "quart",
        "falcon",
        "pyramid",
        "bottle",
    }
)

_CI_MARKERS: tuple[tuple[str, str], ...] = (
    (".github/workflows", "github-actions"),
    (".gitlab-ci.yml", "gitlab-ci"),
    ("Jenkinsfile", "jenkins"),
    (".circleci/config.yml", "circleci"),
    ("azure-pipelines.yml", "azure-pipelines"),
)

_PY_DEP_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _scan(root: Path) -> list[tuple[str, set[str]]]:
    """(relative posix dir, file names) for `root` and every directory
    up to `_MAX_DEPTH` below it, pruning `_SKIP_DIRS`, without following
    symlinks."""
    result: list[tuple[str, set[str]]] = []
    frontier: list[tuple[Path, int]] = [(root, 0)]
    while frontier:
        current, depth = frontier.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        files: set[str] = set()
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_file():
                files.add(entry.name)
            elif entry.is_dir() and depth < _MAX_DEPTH and entry.name not in _SKIP_DIRS:
                frontier.append((entry, depth + 1))
        rel = "." if current == root else current.relative_to(root).as_posix()
        result.append((rel, files))
    return result


def _read_limited(path: Path) -> str | None:
    try:
        if path.stat().st_size > _MAX_PARSE_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _normalise_py(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _node_hint(manifest: Path) -> str:
    text = _read_limited(manifest)
    if text is None:
        return ""
    try:
        data = json.loads(text)
    except ValueError:
        return ""
    if not isinstance(data, dict):
        return ""
    deps: set[str] = set()
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        section = data.get(key)
        if isinstance(section, dict):
            deps.update(str(k) for k in section)
    front = bool(deps & _NODE_FRONTEND)
    back = bool(deps & _NODE_BACKEND)
    if front and not back:
        return "frontend"
    if back and not front:
        return "backend"
    return ""


def _python_hint(directory: Path, files: set[str]) -> str:
    names: set[str] = set()
    if "pyproject.toml" in files:
        text = _read_limited(directory / "pyproject.toml")
        if text is not None:
            try:
                data = tomllib.loads(text)
            except tomllib.TOMLDecodeError:
                data = {}
            project = data.get("project")
            if isinstance(project, dict):
                deps = project.get("dependencies")
                if isinstance(deps, list):
                    for dep in deps:
                        match = _PY_DEP_NAME.match(str(dep))
                        if match:
                            names.add(_normalise_py(match.group(1)))
            poetry = data.get("tool", {}).get("poetry", {})
            if isinstance(poetry, dict) and isinstance(
                poetry.get("dependencies"), dict
            ):
                names.update(_normalise_py(str(k)) for k in poetry["dependencies"])
    if "requirements.txt" in files:
        text = _read_limited(directory / "requirements.txt")
        for line in (text or "").splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "-")):
                continue
            match = _PY_DEP_NAME.match(line)
            if match:
                names.add(_normalise_py(match.group(1)))
    return "backend" if names & _PY_BACKEND else ""


def _application_components(
    root: Path, scanned: list[tuple[str, set[str]]]
) -> list[Component]:
    apps: list[Component] = []
    for rel, files in scanned:
        markers = [
            m
            for m in PROJECT_MARKERS
            if m in files and PROJECT_MARKERS[m][0] != "Generic"
        ]
        if not markers:
            continue
        if rel != "." and all(m in _WEAK_MARKERS for m in markers):
            continue
        languages: list[str] = []
        for marker in markers:
            language = PROJECT_MARKERS[marker][0]
            if language not in languages:
                languages.append(language)
        directory = root if rel == "." else root / rel
        hints: set[str] = set()
        if "package.json" in markers:
            hints.add(_node_hint(directory / "package.json"))
        if "Python" in languages:
            hints.add(_python_hint(directory, files))
        hints.discard("")
        kind = next(iter(hints)) if len(hints) == 1 else ""
        apps.append(
            Component(
                path=rel,
                role="application",
                kind=kind,
                languages=languages,
                evidence=markers,
            )
        )
    return apps


def _infrastructure_components(
    scanned: list[tuple[str, set[str]]],
    kubernetes: KubernetesInfo | None,
    compose: ComposeInfo | None,
) -> list[Component]:
    infra: list[Component] = []
    if kubernetes is not None:
        infra.extend(
            Component(
                path=c.path, role="infrastructure", kind="helm", evidence=["Chart.yaml"]
            )
            for c in kubernetes.helm_charts
        )
        infra.extend(
            Component(
                path=o.path,
                role="infrastructure",
                kind="kustomize",
                evidence=["kustomization.yaml"],
            )
            for o in kubernetes.kustomize_overlays
        )
    if compose is not None:
        infra.extend(
            Component(
                path=f.path,
                role="infrastructure",
                kind="compose",
                evidence=[posixpath.basename(f.path)],
            )
            for f in compose.files
        )
    for rel, files in scanned:
        if any(name.endswith(".tf") for name in files):
            infra.append(
                Component(
                    path=rel,
                    role="infrastructure",
                    kind="terraform",
                    evidence=["*.tf"],
                )
            )
        if "Dockerfile" in files:
            infra.append(
                Component(
                    path=rel,
                    role="infrastructure",
                    kind="container",
                    evidence=["Dockerfile"],
                )
            )
    return infra


def _ci_components(root: Path) -> list[Component]:
    found: list[Component] = []
    for marker, kind in _CI_MARKERS:
        target = root / marker
        if kind == "github-actions":
            try:
                present = target.is_dir() and any(
                    p.suffix.lower() in (".yml", ".yaml") for p in target.iterdir()
                )
            except OSError:
                present = False
        else:
            present = target.is_file()
        if present:
            found.append(
                Component(path=marker, role="ci", kind=kind, evidence=[marker])
            )
    return found


def _documentation_components(root: Path) -> list[Component]:
    docs = root / "docs"
    try:
        if docs.is_dir() and not docs.is_symlink() and any(docs.iterdir()):
            return [
                Component(
                    path="docs", role="documentation", kind="", evidence=["docs/"]
                )
            ]
    except OSError:
        pass
    return []


def _configuration_components(makefile: MakefileInfo | None) -> list[Component]:
    if makefile is None:
        return []
    return [
        Component(
            path=f.path,
            role="configuration",
            kind="make",
            evidence=[posixpath.basename(f.path)],
        )
        for f in makefile.files
    ]


def _compose_links(
    root: Path, compose: ComposeInfo | None, app_paths: set[str]
) -> list[ComponentLink]:
    """Compose services whose `build:` context is a detected application
    directory. Reads each compose file itself (self-contained module,
    same convention as `core/compose.py`)."""
    if compose is None:
        return []
    links: list[ComponentLink] = []
    seen: set[tuple[str, str, str]] = set()
    for cfile in compose.files:
        text = _read_limited(root / cfile.path)
        if text is None:
            continue
        try:
            data = _yaml.safe_load(text)
        except _yaml.YAMLError:
            continue
        services = data.get("services") if isinstance(data, dict) else None
        if not isinstance(services, dict):
            continue
        for name, spec in services.items():
            if not isinstance(spec, dict) or "build" not in spec:
                continue
            build = spec["build"]
            if isinstance(build, dict):
                context = build.get("context", ".")
            else:
                context = build
            if not isinstance(context, str) or not context:
                continue
            if "://" in context or context.startswith(("/", "git@", "github.com")):
                continue
            target = posixpath.normpath(
                posixpath.join(posixpath.dirname(cfile.path) or ".", context)
            )
            if target == ".." or target.startswith("../") or target not in app_paths:
                continue
            key = (cfile.path, target, str(name))
            if key in seen:
                continue
            seen.add(key)
            links.append(
                ComponentLink(
                    source=cfile.path,
                    target=target,
                    relation="builds",
                    evidence=f"service '{name}' build context",
                )
            )
    return links


def _is_hybrid(apps: list[Component], infra: list[Component]) -> bool:
    signatures = {(tuple(a.languages), a.kind) for a in apps}
    if len(signatures) >= 2:
        return True
    return bool(apps) and any(i.kind in _HYBRID_INFRA_KINDS for i in infra)


def nested_application_components(root: Path) -> list[Component]:
    """Application components below the root (never the root itself).

    Used by `core/per_component.py` to plan nested runs for a project that is
    NOT hybrid, where `detect_components` returns `None`. Same discovery rules
    as the component view (bounded depth, `_SKIP_DIRS` pruned, weak markers
    ignored), so `examples/`, `tests/`, `fixtures/` and `vendor/` never count.
    کامپوننت‌های application زیر ریشه؛ برای برنامه‌ریزی اجرای تو در تو در
    پروژه‌ی غیرهیبرید (جایی که detect_components مقدار None می‌دهد).
    """
    return [c for c in _application_components(root, _scan(root)) if c.path != "."]


def detect_components(
    root: Path,
    kubernetes: KubernetesInfo | None = None,
    compose: ComposeInfo | None = None,
    makefile: MakefileInfo | None = None,
) -> ComponentsInfo | None:
    """Component view of a hybrid project. Returns `None` for a project
    that is not hybrid (see the module docstring for the rule) -- the
    common case, which keeps ordinary reports unchanged.
    """
    scanned = _scan(root)
    apps = _application_components(root, scanned)
    infra = _infrastructure_components(scanned, kubernetes, compose)
    if not _is_hybrid(apps, infra):
        return None

    components = [
        *apps,
        *infra,
        *_ci_components(root),
        *_documentation_components(root),
        *_configuration_components(makefile),
    ]
    components.sort(key=lambda c: (_ROLE_ORDER[c.role], c.path, c.kind))
    links = _compose_links(root, compose, {a.path for a in apps})
    links.sort(key=lambda link: (link.source, link.target, link.evidence))
    return ComponentsInfo(
        components=components[:_MAX_COMPONENTS],
        links=links[:_MAX_LINKS],
        total_components=len(components),
        total_links=len(links),
    )
