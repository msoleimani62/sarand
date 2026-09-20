"""Lockfile validation: is the dependency set of this project actually
pinned, and is that pin actually committed?

Pure Python (plus one `git check-ignore` call), no external scanner --
this is the "reproducible-build / lockfile validation" item of
AGENTS.md §5.10's P2 list. It answers two questions per ecosystem, both
gated on a real manifest marker at the project root (§4.3):

1. Does the manifest have its lockfile at all?
2. If so, is that lockfile git-ignored? A lockfile that exists on one
   machine but is not committed does not make anyone else's build
   reproducible.

Deliberately NOT done here: checking that the lockfile is *in sync* with
the manifest. That needs each ecosystem's own tool (`cargo metadata
--locked`, `npm ci --dry-run`, `go mod verify`, ...) and is left for a
later round rather than half-implemented with heuristics.

اعتبارسنجی lockfile: آیا مجموعه‌ی وابستگی‌های این پروژه واقعاً pin شده،
و آیا آن pin واقعاً commit شده؟

پایتون خالص (به‌علاوه‌ی یک فراخوانی `git check-ignore`)، بدون اسکنر
خارجی -- این همان آیتم «اعتبارسنجی reproducible-build / lockfile» از
لیست P2 در §5.10 AGENTS.md است. برای هر اکوسیستم دو سؤال را جواب
می‌دهد، هر دو گیت‌شده روی یک نشانگر واقعیِ manifest در ریشه‌ی پروژه
(§4.3):

۱. آیا manifest اصلاً lockfile خودش را دارد؟
۲. اگر دارد، آیا آن lockfile در git نادیده گرفته شده (ignored)؟ یک
   lockfile که روی یک ماشین هست ولی commit نشده، build دیگران را
   reproducible نمی‌کند.

عمداً انجام نمی‌شود: بررسی هماهنگ‌بودنِ lockfile با manifest. این کار
به ابزار خودِ هر اکوسیستم نیاز دارد (`cargo metadata --locked`،
`npm ci --dry-run`، `go mod verify`، ...) و به‌جای پیاده‌سازیِ نیمه‌کاره
با heuristic به دور بعدی موکول شده.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sarand.constants import DEFAULT_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("core.lockfiles")

_KIND = "lockfile check"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _always(root: Path) -> bool:
    return True


def _node_has_deps(root: Path) -> bool:
    # A package.json with no dependencies has nothing to lock.
    # package.json بدون وابستگی چیزی برای lock کردن ندارد.
    try:
        data = json.loads(_read_text(root / "package.json"))
    except json.JSONDecodeError:
        return False
    if not isinstance(data, dict):
        return False
    return any(
        isinstance(data.get(key), dict) and data[key]
        for key in ("dependencies", "devDependencies", "optionalDependencies")
    )


def _go_has_requires(root: Path) -> bool:
    return (
        re.search(r"^\s*require\b", _read_text(root / "go.mod"), re.MULTILINE)
        is not None
    )


def _php_has_packages(root: Path) -> bool:
    try:
        data = json.loads(_read_text(root / "composer.json"))
    except json.JSONDecodeError:
        return False
    if not isinstance(data, dict):
        return False
    for key in ("require", "require-dev"):
        section = data.get(key)
        if isinstance(section, dict) and any(
            name != "php" and not name.startswith(("ext-", "lib-")) for name in section
        ):
            return True
    return False


def _pyproject_mentions(marker: str) -> Callable[[Path], bool]:
    # Python has no single lockfile convention, so only a real marker for
    # a lock-producing tool counts (§4.3) -- a plain pyproject.toml for a
    # library or a pip-installed app is not expected to have one.
    # پایتون یک قرارداد واحد برای lockfile ندارد، پس فقط نشانگر واقعیِ یک
    # ابزار تولیدکننده‌ی lock حساب می‌شود (§4.3) -- یک pyproject.toml ساده
    # برای کتابخانه یا اپ نصب‌شده با pip انتظار lockfile ندارد.
    def gate(root: Path) -> bool:
        return marker in _read_text(root / "pyproject.toml")

    return gate


@dataclass(frozen=True)
class _Rule:
    ecosystem: str
    manifest: str
    locks: tuple[str, ...]
    gate: Callable[[Path], bool]


_RULES: tuple[_Rule, ...] = (
    _Rule("Rust", "Cargo.toml", ("Cargo.lock",), _always),
    _Rule(
        "Node.js",
        "package.json",
        ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lock", "bun.lockb"),
        _node_has_deps,
    ),
    _Rule("Go", "go.mod", ("go.sum",), _go_has_requires),
    _Rule("Ruby", "Gemfile", ("Gemfile.lock",), _always),
    _Rule("PHP", "composer.json", ("composer.lock",), _php_has_packages),
    _Rule(
        "Python (poetry)",
        "pyproject.toml",
        ("poetry.lock",),
        _pyproject_mentions("[tool.poetry"),
    ),
    _Rule(
        "Python (uv)", "pyproject.toml", ("uv.lock",), _pyproject_mentions("[tool.uv")
    ),
    _Rule(
        "Python (pdm)",
        "pyproject.toml",
        ("pdm.lock",),
        _pyproject_mentions("[tool.pdm"),
    ),
    _Rule("Python (pipenv)", "Pipfile", ("Pipfile.lock",), _always),
)


async def _is_git_ignored(root: Path, relative: str) -> bool:
    if not (root / ".git").exists():
        return False
    rc, _out, _dur = await run_cmd_async(
        ["git", "check-ignore", "-q", "--", relative], root, DEFAULT_CMD_TIMEOUT
    )
    # 0 = ignored, 1 = not ignored, anything else (git missing, not a
    # repo, ...) = unknown, which must not be reported as a problem.
    # 0 = نادیده گرفته شده، 1 = نه، هر چیز دیگر (نبودن git، نبودن repo، ...)
    # = نامعلوم، که نباید به‌عنوان مشکل گزارش شود.
    return rc == 0


async def run_lockfile_check(root: Path) -> CommandResult:
    """Check every applicable manifest at the project root for a committed
    lockfile. Fails only on a definite problem (no lockfile, or a
    git-ignored one); several lockfiles for one ecosystem is a warning.

    Output lines deliberately avoid the words `error:` / `failed`:
    sarand's known-issue and error scanners match those substrings and
    would misreport a lockfile problem as a compile error.
    """
    start = time.perf_counter()
    lines: list[str] = []
    problems = 0
    checked = 0

    for rule in _RULES:
        if not (root / rule.manifest).is_file() or not rule.gate(root):
            continue
        checked += 1
        present = [name for name in rule.locks if (root / name).is_file()]
        if not present:
            problems += 1
            lines.append(
                f"problem: {rule.manifest} ({rule.ecosystem}) has no lockfile "
                f"-- expected one of: {', '.join(rule.locks)}"
            )
            continue
        if len(present) > 1:
            lines.append(
                f"warning: more than one lockfile for {rule.ecosystem}: "
                f"{', '.join(present)} -- pick one package manager"
            )
        ignored = [name for name in present if await _is_git_ignored(root, name)]
        if ignored:
            problems += 1
            lines.append(
                f"problem: {', '.join(ignored)} is git-ignored -- a lockfile "
                "that is not committed does not make the build reproducible"
            )
        else:
            lines.append(f"ok: {rule.manifest} ({rule.ecosystem}) -> {present[0]}")

    if checked == 0:
        return make_command_result(
            _KIND,
            0,
            "",
            0.0,
            skipped=True,
            skip_reason=(
                "no dependency manifest with a known lockfile convention "
                "found at the project root"
            ),
        )

    duration = time.perf_counter() - start
    return make_command_result(
        _KIND, 1 if problems else 0, "\n".join(lines) + "\n", duration
    )
