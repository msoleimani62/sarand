"""Docker Compose file detection (backlog item 6, "Docker Compose").

Evidence-first audit before any implementation: grepped `analyzers/`
and `core/` for compose awareness. The only trace is
`YamlAnalyzer._ENTRY_POINTS`, which lists `docker-compose.yml`/`.yaml`
as *entry points* (files worth surfacing), and `YamlAnalyzer` itself
only lints top-level YAML with `yamllint` -- it never reads a compose
file's content, never finds `compose.yaml` (the current Compose
Specification name) or override files, and never looks below the
project root. The report therefore cannot say which services a
project defines. CONFIRMED gap, in representation only.

Scope for this round, same discipline as items 8 and 5: **detection
only**. Compose files have a small, fixed naming convention, so the
name is the marker -- no content sniffing across every YAML file:

- `compose.yaml` / `compose.yml` (Compose Specification)
- `docker-compose.yaml` / `docker-compose.yml` (legacy name)
- variants with one extra segment, e.g. `docker-compose.override.yml`,
  `compose.prod.yaml`

For each file the top-level `services` mapping is read (name, `image`,
and whether a `build` key exists). A malformed file is still reported
(its name is a strong marker) with no services rather than dropped or
crashing.

**Deliberately deferred:** any execution (`docker compose config`,
`hadolint`, `dclint`), `include:`/`extends:` resolution, merging
override files into one effective model, and Dockerfile detection.

تشخیص فایل‌های Docker Compose (آیتم ۶ backlog، «Docker Compose»).

ممیزیِ evidence-first: تنها ردپا `YamlAnalyzer._ENTRY_POINTS` است که
`docker-compose.yml`/`.yaml` را به‌عنوان entry point فهرست می‌کند و
خودِ `YamlAnalyzer` فقط YAML سطحِ ریشه را با `yamllint` لینت می‌کند --
هرگز محتوای فایل compose را نمی‌خواند، `compose.yaml` (نامِ فعلیِ
Compose Specification) و فایل‌های override را پیدا نمی‌کند و زیرِ ریشه
را نمی‌گردد. پس گزارش نمی‌تواند بگوید پروژه چه serviceهایی دارد. شکافِ
CONFIRMED، فقط در بازنمایی.

اسکوپِ این دور: **فقط تشخیص**. نامِ فایل همان نشانگر است، بدون بررسیِ
محتوای همه‌ی YAMLها. برای هر فایل نگاشتِ سطح‌بالای `services` خوانده
می‌شود (نام، `image`، و وجودِ کلیدِ `build`). فایلِ بدشکل هم گزارش
می‌شود (بدون service) و نه حذف می‌شود نه کرش می‌کند.

عمداً به بعد موکول شد: هر اجرا (`docker compose config`، `hadolint`)،
حل‌کردنِ `include:`/`extends:`، ادغامِ overrideها و تشخیصِ Dockerfile.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml as _yaml

from sarand.models.results import ComposeFile, ComposeInfo, ComposeService

# Compose Specification names plus one optional extra segment
# (`.override`, `.prod`, ...). Anchored on both ends so
# `my-compose.yml` or `compose.yml.bak` never match.
# نام‌های Compose Specification به‌علاوه‌ی یک بخشِ اختیاریِ اضافه
# (`.override`، `.prod`، ...). از هر دو سو لنگر شده تا `my-compose.yml`
# یا `compose.yml.bak` هرگز تطبیق نکنند.
_COMPOSE_NAME = re.compile(r"^(?:docker-)?compose(?:\.[A-Za-z0-9_-]+)?\.ya?ml$")

# Same build/dependency/VCS prune list as `core/kubernetes.py` and
# `core/sbom.py`'s syft fix: those directories only hold third-party
# or generated content. Kept as a local copy on purpose -- AGENTS.md
# favours self-contained modules over shared private helpers.
# همان فهرستِ حذفِ build/وابستگی/VCS در `core/kubernetes.py` و اصلاح
# syft در `core/sbom.py`. عمداً نسخه‌ی محلی نگه داشته شده -- AGENTS.md
# ماژول‌های خودکفا را به helperهای خصوصیِ مشترک ترجیح می‌دهد.
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

# Compose files sit at the root or a few levels down in real layouts
# (`deploy/compose.yaml`, `services/api/docker-compose.yml`).
# فایل‌های compose در چیدمان‌های واقعی در ریشه یا چند سطح پایین‌تر
# هستند (`deploy/compose.yaml`، `services/api/docker-compose.yml`).
_MAX_DEPTH = 5

# A real compose file is a few KiB; refuse to parse anything absurd
# (generated or hostile) rather than spend memory on it.
# فایل compose واقعی چند KiB است؛ از پارسِ هر چیز غیرعادی (تولیدشده یا
# مخرب) صرف‌نظر می‌شود تا حافظه هدر نرود.
_MAX_PARSE_BYTES = 1024 * 1024


def _find_compose_files(root: Path) -> list[Path]:
    """Compose files under `root`, pruning `_SKIP_DIRS` and anything
    past `_MAX_DEPTH`, without following symlinks (no cycles, no
    escaping the project tree)."""
    found: list[Path] = []
    frontier = [(root, 0)]
    while frontier:
        current, depth = frontier.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_file():
                if _COMPOSE_NAME.match(entry.name):
                    found.append(entry)
            elif entry.is_dir() and depth < _MAX_DEPTH and entry.name not in _SKIP_DIRS:
                frontier.append((entry, depth + 1))
    return found


def _read_services(path: Path) -> list[ComposeService]:
    """Services declared in one compose file, in file order. Any read
    or parse failure yields an empty list -- malformed content is not
    this detector's job to report."""
    try:
        if path.stat().st_size > _MAX_PARSE_BYTES:
            return []
        data = _yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, _yaml.YAMLError):
        # ValueError covers UnicodeDecodeError.
        # ValueError شاملِ UnicodeDecodeError هم می‌شود.
        return []
    if not isinstance(data, dict):
        return []
    raw_services = data.get("services")
    if not isinstance(raw_services, dict):
        return []
    services: list[ComposeService] = []
    for name, spec in raw_services.items():
        if isinstance(spec, dict):
            image = spec.get("image")
            services.append(
                ComposeService(
                    name=str(name),
                    image=image if isinstance(image, str) else "",
                    builds="build" in spec,
                )
            )
        else:
            services.append(ComposeService(name=str(name)))
    return services


def detect_compose(root: Path) -> ComposeInfo | None:
    """Detect Docker Compose files under `root`. Returns `None` when
    none are found -- the common case for a project that does not use
    Compose at all.
    """
    paths = _find_compose_files(root)
    if not paths:
        return None
    files = [
        ComposeFile(
            path=path.relative_to(root).as_posix(),
            services=_read_services(path),
        )
        for path in paths
    ]
    files.sort(key=lambda f: f.path)
    return ComposeInfo(files=files)
