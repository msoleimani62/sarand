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
            content = os_release.read_text(errors="replace").lower()
        except OSError:
            content = ""
        if "kali" in content:
            detected.append("Kali")

    if os.environ.get("PROOT_TMP_DIR") or os.environ.get("PROOT_LOADER"):
        detected.append("proot")

    try:
        is_root = os.getuid() == 0
    except AttributeError:
        is_root = False
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
    """Run cmd if the binary exists; return (ran, combined_output)."""
    if not tool_available(cmd[0]):
        return False, f"(command not available: {cmd[0]})"
    _rc, output, _duration = run_cmd(list(cmd), cwd, timeout=timeout)
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
    "/tmp",
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
    }
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
    "/tmp",
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
