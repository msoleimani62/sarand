"""Python analyzer: pytest + ruff, gated on real Python markers.

Unlike the old bxt behaviour, ``ruff``/``pytest`` are never run just
because they happen to be installed globally -- ``matches()`` must be
True first.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.python")

_MARKERS = ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")

# BUG FIX (the real culprit behind the whole --full slowdown
# investigation, confirmed live on-device): `bandit -r . -q` with no
# excludes recurses into *everything* under the project root,
# including `.venv/` -- so it was scanning the source of every
# installed package (mypy, pytest, ruff, pip-audit, cyclonedx-lib,
# bandit itself, ...) on every single run, not just sarand's own
# code. This is a well-known bandit issue (PyCQA/bandit#543): "bandit
# automatically scans all of the virtualenv site-packages... many
# many python files that don't need to be scanned." Confirmed live:
# the user's own bandit output showed it scanning
# `./.venv/lib/python3.14/site-packages/bandit/plugins/...`.
#
# The exclude paths are deliberately `./`-prefixed: per
# PyCQA/bandit#975, `-x .venv` and `-x ./.venv` are NOT equivalent in
# bandit -- only the `./`-prefixed form reliably excludes the
# directory (that issue's own repro: `-x ./.tox` scanned 94 files,
# `-x .tox` scanned 19282).
#
# اصلاح باگ (مقصر واقعیِ کل این بررسیِ کندی --full، زنده روی خودِ
# دستگاه تأیید شد): `bandit -r . -q` بدون exclude به هرچیزی زیر ریشه‌ی
# پروژه recurse می‌کند، شامل `.venv/` -- پس هر بار داشت سورس هر پکیج
# نصب‌شده (mypy، pytest، ruff، pip-audit، cyclonedx-lib، خودِ bandit،
# ...) را اسکن می‌کرد، نه فقط کد خودِ sarand. این یک باگ شناخته‌شده‌ی
# خودِ bandit است (PyCQA/bandit#543). زنده تأیید شد: خروجی خودِ bandit
# روی دستگاه کاربر نشان داد دارد
# `./.venv/lib/python3.14/site-packages/bandit/plugins/...` را اسکن
# می‌کند.
#
# مسیرهای exclude عمداً با `./` شروع می‌شوند: طبق PyCQA/bandit#975،
# `-x .venv` و `-x ./.venv` در bandit معادل *نیستند* -- فقط فرم با
# پیشوند `./` واقعاً پوشه را حذف می‌کند.
_BANDIT_EXCLUDE_DIRS = (
    ".venv",
    "venv",
    ".env",
    "env",
    "target",
    "node_modules",
    ".git",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
    ".tox",
)
_BANDIT_EXCLUDE_ARG = ",".join(f"./{d}" for d in _BANDIT_EXCLUDE_DIRS)

# BUG FIX (round 2 -- round 1's "pip-audit ." made things *worse*: 157.6s
# -> 201.8s on a real run). pip-audit's own README is explicit about why:
# pointing it at a project (a pyproject.toml path) makes it perform full
# dependency *resolution* first ("you have two options for avoiding
# dependency resolution: audit a pre-installed environment, or ensure
# your dependencies are already fully resolved") -- which is more
# expensive than simply listing an already-installed environment, not
# less. The actually-correct fix needs BOTH properties at once: scoped
# to just the target project's own declared runtime dependencies (not
# the whole dev environment), AND already fully resolved (exact pinned
# versions, no resolution work for pip-audit to do). That means: read
# the *target project's* (not sarand's own) pyproject.toml, find its
# declared runtime dependency names, look up each one's already-
# installed exact version via importlib.metadata (no subprocess, no
# network), and hand pip-audit a small pre-pinned requirements list via
# `-r ... --no-deps` -- so it only ever queries the handful of packages
# the project actually declared, at their exact installed versions,
# with no resolution step.
#
# A lightweight regex is used to pull dependency names out of
# `[project] dependencies = [...]`, deliberately not a full TOML parser:
# `tomllib` isn't available before Python 3.11, and this project
# supports 3.10+. This covers the overwhelmingly common case (a plain
# string-list `dependencies` array); anything the regex can't confidently
# parse is simply skipped rather than guessed at, and if nothing at all
# is found, this analyzer falls back to the pre-installed-environment
# form pip-audit itself recommends as the *other* correct option --
# never to the slow "resolve from pyproject.toml" path that started
# this investigation.
#
# اصلاح باگ (دور دوم -- «pip-audit .» در دور اول واقعاً بدتر کرد: از
# ۱۵۷.۶ به ۲۰۱.۸ ثانیه در یک اجرای واقعی). خودِ README پیپ‌آدیت صریح
# می‌گوید چرا: اشاره‌دادنش به یک پروژه (مسیر pyproject.toml) باعث
# می‌شود اول یک resolve کامل وابستگی انجام دهد («برای اجتناب از
# dependency resolution دو گزینه داری: audit یک محیط از‌قبل‌نصب‌شده،
# یا مطمئن شو وابستگی‌هایت از قبل کاملاً resolve شده‌اند») -- که
# گران‌تر از صرفاً لیست‌کردن یک محیط نصب‌شده است، نه ارزان‌تر. فیکس
# واقعاً درست باید هر دو ویژگی را همزمان داشته باشد: محدود به
# وابستگی‌های runtime اعلام‌شده‌ی خودِ پروژه‌ی هدف (نه کل محیط dev)، و
# از قبل کاملاً resolve شده (نسخه‌های pin‌شده‌ی دقیق، بدون کار
# resolve برای pip-audit). یعنی: pyproject.toml *پروژه‌ی هدف* (نه
# خودِ sarand) را بخوان، نام وابستگی‌های runtime اعلام‌شده‌اش را پیدا
# کن، نسخه‌ی دقیق از‌قبل‌نصب‌شده‌ی هرکدام را از importlib.metadata
# بگیر (بدون subprocess، بدون شبکه)، و یک لیست requirements کوچک و
# pin‌شده را با `-r ... --no-deps` به pip-audit بده -- تا فقط همان
# چندتا پکیجی که پروژه واقعاً اعلام کرده، در نسخه‌ی دقیق نصب‌شده،
# بدون هیچ مرحله‌ی resolve، پرسیده شود.
#
# یک regex سبک برای استخراج نام‌های وابستگی از
# `[project] dependencies = [...]` استفاده می‌شود، عمداً نه یک TOML
# parser کامل: tomllib قبل از پایتون ۳.۱۱ موجود نیست، و این پروژه از
# ۳.۱۰+ پشتیبانی می‌کند. این حالت رایج (یک آرایه‌ی رشته‌ای ساده‌ی
# dependencies) را پوشش می‌دهد؛ هرچه regex نتواند با اطمینان پارس کند
# صرفاً رد می‌شود نه حدس زده، و اگر اصلاً چیزی پیدا نشود، این آنالایزر
# به همان فرم «محیط از‌قبل‌نصب‌شده» که خودِ pip-audit به‌عنوان گزینه‌ی
# صحیح *دیگر* توصیه می‌کند برمی‌گردد -- هرگز به مسیر کندِ «resolve از
# pyproject.toml» که این بررسی را شروع کرد.
_DEPENDENCY_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+")


def _find_dependencies_array_body(text: str) -> str | None:
    """Return the raw text inside `dependencies = [ ... ]`, or None.

    Deliberately NOT a single regex: a naive `\\[(.*?)\\]` non-greedy
    match breaks the moment any dependency spec itself contains a `]`
    -- e.g. an extras marker like `"requests[socks]>=2"` -- because
    the regex stops at that *inner* bracket, not the array's real
    closing one. Caught by this module's own tests before it ever
    shipped. This walks the text with a small bracket-depth counter
    that ignores brackets while inside a quoted string, so extras
    syntax and any other `[`/`]` inside a dependency spec don't affect
    where the array actually ends.

    عمداً یک regex واحد نیست: تطبیق non-greedy ساده‌ی `\\[(.*?)\\]`
    همین‌که یک specِ وابستگی خودش یک `]` داشته باشد خراب می‌شود --
    مثلاً یک نشانگر extras مثل `"requests[socks]>=2"` -- چون regex
    روی همان براکت *داخلی* متوقف می‌شود، نه براکت بسته‌شونده‌ی واقعیِ
    آرایه. همین ماژول با تست خودش این را قبل از هر انتشاری گرفت. این
    تابع متن را با یک شمارنده‌ی عمق براکت کوچک می‌پیماید که داخل یک
    رشته‌ی داخل‌گیومه براکت‌ها را نادیده می‌گیرد، پس نحو extras یا هر
    `[`/`]` دیگر داخل specِ یک وابستگی روی این‌که آرایه واقعاً کجا
    تمام می‌شود اثر نمی‌گذارد.
    """
    key_match = re.search(r"dependencies\s*=\s*\[", text)
    if not key_match:
        return None

    start = key_match.end()
    depth = 1
    in_string: str | None = None
    i = start
    while i < len(text):
        ch = text[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == in_string:
                in_string = None
        elif ch in "\"'":
            in_string = ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start:i]
        i += 1
    return None


def _project_dependency_names(root: Path) -> list[str]:
    pyproject = root / "pyproject.toml"
    try:
        text = pyproject.read_text(errors="replace")
    except OSError:
        return []

    body = _find_dependencies_array_body(text)
    if body is None:
        return []

    names: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip().strip(",")
        if not line.startswith(('"', "'")):
            continue
        quote = line[0]
        end = line.rfind(quote)
        if end <= 0:
            continue
        spec = line[1:end]
        # Strip any environment marker (`; python_version >= "3.10"`)
        # before pulling the bare package name out of the specifier.
        spec = spec.split(";", 1)[0].strip()
        name_match = _DEPENDENCY_NAME_RE.match(spec)
        if name_match:
            names.append(name_match.group(0))
    return names


def _pinned_requirements_file(names: list[str]) -> Path | None:
    lines = []
    for name in names:
        try:
            lines.append(f"{name}=={installed_version(name)}")
        except PackageNotFoundError:
            logger.debug("Declared dependency %r is not installed -- skipping", name)
    if not lines:
        return None

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", prefix="sarand-pip-audit-", delete=False
    ) as handle:
        handle.write("\n".join(lines) + "\n")
        temp_path = handle.name
    return Path(temp_path)


_ENTRY_POINTS = ("src/main.py", "main.py", "cli.py", "__main__.py", "app.py")


class PythonAnalyzer:
    name = "Python"

    def matches(self, root: Path) -> bool:
        return any((root / m).exists() for m in _MARKERS)

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).exists()]

    async def run_tests(self, root: Path) -> CommandResult | None:
        if shutil.which("pytest") is None:
            return make_command_result(
                "pytest",
                127,
                "",
                0.0,
                skipped=True,
                skip_reason="pytest not found in PATH",
            )
        logger.info("Running pytest -q")
        rc, output, duration = await run_cmd_async(
            ["pytest", "-q", "--tb=short"], root, LONG_CMD_TIMEOUT
        )
        return make_command_result("pytest", rc, output, duration)

    async def run_quality(self, root: Path) -> list[CommandResult]:
        if shutil.which("ruff") is None:
            return [
                make_command_result(
                    "ruff", 127, "", 0.0, skipped=True, skip_reason="ruff not installed"
                )
            ]
        results = []
        rc, out, dur = await run_cmd_async(
            ["ruff", "check", ".", "--output-format=concise"], root, LONG_CMD_TIMEOUT
        )
        results.append(make_command_result("ruff check", rc, out, dur))
        rc, out, dur = await run_cmd_async(
            ["ruff", "format", ".", "--check"], root, LONG_CMD_TIMEOUT
        )
        results.append(make_command_result("ruff format --check", rc, out, dur))
        return results

    async def run_security(self, root: Path) -> list[CommandResult]:
        results: list[CommandResult] = []

        if shutil.which("pip-audit") is None:
            results.append(
                make_command_result(
                    "pip-audit",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="pip-audit not installed",
                )
            )
        else:
            # BUG FIX (round 2 -- see the module-level comment near
            # _project_dependency_names for the full "why"). Uses a
            # pre-pinned, project-scoped requirements file with
            # --no-deps: no environment-wide scan, no resolution step.
            names = _project_dependency_names(root)
            req_file = _pinned_requirements_file(names) if names else None
            try:
                if req_file is not None:
                    cmd = ["pip-audit", "-r", str(req_file), "--no-deps"]
                else:
                    # Couldn't determine the project's own declared
                    # dependencies (no pyproject.toml, an unusual
                    # `dependencies` format the regex doesn't cover,
                    # or none of them are actually installed) -- fall
                    # back to pip-audit's own "pre-installed
                    # environment" mode (its recommended alternative
                    # to project-mode resolution), not the slow
                    # resolve-from-pyproject.toml path.
                    cmd = ["pip-audit"]
                rc, out, dur = await run_cmd_async(cmd, root, LONG_CMD_TIMEOUT)
            finally:
                if req_file is not None:
                    req_file.unlink(missing_ok=True)
            results.append(make_command_result("pip-audit", rc, out, dur))

        if shutil.which("bandit") is None:
            results.append(
                make_command_result(
                    "bandit",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="bandit not installed",
                )
            )
        else:
            rc, out, dur = await run_cmd_async(
                ["bandit", "-r", ".", "-q", "-x", _BANDIT_EXCLUDE_ARG],
                root,
                LONG_CMD_TIMEOUT,
            )
            results.append(make_command_result("bandit", rc, out, dur))

        return results
