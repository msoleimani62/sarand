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

**Nested packages whose analyzer also matches the root (follow-up 2).** The
"root first, never both" rule assumes the root run covers the subdirectories.
That holds for Python (pytest and ruff recurse) but not for three tools whose
root run stops at its own package boundary: `npm test` (Node.js), `go test
./...` (a nested `go.mod` is a separate module) and `cargo test --all` (only
workspace members). In a hybrid project such a nested package was never
checked: on four fixtures (Node root with React `web/` and Express `api/`; Go
root with a nested module; Rust root with a nested non-member crate; plus a
Python control) the plan was empty for all three. Now those three analyzers
are also planned inside nested component directories, unless the root already
covers the directory: a Node workspace member (planned separately), a Cargo
workspace member, or anything under a root with `go.work`. For Node the root
`test` / `lint` fan-out and a root ESLint configuration still drop that phase
(same rules as for workspace members); `security` stays, since a separate
package has its own lockfile. A directory can therefore hold two targets with
different phases; each analyzer still runs at most once per phase.

**Non-hybrid projects (follow-up 2, second half).** `detect_components`
returns `None` for a project that is not hybrid, so the plan used to be
empty and a standalone nested Node.js / Go / Rust package was never
checked (confirmed on five fixtures: Node root + `tools/cli`, Node root +
two nested packages, Go root + nested module, Rust root + nested crate,
and a root with only a `Makefile` + two Node packages). The planner now
asks `nested_application_components` for the packages below the root and
plans them exactly like the components of a hybrid project (5.56): an
analyzer that does not match the root runs inside each nested package, one
that does is not repeated, except the three non-recursive ones with the
coverage rules above (workspace members, Cargo members, `go.work`). A root
that matches no analyzer (a `Makefile` plus `services/a` and `services/b`)
therefore gets Python or Maven runs in each service. Nothing else changes:
no component view in the report, and Python stays covered by the root run
when the root has its own Python project. `examples/`, `tests/`,
`fixtures/`, `vendor/` and `node_modules` are never scanned.

پروژه‌ی غیرهیبرید: `detect_components` برایش `None` می‌دهد و برنامه خالی
بود؛ حالا آنالایزرها در بسته‌های
تو در تو برنامه‌ریزی می‌شوند، با همان قاعده‌ی پوشش‌داده‌شده‌ها. (۵.۵۶:
همین قاعده‌ی پروژه‌ی هیبرید برای همه‌ی آنالایزرها اعمال می‌شود؛ آنالایزری که
ریشه را match نمی‌کند داخل بسته‌ی تو در تو اجرا می‌شود.) بخش اجزا در
گزارش اضافه نمی‌شود.

بسته‌های تو در تو که آنالایزرشان ریشه را هم match می‌کند (شکاف ۲): برای
Node.js (`npm test`)، Go (`./...` از مرز ماژول رد نمی‌شود) و Rust (فقط اعضای
workspace) اجرای ریشه به زیرپوشه نمی‌رسد؛ پس در پروژه‌ی ترکیبی این سه آنالایزر
داخل پوشه‌ی اجزای تو در تو هم اجرا می‌شوند، مگر ریشه خودش آن پوشه را پوشش
بدهد (عضو workspace، یا `go.work`). Python مثل قبل پوشش‌داده‌شده حساب می‌شود.

**Workspace members (npm / Yarn / pnpm, follow-up 1 of the backlog status).**
`core/node_workspace.py` detects these workspaces. `npm test` at the root
only runs the root's script, so the members are tested and linted by running
the Node.js analyzer inside each member directory (labelled
`<member>: npm test`). This is the one deliberate exception to "root first,
never both", and it is guarded against duplicates:

- a root `test` / `lint` script that already fans out (`--workspaces`,
  `pnpm -r`, `turbo`, `nx`, `lerna`, ...) drops that phase for the members;
