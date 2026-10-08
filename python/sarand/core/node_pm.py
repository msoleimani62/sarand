"""Which package manager a Node.js project uses, and what that means for
the report and for `npm audit` (backlog status follow-up: package-manager
awareness; AGENTS.md section 5.53).

Evidence (a pnpm, a Yarn and a lockfile-less Node fixture, run against
v0.6.14 through `NodeAnalyzer` and `detect_project`):

- `build system` said `npm` for all three -- every `package.json` is mapped
  to `npm` in the marker table, so a pnpm or Yarn repository was mislabelled
  in Detected Project, Quick Context, text and HTML output.
- With `--security`, `npm audit` was run unconditionally and exited 1 with
  `ENOLOCK` ("This command requires an existing lockfile") for all three. It
  was recorded as a FAILED security check, not as skipped: a false failure
  that lowered the health score and showed up in Quick Context as a failed
  check, although nothing was wrong with the project. `npm audit` only reads
  `package-lock.json` / `npm-shrinkwrap.json`.

Changes, deliberately small:

- `node_package_manager(root)`: `packageManager` in the root `package.json`
  (the corepack field) wins; else the lockfile (`pnpm-lock.yaml`,
  `yarn.lock`, `bun.lock` / `bun.lockb`, `package-lock.json`); a root
  `pnpm-workspace.yaml` counts as pnpm; otherwise `npm`.
- `refine_build_system(detection, root)` corrects only the label, and only
  when it currently says `npm` (or nothing was detected -- `none detected` or
  `unknown` -- but a pnpm workspace file exists). Other build systems and every other field are untouched.
- `audit_skip_reason(root)` is `None` when `npm audit` can run (a lockfile it
  understands exists) and otherwise a sentence for a SKIPPED result naming the
  real reason and the right command (`pnpm audit`, `yarn npm audit` or
  `yarn audit`, `npm install` to create a lockfile).

**Deliberately not changed:** the test and lint commands. Members and root are
still run with `npm test` / `npm run lint`: it works in pnpm and Yarn
repositories (scripts only invoke binaries from `node_modules/.bin`), whereas
switching to `pnpm`/`yarn` would turn into a skipped check on every machine
that does not have them installed. `pnpm audit` / `yarn audit` are not run
either (different flags per Yarn major, network and tool required).

سیستم ساخت و `npm audit` در پروژه‌های Node.

شواهد (fixtureهای pnpm، Yarn و بدون lockfile): `build system` برای هر سه `npm`
گفته می‌شد، و با `--security` دستور `npm audit` بی‌قید اجرا می‌شد و با `ENOLOCK`
(نیاز به lockfile) خارج می‌شد؛ نتیجه به‌جای skipped به‌صورت **شکست** ثبت می‌شد:
شکستِ کاذبی که امتیاز سلامت را پایین می‌آورد، در حالی که مشکلی در پروژه نبود.

تغییر کوچک: package manager از فیلد `packageManager` یا lockfile تشخیص داده
می‌شود، برچسب build system اصلاح می‌شود، و وقتی `npm audit` نمی‌تواند اجرا شود
نتیجه‌ی skipped با دلیل واقعی و دستور درست برمی‌گردد. دستورهای تست و lint عمداً
دست نخوردند: `npm test` در مخزن pnpm و Yarn کار می‌کند، ولی عوض‌کردنش روی
ماشینی که pnpm یا yarn ندارد چک را skipped می‌کرد.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from sarand.models.results import ProjectDetection

_MAX_PARSE_BYTES = 1024 * 1024

# Lockfiles in the order they are tried when `packageManager` is absent.
# lockfileها به ترتیبی که وقتی `packageManager` نیست بررسی می‌شوند.
_LOCKFILES: tuple[tuple[str, str], ...] = (
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("bun.lock", "bun"),
    ("bun.lockb", "bun"),
    ("package-lock.json", "npm"),
    ("npm-shrinkwrap.json", "npm"),
)
_NPM_LOCKFILES = ("package-lock.json", "npm-shrinkwrap.json")
_KNOWN = frozenset({"npm", "pnpm", "yarn", "bun"})
# What `detect_project` reports when the root has no build marker at all.
# آنچه `detect_project` وقتی ریشه هیچ نشانگر build ندارد برمی‌گرداند.
_NOTHING_DETECTED = frozenset({"none detected", "unknown", ""})

_AUDIT_ADVICE = {
    "pnpm": "run `pnpm audit` yourself",
    "yarn": "run `yarn npm audit` (Yarn 2+) or `yarn audit` (Yarn 1) yourself",
    "bun": "audit the bun lockfile with another tool",
}


def _declared_manager(root: Path) -> str | None:
    manifest = root / "package.json"
    try:
        if manifest.stat().st_size > _MAX_PARSE_BYTES:
            return None
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    declared = data.get("packageManager") if isinstance(data, dict) else None
    if not isinstance(declared, str):
        return None
    name = declared.split("@", 1)[0].strip().lower()
    return name if name in _KNOWN else None


def node_package_manager(root: Path) -> str:
    """`npm`, `pnpm`, `yarn` or `bun` for the project rooted at `root`."""
    declared = _declared_manager(root)
    if declared is not None:
        return declared
    for filename, manager in _LOCKFILES:
        if (root / filename).is_file():
            return manager
    if (root / "pnpm-workspace.yaml").is_file():
        return "pnpm"
    return "npm"


def refine_build_system(detection: ProjectDetection, root: Path) -> ProjectDetection:
    """`detection` with an accurate Node build system label; the same object
    when nothing needs correcting."""
    current = detection.build_system
    has_pnpm_workspace = (root / "pnpm-workspace.yaml").is_file()
    if current == "npm" or (has_pnpm_workspace and current in _NOTHING_DETECTED):
        manager = node_package_manager(root)
        if manager != current:
            return replace(detection, build_system=manager)
    return detection


def audit_skip_reason(root: Path) -> str | None:
    """Why `npm audit` cannot run in `root`, or `None` when it can."""
    if any((root / name).is_file() for name in _NPM_LOCKFILES):
        return None
    manager = node_package_manager(root)
    if manager == "npm":
        return (
            "npm audit needs a package-lock.json and this project has none "
            "(run `npm install` to create one)"
        )
    present = next(
        (name for name, pm in _LOCKFILES if pm == manager and (root / name).is_file()),
        None,
    )
    where = f" ({present})" if present else ""
    advice = _AUDIT_ADVICE[manager]
    return (
        f"npm audit needs a package-lock.json; this project uses {manager}"
        f"{where} -- {advice}"
    )
