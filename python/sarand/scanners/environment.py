"""Environment and toolchain inspection.

Unlike the old bxt version (which had a fixed field per Rust/Python
tool), this collects an open-ended ``tool_versions`` dict so analyzers
for any language can contribute without changing this module.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import socket
import sys
from pathlib import Path

from sarand.models.results import EnvironmentInfo
from sarand.progress import status
from sarand.rust_bridge import RUST_CORE_AVAILABLE
from sarand.utils.command import run_cmd
from sarand.utils.logging import get_logger

logger = get_logger("environment")

# Tools worth reporting the version of, if present on PATH.
# ابزارهایی که ارزش گزارش نسخه‌شان را دارند، در صورت وجود در PATH.
_KNOWN_TOOLS = (
    "git",
    "rustc",
    "cargo",
    "ruff",
    "pytest",
    "mypy",
    "go",
    "node",
    "npm",
)


def _version(cmd: list[str], timeout: int = 30) -> str:
    rc, out, _ = run_cmd(cmd, cwd=Path.home(), timeout=timeout)
    if rc == 0 and out.strip():
        return out.strip().splitlines()[0]
    return "(unavailable)"


# (available_bytes or None when the OS does not report it, total_bytes)
# (بایت‌های در دسترس، یا None وقتی سیستم‌عامل گزارشش نمی‌کند، کل بایت‌ها)
_MemoryReading = tuple[int | None, int]


def _parse_meminfo(text: str) -> _MemoryReading | None:
    """Parse the contents of Linux's /proc/meminfo (also Android/Termux, WSL)."""
    total_kb = available_kb = 0
    for line in text.splitlines():
        if line.startswith("MemTotal:"):
            total_kb = int(line.split()[1])
        elif line.startswith("MemAvailable:"):
            available_kb = int(line.split()[1])
    if not total_kb:
        return None
    return available_kb * 1024, total_kb * 1024


def _proc_meminfo() -> _MemoryReading | None:
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            return _parse_meminfo(fh.read())
    except (OSError, ValueError, IndexError):
        return None


def _parse_vm_stat(text: str) -> int | None:
    """Available bytes from macOS `vm_stat` (free + inactive + speculative)."""
    page_match = re.search(r"page size of (\d+) bytes", text)
    if not page_match:
        return None
    pages = 0
    for label in ("free", "inactive", "speculative"):
        match = re.search(rf"^Pages {label}:\s+(\d+)\.", text, re.MULTILINE)
        if match:
            pages += int(match.group(1))
    return pages * int(page_match.group(1)) if pages else None


def _sysconf_total() -> int | None:
    """Total physical memory through POSIX `sysconf` (Linux, macOS, BSD)."""
    if sys.platform == "win32":
        return None
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError, AttributeError):
        return None
    return pages * page_size if pages > 0 and page_size > 0 else None


def _macos_memory() -> _MemoryReading | None:
    total = _sysconf_total()
    if total is None:
        return None
    rc, out, _ = run_cmd(["vm_stat"], cwd=Path.home(), timeout=10)
    return (_parse_vm_stat(out) if rc == 0 else None), total


def _windows_memory() -> _MemoryReading | None:
    """Physical memory through `GlobalMemoryStatusEx` (stdlib `ctypes`)."""
    if sys.platform != "win32":
        return None
    import ctypes

    class MemoryStatusEx(ctypes.Structure):
        _fields_ = (
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        )

    status_ex = MemoryStatusEx()
    status_ex.dwLength = ctypes.sizeof(status_ex)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status_ex)):
        return None
    return int(status_ex.ullAvailPhys), int(status_ex.ullTotalPhys)


def _memory_reading() -> _MemoryReading | None:
    """One reading per platform, so the report says the same thing on all.

    Windows -> ctypes; everything else tries /proc/meminfo first (Linux,
    Android/Termux, WSL), then macOS `vm_stat`, then plain `sysconf`
    (total only).

    یک خواندن برای هر پلتفرم، تا گزارش روی همه یک چیز بگوید. Windows ->
    ctypes؛ بقیه اول /proc/meminfo (لینوکس، اندروید/Termux، WSL)، بعد
    `vm_stat` مک، بعد `sysconf` ساده (فقط کل حافظه).
    """
    if sys.platform == "win32":
        return _windows_memory()
    reading = _proc_meminfo()
    if reading is None and sys.platform == "darwin":
        reading = _macos_memory()
    if reading is None:
        total = _sysconf_total()
        reading = (None, total) if total else None
    return reading


def _memory_summary() -> str:
    reading = _memory_reading()
    if reading is None:
        return "(unknown)"
    available, total = reading
    total_mib = total // 1024**2
    if available is None:
        return f"{total_mib} MiB total"
    return f"{available // 1024**2} MiB available / {total_mib} MiB total"


def _disk_free(path: Path) -> str:
    try:
        usage = shutil.disk_usage(path)
        return f"{usage.free / 1024**3:.1f} GiB free / {usage.total / 1024**3:.1f} GiB total"
    except OSError:
        return "(unknown)"


def _cpu_summary() -> str:
    proc = platform.processor() or platform.machine()
    cores = os.cpu_count() or 0
    return f"{proc} ({cores} cores)" if cores else proc or "(unknown)"


def collect_environment_info(project_root: Path | None = None) -> EnvironmentInfo:
    """Collect host and toolchain information."""
    status("Collecting environment information...")
    logger.info("Starting environment inspection")

    root = project_root or Path.cwd()
    tool_versions: dict[str, str] = {}
    for tool in _KNOWN_TOOLS:
        if shutil.which(tool):
            tool_versions[tool] = _version([tool, "--version"])

    info = EnvironmentInfo(
        python=_version([sys.executable, "--version"]),
        rust_core="available (native scan)"
        if RUST_CORE_AVAILABLE
        else "unavailable (pure-Python fallback)",
        os_name=f"{platform.system()} {platform.release()}",
        architecture=platform.machine(),
        cpu_summary=_cpu_summary(),
        memory_summary=_memory_summary(),
        disk_free=_disk_free(root),
        hostname=socket.gethostname(),
        tool_versions=tool_versions,
    )
    logger.debug("Environment collected: %s", info)
    return info
