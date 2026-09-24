#!/usr/bin/env python3
"""Real runtime/peak-memory/report-size/source-size measurements for
backlog item 9 ("Report Size and Low-Memory Operation"), section 9.1's
"Required measurements": small/medium/large project, on a real
(ideally constrained) device -- not guessed, not simulated.

This is a dev tool, not part of the sarand package: it shells out to
the installed `sarand` command twice per project (`--full`, then
`--full --no-source`) and reports what actually happened, using GNU
`time -v` for accurate peak RSS when available (Linux only, which
covers this project's own dev machines -- Kali NetHunter proot and
Arch -- see AGENTS.md's dev-environment notes; Windows/macOS were
never a target for this script). Without `time -v` it still reports
wall-clock runtime and file sizes, and says plainly that peak memory
could not be measured rather than guessing.

Usage:
    python scripts/benchmark_report.py PROJECT [PROJECT ...]
    python scripts/benchmark_report.py --skip-tests PROJECT [PROJECT ...]

Each PROJECT is a directory sarand can scan. Pick a genuine small/
medium/large spread (e.g. a small script's repo, sarand itself,
something bigger you have lying around) to get the DoD's required
spread of data points, not just one.

اندازه‌گیری واقعیِ زمان اجرا/اوج حافظه/حجم گزارش/حجم سورس برای آیتم ۹
backlog («حجم گزارش و عملکرد کم‌حافظه»)، بخش «اندازه‌گیری‌های لازم» در
۹.۱: پروژه‌ی کوچک/متوسط/بزرگ، روی یک دستگاه واقعی (ترجیحاً محدود) --
نه حدس‌زده، نه شبیه‌سازی‌شده.

این یک ابزار توسعه است، نه بخشی از بسته‌ی sarand: دستور نصب‌شده‌ی
`sarand` را به‌ازای هر پروژه دوبار اجرا می‌کند (`--full`، سپس
`--full --no-source`) و آنچه واقعاً رخ داده را گزارش می‌کند، با
استفاده از `time -v` گنو برای اوج RSS دقیق در صورت وجود (فقط لینوکس --
که همان ماشین‌های توسعه‌ی خودِ این پروژه را پوشش می‌دهد -- proot
Kali NetHunter و Arch؛ Windows/macOS هرگز هدف این اسکریپت نبوده‌اند).
بدون `time -v` باز هم زمان اجرا و حجم فایل‌ها را گزارش می‌کند، و صریحاً
می‌گوید اوج حافظه قابل اندازه‌گیری نبود، به‌جای حدس زدن.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess  # nosec B404 -- fixed argv only, this is a dev tool
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

_MAXRSS_RE = re.compile(r"Maximum resident set size \(kbytes\):\s*(\d+)")
_ELAPSED_RE = re.compile(r"Elapsed \(wall clock\) time.*?:\s*([\d:.]+)")


@dataclass
class RunResult:
    ok: bool
    wall_seconds: float
    peak_kb: int | None  # None when /usr/bin/time -v was not available
    report_bytes: int
    detail: str = ""


def _parse_gnu_time_elapsed(text: str) -> float | None:
    """GNU time prints elapsed as `[h:]mm:ss[.cc]`; convert to seconds."""
    match = _ELAPSED_RE.search(text)
    if not match:
        return None
    values = [float(p) for p in match.group(1).split(":")]
    while len(values) < 3:
        values.insert(0, 0.0)
    hours, minutes, seconds = values
    return hours * 3600 + minutes * 60 + seconds


def _run_once(sarand_argv: list[str], gnu_time: str | None) -> RunResult:
    start = time.perf_counter()
    if gnu_time:
        proc = subprocess.run(  # nosec B603
            [gnu_time, "-v", *sarand_argv],
            capture_output=True,
            text=True,
            check=False,
        )
        wall = time.perf_counter() - start
        stderr = proc.stderr or ""
        maxrss_match = _MAXRSS_RE.search(stderr)
        peak_kb = int(maxrss_match.group(1)) if maxrss_match else None
        elapsed = _parse_gnu_time_elapsed(stderr)
        return RunResult(
            ok=proc.returncode == 0,
            wall_seconds=elapsed if elapsed is not None else wall,
            peak_kb=peak_kb,
            report_bytes=0,  # filled in by the caller, who knows the path
            detail="" if proc.returncode == 0 else stderr[-2000:],
        )
    proc = subprocess.run(  # nosec B603
        sarand_argv, capture_output=True, text=True, check=False
    )
    wall = time.perf_counter() - start
    return RunResult(
        ok=proc.returncode == 0,
        wall_seconds=wall,
        peak_kb=None,
        report_bytes=0,
        detail="" if proc.returncode == 0 else (proc.stderr or "")[-2000:],
    )


def _human_kb(kb: int | None) -> str:
    if kb is None:
        return "n/a"
    mb = kb / 1024
    return f"{mb:.1f} MiB" if mb >= 1 else f"{kb} KiB"


def _human_bytes(n: int) -> str:
    mb = n / (1024 * 1024)
    return f"{mb:.2f} MiB" if mb >= 1 else f"{n / 1024:.1f} KiB"


def benchmark_project(
    project: Path,
    out_dir: Path,
    sarand_cmd: list[str],
    gnu_time: str | None,
    skip_tests: bool,
) -> None:
    print(f"\n## {project}\n")
    common = [*sarand_cmd, "--project", str(project), "--full", "-d", str(out_dir)]
    if skip_tests:
        common.append("--skip-tests")

    rows: list[tuple[str, RunResult]] = []
    for label, extra, name in (
        ("--full", [], "bench-full.md"),
        ("--full --no-source", ["--no-source"], "bench-nosource.md"),
    ):
        report_path = out_dir / name
        result = _run_once(
            [*common, "--format", "markdown", "-o", name, *extra], gnu_time
        )
        result.report_bytes = report_path.stat().st_size if report_path.exists() else 0
        rows.append((label, result))

    print("| Mode | Wall time | Peak RSS | Report size |")
    print("|---|---|---|---|")
    for label, r in rows:
        status = "" if r.ok else " (FAILED -- see below)"
        print(
            f"| {label}{status} | {r.wall_seconds:.1f}s | {_human_kb(r.peak_kb)} "
            f"| {_human_bytes(r.report_bytes)} |"
        )
    full_bytes = rows[0][1].report_bytes
    nosource_bytes = rows[1][1].report_bytes
    if rows[0][1].ok and rows[1][1].ok:
        print(
            f"\nEmbedded-source contribution to report size: "
            f"~{_human_bytes(max(0, full_bytes - nosource_bytes))}"
        )
    for label, r in rows:
        if not r.ok:
            print(f"\n`{label}` failed:\n```\n{r.detail}\n```")
    if gnu_time is None:
        print(
            "\n(Peak RSS is n/a: `time -v` not found. Install GNU time -- "
            "`pacman -S time` on Arch, `apt install time` on Debian/Kali/"
            "Termux -- and rerun for real memory numbers.)"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "projects", nargs="+", type=Path, help="Project directories to scan"
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Pass --skip-tests to sarand (faster iteration; the DoD's real "
        "numbers should eventually come from a run WITHOUT this)",
    )
    parser.add_argument(
        "--sarand",
        default=None,
        help="How to invoke sarand (default: the installed 'sarand' command, "
        "or 'python -m sarand' as a fallback if that is not on PATH)",
    )
    args = parser.parse_args(argv)

    installed_sarand = shutil.which("sarand")
    if args.sarand:
        sarand_cmd = [args.sarand]
    elif installed_sarand:
        sarand_cmd = [installed_sarand]
    else:
        sarand_cmd = [sys.executable, "-m", "sarand"]
    gnu_time = shutil.which("time") or (
        "/usr/bin/time" if Path("/usr/bin/time").exists() else None
    )
    if gnu_time is None:
        print(
            "NOTE: GNU `time -v` not found -- peak memory will be reported as "
            "n/a, not guessed. See the note after each project below.",
            file=sys.stderr,
        )

    with tempfile.TemporaryDirectory(prefix="sarand-bench-") as tmp:
        out_dir = Path(tmp)
        for project in args.projects:
            benchmark_project(project, out_dir, sarand_cmd, gnu_time, args.skip_tests)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
