"""Makefile detection (backlog item 7, "Makefile").

Evidence-first audit before any implementation: grepped `python/sarand`
for Makefile awareness. The only trace is `constants.py`'s
project-marker table, which maps the exact filename `Makefile` to
`("Generic", "unknown", "make")` -- so a root `Makefile` makes the
build system show up as "make" and `core/ai_summary.py` ranks it as a
high-priority file. Nothing reads its content: the report cannot say
which targets exist or which one is the default, `GNUmakefile` /
`makefile` are not recognised, and Makefiles below the root (monorepo
layouts such as `docs/Makefile`) are invisible. CONFIRMED gap, in
representation only.

Scope for this round, same discipline as items 8, 5 and 6: **detection
only** -- read the file, list its explicit targets. `make` is never
run (not even `make -n`/`make -p`): a Makefile is arbitrary shell, so
executing it during a scan would be neither safe nor deterministic.

Parsing is deliberately a line-based heuristic, not a Make
implementation. Rules applied: backslash continuations are joined;
recipe lines (leading tab), comments, conditionals, includes,
`define ... endef` bodies and variable assignments are skipped;
pattern rules (`%`), special targets (leading `.`) and targets built
from variable expansion (`$`) are not listed. `.PHONY` names are
collected; the default target is `.DEFAULT_GOAL` when set, else the
first listed target.

**Deliberately deferred:** `make` execution, `include`/`-include`
resolution, `.mk` fragment files, macro/conditional evaluation, and
extracting per-target descriptions (`## help` comments).

تشخیص Makefile (آیتم ۷ backlog، «Makefile»).

ممیزیِ evidence-first: تنها ردپا جدول نشانگرهای پروژه در
`constants.py` است که نامِ دقیقِ `Makefile` را به
`("Generic", "unknown", "make")` نگاشت می‌کند -- پس Makefile ریشه
باعث می‌شود build system «make» نمایش داده شود. هیچ‌چیز محتوای آن را
نمی‌خواند: گزارش نمی‌تواند بگوید چه targetهایی هست و کدام پیش‌فرض
است، `GNUmakefile`/`makefile` شناخته نمی‌شوند و Makefileهای زیرِ ریشه
(مثل `docs/Makefile`) دیده نمی‌شوند. شکافِ CONFIRMED، فقط در بازنمایی.

اسکوپِ این دور: **فقط تشخیص** -- خواندنِ فایل و فهرست‌کردنِ targetهای
صریح. `make` هرگز اجرا نمی‌شود (حتی `make -n`/`make -p`): Makefile
شِلِ دلخواه است و اجرایش هنگام اسکن نه امن است نه قطعی.

پارس عمداً یک heuristicِ خط‌به‌خط است، نه پیاده‌سازیِ Make. خطوطِ
recipe (شروع‌شده با tab)، کامنت‌ها، شرط‌ها، includeها، بدنه‌ی
`define ... endef` و انتساب متغیر رد می‌شوند؛ الگوقاعده‌ها (`%`)،
targetهای ویژه (شروع با `.`) و targetهای ساخته‌شده با `$` فهرست
نمی‌شوند. نام‌های `.PHONY` جمع می‌شوند؛ target پیش‌فرض `.DEFAULT_GOAL`
است اگر تنظیم شده باشد، وگرنه اولین target فهرست‌شده.

عمداً به بعد موکول شد: اجرای `make`، حل‌کردنِ `include`، فایل‌های
`.mk`، ارزیابیِ macro/شرط و استخراجِ توضیح هر target.
"""

from __future__ import annotations

import re
from pathlib import Path

from sarand.models.results import MakefileEntry, MakefileInfo

# GNU make's own lookup names, in its own precedence order. Exact,
# case-sensitive match: `Makefile.PL`, `makefile.bak`, `my.mk` etc.
# never qualify.
# نام‌هایی که خودِ GNU make می‌جوید. تطبیق دقیق و حساس به حروف.
_MAKEFILE_NAMES = frozenset({"GNUmakefile", "makefile", "Makefile"})

# Same build/dependency/VCS prune list as `core/kubernetes.py` and
# `core/compose.py` (kept as a deliberate local copy, AGENTS.md 5.38).
# همان فهرستِ حذفِ `core/kubernetes.py` و `core/compose.py` (نسخه‌ی
# محلیِ عمدی، AGENTS.md بخش 5.38).
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
        "dist",
        "build",
    }
)

_MAX_DEPTH = 5

# Report-size guards (backlog item 9 is about exactly this kind of
# growth): a C monorepo can hold hundreds of Makefiles with thousands
# of object-file targets. The counts of what was dropped are kept so
# the report never silently loses information.
# محافظ اندازه‌ی گزارش: تعدادِ موارد حذف‌شده نگه داشته می‌شود تا گزارش
# هرگز بی‌صدا اطلاعات از دست ندهد.
_MAX_FILES = 25
_MAX_TARGETS_PER_FILE = 100
_MAX_PARSE_BYTES = 1024 * 1024

