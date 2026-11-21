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
import tomllib
from pathlib import Path
from typing import NamedTuple

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


class DeclaredDependency(NamedTuple):
    """One dependency name read from a manifest. `scope` is `runtime` or
    `dev` only where the manifest makes it unambiguous, otherwise empty.
    یک نام وابستگی از مانیفست؛ `scope` فقط وقتی بی‌ابهام است پر می‌شود.
    """

    name: str
    scope: str
    manifest: str  # file name inside the directory, e.g. "package.json"


_NODE_SECTIONS: tuple[tuple[str, str], ...] = (
    ("dependencies", "runtime"),
    ("devDependencies", "dev"),
    ("peerDependencies", ""),
)


def _node_dependencies(directory: Path) -> list[DeclaredDependency]:
    text = _read_limited(directory / "package.json")
    if text is None:
        return []
    try:
        data = json.loads(text)
    except ValueError:
        return []
    if not isinstance(data, dict):
        return []
    found: list[DeclaredDependency] = []
    for key, scope in _NODE_SECTIONS:
        section = data.get(key)
        if isinstance(section, dict):
            found.extend(
                DeclaredDependency(str(name), scope, "package.json") for name in section
            )
    return found


class PythonDeclaration(NamedTuple):
    """One Python dependency name and the section of the manifest that declares it.

    `section` names where the manifest declared it, so a reader can tell a runtime
    dependency from an optional extra or a development group: `project.dependencies`,
    `project.optional-dependencies.<extra>`, `dependency-groups.<group>`,
    `build-system.requires`, `tool.poetry.dependencies`,
    `tool.poetry.dev-dependencies`, `tool.poetry.group.<group>.dependencies`, or
    `requirements.txt`. `name` is the PEP 503 normalised distribution name.
    یک نام وابستگی پایتون و بخشی از مانیفست که آن را اعلام کرده است.
    """

    name: str
    section: str
    manifest: str


_PYPROJECT = "pyproject.toml"
_REQUIREMENTS = "requirements.txt"
# The sections whose names `declared_dependencies` has always reported, with the scope
# it gives them (Quick Context reads those names; the other sections stay out of it).
# بخش‌هایی که `declared_dependencies` همیشه گزارش کرده است.
_LEGACY_PYTHON_SECTIONS: dict[str, str] = {
    "project.dependencies": "runtime",
    "tool.poetry.dependencies": "runtime",
    _REQUIREMENTS: "",
}


def _requirement_names(items: object) -> list[str]:
    """Normalised names of the PEP 508 requirement strings in `items`. Anything else
    (for example the `{include-group = ...}` tables of PEP 735) is not a package and
    is skipped."""
    names: list[str] = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, str):
                match = _PY_DEP_NAME.match(item)
                if match:
                    names.append(_normalise_py(match.group(1)))
    return names


def _poetry_names(table: object) -> list[str]:
    """Names in a Poetry dependency table. `python` is the interpreter constraint, not
    a package."""
    if not isinstance(table, dict):
        return []
    return [
        _normalise_py(str(name))
        for name in table
        if _normalise_py(str(name)) != "python"
    ]


def _pyproject_declarations(data: dict[str, object]) -> list[PythonDeclaration]:
    found: list[PythonDeclaration] = []

    def add(names: list[str], section: str) -> None:
        found.extend(PythonDeclaration(name, section, _PYPROJECT) for name in names)

    project = data.get("project")
    if isinstance(project, dict):
        add(_requirement_names(project.get("dependencies")), "project.dependencies")
        extras = project.get("optional-dependencies")
        if isinstance(extras, dict):
            for extra in sorted(extras, key=str):
                add(
                    _requirement_names(extras[extra]),
                    f"project.optional-dependencies.{extra}",
                )
    groups = data.get("dependency-groups")
    if isinstance(groups, dict):
        for group in sorted(groups, key=str):
            add(_requirement_names(groups[group]), f"dependency-groups.{group}")
    build = data.get("build-system")
    if isinstance(build, dict):
        add(_requirement_names(build.get("requires")), "build-system.requires")
    tool = data.get("tool")
    poetry = tool.get("poetry") if isinstance(tool, dict) else None
    if isinstance(poetry, dict):
        add(_poetry_names(poetry.get("dependencies")), "tool.poetry.dependencies")
        add(
            _poetry_names(poetry.get("dev-dependencies")),
            "tool.poetry.dev-dependencies",
        )
        poetry_groups = poetry.get("group")
        if isinstance(poetry_groups, dict):
            for group in sorted(poetry_groups, key=str):
                body = poetry_groups[group]
                if isinstance(body, dict):
                    add(
                        _poetry_names(body.get("dependencies")),
                        f"tool.poetry.group.{group}.dependencies",
                    )
    return found


