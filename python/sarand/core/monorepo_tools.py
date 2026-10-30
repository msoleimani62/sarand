"""Turborepo and Nx detection (backlog item 1, round R12): declared tasks, read
statically.

Evidence-first audit before any implementation (AGENTS.md 5.87). Read from the
code: `core/node_workspace.py` already recognises `turbo` / `nx` in a root
`test` or `lint` script and then skips running the members (so a Turborepo or
Nx repository is run without duplicates), and the npm/pnpm/Yarn workspace under
it has been detected since 5.50 -- the blocker the older docs gave for leaving
these tools out. What is missing is only the representation: the report never
says that the repository is managed by one of these tools or which tasks it
declares. CONFIRMED gap, in representation only.

Scope, decided with the owner (D-NX1 to D-NX5): **static** -- read configuration
files, never run `turbo`, `nx` or any project code (their plugins execute code
and may use the network). Nothing here imports `subprocess`.

Evidence rules (a file name alone is not proof of a tool):

- **Turborepo**: a `turbo.json` (parsed) or a `turbo.jsonc` (noted, not parsed:
  it may contain comments) at the project root. A `turbo` dependency or a root
  script that calls `turbo` is NOT enough on its own.
- **Nx**: an `nx.json` at the project root. `project.json` files alone are NOT
  enough (the name is generic); they are only read as the declared projects of a
  repository that has `nx.json`.

What is read: Turborepo `tasks` (or the legacy `pipeline`) with `dependsOn`,
`cache`, `persistent` and the number of `outputs`; Nx `targetDefaults`, each
`project.json` (name, declared `targets`) and an explicit `nx.targets` block in a
workspace member's `package.json`. What is **not** shown, and is said in the
report: targets that Nx plugins infer (for example from `package.json` scripts
or tool configuration files), the computed project graph, package-level
`turbo.json` files, `turbo.jsonc` content. Everything is capped; counts say what
was left out.

تشخیص Turborepo و Nx (آیتم ۱ backlog، دور R12): taskهای اعلام‌شده، فقط به‌صورت
ایستا. ممیزی evidence-first: `core/node_workspace.py` از قبل `turbo`/`nx` در
اسکریپت ریشه را می‌شناسد و اعضا را دوباره اجرا نمی‌کند، و workspace زیرین از 5.50
تشخیص داده می‌شود؛ شکاف فقط در نمایش است. هیچ‌چیز اجرا نمی‌شود. فقط وجود
`turbo.json` یا `nx.json` در ریشه شاهد کافی است؛ `project.json` تنها کافی نیست.
targetهایی که پلاگین‌های Nx استنتاج می‌کنند و گراف محاسبه‌شده نشان داده نمی‌شوند.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from sarand.models.results import (
    MonorepoProject,
    MonorepoTask,
    MonorepoToolInfo,
    WorkspaceInfo,
)

MAX_TASKS = 40
MAX_PROJECTS = 60
MAX_TARGETS_PER_PROJECT = 12
# How many `project.json` files are opened at most, and how deep they are looked
# for (real layouts: `apps/web/project.json`, `libs/shared/ui/project.json`).
# حداکثر تعداد project.json که باز می‌شود و عمق جست‌وجو.
_MAX_PROJECT_FILES = 400
_MAX_DEPTH = 6
_MAX_PARSE_BYTES = 1024 * 1024
_MAX_PLUGIN_NAMES = 6
_MAX_DEPENDS_TEXT = 80

# Local copy of the usual prune list, on purpose: AGENTS.md prefers
# self-contained modules over shared private helpers.
# نسخه‌ی محلی فهرست حذف؛ عمداً: AGENTS.md ماژول‌های خودکفا را ترجیح می‌دهد.
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
        ".nx",
        ".turbo",
        "dist",
        "build",
    }
)

_NX_LIMITATION = (
    "Only configuration written in the repository is read: targets that Nx "
    "plugins infer (for example from package.json scripts or tool configuration "
    "files) and the computed project graph need Nx itself and are not shown."
)


def _read_object(path: Path) -> tuple[dict[str, object] | None, str]:
    """A JSON object from `path`, or `(None, short reason)`. Never the content."""
    try:
        if path.is_symlink():
            return None, "is a symbolic link"
        if path.stat().st_size > _MAX_PARSE_BYTES:
            return None, "is too large to read"
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return None, "could not be read"
    except ValueError:
        return None, "is not valid JSON"
    if not isinstance(data, dict):
        return None, "is not a JSON object"
    return data, ""


def _depends(value: object) -> list[str]:
    """`dependsOn` as declared: strings as they are, objects as compact JSON."""
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
        elif isinstance(item, dict):
            text = json.dumps(item, separators=(",", ":"), sort_keys=True)
            result.append(text[:_MAX_DEPENDS_TEXT])
    return result


def _turbo_task(name: str, spec: object) -> MonorepoTask:
    body = spec if isinstance(spec, dict) else {}
    details: list[str] = []
    if body.get("cache") is False:
        details.append("cache off")
    if body.get("persistent") is True:
        details.append("persistent")
    outputs = body.get("outputs")
    if isinstance(outputs, list) and outputs:
        details.append(f"{len(outputs)} output pattern(s)")
    return MonorepoTask(
        name=name, depends_on=_depends(body.get("dependsOn")), detail=", ".join(details)
    )


def _members(workspaces: list[WorkspaceInfo]) -> list[str]:
    seen: list[str] = []
    for workspace in workspaces:
        for member in workspace.members:
            if member.path not in seen:
                seen.append(member.path)
    return seen


def _root_depends_on(root: Path, prefix: str) -> bool:
    manifest, _ = _read_object(root / "package.json")
    if manifest is None:
        return False
    for key in ("dependencies", "devDependencies"):
        table = manifest.get(key)
        if isinstance(table, dict) and any(
            str(name) == prefix or str(name).startswith(prefix + "/") for name in table
        ):
            return True
    return False


def _detect_turbo(
    root: Path, workspaces: list[WorkspaceInfo]
) -> MonorepoToolInfo | None:
    has_json = (root / "turbo.json").is_file()
    has_jsonc = (root / "turbo.jsonc").is_file()
    if not has_json and not has_jsonc:
        return None
    info = MonorepoToolInfo(kind="turbo")
    notes = info.notes
    if has_json:
        info.config_files.append("turbo.json")
        data, problem = _read_object(root / "turbo.json")
        if data is None:
            notes.append(f"turbo.json {problem}; its tasks are not listed.")
        else:
            table = data.get("tasks")
            if not isinstance(table, dict):
                legacy = data.get("pipeline")
                if isinstance(legacy, dict):
                    table = legacy
                    notes.append(
                        "turbo.json uses the legacy `pipeline` key (Turborepo 1.x)."
                    )
            if not isinstance(table, dict):
                notes.append("turbo.json has no `tasks` or `pipeline` object.")
            else:
                info.evidence.append("turbo.json declares tasks")
                info.tasks_total = len(table)
                for name, spec in list(table.items())[:MAX_TASKS]:
                    info.tasks.append(_turbo_task(str(name), spec))
    if has_jsonc:
        info.config_files.append("turbo.jsonc")
        notes.append(
            "turbo.jsonc is present but is not parsed (it may contain comments); "
            "its tasks are not listed."
        )
        info.evidence.append("turbo.jsonc exists")
    if _root_depends_on(root, "turbo"):
        info.evidence.append("package.json depends on turbo")
    package_level = sum(
        1
        for member in _members(workspaces)
        if member != "." and (root / member / "turbo.json").is_file()
    )
    if package_level:
        notes.append(f"{package_level} package-level turbo.json file(s) are not read.")
    return info


def _nx_target(name: str, spec: object) -> MonorepoTask:
    body = spec if isinstance(spec, dict) else {}
    details: list[str] = []
    executor = body.get("executor")
    if isinstance(executor, str) and executor:
        details.append(f"executor {executor}")
    elif isinstance(body.get("command"), str):
        details.append("command")
    if body.get("cache") is True:
        details.append("cache on")
    elif body.get("cache") is False:
        details.append("cache off")
    return MonorepoTask(
        name=name, depends_on=_depends(body.get("dependsOn")), detail=", ".join(details)
    )


def _project_files(root: Path) -> tuple[list[Path], bool]:
    """`project.json` files under `root`, without following symlinks.

    Returns the files (sorted) and whether the scan stopped at the cap.
    """
    found: list[Path] = []
    capped = False
    frontier = [(root, 0)]
    while frontier and not capped:
        directory, depth = frontier.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError:
            continue
        for entry in entries:
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
                is_file = entry.is_file(follow_symlinks=False)
            except OSError:
                continue
            if is_dir:
                if entry.name in _SKIP_DIRS or entry.name.startswith("."):
                    continue
                if depth + 1 <= _MAX_DEPTH:
                    frontier.append((Path(entry.path), depth + 1))
            elif is_file and entry.name == "project.json":
                if len(found) >= _MAX_PROJECT_FILES:
                    capped = True
                    break
                found.append(Path(entry.path))
    return sorted(found), capped


def _targets(table: object) -> tuple[list[MonorepoTask], int]:
    if not isinstance(table, dict):
        return [], 0
    items = list(table.items())
    return [
        _nx_target(str(name), spec) for name, spec in items[:MAX_TARGETS_PER_PROJECT]
    ], len(items)


def _detect_nx(root: Path, workspaces: list[WorkspaceInfo]) -> MonorepoToolInfo | None:
    if not (root / "nx.json").is_file():
        return None
    info = MonorepoToolInfo(kind="nx", config_files=["nx.json"])
    info.evidence.append("nx.json exists")
    info.notes.append(_NX_LIMITATION)
    data, problem = _read_object(root / "nx.json")
    if data is None:
        info.notes.append(f"nx.json {problem}; its settings are not listed.")
    else:
        defaults = data.get("targetDefaults")
        if isinstance(defaults, dict):
            info.tasks_total = len(defaults)
            for name, spec in list(defaults.items())[:MAX_TASKS]:
                info.tasks.append(_nx_target(str(name), spec))
        plugins = data.get("plugins")
        if isinstance(plugins, list) and plugins:
            names = [
                str(item.get("plugin")) if isinstance(item, dict) else str(item)
                for item in plugins
            ]
            shown = ", ".join(names[:_MAX_PLUGIN_NAMES])
            more = len(names) - _MAX_PLUGIN_NAMES
            tail = f" (+{more} more)" if more > 0 else ""
            info.notes.append(
                f"{len(names)} plugin(s) declared ({shown}{tail}); the targets they "
                "infer are not listed."
            )
    if _root_depends_on(root, "nx") or _root_depends_on(root, "@nx"):
        info.evidence.append("package.json depends on nx")

    projects: dict[str, MonorepoProject] = {}
    unreadable = 0
    files, capped = _project_files(root)
    for path in files:
        spec, _ = _read_object(path)
        if spec is None:
            unreadable += 1
            continue
        relative = path.parent.relative_to(root).as_posix() or "."
        declared = spec.get("name")
        name = declared if isinstance(declared, str) and declared else path.parent.name
        targets, total = _targets(spec.get("targets"))
        projects[relative] = MonorepoProject(
            path=relative,
            name=name,
            name_declared=isinstance(declared, str) and bool(declared),
            targets=targets,
            targets_total=total,
        )
    for member in _members(workspaces):
        if member in projects:
            continue
        manifest, _ = _read_object(root / member / "package.json")
        block = manifest.get("nx") if manifest else None
        table = block.get("targets") if isinstance(block, dict) else None
        targets, total = _targets(table)
        if not targets:
            continue
        pkg_name = manifest.get("name") if manifest else None
        projects[member] = MonorepoProject(
            path=member,
            name=pkg_name if isinstance(pkg_name, str) and pkg_name else member,
            name_declared=isinstance(pkg_name, str) and bool(pkg_name),
            targets=targets,
            targets_total=total,
        )
    ordered = [projects[key] for key in sorted(projects)]
    info.projects_total = len(ordered)
    info.projects = ordered[:MAX_PROJECTS]
    if files:
        info.evidence.append(f"{len(files)} project.json file(s)")
    if unreadable:
        info.notes.append(f"{unreadable} project.json file(s) could not be read.")
    if capped:
        info.notes.append(
            f"Only the first {_MAX_PROJECT_FILES} project.json files were read."
        )
    return info


def detect_monorepo_tools(
    root: Path, workspaces: list[WorkspaceInfo]
) -> list[MonorepoToolInfo]:
    """Turborepo and/or Nx declared in `root`, read statically. Empty when none."""
    tools = [_detect_turbo(root, workspaces), _detect_nx(root, workspaces)]
    return [tool for tool in tools if tool is not None]