# Logical lines starting with one of these words are never rules.
# خطوط منطقی که با این کلمات شروع شوند هرگز rule نیستند.
_NON_RULE_KEYWORDS = (
    "ifeq",
    "ifneq",
    "ifdef",
    "ifndef",
    "else",
    "endif",
    "include",
    "-include",
    "sinclude",
    "export",
    "unexport",
    "vpath",
    "override",
    "private",
    "undefine",
)

_RULE = re.compile(r"^([^:=#\t][^:=#]*?)\s*(?::(?![:=])|::(?!=))")
_DEFAULT_GOAL = re.compile(r"^\.DEFAULT_GOAL\s*:?:?=\s*(\S+)")
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_BAD_TARGET_CHARS = re.compile(r"[%$()\[\]{}\\\"'`;|&<>]")


def _logical_lines(text: str) -> list[str]:
    """Physical lines with backslash continuations joined."""
    lines: list[str] = []
    buffer = ""
    for raw in text.splitlines():
        if buffer:
            buffer += " " + raw.strip()
        else:
            buffer = raw
        if buffer.endswith("\\"):
            buffer = buffer[:-1].rstrip()
            continue
        lines.append(buffer)
        buffer = ""
    if buffer:
        lines.append(buffer)
    return lines


def _is_non_rule(line: str) -> bool:
    word = re.split(r"[\s(]", line, maxsplit=1)[0]
    return word in _NON_RULE_KEYWORDS


def _parse(text: str) -> tuple[list[str], list[str], str]:
    """(targets, phony, default_target) for one Makefile's text."""
    targets: list[str] = []
    seen: set[str] = set()
    phony: list[str] = []
    explicit_default = ""
    in_define = False

    for line in _logical_lines(text):
        stripped = line.strip()
        if in_define:
            if stripped.split(maxsplit=1)[:1] == ["endef"]:
                in_define = False
            continue
        if not stripped or line.startswith("\t") or stripped.startswith("#"):
            continue
        if stripped.split(maxsplit=1)[:1] == ["define"]:
            in_define = True
            continue

        goal = _DEFAULT_GOAL.match(stripped)
        if goal:
            explicit_default = goal.group(1)
            continue
        if _is_non_rule(stripped):
            continue

        match = _RULE.match(stripped)
        if match is None:
            continue
        head = match.group(1)
        if _CONTROL_CHARS.search(head):
            # Binary/garbage content is never a real rule head.
            # محتوای باینری/آشغال هرگز سرِ یک rule واقعی نیست.
            continue
        rest = stripped[match.end() :]
        if rest.startswith("="):
            continue

        if head.strip() == ".PHONY":
            for name in rest.split("#", 1)[0].split():
                if name not in phony and not _BAD_TARGET_CHARS.search(name):
                    phony.append(name)
            continue

        for name in head.split():
            if name.startswith(".") and "/" not in name:
                continue
            if _BAD_TARGET_CHARS.search(name) or name in seen:
                continue
            seen.add(name)
            targets.append(name)

    default = explicit_default or (targets[0] if targets else "")
    return targets, phony, default


def _read_entry(path: Path, rel: str) -> MakefileEntry:
    try:
        if path.stat().st_size > _MAX_PARSE_BYTES:
            return MakefileEntry(path=rel)
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return MakefileEntry(path=rel)
    targets, phony, default = _parse(text)
    shown = targets[:_MAX_TARGETS_PER_FILE]
    shown_set = set(shown)
    return MakefileEntry(
        path=rel,
        targets=shown,
        phony=[p for p in phony if p in shown_set],
        default_target=default,
        total_targets=len(targets),
    )


def _find_makefiles(root: Path) -> list[Path]:
    """Makefiles under `root`, pruning `_SKIP_DIRS` and anything past
    `_MAX_DEPTH`, without following symlinks. When a directory has
    several of GNU make's names, only the first in make's own lookup
    order is kept, as `make` itself would pick exactly one.
    """
    found: list[Path] = []
    frontier = [(root, 0)]
    while frontier:
        current, depth = frontier.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        here: dict[str, Path] = {}
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_file() and entry.name in _MAKEFILE_NAMES:
                here[entry.name] = entry
            elif entry.is_dir() and depth < _MAX_DEPTH and entry.name not in _SKIP_DIRS:
                frontier.append((entry, depth + 1))
        for name in ("GNUmakefile", "makefile", "Makefile"):
            if name in here:
                found.append(here[name])
                break
    return found


def detect_makefiles(root: Path) -> MakefileInfo | None:
    """Detect Makefiles under `root` and list their targets. Returns
    `None` when none are found -- the common case for a project that
    does not use Make at all.
    """
    paths = _find_makefiles(root)
    if not paths:
        return None
    rels = sorted(p.relative_to(root).as_posix() for p in paths)
    by_rel = {p.relative_to(root).as_posix(): p for p in paths}
    kept = rels[:_MAX_FILES]
    return MakefileInfo(
        files=[_read_entry(by_rel[r], r) for r in kept],
        total_files=len(rels),
    )
