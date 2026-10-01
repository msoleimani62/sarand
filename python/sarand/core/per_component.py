"""Run analyzers inside each component of a hybrid project (follow-up
to backlog item 11; the "Root-only detection and analyzer matching"
gap recorded in `docs/BACKLOG_STATUS.md`).

The gap, confirmed on the item-11 hybrid fixture: every analyzer's
`matches(root)` looks at the project root only, so for
`backend/pyproject.toml` + `frontend/package.json` + a root
`docker-compose.yml` only the GitHub Actions, YAML and Markdown
analyzers ran -- no tests, quality or security for either real
component.

Design (kept deliberately small; the `LanguageAnalyzer` protocol that
third-party plugins implement is NOT changed -- every analyzer already
takes the directory to work in as its `root` argument):

1. **Only for hybrid projects.** Runs are planned from the application
   components `core/components.py` already found, so ordinary
   single-root projects behave exactly as before.
2. **Root first, never both.** An analyzer that already matches the
   project root is not run again inside a component: per analyzer it
   either runs once at the root or only inside components. This is
   what rules out duplicate findings -- a root-level ruff/pytest/
   cargo run already recurses into subdirectories and Cargo
   workspace members, so repeating it per component would report the
   same problems twice. A root-level analyzer that does not cascade
   (e.g. a root `npm test`) is a documented limitation, not something
   this module tries to outsmart.
3. **Outermost component wins.** If `a` and `a/b` are both components,
   an analyzer that matched `a` is not run again in `a/b`.
4. **Attribution.** Every result is relabelled `"<component>: <kind>"`
   (and each issue's `source` likewise) so the report shows which
   component a check belongs to. `kind` is display-only downstream
   (health counts, markdown/html headings), verified by grep.
5. **Bounded.** At most `_MAX_TARGETS` components are analysed;
   the rest are reported as one skipped result, never silently
   dropped. Components run one after another (analyzers inside one
   component still run concurrently, as at the root) to keep peak
   memory close to a normal run on low-RAM devices.
6. **Escape hatch.** `SARAND_NO_COMPONENTS=1` disables all of it (an
   environment variable rather than a flag, like `SARAND_SKIP_AUDIT`,
   so the README option-sync test and plugin contract are untouched).

**Deliberately not covered:** the project-wide gitleaks/syft/lockfile
passes (they already walk the whole tree or only look at the root --
the lockfile check stays root-only), non-hybrid projects whose only
code lives below the root, and a root analyzer that does not cascade
into components.

اجرای آنالایزرها داخل هر جزءِ پروژه‌ی ترکیبی (ادامه‌ی آیتم ۱۱؛ همان
شکافِ «تشخیص و match آنالایزر فقط در ریشه» که در BACKLOG_STATUS.md ثبت
شده بود).

شکاف، روی fixture ترکیبی تأیید شد: `matches(root)` همه‌ی آنالایزرها فقط
ریشه را می‌بیند، پس برای `backend/pyproject.toml` + `frontend/
package.json` فقط GitHub Actions، YAML و Markdown اجرا می‌شدند.

طراحی (عمداً کوچک؛ پروتکل `LanguageAnalyzer` که پلاگین‌ها پیاده
می‌کنند تغییر نمی‌کند):
۱. فقط برای پروژه‌ی ترکیبی، از روی اجزای application که
`core/components.py` پیدا کرده.
۲. اول ریشه، هرگز هر دو: آنالایزری که ریشه را match می‌کند دوباره
داخل جزء اجرا نمی‌شود -- این همان چیزی است که finding تکراری را
ممکن نمی‌گذارد.
۳. بیرونی‌ترین جزء برنده است (`a` و `a/b`).
۴. نتایج با پیشوند `"<جزء>: <kind>"` برچسب می‌خورند.
۵. حداکثر `_MAX_TARGETS` جزء، بقیه به‌صورت یک نتیجه‌ی skipped گزارش
می‌شوند و بی‌صدا حذف نمی‌شوند؛ اجزا پشت‌سرهم اجرا می‌شوند.
۶. `SARAND_NO_COMPONENTS=1` همه را خاموش می‌کند.

عمداً پوشش داده نمی‌شود: پاس‌های کل‌پروژه‌ی gitleaks/syft/lockfile،
پروژه‌های غیرترکیبی که کدشان زیر ریشه است، و آنالایزر ریشه‌ای که به
اجزا cascade نمی‌کند.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, replace
from pathlib import Path

from sarand.analyzers.base import LanguageAnalyzer
from sarand.analyzers.registry import (
    run_quality_concurrently,
    run_security_concurrently,
    run_tests_concurrently,
)
from sarand.models.results import CommandResult, ComponentsInfo, Issue
from sarand.progress import status
from sarand.utils.command import make_command_result

logger = logging.getLogger("sarand.per_component")

_MAX_TARGETS = 8
_DISABLE_ENV = "SARAND_NO_COMPONENTS"


@dataclass(frozen=True)
class ComponentTarget:
    """One component directory and the analyzers to run inside it."""

    path: str
    directory: Path
    analyzers: tuple[LanguageAnalyzer, ...]


@dataclass(frozen=True)
class ComponentPlan:
    """Which components to analyse; `omitted` counts those over the cap."""

    targets: tuple[ComponentTarget, ...] = ()
    omitted: int = 0


def _is_inside(path: str, ancestor: str) -> bool:
    return path.startswith(ancestor.rstrip("/") + "/")


def _safe_matches(analyzer: LanguageAnalyzer, directory: Path) -> bool:
    try:
        return bool(analyzer.matches(directory))
    except Exception as exc:  # noqa: BLE001 - a broken plugin must not crash sarand
        logger.warning(
            "Analyzer '%s' failed to match %s: %s", analyzer.name, directory, exc
        )
        return False


def plan_component_runs(
    root: Path,
    components: ComponentsInfo | None,
    all_analyzers: list[LanguageAnalyzer],
    active: list[LanguageAnalyzer],
) -> ComponentPlan:
    """Decide what to run inside which component (see module docstring
    for the rules). Returns an empty plan for a non-hybrid project or
    when `SARAND_NO_COMPONENTS` is set.
    """
    if components is None or os.environ.get(_DISABLE_ENV):
        return ComponentPlan()

    paths = sorted(
        {
            c.path
            for c in components.components
            if c.role == "application" and c.path != "."
        }
    )
    root_ids = {id(a) for a in active}
    claimed: dict[int, list[str]] = {}
    targets: list[ComponentTarget] = []

    for path in paths:
        directory = root / path
        chosen: list[LanguageAnalyzer] = []
        for analyzer in all_analyzers:
            if id(analyzer) in root_ids:
                continue
            if any(_is_inside(path, c) for c in claimed.get(id(analyzer), [])):
                continue
            if _safe_matches(analyzer, directory):
                chosen.append(analyzer)
        for analyzer in chosen:
            claimed.setdefault(id(analyzer), []).append(path)
        if chosen:
            targets.append(ComponentTarget(path, directory, tuple(chosen)))

    return ComponentPlan(
        targets=tuple(targets[:_MAX_TARGETS]),
        omitted=max(0, len(targets) - _MAX_TARGETS),
    )


def _relabel(result: CommandResult, label: str) -> CommandResult:
    def tag(issue: Issue) -> Issue:
        return replace(issue, source=f"{label}: {issue.source}")

    return replace(
        result,
        kind=f"{label}: {result.kind}",
        warnings=[tag(i) for i in result.warnings],
        errors=[tag(i) for i in result.errors],
    )


def _omitted_note(plan: ComponentPlan) -> list[CommandResult]:
    if not plan.omitted:
        return []
    return [
        make_command_result(
            "components",
            0,
            "",
            0.0,
            skipped=True,
            skip_reason=(
                f"{plan.omitted} more component(s) not analysed (limit {_MAX_TARGETS})"
            ),
        )
    ]


async def run_component_tests(plan: ComponentPlan) -> list[CommandResult]:
    """Test suites of every planned component, labelled by component."""
    results: list[CommandResult] = []
    for target in plan.targets:
        names = ", ".join(a.name for a in target.analyzers)
        status(f"Running tests in component {target.path} ({names})...")
        ran = await run_tests_concurrently(target.directory, target.analyzers)
        results.extend(_relabel(r, target.path) for r in ran)
    return results + _omitted_note(plan)


async def run_component_quality(plan: ComponentPlan) -> list[CommandResult]:
    """Quality checks of every planned component, labelled by component."""
    results: list[CommandResult] = []
    for target in plan.targets:
        names = ", ".join(a.name for a in target.analyzers)
        status(f"Running quality checks in component {target.path} ({names})...")
        ran = await run_quality_concurrently(target.directory, target.analyzers)
        results.extend(_relabel(r, target.path) for r in ran)
    return results


async def run_component_security(plan: ComponentPlan) -> list[CommandResult]:
    """Security checks of every planned component, labelled by component."""
    results: list[CommandResult] = []
    for target in plan.targets:
        names = ", ".join(a.name for a in target.analyzers)
        status(f"Running security checks in component {target.path} ({names})...")
        ran = await run_security_concurrently(target.directory, target.analyzers)
        results.extend(_relabel(r, target.path) for r in ran)
    return results
