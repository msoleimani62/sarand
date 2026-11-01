"""Declared frameworks: the Quick Context line "Declared frameworks (from
manifests, not verified in code)" (docs/QUICK_CONTEXT_DESIGN.md, section 4,
decision D-QC2).

Three different things must not be conflated, and this module provides only
the first two:

1. a dependency **declared** in a manifest;
2. a framework **recognised** from a fixed table of dependency names;
3. actual **use** in code -- never claimed here.

Where the names come from: one reader, `declared_dependencies` in
`core/components.py`. R11a (2026-10-30) found Node (`package.json`) and Python
(`pyproject.toml`, `requirements.txt`) already parsed there and reused them;
2026-11-01 added Cargo (`[dependencies]`, `[dev-dependencies]`,
`[build-dependencies]`, `[workspace.dependencies]`) and Go (direct `require`
lines of `go.mod`, `// indirect` skipped, `/vN` suffix dropped) to the same
function, at the owner's request (design file, D-QC8 and D-QC9). There is no
second parser.

Rules:

- Frameworks come only from manifests, never from folder layout or file names.
- Directories read: the project root and the application components found by
  `core/components.py` (same bounded, pruned search), nothing else.
- `scope` is `runtime` for `dependencies` / `[project].dependencies` /
  poetry dependencies / Cargo `[dependencies]` / a direct Go `require`, `dev` for
  `devDependencies` and Cargo `[dev-dependencies]`, and empty for
  `peerDependencies`, `requirements.txt`, Cargo build and workspace dependencies,
  whose meaning is not unambiguous.
- Pure and deterministic: no clock, no environment; output is sorted by
  (manifest, label, name) and capped.

فریم‌ورک‌های اعلام‌شده: فقط از وابستگی‌های مانیفست و یک جدول ثابت، نه از
ساختار پوشه و نه از استفاده‌ی واقعی در کد. Node، Python، Rust و Go خوانده
می‌شوند. خروجی مرتب و محدود است.
"""

from __future__ import annotations

from pathlib import Path

from sarand.core.components import declared_dependencies, nested_application_components
from sarand.models.results import FrameworkEntry

# Bump on every deliberate edit of the table; a snapshot test pins both.
# با هر ویرایش عمدی جدول افزایش می‌یابد؛ یک تست snapshot هر دو را قفل می‌کند.
FRAMEWORK_TABLE_VERSION = 2

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
    # Rust (crate names)
    "actix-web": "Actix Web",
    "axum": "Axum",
    "bevy": "Bevy",
    "clap": "clap",
    "diesel": "Diesel",
    "leptos": "Leptos",
    "rocket": "Rocket",
    "sqlx": "SQLx",
    "tauri": "Tauri",
    "tokio": "Tokio",
    "tonic": "tonic",
    "warp": "warp",
    "yew": "Yew",
    # Go (module paths without a /vN suffix)
    "github.com/gin-gonic/gin": "Gin",
    "github.com/go-chi/chi": "chi",
    "github.com/gofiber/fiber": "Fiber",
    "github.com/gorilla/mux": "gorilla/mux",
    "github.com/labstack/echo": "Echo",
    "github.com/spf13/cobra": "Cobra",
    "google.golang.org/grpc": "gRPC",
    "gorm.io/gorm": "GORM",
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
