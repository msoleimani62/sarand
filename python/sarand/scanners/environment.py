"""Environment and toolchain inspection.

Unlike the old bxt version (which had a fixed field per Rust/Python
tool), this collects an open-ended ``tool_versions`` dict so analyzers
for any language can contribute without changing this module.
"""

from __future__ import annotations

import os
import platform
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


def _memory_summary() -> str:
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            lines = fh.readlines()
        total_kb = available_kb = 0
        for line in lines:
            if line.startswith("MemTotal:"):
                total_kb = int(line.split()[1])
            elif line.startswith("MemAvailable:"):
                available_kb = int(line.split()[1])
        if total_kb:
            return (
                f"{available_kb // 1024} MiB available / {total_kb // 1024} MiB total"
            )
    except OSError:
        pass
    return "(unknown)"


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
