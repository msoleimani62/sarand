"""The 12 report sections, ported from device-audit.sh (bash) to
portable Python.

External, genuinely platform-specific tools (dpkg-query, pacman, pip,
npm, cargo, rustup, gem, getprop, git, findmnt/mount) are still shelled
out to via `environment.run_tool` and skip cleanly when absent -- same
convention as every other sarand analyzer. Everything that bash needed
`du`/`find -printf`/`numfmt`/`sha256sum` for for is now pure Python
(`walking.py`), which is the actual portability fix: those tools' flag
sets differ across GNU/BSD/BusyBox/Toybox userlands, while
`os.walk`/`hashlib` do not.

۱۲ بخش گزارش، از device-audit.sh (بش) به پایتون پرتابل پورت شده.

ابزارهای بیرونیِ واقعاً مخصوصِ پلتفرم (dpkg-query، pacman، pip، npm،
cargo، rustup، gem، getprop، git، findmnt/mount) همچنان از طریق
`environment.run_tool` صدا زده می‌شوند و در نبودشان تمیز رد می‌شوند --
دقیقاً همان قرارداد هر آنالایزر دیگر sarand. هر چیزی که بش برایش به
`du`/`find -printf`/`numfmt`/`sha256sum` نیاز داشت الان پایتون خالص است
(`walking.py`)، که فیکس واقعی پرتابل‌بودن همین است: مجموعه‌فلگ‌های آن
ابزارها بین GNU/BSD/BusyBox/Toybox فرق می‌کند، اما `os.walk`/`hashlib`
فرق نمی‌کند.
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sarand.device_report import environment as env
from sarand.device_report.classify import classify_path
from sarand.device_report.config import UNLIMITED, DeviceReportConfig
from sarand.device_report.walking import (
    find_dirs_named,
    is_excluded,
    iter_files,
    path_size_bytes,
    sha256_file,
)
from sarand.utils.fs import human_size

SCRIPT_VERSION = (
    "3.0.0"  # first sarand-native release; bash v2.3.1 was the last standalone one
)


@dataclass
class Report:
    """Accumulates markdown output plus cross-section bookkeeping."""

    lines: list[str] = field(default_factory=list)
    space_hogs: list[tuple[int, str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def write(self, text: str = "") -> None:
        self.lines.append(text)

    def section(self, title: str) -> None:
        self.write()
        self.write(f"## {title}")
        self.write()

    def subsection(self, title: str) -> None:
        self.write(f"### {title}")
        self.write()

    def fence_open(self) -> None:
        self.write("```")

    def fence_close(self) -> None:
        self.write("```")
        self.write()

    def record_space(self, num_bytes: int, path: str, label: str) -> None:
        if num_bytes > 0:
            self.space_hogs.append((num_bytes, path, label))

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def render(self) -> str:
        return "\n".join(self.lines) + "\n"


def _limit(rows: list, top_n: int) -> list:
    return rows if top_n == UNLIMITED else rows[:top_n]


def _read_proc_file(path: str) -> str | None:
    try:
        return Path(path).read_text(errors="replace")
    except OSError:
        return None


# --- 1. System overview --------------------------------------------------


def collect_system_info(report: Report, config: DeviceReportConfig) -> None:
    print("--> Collecting system overview...")
    report.section("1. System Overview")

    environment = env.detect_environment()
    uname = platform.uname()

    report.write(
        f"- Report generated: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')}`"
    )
    report.write(f"- Script version: `{SCRIPT_VERSION}`")
    report.write(f"- Detected environment: `{environment}`")
    report.write(f"- Effective user: `{_username()}`")
    report.write(f"- UID: `{os.getuid() if hasattr(os, 'getuid') else 'unknown'}`")
    report.write(f"- HOME: `{Path.home()}`")
    report.write(f"- Shell: `{os.environ.get('SHELL', 'unknown')}`")
    report.write(f"- Quick mode: `{'yes' if config.quick_mode else 'no'}`")
    top_display = "unlimited" if config.top_n == UNLIMITED else str(config.top_n)
    report.write(f"- Top rows: `{top_display}`")
    depth_display = (
        "unlimited" if config.max_depth == UNLIMITED else str(config.max_depth)
    )
    report.write(f"- Max depth: `{depth_display}`")
    report.write(f"- Stale threshold: `{config.old_days} days`")
    report.write(f"- Large-file threshold: `{config.min_file_size_mb} MB`")
    report.write(f"- Duplicate threshold: `{config.dup_min_size_mb} MB`")
    report.write("- Destructive operations: `none`")
    report.write("- Environment variables: `not collected`")
    report.write()
    report.write("### Scan Roots")
    report.write()
    for root in config.scan_roots:
        report.write(f"- `{root}`")
    if config.exclude_paths:
        report.write()
        report.write("### Excluded Paths")
        report.write()
        for excluded in config.exclude_paths:
            report.write(f"- `{excluded}`")
    report.write()

    report.write("**uname**")
    report.write()
    report.fence_open()
    report.write(
        f"{uname.system} {uname.node} {uname.release} {uname.version} {uname.machine}"
    )
    report.fence_close()

    os_release = _read_proc_file("/etc/os-release")
    report.write("**OS release**")
    report.write()
    report.fence_open()
    report.write((os_release or "(unavailable: /etc/os-release)").rstrip())
    report.fence_close()

    report.write("**Memory**")
    report.write()
    report.fence_open()
    ran, output = env.run_tool(Path.home(), "free", "-h")
    if ran:
        report.write(output.rstrip())
    else:
        report.write(_meminfo_fallback())
    report.fence_close()

    report.write("**CPU summary**")
    report.write()
    report.fence_open()
    ran, output = env.run_tool(Path.home(), "lscpu")
    if ran:
        report.write(output.rstrip())
    else:
        report.write(_cpuinfo_fallback())
    report.fence_close()


def _username() -> str:
    try:
        import pwd

        return pwd.getpwuid(os.getuid()).pw_name
    except (ImportError, KeyError, AttributeError):
        return os.environ.get("USER", "unknown")


def _meminfo_fallback() -> str:
    """Portable fallback for `free -h` via /proc/meminfo (any Linux
    kernel has this, including Android's -- useful when a minimal
    Termux/BusyBox install lacks the `free` binary itself)."""
    content = _read_proc_file("/proc/meminfo")
    if not content:
        return "(unavailable: free binary and /proc/meminfo both missing)"
    wanted = {"MemTotal", "MemFree", "MemAvailable", "SwapTotal", "SwapFree"}
    lines = []
    for line in content.splitlines():
        key = line.split(":", 1)[0].strip()
        if key in wanted:
            lines.append(line.strip())
    return "\n".join(lines) if lines else content.strip()


def _cpuinfo_fallback() -> str:
    """Portable fallback for `lscpu` via /proc/cpuinfo."""
    content = _read_proc_file("/proc/cpuinfo")
    if not content:
        return "(unavailable: lscpu binary and /proc/cpuinfo both missing)"
    model = ""
    count = 0
    for line in content.splitlines():
        if line.lower().startswith(("model name", "processor", "hardware")):
            if line.lower().startswith("processor"):
                count += 1
            elif not model and ":" in line:
                model = line.split(":", 1)[1].strip()
    machine = platform.machine()
    return (
        f"Architecture: {machine}\n"
        f"Model: {model or 'unknown'}\n"
        f"Logical CPUs: {count or 'unknown'}"
    )


# --- 2. Mounts -------------------------------------------------------------


def collect_mounts(report: Report, config: DeviceReportConfig) -> None:
    print("--> Collecting mounts and filesystems...")
    report.section("2. Filesystems, Mounts, and Inodes")

    for title, cmd in (
        ("Disk usage", ("df", "-hT")),
        ("Inode usage", ("df", "-ih")),
    ):
        report.write(f"**{title}**")
        report.write()
        report.fence_open()
        ran, output = env.run_tool(Path.home(), *cmd)
        report.write(output.rstrip() if ran else f"(command not available: {cmd[0]})")
        report.fence_close()

    report.write("**Mount table**")
    report.write()
    report.fence_open()
    ran, output = env.run_tool(
        Path.home(), "findmnt", "-o", "TARGET,SOURCE,FSTYPE,OPTIONS"
    )
    if not ran:
        ran, output = env.run_tool(Path.home(), "mount")
    if ran:
        report.write(output.rstrip())
    else:
        proc_mounts = _read_proc_file("/proc/mounts")
        report.write((proc_mounts or "(unavailable)").rstrip())
    report.fence_close()

    report.subsection("Important Paths")
    report.fence_open()
    report.write(f"{'path':<35} {'size':<12} {'status':<15}")
    for path_str in env.IMPORTANT_PATHS + (str(Path.home()),):
        path = Path(path_str)
        if not path.exists():
            continue
        try:
            usage = os.statvfs(path) if hasattr(os, "statvfs") else None
            size = human_size(usage.f_blocks * usage.f_frsize) if usage else "unknown"
        except OSError:
            size = "unknown"
        status = "readable" if os.access(path, os.R_OK) else "not readable"
        report.write(f"{path_str:<35} {size:<12} {status:<15}")
    report.fence_close()


# --- 3. Storage overview -----------------------------------------------


def collect_storage_overview(report: Report, config: DeviceReportConfig) -> None:
    print("--> Collecting storage overview...")
    report.section("3. Storage Overview")

    for root in config.scan_roots:
        if not root.is_dir():
            continue
        report.subsection(f"Top-level breakdown: {root}")
        entries: list[tuple[int, str]] = []
        try:
            children = [
                c for c in root.iterdir() if not is_excluded(c, config.exclude_paths)
            ]
        except OSError:
            children = []
        for child in children:
            num_bytes = path_size_bytes(child)
            entries.append((num_bytes, str(child)))
            report.record_space(num_bytes, str(child), "top-level")

        entries.sort(key=lambda e: e[0], reverse=True)
        report.fence_open()
        for num_bytes, path_str in _limit(entries, config.top_n):
            report.write(f"{human_size(num_bytes):>12}  {path_str}")
        report.fence_close()


# --- 4. Packages -----------------------------------------------------------


def collect_packages(report: Report, config: DeviceReportConfig) -> None:
    print("--> Collecting packages and caches...")
    report.section("4. Installed Packages and Package Caches")

    if env.tool_available("dpkg-query"):
        report.subsection("APT/dpkg Packages by Installed Size")
        report.fence_open()
        report.write(f"{'package':<50} {'installed-size':>12}")
        _ran, output = env.run_tool(
            Path.home(), "dpkg-query", "-Wf", "${Installed-Size}\\t${Package}\\n"
        )
        rows = []
        for line in output.splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2 and parts[0].strip().isdigit():
                rows.append((int(parts[0]), parts[1]))
        rows.sort(reverse=True)
        for size_kb, name in _limit(rows, config.top_n):
            report.write(f"{name:<50} {size_kb:>9} KB")
        report.fence_close()
        report.write(f"Total installed packages: {len(rows)}")
        report.write()

        apt_cache = Path("/var/cache/apt/archives")
        if apt_cache.is_dir():
            report.record_space(path_size_bytes(apt_cache), str(apt_cache), "APT cache")

    if env.tool_available("pacman"):
        ran, output = env.run_tool(Path.home(), "pacman", "-Q")
        count = len(output.splitlines()) if ran else 0
        report.write("**Pacman package count**")
        report.write()
        report.fence_open()
        report.write(str(count))
        report.fence_close()

        pacman_cache = Path("/var/cache/pacman/pkg")
        if pacman_cache.is_dir():
            cache_bytes = path_size_bytes(pacman_cache)
            report.write("**Pacman cache**")
            report.write()
            report.fence_open()
            report.write(f"{human_size(cache_bytes)}\t{pacman_cache}")
            report.fence_close()
            report.record_space(cache_bytes, str(pacman_cache), "Pacman cache")

    pip_cmd = env.pip_command()
    if pip_cmd:
        for title, args in (
            ("pip package list", (pip_cmd, "list", "--format=columns")),
            ("pip cache information", (pip_cmd, "cache", "info")),
        ):
            report.write(f"**{title}**")
            report.write()
            report.fence_open()
            _ran, output = env.run_tool(Path.home(), *args)
            report.write(output.rstrip())
            report.fence_close()

    for title, cmd in (
        ("npm global packages", ("npm", "list", "-g", "--depth=0")),
        ("Cargo-installed binaries", ("cargo", "install", "--list")),
        ("Rust toolchains", ("rustup", "toolchain", "list")),
        ("Ruby gems", ("gem", "list")),
    ):
        if env.tool_available(cmd[0]):
            report.write(f"**{title}**")
            report.write()
            report.fence_open()
            _ran, output = env.run_tool(Path.home(), *cmd)
            report.write(output.rstrip())
            report.fence_close()


# --- 5. Toolchain footprint -------------------------------------------------


def collect_toolchain(report: Report, config: DeviceReportConfig) -> None:
    print("--> Collecting toolchain and build artifacts...")
    report.section("5. Development Toolchain Footprint")

    candidates = [Path(c).expanduser() for c in env.TOOLCHAIN_CANDIDATES]
    pip_cmd = env.pip_command()
    if pip_cmd:
        _ran, cache_dir = env.run_tool(Path.home(), pip_cmd, "cache", "dir")
        cache_dir = cache_dir.strip()
        if cache_dir:
            candidates.append(Path(cache_dir))

    report.subsection("Known Toolchain and Cache Directories")
    report.fence_open()
    report.write(f"{'path':<55} {'size':>12}")
    for directory in candidates:
        if not directory.exists():
            continue
        num_bytes = path_size_bytes(directory)
        report.write(f"{directory!s:<55} {human_size(num_bytes):>12}")
        report.record_space(num_bytes, str(directory), "toolchain/cache")
    report.fence_close()

    report.subsection("Build Artifact Directories")
    report.fence_open()
    for root in config.scan_roots:
        if not root.is_dir():
            continue
        for found_dir in find_dirs_named(
            root,
            env.BUILD_ARTIFACT_DIR_NAMES,
            exclude_paths=config.exclude_paths,
            max_depth=config.max_depth,
        ):
            num_bytes = path_size_bytes(found_dir)
            report.write(f"{found_dir!s:<75} {human_size(num_bytes):>12}")
            report.record_space(num_bytes, str(found_dir), "build artifact")
    report.fence_close()


# --- 6. Android / Termux / NetHunter / Kali --------------------------------


def collect_android_termux_kali(report: Report, config: DeviceReportConfig) -> None:
    print("--> Collecting Android / Termux / NetHunter info...")
    report.section("6. Android / Termux / NetHunter / Kali Environment")

    if env.tool_available("getprop"):
        ran, output = env.run_tool(Path.home(), "getprop")
        if ran:
            report.subsection("Selected Android Properties")
            report.fence_open()
            for line in output.splitlines():
                prefixes = env.ANDROID_PROPERTY_PREFIXES
                if any(line.startswith(f"[{prefix}]:") for prefix in prefixes):
                    report.write(line)
            report.fence_close()

    ran, output = env.run_tool(Path.home(), "mount")
    if ran:
        storage_markers = (
            "/sdcard",
            "/storage",
            "/data",
            "/system",
            "/vendor",
            "/product",
        )
        relevant = [
            line
            for line in sorted(output.splitlines())
            if any(tok in line for tok in storage_markers)
        ]
        if relevant:
            report.write("**Relevant Android storage mounts**")
            report.write()
            report.fence_open()
            for line in relevant:
                report.write(line)
            report.fence_close()

    if Path("/data/data/com.termux").is_dir():
        report.subsection("Termux-specific Paths")
        report.fence_open()
        report.write(f"{'path':<55} {'size':>12}")
        for path_str in env.TERMUX_PATHS:
            path = Path(path_str)
            if not path.exists():
                continue
            num_bytes = path_size_bytes(path)
            report.write(f"{path_str:<55} {human_size(num_bytes):>12}")
            report.record_space(num_bytes, path_str, "Termux")
        report.fence_close()

    if Path("/data/local/nhsystem").is_dir():
        report.subsection("NetHunter Paths")
        report.fence_open()
        report.write(f"{'path':<60} {'size':>12}")
        for path_str in env.NETHUNTER_PATHS:
            path = Path(path_str)
            if not path.exists():
                continue
            num_bytes = path_size_bytes(path)
            report.write(f"{path_str:<60} {human_size(num_bytes):>12}")
            report.record_space(num_bytes, path_str, "NetHunter")
        report.fence_close()

    os_release = _read_proc_file("/etc/os-release")
    if os_release and "kali" in os_release.lower():
        report.subsection("Kali Indicators")
        report.fence_open()
        for line in os_release.splitlines():
            if line.split("=", 1)[0] in {
                "PRETTY_NAME",
                "NAME",
                "ID",
                "VERSION",
                "VERSION_ID",
                "VERSION_CODENAME",
            }:
                report.write(line)
        report.write()
        report.write("proot indicators:")
        for key, value in os.environ.items():
            if key.startswith(("PROOT", "TERMUX", "PREFIX", "ANDROID")):
                secret_markers = ("TOKEN", "KEY", "SECRET", "PASSWORD", "PASS", "AUTH")
                if any(s in key.upper() for s in secret_markers):
                    value = "<redacted>"
                report.write(f"{key}={value}")
        report.fence_close()


# --- 7. Git repositories -----------------------------------------------


def collect_git_repos(report: Report, config: DeviceReportConfig) -> None:
    print("--> Collecting Git repositories...")
    report.section("7. Git Repositories")

    report.fence_open()
    report.write(f"{'repository':<65} {'size':>12}  {'status':<24}")
    for root in config.scan_roots:
        if not root.is_dir():
            continue
        for git_dir in find_dirs_named(
            root,
            {".git"},
            exclude_paths=config.exclude_paths,
            max_depth=config.max_depth,
        ):
            repo = git_dir.parent
            if not repo.is_dir():
                continue
            num_bytes = path_size_bytes(repo)
            status = "unknown"
            if env.tool_available("git"):
                _rc, output, _d = _git_status(repo)
                status = "clean" if output == "" else "modified"
            report.write(f"{repo!s:<65} {human_size(num_bytes):>12}  {status:<24}")
            report.record_space(num_bytes, str(repo), "Git repository")
    report.fence_close()


def _git_status(repo: Path) -> tuple[int, str, float]:
    from sarand.utils.command import run_cmd

    return run_cmd(
        ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"],
        repo,
        timeout=15,
    )


# --- 8. Largest individual files -------------------------------------------


def collect_large_files(report: Report, config: DeviceReportConfig) -> None:
    print("--> Collecting largest files...")
    report.section("8. Largest Individual Files")

    min_bytes = config.min_file_size_bytes
    report.write(f"Threshold: {config.min_file_size_mb} MB ({min_bytes} bytes)")
    report.write()
    report.fence_open()

    candidates: list[tuple[int, str]] = []
    for root in config.scan_roots:
        if not root.is_dir():
            continue
        for fp in iter_files(
            root, exclude_paths=config.exclude_paths, max_depth=config.max_depth
        ):
            try:
                size = fp.stat().st_size
            except OSError:
                continue
            if size > min_bytes:
                candidates.append((size, str(fp)))

    candidates.sort(reverse=True)
    for size, path_str in _limit(candidates, config.top_n):
        report.write(f"{human_size(size):>12}  {path_str}")
    report.fence_close()


# --- 9. Duplicate files ------------------------------------------------


def collect_duplicates(report: Report, config: DeviceReportConfig) -> None:
    print("--> Collecting duplicate files...")
    report.section("9. Duplicate Files")

    if config.quick_mode:
        report.write("Skipped because quick mode is enabled.")
        report.write()
        return

    min_bytes = config.dup_min_size_bytes
    by_size: dict[int, list[str]] = {}
    for root in config.scan_roots:
        if not root.is_dir():
            continue
        for fp in iter_files(
            root, exclude_paths=config.exclude_paths, max_depth=config.max_depth
        ):
            try:
                size = fp.stat().st_size
            except OSError:
                continue
            if size > min_bytes:
                by_size.setdefault(size, []).append(str(fp))

    candidate_count = sum(len(v) for v in by_size.values())

    report.subsection("Duplicate Detection")
    report.write(f"- Minimum size: `{config.dup_min_size_mb} MB`")
    report.write(f"- Candidate files: `{candidate_count}`")
    report.write("- Algorithm: group by size → SHA-256\n")
    report.fence_open()

    if candidate_count == 0:
        report.write("No duplicate candidates found.")
        report.fence_close()
        return

    total_wasted = 0
    for size, paths in by_size.items():
        if len(paths) < 2:
            continue
        by_hash: dict[str, list[str]] = {}
        for p in paths:
            digest = sha256_file(Path(p))
            if digest is None:
                report.warn(f"Could not read file for hashing: {p}")
                continue
            by_hash.setdefault(digest, []).append(p)
        for group in by_hash.values():
            if len(group) > 1:
                report.write(
                    f"Duplicate group: {len(group)} files, {human_size(size)} each"
                )
                for p in group:
                    report.write(f"  - {p}")
                total_wasted += size * (len(group) - 1)

    report.write(f"Estimated reclaimable duplicate space: {human_size(total_wasted)}")
    report.fence_close()


# --- 10. Stale files ---------------------------------------------------


def collect_stale_files(report: Report, config: DeviceReportConfig) -> None:
    print("--> Collecting stale files...")
    report.section("10. Stale Files")

    if config.quick_mode:
        report.write("Skipped because quick mode is enabled.")
        report.write()
        return

    report.write(f"Threshold: {config.old_days} days")
    report.write()
    report.fence_open()

    cutoff = datetime.now(timezone.utc).timestamp() - (config.old_days * 86400)
    candidates: list[tuple[int, str, str]] = []
    for root in config.scan_roots:
        if not root.is_dir():
            continue
        for fp in iter_files(
            root, exclude_paths=config.exclude_paths, max_depth=config.max_depth
        ):
            try:
                st = fp.stat()
            except OSError:
                continue
            if st.st_mtime < cutoff:
                date_str = datetime.fromtimestamp(
                    st.st_mtime, tz=timezone.utc
                ).strftime("%Y-%m-%d")
                candidates.append((st.st_size, date_str, str(fp)))

    candidates.sort(reverse=True)
    for size, date_str, path_str in _limit(candidates, config.top_n):
        report.write(f"{human_size(size):>12}  {date_str:<12}  {path_str}")
    report.fence_close()

    report.write(
        "> Stale files are evidence only. Age alone is not a deletion recommendation."
    )
    report.write()


# --- 11. Downloads -------------------------------------------------------


def collect_downloads(report: Report, config: DeviceReportConfig) -> None:
    print("--> Collecting downloads and archives...")
    report.section("11. Downloads and Archives")

    dl_dir = None
    for candidate in env.DOWNLOAD_CANDIDATES:
        path = Path(candidate).expanduser()
        if path.is_dir():
            dl_dir = path
            break

    if dl_dir is None:
        report.write("No Downloads directory found among known locations.")
        report.write()
        return

    report.record_space(path_size_bytes(dl_dir), str(dl_dir), "Downloads")

    report.subsection("Largest Download Entries")
    report.fence_open()
    try:
        entries = [(path_size_bytes(c), str(c)) for c in dl_dir.iterdir()]
    except OSError:
        entries = []
    entries.sort(reverse=True)
    for size, path_str in _limit(entries, config.top_n):
        report.write(f"{human_size(size):>12}  {path_str}")
    report.fence_close()

    report.subsection("Archive Files")
    report.fence_open()
    archives = []
    try:
        for child in dl_dir.iterdir():
            if child.is_file() and child.suffix.lower() in env.ARCHIVE_EXTENSIONS:
                try:
                    st = child.stat()
                except OSError:
                    continue
                date_str = datetime.fromtimestamp(
                    st.st_mtime, tz=timezone.utc
                ).strftime("%Y-%m-%d")
                archives.append((date_str, st.st_size, str(child)))
    except OSError:
        pass
    archives.sort(reverse=True)
    for date_str, size, path_str in archives:
        report.write(f"{date_str}  {size} bytes  {path_str}")
    report.fence_close()


# --- 12. Executive summary -----------------------------------------------


def write_summary(report: Report, config: DeviceReportConfig) -> None:
    print("--> Writing executive summary...")
    report.section("12. Executive Summary")

    report.write(f"- Space records collected: `{len(report.space_hogs)}`")
    report.write("- This report is evidence, not an automatic deletion plan.")
    report.write("- No destructive operation was performed.")
    report.write()
    report.write("### Risk Classification")
    report.write()
    report.write("| Classification | Meaning |")
    report.write("|---|---|")
    report.write(
        "| `LIKELY_RECLAIMABLE` | Usually generated or rebuildable data; verify first. |"
    )
    report.write(
        "| `SAFE_TO_REVIEW` | Usually user-controlled or cache/archive content; inspect first. |"
    )
    report.write("| `REQUIRES_REVIEW` | No safe automated conclusion. |")
    report.write(
        "| `DO_NOT_DELETE_AUTOMATICALLY` | Potentially important development or user data. |"
    )
    report.write("| `SYSTEM_CRITICAL` | Treat as protected system content. |")
    report.write()
    report.write("### Top Space Users")
    report.write()
    report.fence_open()
    report.write(f"{'size':>12}  {'classification':<28}  {'category':<24}  path")

    seen: set[str] = set()
    deduped = []
    for num_bytes, path_str, label in sorted(report.space_hogs, reverse=True):
        if path_str in seen:
            continue
        seen.add(path_str)
        deduped.append((num_bytes, path_str, label))

    for num_bytes, path_str, label in _limit(deduped, config.top_n):
        report.write(
            f"{human_size(num_bytes):>12}  {classify_path(path_str):<28}  {label:<24}  {path_str}"
        )
    report.fence_close()

    report.subsection("Warnings and Limitations")
    if report.warnings:
        report.fence_open()
        for message in report.warnings:
            report.write(message)
        report.fence_close()
    else:
        report.write("No runtime warnings were recorded.")
        report.write()

    report.write("### Cleanup Decision Rules")
    report.write()
    for i, rule in enumerate(
        [
            "Do not delete anything solely because it is large.",
            "Do not delete anything solely because it is old.",
            "Prefer rebuildable caches and project artifacts as first review candidates.",
            (
                "Verify active projects before removing `target`, `build`, "
                "`node_modules`, `.venv`, or similar directories."
            ),
            (
                "Treat Git repositories, Android system paths, package databases, "
                "and runtime directories as protected until explicitly reviewed."
            ),
            "Duplicate groups require keeping at least one verified copy.",
            "A reclaimable-space estimate is not a deletion command or guarantee.",
            (
                "Environment variables are intentionally excluded to avoid "
                "leaking credentials into the report."
            ),
            (
                "Android properties are intentionally limited to "
                "storage/environment-relevant fields."
            ),
        ],
        start=1,
    ):
        report.write(f"{i}. {rule}")
    report.write()
    report.write(f"> Generated by `sarand.device_report {SCRIPT_VERSION}`.")


SECTIONS = (
    collect_system_info,
    collect_mounts,
    collect_storage_overview,
    collect_packages,
    collect_toolchain,
    collect_android_termux_kali,
    collect_git_repos,
    collect_large_files,
    collect_duplicates,
    collect_stale_files,
    collect_downloads,
    write_summary,
)


def generate_report(config: DeviceReportConfig) -> str:
    report = Report()
    report.write("# Device Storage & Environment Audit")
    report.write()
    report.write("> Read-only report generated for evidence-based cleanup review.")
    report.write("> No files were deleted or modified by this script.")
    report.write(f"> sarand.device_report version: `{SCRIPT_VERSION}`")

    for section_fn in SECTIONS:
        section_fn(report, config)

    return report.render()