def python_declarations(directory: Path, files: set[str]) -> list[PythonDeclaration]:
    """Every Python dependency name declared in `directory`, with its section.

    Reads `pyproject.toml` (PEP 621 dependencies and optional dependencies, PEP 735
    dependency groups, `build-system.requires`, the Poetry tables) and
    `requirements.txt`. It reads declarations only: it never reads installed
    packages, so an import name is not mapped to a distribution name here.
    """
    found: list[PythonDeclaration] = []
    if _PYPROJECT in files:
        text = _read_limited(directory / _PYPROJECT)
        if text is not None:
            try:
                data = tomllib.loads(text)
            except tomllib.TOMLDecodeError:
                data = {}
            found.extend(_pyproject_declarations(data))
    if _REQUIREMENTS in files:
        text = _read_limited(directory / _REQUIREMENTS)
        for line in (text or "").splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "-")):
                continue
            match = _PY_DEP_NAME.match(line)
            if match:
                found.append(
                    PythonDeclaration(
                        _normalise_py(match.group(1)), _REQUIREMENTS, _REQUIREMENTS
                    )
                )
    return found


def _python_dependencies(directory: Path, files: set[str]) -> list[DeclaredDependency]:
    """The names `declared_dependencies` reports for Python: runtime dependencies, the
    Poetry table and `requirements.txt`, as before. The other sections are read by
    `python_declarations` for the structure only."""
    return [
        DeclaredDependency(d.name, _LEGACY_PYTHON_SECTIONS[d.section], d.manifest)
        for d in python_declarations(directory, files)
        if d.section in _LEGACY_PYTHON_SECTIONS
    ]


_CARGO_SECTIONS: tuple[tuple[str, str], ...] = (
    ("dependencies", "runtime"),
    ("dev-dependencies", "dev"),
    ("build-dependencies", ""),
)
_GO_VERSION_SUFFIX = re.compile(r"/v\d+$")


def _cargo_names(table: object, scope: str) -> list[DeclaredDependency]:
    """Crate names of one dependency table. A renamed dependency
    (`alias = { package = "real" }`) is reported under its real crate name."""
    if not isinstance(table, dict):
        return []
    found: list[DeclaredDependency] = []
    for key, value in table.items():
        name = value.get("package") if isinstance(value, dict) else None
        found.append(
            DeclaredDependency(
                str(name if isinstance(name, str) else key), scope, "Cargo.toml"
            )
        )
    return found


def _cargo_dependencies(directory: Path) -> list[DeclaredDependency]:
    """`[dependencies]` (runtime), `[dev-dependencies]` (dev), `[build-dependencies]`
    and `[workspace.dependencies]` (scope unknown: declared once, used by members).
    Target-specific tables are not read."""
    text = _read_limited(directory / "Cargo.toml")
    if text is None:
        return []
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    found: list[DeclaredDependency] = []
    for key, scope in _CARGO_SECTIONS:
        found.extend(_cargo_names(data.get(key), scope))
    workspace = data.get("workspace")
    if isinstance(workspace, dict):
        found.extend(_cargo_names(workspace.get("dependencies"), ""))
    return found


def _go_dependencies(directory: Path) -> list[DeclaredDependency]:
    """Direct `require` entries of `go.mod` (single line or block). Entries marked
    `// indirect` are the project's transitive dependencies, not its declarations,
    so they are skipped. A trailing major-version suffix (`/v2`) is dropped."""
    text = _read_limited(directory / "go.mod")
    if text is None:
        return []
    found: list[DeclaredDependency] = []
    in_block = False
    for raw in text.splitlines():
        line = raw.strip()
        if in_block:
            if line.startswith(")"):
                in_block = False
                continue
            entry = line
        elif line.startswith("require ("):
            in_block = True
            continue
        elif line.startswith("require "):
            entry = line[len("require ") :].strip()
        else:
            continue
        if not entry or entry.startswith("//") or "// indirect" in entry:
            continue
        module = entry.split()[0]
        found.append(
            DeclaredDependency(_GO_VERSION_SUFFIX.sub("", module), "runtime", "go.mod")
        )
    return found


def declared_dependencies(directory: Path, files: set[str]) -> list[DeclaredDependency]:
    """Dependency names declared in the manifests of one directory (Node:
    `package.json`; Python: `pyproject.toml` and `requirements.txt`; Rust:
    `Cargo.toml`; Go: `go.mod`). The single reader behind the `kind` hint below
    and the declared-frameworks line of Quick Context (core/frameworks.py), so
    the two cannot disagree. The `kind` hint itself reads only Node and Python.
    خواننده‌ی واحد وابستگی‌های اعلام‌شده (Node، Python، Rust و Go).
    """
    found: list[DeclaredDependency] = []
    if "package.json" in files:
        found.extend(_node_dependencies(directory))
    found.extend(_python_dependencies(directory, files))
    if "Cargo.toml" in files:
        found.extend(_cargo_dependencies(directory))
    if "go.mod" in files:
        found.extend(_go_dependencies(directory))
    return found


def _node_hint(directory: Path) -> str:
    deps = {d.name for d in _node_dependencies(directory)}
    front = bool(deps & _NODE_FRONTEND)
    back = bool(deps & _NODE_BACKEND)
    if front and not back:
        return "frontend"
    if back and not front:
        return "backend"
    return ""


def _python_hint(directory: Path, files: set[str]) -> str:
    names = {d.name for d in _python_dependencies(directory, files)}
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
            hints.add(_node_hint(directory))
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
