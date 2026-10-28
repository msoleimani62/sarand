"""Docker Compose analyzer: `docker compose config` on the detected Compose files.

Matches when `core/compose.py` finds Compose files (it already knows the file
names; this analyzer only adds the check). It never builds an image, pulls one
or starts a container: `docker compose config` loads, merges and validates the
files and prints the result, and `--quiet` drops that output. Two flags keep it
safe and honest:

- `--no-interpolate`: `${VARIABLE}` is not substituted, so a variable that is
  only set on the developer's machine (even `${X:?required}`) is not a failure
  here, and nothing from the environment is ever resolved into the output.
- a file that pulls in something remote (`include:` or `extends: file:` with a
  URL) is skipped, because loading it would need the network.

Files that belong together are checked together (one run per group): a base
file alone, and the base with each override or variant next to it, because an
override on its own is incomplete by design. Missing `docker`, a missing
Compose plugin or a Compose too old for the flag give a clean skipped result,
never a false failure. See AGENTS.md section 5.86.

تحلیل‌گر Docker Compose: `docker compose config` روی فایل‌های شناسایی‌شده.

هرگز image نمی‌سازد، pull نمی‌کند و container اجرا نمی‌کند. با `--no-interpolate`
متغیرها جایگزین نمی‌شوند (پس متغیری که فقط روی ماشین توسعه‌دهنده تنظیم است
شکست نیست) و فایلی که به چیز راه‌دور (URL) ارجاع دهد به‌دلیل نیاز به شبکه
skipped می‌شود. فایل‌های وابسته با هم بررسی می‌شوند؛ نبودن docker یا افزونه‌ی
Compose نتیجه‌ی skipped می‌دهد، نه شکست کاذب.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import yaml

from sarand.analyzers._tooling import run_tool, skipped
from sarand.core.compose import detect_compose
from sarand.models.results import CommandResult

# More groups than this is a monorepo of deployment files; the rest is counted.
# بیش از این تعداد گروه معمولاً مخزن بزرگی از فایل‌های استقرار است؛ بقیه شمرده می‌شوند.
MAX_GROUPS = 8
_MAX_PARSE_BYTES = 1024 * 1024
_BASE_NAMES = (
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",
)


def compose_groups(paths: list[str]) -> list[list[str]]:
    """Which files one `docker compose config` run is given together.

    Per directory: the base file alone, then the base plus each other file
    (an override or a variant such as `compose.prod.yaml`); a directory with no
    base file checks each file alone. A second base-style name in the same
    directory is a group of its own. Deterministic: sorted by path.
    """
    by_dir: dict[str, dict[str, str]] = {}
    for path in sorted(paths):
        parent, _, name = path.rpartition("/")
        by_dir.setdefault(parent, {})[name] = path
    groups: list[list[str]] = []
    for parent in sorted(by_dir):
        names = by_dir[parent]
        base_name = next((name for name in _BASE_NAMES if name in names), None)
        base = names[base_name] if base_name else None
        if base is not None:
            groups.append([base])
        for name in sorted(names):
            path = names[name]
            if path == base:
                continue
            if name in _BASE_NAMES or base is None:
                groups.append([path])
            else:
                groups.append([base, path])
    return groups


def _references(data: dict[object, object]) -> Iterator[str]:
    """Paths a Compose file loads from elsewhere: `include:` and `extends: file:`."""
    include = data.get("include")
    for item in include if isinstance(include, list) else []:
        if isinstance(item, str):
            yield item
        elif isinstance(item, dict):
            target = item.get("path")
            if isinstance(target, str):
                yield target
            elif isinstance(target, list):
                yield from (entry for entry in target if isinstance(entry, str))
    services = data.get("services")
    if isinstance(services, dict):
        for spec in services.values():
            extends = spec.get("extends") if isinstance(spec, dict) else None
            if isinstance(extends, dict) and isinstance(extends.get("file"), str):
                yield str(extends["file"])


def remote_reference(root: Path, files: list[str]) -> str:
    """The first file in `files` that loads something by URL, or ""."""
    for relative in files:
        try:
            path = root / relative
            if path.stat().st_size > _MAX_PARSE_BYTES:
                continue
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, yaml.YAMLError):
            continue
        if not isinstance(data, dict):
            continue
        for reference in _references(data):
            if "://" in reference or reference.startswith("git@"):
                return relative
    return ""


def judge(result: CommandResult) -> CommandResult:
    """Turn "the tool cannot do this here" into a skip instead of a failure."""
    if result.skipped or result.passed:
        return result
    text = result.raw_output
    if "is not a docker command" in text or (
        "unknown command" in text and "compose" in text
    ):
        return skipped(result.kind, "the docker Compose plugin is not installed")
    if "unknown flag: --no-interpolate" in text:
        return skipped(
            result.kind, "the installed docker compose is too old (no --no-interpolate)"
        )
    if "Cannot connect to the Docker daemon" in text:
        return skipped(result.kind, "the Docker daemon is not reachable")
    return result


def config_argv(files: list[str]) -> list[str]:
    argv = ["docker", "compose"]
    for file in files:
        argv += ["-f", file]
    argv += ["config", "--quiet", "--no-interpolate"]
    return argv


class ComposeAnalyzer:
    name = "Compose"

    def matches(self, root: Path) -> bool:
        return detect_compose(root) is not None

    def entry_points(self, root: Path) -> list[str]:
        # The YAML analyzer already lists Compose files as entry points.
        # آنالایزر YAML فایل‌های Compose را از قبل به‌عنوان entry point فهرست می‌کند.
        return []

    async def run_tests(self, root: Path) -> CommandResult | None:
        return None

    async def run_quality(self, root: Path) -> list[CommandResult]:
        info = detect_compose(root)
        if info is None:
            return []
        groups = compose_groups([file.path for file in info.files])
        results: list[CommandResult] = []
        for files in groups[:MAX_GROUPS]:
            kind = "docker compose config " + " + ".join(files)
            remote = remote_reference(root, files)
            if remote:
                results.append(
                    skipped(kind, f"{remote} loads a remote file (needs the network)")
                )
                continue
            results.append(judge(await run_tool(root, kind, config_argv(files))))
        extra = len(groups) - MAX_GROUPS
        if extra > 0:
            results.append(
                skipped(
                    "docker compose config",
                    f"{extra} more group(s) of Compose files not checked "
                    f"(limit {MAX_GROUPS})",
                )
            )
        return results

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