- a root ESLint configuration drops member linting (`eslint .` at the root
  already recurses into the packages);
- `npm audit` is never run per member (the root lockfile audit covers the
  whole workspace);
- when a member directory is also a hybrid component, the two plans are
  merged into one target, so the analyzer runs once;
- at most 20 members run (the rest become one skipped result with the true
  count), one after another.

اجرای اعضای workspace (npm / Yarn / pnpm): `npm test` ریشه فقط اسکریپت
خودِ ریشه را اجرا می‌کند، پس آنالایزر Node.js داخل پوشه‌ی هر عضو اجرا می‌شود.
برای جلوگیری از تکرار: اسکریپت ریشه‌ای که خودش cascade می‌کند، کانفیگ ESLint
ریشه، و `npm audit` (که فقط یک بار در ریشه اجرا می‌شود) در نظر گرفته شده؛
تا ۲۰ عضو.

**Deliberately not covered:** the project-wide gitleaks/syft/lockfile
passes (they already walk the whole tree or only look at the root --
the lockfile check stays root-only), and a root analyzer that does not cascade
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
from sarand.analyzers.go_analyzer import GoAnalyzer
from sarand.analyzers.node_analyzer import NodeAnalyzer, _has_eslint_config
from sarand.analyzers.registry import (
    run_quality_concurrently,
    run_security_concurrently,
    run_tests_concurrently,
)
from sarand.analyzers.rust_analyzer import RustAnalyzer
from sarand.core.components import nested_application_components
from sarand.core.node_workspace import root_script_cascades
from sarand.models.results import (
    CommandResult,
    ComponentsInfo,
    Issue,
    WorkspaceInfo,
)
from sarand.progress import status
from sarand.utils.command import make_command_result

logger = logging.getLogger("sarand.per_component")

_MAX_TARGETS = 8
_MAX_MEMBER_TARGETS = 20
_ALL_PHASES = frozenset({"tests", "quality", "security"})
_NODE_WORKSPACE_KINDS = frozenset({"npm", "yarn", "pnpm"})
_DISABLE_ENV = "SARAND_NO_COMPONENTS"


@dataclass(frozen=True)
class ComponentTarget:
    """One component directory and the analyzers to run inside it."""

    path: str
    directory: Path
    analyzers: tuple[LanguageAnalyzer, ...]
    phases: frozenset[str] = _ALL_PHASES


@dataclass(frozen=True)
class ComponentPlan:
    """Which components to analyse. `omitted` counts hybrid components and
    `omitted_members` workspace members left out by the caps."""

    targets: tuple[ComponentTarget, ...] = ()
    omitted: int = 0
    omitted_members: int = 0


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


_NON_RECURSIVE = (NodeAnalyzer, GoAnalyzer, RustAnalyzer)


def _covered_paths(
    analyzer: LanguageAnalyzer, root: Path, workspace: WorkspaceInfo | None
) -> set[str] | None:
    """Directories the root run of `analyzer` already covers. `None` means
    "everything below the root" (Go with `go.work`)."""
    members = {m.path for m in workspace.members} if workspace else set()
    kind = workspace.kind if workspace else ""
    if isinstance(analyzer, NodeAnalyzer):
        return members if kind in _NODE_WORKSPACE_KINDS else set()
    if isinstance(analyzer, RustAnalyzer):
        return members if kind == "cargo" else set()
    if isinstance(analyzer, GoAnalyzer):
        return None if (root / "go.work").exists() else set()
    return set()


def _node_phases(root: Path) -> frozenset[str]:
    """Phases of a nested Node package that the root does not already run."""
    phases = {"security"}
    if not root_script_cascades(root, "test"):
        phases.add("tests")
    if not root_script_cascades(root, "lint") and not _has_eslint_config(root):
        phases.add("quality")
    return frozenset(phases)


