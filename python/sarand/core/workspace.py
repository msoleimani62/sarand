"""Monorepo/workspace structure detection (backlog item 8, "Monorepo /
Workspace architecture").

Evidence-first audit before any implementation (item 8.1's own required
first step) -- current state of the eight workspace models the backlog
document names, checked directly against this repository's source, not
assumed:

- **Cargo workspace** (`[workspace]` in `Cargo.toml`) -- CONFIRMED gap,
  zero representation. `RustAnalyzer.matches()` only checks that *a*
  `Cargo.toml` exists; it never distinguishes a workspace root from a
  single-package crate. Note this is a gap in *representation*, not
  necessarily in *test execution*: `cargo test --all` (what
  `rust_analyzer.py` already runs) is workspace-aware by Cargo's own
  design and already exercises every member crate. **Implemented this
  round** -- see `detect_workspace` below.
- **npm workspaces** (`"workspaces"` in `package.json`) -- CONFIRMED
  gap, and unlike Cargo, also a gap in *execution*: `npm test` at the
  root only runs the root package's own `test` script; it does not
  cascade into workspace packages unless that script itself opts in
  (`npm test --workspaces`) or a task runner like Turborepo/Nx is
  driving it. `node_analyzer.py` has no awareness of either. Not
  implemented this round.
- **pnpm workspace** (`pnpm-workspace.yaml`) -- CONFIRMED gap, and a
  deeper one: this file is not even in `constants.py`'s
  `PROJECT_MARKERS`, so a pnpm-workspace-only repo (no root
  `package.json`) is not detected as a Node project at all. Not
  implemented this round.
- **Yarn workspaces** (`"workspaces"` in `package.json`, same file and
  same execution caveat as npm) -- CONFIRMED gap, not implemented this
  round.
- **Gradle multi-project** (`include(...)` in `settings.gradle[.kts]`)
  -- like Cargo, `./gradlew test` from the root already builds and
  tests every subproject via Gradle's own multi-project model, so this
  is a representation-only gap, not an execution one. Not implemented
  this round (Cargo was chosen as the one ecosystem for this round's
  minimal scope, per item 8's own "do not implement every monorepo
  ecosystem in one change").
- **Maven multi-module** (`<modules>` in a parent `pom.xml`) -- same
  shape as Gradle: `mvn test` from the reactor root already covers
  every module. Representation-only gap. Not implemented this round.
- **Bazel** (`WORKSPACE`/`MODULE.bazel`) -- OUT OF SCOPE, not merely
  deferred: sarand has no Bazel analyzer at all in the 40-analyzer
  roster (`registry.py`), so there is no existing test/quality/security
  execution to represent workspace structure *for* yet. Adding Bazel
  support is a new-analyzer backlog item in its own right, prior to
  anything workspace-shaped.
- **Nx / Turborepo** (`nx.json` / `turbo.json`) -- OUT OF SCOPE for the
  same reason as Bazel, one level removed: both layer on top of an
  npm/pnpm/Yarn workspace, so they need that base workspace detection
  built first (see above, also not implemented this round).

This module's public surface (`detect_workspace`) is deliberately
generic, not `detect_cargo_workspace`, so the *next* ecosystem
(npm/pnpm/Yarn workspaces are the natural next pick, per the audit
above) is an additional internal check added to the same function
later, not a new call site wired into `cli.py` every time.

تشخیص ساختار monorepo/workspace (آیتم ۸ backlog، «معماری Monorepo /
Workspace»).

ممیزیِ evidence-first پیش از هرگونه پیاده‌سازی (اولین گام الزامیِ خودِ
آیتم ۸.۱) -- وضعیت فعلیِ هشت مدل workspace که سند backlog نام می‌برد،
مستقیماً روی سورس همین مخزن چک شده، نه فرض‌شده -- برای جزئیات به متن
انگلیسیِ بالا نگاه کنید. خلاصه: Cargo workspace این دور پیاده‌سازی شد؛
npm/pnpm/Yarn workspaces و Gradle multi-project و Maven multi-module
شکاف تأییدشده‌اند ولی این دور پیاده نشدند؛ Bazel و Nx/Turborepo کاملاً
خارج از scope‌اند چون sarand اصلاً آنالایزر Bazel ندارد.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sarand.models.results import WorkspaceInfo, WorkspaceMember

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10: same parser, packaged separately
    import tomli as tomllib


def detect_workspace(root: Path) -> WorkspaceInfo | None:
    """Try every workspace model this module currently knows how to
    detect, in order, and return the first match (or `None`). Today
    that is Cargo alone -- see the module docstring for the audit of
    what else is and isn't implemented yet.
    """
    return _detect_cargo_workspace(root)


def _detect_cargo_workspace(root: Path) -> WorkspaceInfo | None:
    manifest_path = root / "Cargo.toml"
    if not manifest_path.is_file():
        return None
    try:
        manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        # Not this detector's job to report a malformed Cargo.toml --
        # RustAnalyzer's own `cargo test`/`cargo fmt` runs will surface
        # that loudly enough. Just don't claim a workspace exists.
        #
        # گزارشِ یک Cargo.toml بدشکل کار این تشخیص‌دهنده نیست -- اجرای
        # خودِ `cargo test`/`cargo fmt` در RustAnalyzer به‌اندازه‌ی کافی
        # بلند آن را نشان می‌دهد. فقط ادعا نکن workspace‌ای وجود دارد.
        return None

    workspace_table = manifest.get("workspace")
    if not isinstance(workspace_table, dict):
        return None

    exclude_patterns = [
        p for p in workspace_table.get("exclude", []) if isinstance(p, str)
    ]
    excluded_dirs = {
        resolved
        for pattern in exclude_patterns
        for resolved in _resolve_member_pattern(root, pattern)
    }

    member_dirs: set[Path] = set()
    for pattern in workspace_table.get("members", []):
        if isinstance(pattern, str):
            member_dirs.update(_resolve_member_pattern(root, pattern))
    member_dirs -= excluded_dirs

    # A root `Cargo.toml` with both `[workspace]` and its own
    # `[package]` counts the root itself as a member too.
    # `Cargo.toml` ریشه‌ای که هم `[workspace]` دارد هم `[package]`
    # خودش، خودِ ریشه را هم به‌عنوان یک عضو حساب می‌کند.
    if isinstance(manifest.get("package"), dict):
        member_dirs.add(root)

    members = sorted(
        (
            WorkspaceMember(
                path=_relative_posix(root, member_dir),
                name=_member_package_name(member_dir),
            )
            for member_dir in member_dirs
        ),
        key=lambda m: m.path,
    )
    return WorkspaceInfo(
        kind="cargo", members=members, exclude_patterns=exclude_patterns
    )


def _resolve_member_pattern(root: Path, pattern: str) -> list[Path]:
    """A `members`/`exclude` entry is a path or a glob (Cargo allows
    both, e.g. `"crates/*"`); only directories that actually contain a
    `Cargo.toml` count as real members -- a glob can otherwise sweep up
    a non-crate directory that merely matches the pattern.
    """
    candidates = [root / pattern] if "*" not in pattern else list(root.glob(pattern))
    return [c for c in candidates if c.is_dir() and (c / "Cargo.toml").is_file()]


def _member_package_name(member_dir: Path) -> str:
    manifest_path = member_dir / "Cargo.toml"
    try:
        manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
        name = manifest.get("package", {}).get("name")
        if isinstance(name, str) and name:
            return name
    except (OSError, tomllib.TOMLDecodeError, AttributeError):
        pass
    return member_dir.name


def _relative_posix(root: Path, path: Path) -> str:
    if path == root:
        return "."
    return path.relative_to(root).as_posix()
