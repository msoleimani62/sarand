"""Environment detection and package/toolchain inventory.

Detection logic (Termux/Android/Kali/proot/root) is pure Python file
and env-var checks -- fully portable. Package-manager and toolchain
listings genuinely need the real external tools (dpkg-query, pacman,
pip, npm, cargo, rustup, gem, getprop) since there is no portable
stdlib equivalent for "what did apt install" -- those are shelled out
to via sarand's existing `run_cmd` helper and skip cleanly when the
tool is absent, exactly like every other sarand analyzer.

تشخیص محیط و فهرست پکیج/زنجیره‌ابزار.

منطق تشخیص (Termux/Android/Kali/proot/root) صرفاً چک فایل و متغیر
محیطی پایتونی است -- کاملاً پرتابل. فهرست‌های package manager و
toolchain واقعاً به ابزارهای بیرونی واقعی نیاز دارند (dpkg-query،
pacman، pip، npm، cargo، rustup، gem، getprop) چون معادل stdlib
پرتابلی برای «apt چی نصب کرده» وجود ندارد -- این‌ها با همان helper
موجودِ sarand یعنی `run_cmd` صدا زده می‌شوند و وقتی ابزار غایب باشد،
دقیقاً مثل هر آنالایزر دیگر sarand، تمیز رد می‌شوند.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from sarand.utils.command import run_cmd

_CMD_TIMEOUT = 30


def detect_environment() -> str:
    """Best-effort label like 'Termux + Android + proot + non-root'."""
    detected: list[str] = []

    if Path("/data/data/com.termux").is_dir():
        detected.append("Termux")
    if Path("/system").is_dir() or Path("/system/bin").is_dir():
        detected.append("Android")

    os_release = Path("/etc/os-release")
    if os_release.is_file():
        try:
            content = os_release.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            content = ""
        if "kali" in content:
            detected.append("Kali")

    if os.environ.get("PROOT_TMP_DIR") or os.environ.get("PROOT_LOADER"):
        detected.append("proot")

    # No UIDs on Windows; `sys.platform` so mypy skips this branch there.
    # روی Windows UID وجود ندارد؛ `sys.platform` تا mypy آنجا این شاخه را رد کند.
    if sys.platform == "win32":
        is_root = False
    else:
        is_root = os.getuid() == 0
    detected.append("UID0" if is_root else "non-root")

    return " + ".join(detected) if detected else "Unknown"


def tool_available(name: str) -> bool:
    return shutil.which(name) is not None


def pip_command() -> str | None:
    """`pip3` if present, else `pip`, else None -- shared by any section
    that needs to shell out to pip (avoids repeating the same
    fallback chain in multiple places)."""
    if tool_available("pip3"):
        return "pip3"
    if tool_available("pip"):
        return "pip"
    return None


def run_tool(cwd: Path, *cmd: str, timeout: int = _CMD_TIMEOUT) -> tuple[bool, str]:
    """Run cmd if the binary exists; return (ran, combined_output).

    `ran` only means the binary was found and executed -- it says
    nothing about whether the command actually succeeded. Most call
    sites just want best-effort output either way (e.g. `git status`,
    package listings). For the handful of sections that have a
    portable fallback and need to know whether to actually use it,
    use `run_tool_checked` instead.
    """
    if not tool_available(cmd[0]):
        return False, f"(command not available: {cmd[0]})"
    _rc, output, _duration = run_cmd(list(cmd), cwd, timeout=timeout)
    return True, output


def run_tool_checked(
    cwd: Path, *cmd: str, timeout: int = _CMD_TIMEOUT
) -> tuple[bool, str]:
    """Like `run_tool`, but `ok` also requires a zero exit code and
    non-empty output.

    BUG FIX: `lscpu` is commonly *installed* but still fails under a
    Termux/Kali proot (`/sys/devices/system/cpu/possible` isn't
    reachable there), and plain `run_tool` would still report that as
    "ran successfully" and print lscpu's raw error text into the
    report instead of falling back to the portable /proc/cpuinfo
    reader. Confirmed live: exactly this happened on-device. Sections
    with a portable fallback (CPU, memory) should use this instead of
    `run_tool` so a present-but-broken binary triggers the fallback
    the same way a missing one would.

    اصلاح باگ: `lscpu` معمولاً نصب *هست* ولی زیر یک proot با
    Termux/Kali همچنان شکست می‌خورد (`/sys/devices/system/cpu/possible`
    آنجا در دسترس نیست)، و `run_tool` ساده همچنان این را «با موفقیت
    اجرا شد» گزارش می‌کرد و متن خطای خامِ lscpu را به‌جای برگشتن به
    خواننده‌ی پرتابل `/proc/cpuinfo` توی گزارش می‌گذاشت. زنده تأیید شد:
    دقیقاً همین روی دستگاه رخ داد. بخش‌هایی که fallback پرتابل دارند
    (CPU، حافظه) باید از این استفاده کنند تا یک باینری موجود-ولی-خراب
    هم دقیقاً مثل یک باینری غایب باعث fallback شود.
    """
    if not tool_available(cmd[0]):
        return False, f"(command not available: {cmd[0]})"
    rc, output, _duration = run_cmd(list(cmd), cwd, timeout=timeout)
    if rc != 0 or not output.strip():
        return False, output
    return True, output


# Candidate toolchain/cache directories checked for existence + size.
# کاندیدهای دایرکتوری toolchain/cache که برای وجود + اندازه چک می‌شوند.
TOOLCHAIN_CANDIDATES: tuple[str, ...] = (
    "~/.cache",
    "~/.gradle",
    "~/.cargo",
    "~/.cargo/registry",
    "~/.cargo/git",
    "~/.rustup",
    "~/.npm",
    "~/.m2",
    "~/.android",
    "~/android-sdk",
    "~/.local/share",
    "~/toolchains",
    "/usr/lib/android-sdk",
    "/opt/android-sdk",
    "/var/cache/apt/archives",
    "/root/.cache",
    "/tmp",  # nosec B108
)

BUILD_ARTIFACT_DIR_NAMES: frozenset[str] = frozenset(
    {
        "target",
        "node_modules",
        "__pycache__",
        ".venv",
        "build",
        "dist",
        ".gradle",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
)

# BUG FIX (feedback: sarand-report-feedback.md): the set above used to be
# listed one-by-one, no matter how many separate copies exist. A real
# Python toolchain easily has hundreds of scattered __pycache__/.mypy_cache/
# .pytest_cache/.ruff_cache dirs (one per package under every
# site-packages), each getting its own report line and its own
# space_hogs entry -- this alone produced most of a reported 5+ MiB
# report. These are split into two sets: a handful of dirs the user
# actually wants to see individually (they're few, and each usually
# belongs to a distinct project worth reviewing on its own), and the
# "spawns hundreds of small copies" cache dirs, which report.py groups
# into one aggregate line by default (see collect_toolchain).
#
# اصلاح باگ (بازخورد: sarand-report-feedback.md): مجموعه‌ی بالا قبلاً
# تک‌تک لیست می‌شد، صرف‌نظر از این‌که چند نسخه‌ی جدا وجود دارد. یک
# toolchain واقعیِ پایتون به‌راحتی صدها __pycache__/.mypy_cache/
# .pytest_cache/.ruff_cache پراکنده دارد (یکی برای هر پکیج زیر هر
# site-packages)، که هرکدام یک خط گزارش و یک رکورد space_hogs جدا
# می‌گیرند -- همین به‌تنهایی بیشتر یک گزارش ۵+ مگابایتی گزارش‌شده را
# ساخته بود. این‌ها به دو مجموعه تقسیم شدند: چند پوشه‌ای که کاربر
# واقعاً می‌خواهد جداگانه ببیند (تعدادشان کم است و معمولاً هرکدام
# مالِ یک پروژه‌ی متفاوت و قابل‌بررسیِ جداست)، و پوشه‌های کشِ
# «صدها نسخه‌ی کوچک می‌سازند»، که report.py به‌طور پیش‌فرض در یک خط
# تجمیعی جمع می‌کند (به collect_toolchain نگاه کنید).
INDIVIDUAL_BUILD_ARTIFACT_DIR_NAMES: frozenset[str] = frozenset(
    {"target", "node_modules", "build", "dist", ".gradle", ".venv"}
)
AGGREGATE_CACHE_DIR_NAMES: frozenset[str] = frozenset(
    {"__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
)

TERMUX_PATHS: tuple[str, ...] = (
    "/data/data/com.termux",
    "/data/data/com.termux/files",
    "/data/data/com.termux/files/home",
    "/data/data/com.termux/files/usr",
    "/data/data/com.termux/files/usr/var/cache",
    "/data/data/com.termux/files/usr/var/lib",
)

NETHUNTER_PATHS: tuple[str, ...] = (
    "/data/local/nhsystem",
    "/data/local/nhsystem/kali",
    "/data/local/nhsystem/kali-arm64",
    "/data/local/nhsystem/kali-armhf",
)

IMPORTANT_PATHS: tuple[str, ...] = (
    "/",
    "/data",
    "/data/data",
    "/sdcard",
    "/storage",
    "/storage/emulated/0",
    "/tmp",  # nosec B108
)

ANDROID_PROPERTY_PREFIXES: tuple[str, ...] = (
    "ro.build.version.release",
    "ro.build.version.sdk",
    "ro.product.manufacturer",
    "ro.product.model",
    "ro.product.name",
    "ro.product.device",
    "ro.build.version.security_patch",
)

DOWNLOAD_CANDIDATES: tuple[str, ...] = (
    "/sdcard/Download",
    "/sdcard/Downloads",
    "~/Download",
    "~/Downloads",
)

ARCHIVE_EXTENSIONS: frozenset[str] = frozenset(
    {".zip", ".tar", ".gz", ".tgz", ".xz", ".zst", ".7z", ".rar"}
)
