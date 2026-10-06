"""Let the component view correct the "Detected Project" section of a
hybrid repository (backlog status follow-up 3: `detect_project()` is
root-only).

Evidence (a hybrid fixture: `backend/pyproject.toml`, `frontend/package.json`,
a root `docker-compose.yml` and `Makefile`; run against v0.6.13):

- With only a `Makefile` at the root, "Detected Project" said primary
  language `Generic`, type `unknown`, languages `['Generic']`. Neither
  Python nor Node.js appeared, although `Project Components` and Quick
  Context two sections later listed both.
- With a root `pyproject.toml` added, it said `Python` but listed
  `['Python', 'Generic']`: the frontend's Node.js was missing from "All
  detected languages".

`detect_project()` itself stays root-only on purpose: it is also the
function that decides which analyzers match the root, and changing what it
reports there would change what runs. Instead `refine_detection` takes its
result plus the component view (`core/components.py`) and corrects only the
*description*:

- **Only for hybrid projects** (the component view exists). Anything else
  is returned unchanged, the very same object.
- **Languages:** the application components' languages are added after the
  root's, in order, without duplicates; the placeholder `Generic` is dropped
  once a real language is known.
- **Primary language:** a real root language is kept (the root's own
  marker is the strongest evidence). When the root has none (`Generic` or
  `Unknown`), no component is arbitrarily promoted: the label lists the
  languages, e.g. `Python + Node.js` (at most 3, then `+N more`), and the
  type says what each part is, e.g. `hybrid: backend (Python), frontend
  (Node.js)` (at most 4 parts). The build system is left alone (`make` stays
  `make`).
- **Markers:** the component markers are appended as `path/marker`
  (`backend/pyproject.toml`) so every language claim is traceable, capped at
  20.

Not covered: choosing a "main" component, entry points of components, and
changing which analyzers match.

اجازه می‌دهد نمای اجزا بخش «Detected Project» را در مخزن ترکیبی اصلاح کند
(شکاف ۳ فایل وضعیت backlog: `detect_project()` فقط ریشه را می‌بیند).

شواهد: روی fixture ترکیبی، با فقط `Makefile` در ریشه، گزارش «زبان اصلی
Generic، نوع unknown» می‌گفت و نه Python دیده می‌شد نه Node.js؛ با افزودن
`pyproject.toml` ریشه، زبان‌ها `['Python', 'Generic']` بود و Node.js فرانت‌اند
جا افتاده بود. `detect_project()` عمداً ریشه‌محور می‌ماند (تعیین‌کننده‌ی
آنالایزرهای ریشه هم هست)؛ فقط *توصیف* اصلاح می‌شود، آن هم برای پروژه‌ی
ترکیبی: زبان اجزا اضافه می‌شود، `Generic` حذف می‌شود، زبان اصلیِ واقعیِ ریشه
حفظ می‌شود و اگر ریشه زبانی ندارد هیچ جزئی دلبخواهی ارتقا نمی‌یابد.
"""

from __future__ import annotations

from dataclasses import replace

from sarand.models.results import Component, ComponentsInfo, ProjectDetection

_PLACEHOLDERS = frozenset({"Generic", "Unknown"})
_MAX_LABEL_LANGUAGES = 3
_MAX_TYPE_PARTS = 4
_MAX_MARKERS = 20


def _applications(components: ComponentsInfo) -> list[Component]:
    return [c for c in components.components if c.role == "application"]


def _label(languages: list[str]) -> str:
    shown = " + ".join(languages[:_MAX_LABEL_LANGUAGES])
    extra = len(languages) - _MAX_LABEL_LANGUAGES
    return f"{shown} +{extra} more" if extra > 0 else shown


def _type_description(apps: list[Component]) -> str:
    parts = []
    for app in apps[:_MAX_TYPE_PARTS]:
        name = app.kind or app.path
        language = app.languages[0] if app.languages else "?"
        parts.append(f"{name} ({language})")
    extra = len(apps) - _MAX_TYPE_PARTS
    tail = f", +{extra} more" if extra > 0 else ""
    return "hybrid: " + ", ".join(parts) + tail


def refine_detection(
    detection: ProjectDetection, components: ComponentsInfo | None
) -> ProjectDetection:
    """`detection` corrected for a hybrid project; the same object otherwise."""
    if components is None:
        return detection
    apps = _applications(components)
    if not apps:
        return detection

    languages = [lang for lang in detection.languages if lang not in _PLACEHOLDERS]
    for app in apps:
        for language in app.languages:
            if language not in languages:
                languages.append(language)
    if not languages:
        return detection

    markers = list(detection.markers_found)
    for app in apps:
        for marker in app.evidence:
            if len(markers) >= len(detection.markers_found) + _MAX_MARKERS:
                break
            name = marker if app.path == "." else f"{app.path}/{marker}"
            if name not in markers:
                markers.append(name)

    primary = detection.primary_language
    project_type = detection.project_type
    if primary in _PLACEHOLDERS:
        primary = _label(languages)
        project_type = _type_description(apps)

    return replace(
        detection,
        languages=languages,
        primary_language=primary,
        project_type=project_type,
        markers_found=markers,
    )
