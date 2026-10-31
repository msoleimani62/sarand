"""Declared frameworks: the Quick Context line "Declared frameworks (from
manifests, not verified in code)" (docs/QUICK_CONTEXT_DESIGN.md, section 4,
decision D-QC2).

Three different things must not be conflated, and this module provides only
the first two:

1. a dependency **declared** in a manifest;
2. a framework **recognised** from a fixed table of dependency names;
3. actual **use** in code -- never claimed here.

Evidence-first audit (R11a, run on the code of 2026-10-30): the only manifests
whose dependency names are already parsed are Node (`package.json`:
`dependencies`, `devDependencies`, `peerDependencies`) and Python
(`pyproject.toml` `[project].dependencies` and `[tool.poetry.dependencies]`,
`requirements.txt`), in `core/components.py`. That reader is reused through
`declared_dependencies`; there is no second parser. Cargo and Go manifests are
not parsed anywhere, so those ecosystems yield no entries (a deliberate gap,
recorded in the design file, not guessed around).

Rules:

- Frameworks come only from manifests, never from folder layout or file names.
- Directories read: the project root and the application components found by
  `core/components.py` (same bounded, pruned search), nothing else.
- `scope` is `runtime` for `dependencies` / `[project].dependencies` /
  poetry dependencies, `dev` for `devDependencies`, and empty for
  `peerDependencies` and `requirements.txt`, whose meaning is not
  unambiguous.
- Pure and deterministic: no clock, no environment; output is sorted by
  (manifest, label, name) and capped.

فریم‌ورک‌های اعلام‌شده: فقط از وابستگی‌های مانیفست و یک جدول ثابت، نه از
ساختار پوشه و نه از استفاده‌ی واقعی در کد. فقط Node و Python خوانده می‌شوند
(Cargo و Go هنوز هیچ‌جا parse نمی‌شوند). خروجی مرتب و محدود است.
"""

from __future__ import annotations

from pathlib import Path

from sarand.core.components import declared_dependencies, nested_application_components
from sarand.models.results import FrameworkEntry

# Bump on every deliberate edit of the table; a snapshot test pins both.
# با هر ویرایش عمدی جدول افزایش می‌یابد؛ یک تست snapshot هر دو را قفل می‌کند.
FRAMEWORK_TABLE_VERSION = 1

_MAX_ENTRIES = 100

# dependency name as declared (Python names are normalised: lowercase, `-`) ->
# display label.
FRAMEWORK_TABLE: dict[str, str] = {
    # Python
    "aiohttp": "aiohttp",
    "bottle": "Bottle",
    "celery": "Celery",
    "dash": "Dash",
    "django": "Django",
    "djangorestframework": "Django REST framework",
    "falcon": "Falcon",
    "fastapi": "FastAPI",
    "flask": "Flask",
    "gradio": "Gradio",
    "litestar": "Litestar",
    "pyramid": "Pyramid",
    "pytest": "pytest",
    "quart": "Quart",
    "sanic": "Sanic",
    "scikit-learn": "scikit-learn",
    "scrapy": "Scrapy",
    "sqlalchemy": "SQLAlchemy",
    "starlette": "Starlette",
    "streamlit": "Streamlit",
    "tensorflow": "TensorFlow",
    "textual": "Textual",
    "torch": "PyTorch",
    "tornado": "Tornado",
    "transformers": "Transformers",
    "typer": "Typer",
    # Node.js
    "@angular/core": "Angular",
    "@capacitor/core": "Capacitor",
    "@hapi/hapi": "hapi",
    "@nestjs/core": "NestJS",
    "@playwright/test": "Playwright",
    "@prisma/client": "Prisma",
    "@reduxjs/toolkit": "Redux Toolkit",
    "@sveltejs/kit": "SvelteKit",
    "@tauri-apps/api": "Tauri",
    "@trpc/server": "tRPC",
    "astro": "Astro",
    "cypress": "Cypress",
    "electron": "Electron",
    "expo": "Expo",
    "express": "Express",
    "fastify": "Fastify",
    "gatsby": "Gatsby",
    "hapi": "hapi",
    "jest": "Jest",
    "koa": "Koa",
    "lit": "Lit",
    "mongoose": "Mongoose",
    "next": "Next.js",
    "nuxt": "Nuxt",
    "pinia": "Pinia",
    "preact": "Preact",
    "react": "React",
    "react-native": "React Native",
    "sequelize": "Sequelize",
    "socket.io": "Socket.IO",
    "solid-js": "Solid",
    "svelte": "Svelte",
    "tailwindcss": "Tailwind CSS",
    "typeorm": "TypeORM",
    "vite": "Vite",
    "vitest": "Vitest",
    "vue": "Vue",
    "webpack": "webpack",
}


def _rel(directory: str, manifest: str) -> str:
    return manifest if directory == "." else f"{directory}/{manifest}"


def detect_declared_frameworks(root: Path) -> list[FrameworkEntry]:
    """Frameworks declared by the manifests of `root` and of its application
    components. Empty when nothing known is declared (the common case for a
    project without a Node or Python manifest).
    """
    directories = ["."] + sorted(c.path for c in nested_application_components(root))
    found: set[tuple[str, str, str, str]] = set()
    for rel in directories:
        directory = root if rel == "." else root / rel
        try:
            files = {e.name for e in directory.iterdir() if e.is_file()}
        except OSError:
            continue
        for dep in declared_dependencies(directory, files):
            label = FRAMEWORK_TABLE.get(dep.name)
            if label is not None:
                found.add((_rel(rel, dep.manifest), label, dep.name, dep.scope))
    ordered = sorted(found)
    return [
        FrameworkEntry(name=name, label=label, scope=scope, manifest=manifest)
        for manifest, label, name, scope in ordered[:_MAX_ENTRIES]
    ]
