"""Repository structure: what the source of a project actually imports (R14-A).

The package reads the Python files of a project with the standard `ast` module
(it never executes repository code) and builds a deterministic, evidence-carrying
model: modules, imports and the cycles between them. It keeps four things apart
that are easy to confuse: dependencies *declared* in manifests, packages
*installed* in an environment (never read), imports *found in source*, and the
*resolved* module-to-module relationships inside the repository.

Everything here is opt-in (`--structure`); a default report is unchanged. See
`docs/STRUCTURE.md` and `docs/R14A_PLAN.md`.

ساختار مخزن: آنچه سورس پروژه واقعاً import می‌کند؛ بدون اجرای کد مخزن.
"""

from __future__ import annotations

from sarand.structure.build import build_structure
from sarand.structure.model import StructureData

__all__ = ["StructureData", "build_structure"]
