"""npm, Yarn and pnpm workspace detection (backlog item 8, next phase).

Evidence-first audit (a fixture per model, run against the code as of
v0.6.12 -- see `core/workspace.py` for the earlier Cargo-only audit):

- **npm workspaces** and **Yarn workspaces** (`"workspaces"` in the root
  `package.json`, either an array or Yarn's `{"packages": [...]}`):
  `detect_workspace` returned `None`; the project was reported as plain
  Node.js, `NodeAnalyzer` ran `npm test` at the root only, and no
  workspace package got tests or lint. CONFIRMED execution gap, because
  `npm test` at the root runs the *root's* script and does not cascade.
- **pnpm workspaces** (`pnpm-workspace.yaml`): same result, plus the
  report said `build system: npm` for a pnpm repo.
- **pnpm workspace without a root `package.json`**: no marker file, so
  `NodeAnalyzer.matches` was false and nothing ran at all.
- Per-component execution (`core/per_component.py`) did not help: it only
  runs for *hybrid* projects, and a monorepo of same-kind packages is not
  one; and it never re-runs an analyzer that matches the root.

Scope of this round, per the backlog ("do not implement every monorepo
ecosystem in one change"): the three Node models above, nothing else.

- Detection: `detect_node_workspace` resolves the member packages from
  the declared globs (`*`, `**`, `?`, and pnpm/Yarn `!negations`), bounded
  to 6 directory levels and never entering `node_modules`, VCS or build
  directories. The root is not a member unless a glob lists it. Kind is
  `pnpm` when `pnpm-workspace.yaml` is valid, else `yarn` when there is a
  `yarn.lock` or `packageManager` says yarn, else `npm`. pnpm wins when
  both declarations exist, as in pnpm itself.
- Duplicate prevention: `root_script_cascades` recognises a root `test` or
  `lint` script that already fans out (`--workspaces`, `-ws`,
  `pnpm -r/--filter`, `yarn workspaces`, `turbo`, `nx`, `lerna`). When it
  does, running the members again would report everything twice, so
  `core/per_component.py` skips that phase for the members.

**Deliberately not covered:** a repo with both a Cargo workspace and a Node
workspace (Cargo is detected first and only one `WorkspaceInfo` exists),
Lerna/Rush/Bolt without one of the declarations above, Nx/Turborepo task
graphs, per-package-manager commands (members are still tested with
`npm test`), `npm audit` per member (the root lockfile audit already covers
the whole workspace), and relationships between member packages.

تشخیص workspaceهای npm، Yarn و pnpm (آیتم ۸ backlog، فاز بعدی).

ممیزی روی fixture هر مدل نشان داد که `detect_workspace` برای هر سه
`None` می‌داد و `npm test` فقط در ریشه اجرا می‌شد و به بسته‌های workspace
نمی‌رسید؛ برای pnpm بدون `package.json` ریشه اصلاً هیچ چیز اجرا نمی‌شد.

اسکوپ: فقط همین سه مدل. اعضا از globهای اعلام‌شده پیدا می‌شوند (با
`**` و `!` برای حذف، تا ۶ سطح، بدون ورود به `node_modules`). برای جلوگیری
از اجرای تکراری، اگر اسکریپت `test` یا `lint` ریشه خودش به اعضا cascade کند
(`--workspaces`، `pnpm -r`، `turbo`، `nx`، `lerna`، ...) آن فاز برای اعضا
اجرا نمی‌شود.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml as _yaml

from sarand.models.results import WorkspaceInfo, WorkspaceMember

_MAX_DEPTH = 6
_MAX_PARSE_BYTES = 1024 * 1024

# Directories that never contain workspace members: third-party code,
# VCS data and build output.
# پوشه‌هایی که هرگز عضو workspace نیستند: کد شخص‌ثالث، VCS و خروجی build.
_SKIP_DIRS = frozenset(
    {
        "node_modules",
        ".git",
        ".venv",
        "venv",
        "target",
        "dist",
        "build",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
    }
)

# Root scripts that already fan out over the workspace packages. Matching
# any of these means a member run would repeat what the root run does.
# `pnpm -w` (= the workspace root only) is deliberately NOT here.
# اسکریپت‌های ریشه‌ای که خودشان روی بسته‌های workspace پخش می‌شوند.
_CASCADE = re.compile(
    r"(--workspaces\b|--workspace\b|(?<!\S)-ws\b"
    r"|\bpnpm\s+(?:run\s+)?(?:-r\b|--recursive\b|-F\b|--filter\b)"
    r"|\byarn\s+workspaces\b|\bturbo\b|\bnx\b|\blerna\b|\bwireit\b)"
)


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        if path.stat().st_size > _MAX_PARSE_BYTES:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [v.strip() for v in value if isinstance(v, str) and v.strip()]


def _normalise(pattern: str) -> str:
    pattern = pattern.replace("\\", "/")
    while pattern.startswith("./"):
        pattern = pattern[2:]
    return pattern.strip("/")


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """`*` = one path segment's characters, `**` = anything, `?` = one
    character. A trailing `/**` also matches the directory itself."""
    out: list[str] = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif char == "*":
            out.append("[^/]*")
            i += 1
        elif char == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(char))
            i += 1
    body = "".join(out)
    if body.endswith("/.*"):
        body = body[: -len("/.*")] + "(?:/.*)?"
    return re.compile(f"^{body}$")


def _declared_patterns(root: Path) -> tuple[str, list[str]] | None:
    """(kind, patterns) from the root declarations, or None."""
    pnpm_file = root / "pnpm-workspace.yaml"
    manifest = _read_json(root / "package.json")

    if pnpm_file.is_file():
        try:
            if pnpm_file.stat().st_size <= _MAX_PARSE_BYTES:
                loaded = _yaml.safe_load(pnpm_file.read_text(encoding="utf-8"))
            else:
                loaded = None
        except (OSError, ValueError, _yaml.YAMLError):
            loaded = None
        if isinstance(loaded, dict):
            patterns = _string_list(loaded.get("packages"))
            if patterns:
                return "pnpm", patterns

    if manifest is None:
        return None
    declared = manifest.get("workspaces")
    if isinstance(declared, dict):
        declared = declared.get("packages")
    patterns = _string_list(declared)
    if not patterns:
        return None
    package_manager = manifest.get("packageManager")
    if (root / "yarn.lock").is_file() or (
        isinstance(package_manager, str) and package_manager.startswith("yarn")
    ):
        return "yarn", patterns
    return "npm", patterns


def _package_dirs(root: Path) -> list[str]:
    """Relative POSIX paths of every directory with a `package.json`,
    bounded by depth and never entering `_SKIP_DIRS`; symlinks are not
    followed."""
    found: list[str] = []
    frontier: list[tuple[Path, int]] = [(root, 0)]
    while frontier:
        current, depth = frontier.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir() and entry.name not in _SKIP_DIRS and depth < _MAX_DEPTH:
                if (entry / "package.json").is_file():
                    found.append(entry.relative_to(root).as_posix())
                frontier.append((entry, depth + 1))
    return found


def _member_name(member_dir: Path) -> str:
    manifest = _read_json(member_dir / "package.json")
    name = manifest.get("name") if manifest else None
    return name if isinstance(name, str) and name else member_dir.name


def detect_node_workspace(root: Path) -> WorkspaceInfo | None:
    """The npm/Yarn/pnpm workspace rooted at `root`, or `None`."""
    declared = _declared_patterns(root)
    if declared is None:
        return None
    kind, raw = declared

    include = [_glob_to_regex(_normalise(p)) for p in raw if not p.startswith("!")]
    negated = [_normalise(p[1:]) for p in raw if p.startswith("!")]
    exclude = [_glob_to_regex(p) for p in negated]

    members = sorted(
        rel
        for rel in _package_dirs(root)
        if any(rx.match(rel) for rx in include)
        and not any(rx.match(rel) for rx in exclude)
    )
    return WorkspaceInfo(
        kind=kind,
        members=[
            WorkspaceMember(path=rel, name=_member_name(root / rel)) for rel in members
        ],
        exclude_patterns=negated,
    )


def root_script_cascades(root: Path, script: str) -> bool:
    """True when the root `package.json` script `script` already runs over
    the workspace packages (so running the members would duplicate it)."""
    manifest = _read_json(root / "package.json")
    scripts = manifest.get("scripts") if manifest else None
    if not isinstance(scripts, dict):
        return False
    body = scripts.get(script)
    return isinstance(body, str) and _CASCADE.search(body) is not None