def _component_targets(
    root: Path,
    components: ComponentsInfo | None,
    all_analyzers: list[LanguageAnalyzer],
    active: list[LanguageAnalyzer],
    workspace: WorkspaceInfo | None = None,
) -> list[ComponentTarget]:
    """Components of a hybrid project, or the nested packages of a project
    that is not hybrid: analyzers that do not match the root, plus the
    three whose root run does not reach nested packages."""
    if components is None:
        return []
    paths = sorted(
        {
            c.path
            for c in components.components
            if c.role == "application" and c.path != "."
        }
    )
    root_ids = {id(a) for a in active}
    node_members = (
        {m.path for m in workspace.members}
        if workspace is not None and workspace.kind in _NODE_WORKSPACE_KINDS
        else set()
    )
    claimed: dict[int, list[str]] = {}
    targets: list[ComponentTarget] = []

    for path in paths:
        directory = root / path
        plain: list[LanguageAnalyzer] = []
        nested_node: list[LanguageAnalyzer] = []
        for analyzer in all_analyzers:
            on_root = id(analyzer) in root_ids
            if isinstance(analyzer, NodeAnalyzer) and path in node_members:
                continue  # planned as a workspace member, with its own phases
            if on_root:
                if not isinstance(analyzer, _NON_RECURSIVE):
                    continue
                covered = _covered_paths(analyzer, root, workspace)
                if covered is None or path in covered:
                    continue
            if any(_is_inside(path, c) for c in claimed.get(id(analyzer), [])):
                continue
            if not _safe_matches(analyzer, directory):
                continue
            if on_root and isinstance(analyzer, NodeAnalyzer):
                nested_node.append(analyzer)
            else:
                plain.append(analyzer)
        for analyzer in (*plain, *nested_node):
            claimed.setdefault(id(analyzer), []).append(path)
        if plain:
            targets.append(ComponentTarget(path, directory, tuple(plain)))
        if nested_node:
            targets.append(
                ComponentTarget(path, directory, tuple(nested_node), _node_phases(root))
            )
    return targets


def _workspace_targets(
    root: Path,
    workspace: WorkspaceInfo | None,
    all_analyzers: list[LanguageAnalyzer],
) -> list[ComponentTarget]:
    """npm / Yarn / pnpm workspace members: the Node.js analyzer's tests and
    lint inside each member, minus whatever the root already fans out."""
    if workspace is None or workspace.kind not in _NODE_WORKSPACE_KINDS:
        return []
    node = next((a for a in all_analyzers if isinstance(a, NodeAnalyzer)), None)
    if node is None:
        return []
    phases: set[str] = set()
    if not root_script_cascades(root, "test"):
        phases.add("tests")
    if not root_script_cascades(root, "lint") and not _has_eslint_config(root):
        phases.add("quality")
    if not phases:
        return []
    return [
        ComponentTarget(m.path, root / m.path, (node,), frozenset(phases))
        for m in workspace.members
        if m.path != "." and _safe_matches(node, root / m.path)
    ]


def _merge(
    members: list[ComponentTarget], components: list[ComponentTarget]
) -> list[ComponentTarget]:
    """One target per (directory, phases): a member that is also a hybrid
    component keeps a single run per analyzer and phase."""
    merged: dict[tuple[str, frozenset[str]], ComponentTarget] = {}
    for target in [*members, *components]:
        key = (target.path, target.phases)
        existing = merged.get(key)
        if existing is None:
            merged[key] = target
            continue
        seen = {id(a) for a in existing.analyzers}
        extra = tuple(a for a in target.analyzers if id(a) not in seen)
        merged[key] = ComponentTarget(
            target.path,
            target.directory,
            (*existing.analyzers, *extra),
            target.phases,
        )
    return list(merged.values())


def _cap_paths(
    targets: list[ComponentTarget], limit: int
) -> tuple[list[ComponentTarget], int]:
    """Keep the targets of the first `limit` distinct directories and count
    the directories left out."""
    order: list[str] = []
    for target in targets:
        if target.path not in order:
            order.append(target.path)
    kept = set(order[:limit])
    return [t for t in targets if t.path in kept], max(0, len(order) - limit)


def plan_component_runs(
    root: Path,
    components: ComponentsInfo | None,
    all_analyzers: list[LanguageAnalyzer],
    active: list[LanguageAnalyzer],
    workspace: WorkspaceInfo | None = None,
) -> ComponentPlan:
    """Decide what to run inside which directory (see the module docstring
    for the rules). Returns an empty plan for a project with no nested
    package that needs a run (neither hybrid nor a Node workspace), or
    when `SARAND_NO_COMPONENTS` is set.
    """
    if os.environ.get(_DISABLE_ENV):
        return ComponentPlan()

    # Not hybrid: plan the nested packages like hybrid components.
    # غیرهیبرید: بسته‌های تو در تو مثل اجزای هیبرید برنامه‌ریزی می‌شوند.
    if components is None:
        nested = nested_application_components(root)
        if nested:
            components = ComponentsInfo(components=nested, total_components=len(nested))

    members = _workspace_targets(root, workspace, all_analyzers)
    hybrid = _component_targets(root, components, all_analyzers, active, workspace)
    kept_members, omitted_members = _cap_paths(members, _MAX_MEMBER_TARGETS)
    kept_hybrid, omitted = _cap_paths(hybrid, _MAX_TARGETS)
    return ComponentPlan(
        targets=tuple(_merge(kept_members, kept_hybrid)),
        omitted=omitted,
        omitted_members=omitted_members,
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


def _omitted_notes(plan: ComponentPlan) -> list[CommandResult]:
    notes: list[CommandResult] = []
    if plan.omitted:
        notes.append(
            make_command_result(
                "components",
                0,
                "",
                0.0,
                skipped=True,
                skip_reason=(
                    f"{plan.omitted} more component(s) not analysed "
                    f"(limit {_MAX_TARGETS})"
                ),
            )
        )
    if plan.omitted_members:
        notes.append(
            make_command_result(
                "workspace members",
                0,
                "",
                0.0,
                skipped=True,
                skip_reason=(
                    f"{plan.omitted_members} more workspace member(s) not "
                    f"analysed (limit {_MAX_MEMBER_TARGETS})"
                ),
            )
        )
    return notes


async def run_component_tests(plan: ComponentPlan) -> list[CommandResult]:
    """Test suites of every planned directory, labelled by directory."""
    results: list[CommandResult] = []
    for target in plan.targets:
        if "tests" not in target.phases:
            continue
        names = ", ".join(a.name for a in target.analyzers)
        status(f"Running tests in {target.path} ({names})...")
        ran = await run_tests_concurrently(target.directory, target.analyzers)
        results.extend(_relabel(r, target.path) for r in ran)
    return results + _omitted_notes(plan)


async def run_component_quality(plan: ComponentPlan) -> list[CommandResult]:
    """Quality checks of every planned directory, labelled by directory."""
    results: list[CommandResult] = []
    for target in plan.targets:
        if "quality" not in target.phases:
            continue
        names = ", ".join(a.name for a in target.analyzers)
        status(f"Running quality checks in {target.path} ({names})...")
        ran = await run_quality_concurrently(target.directory, target.analyzers)
        results.extend(_relabel(r, target.path) for r in ran)
    return results


async def run_component_security(plan: ComponentPlan) -> list[CommandResult]:
    """Security checks of every planned directory, labelled by directory.
    Workspace members never have the `security` phase (the root lockfile
    audit covers them)."""
    results: list[CommandResult] = []
    for target in plan.targets:
        if "security" not in target.phases:
            continue
        names = ", ".join(a.name for a in target.analyzers)
        status(f"Running security checks in {target.path} ({names})...")
        ran = await run_security_concurrently(target.directory, target.analyzers)
        results.extend(_relabel(r, target.path) for r in ran)
    return results
