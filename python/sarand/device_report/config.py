"""Configuration and CLI-argument resolution for the device-report subsystem.

پیکربندی و تبدیل آرگومان‌های CLI برای زیرسیستم device-report.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_TOP_N = 30
DEFAULT_OLD_DAYS = 180
DEFAULT_MIN_FILE_SIZE_MB = 50.0
DEFAULT_DUP_MIN_SIZE_MB = 5.0
DEFAULT_MIN_TOP_SPACE_MB = 1.0

# 0 means "no limit" for both of these, matching the original bash
# script's own convention for --max-depth -- reused here for --top so
# --full has one consistent meaning across both.
#
# صفر یعنی «بدون محدودیت»، برای هر دو -- دقیقاً همان قراردادی که خودِ
# اسکریپت بش برای --max-depth داشت، اینجا برای --top هم استفاده شده تا
# --full یک معنای یکدست در هر دو داشته باشد.
UNLIMITED = 0


@dataclass
class DeviceReportConfig:
    """Resolved configuration for one device-report run."""

    output_file: Path
    scan_roots: list[Path]
    exclude_paths: list[str] = field(default_factory=list)
    quick_mode: bool = False
    top_n: int = DEFAULT_TOP_N
    old_days: int = DEFAULT_OLD_DAYS
    min_file_size_mb: float = DEFAULT_MIN_FILE_SIZE_MB
    dup_min_size_mb: float = DEFAULT_DUP_MIN_SIZE_MB
    max_depth: int = UNLIMITED
    min_top_space_mb: float = DEFAULT_MIN_TOP_SPACE_MB
    expand_aggregates: bool = False
    summary_only: bool = False

    @property
    def min_file_size_bytes(self) -> int:
        return int(self.min_file_size_mb * 1024 * 1024)

    @property
    def dup_min_size_bytes(self) -> int:
        return int(self.dup_min_size_mb * 1024 * 1024)

    @property
    def min_top_space_bytes(self) -> int:
        return int(self.min_top_space_mb * 1024 * 1024)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m sarand.device_report.command",
        description=(
            "Read-only storage and environment inventory for AI-assisted "
            "cleanup review. Never deletes, moves, modifies, chmods, "
            "chowns, or installs anything."
        ),
    )
    parser.add_argument("-o", "--output", metavar="PATH", help="Output report path")
    parser.add_argument(
        "-r",
        "--root",
        action="append",
        dest="roots",
        metavar="DIR",
        help="Extra scan root; may be repeated",
    )
    parser.add_argument(
        "-x",
        "--exclude",
        action="append",
        dest="excludes",
        metavar="PATH",
        help="Exclude path from scans; may be repeated",
    )
    parser.add_argument(
        "-q",
        "--quick",
        action="store_true",
        help="Skip duplicate and stale-file scans",
    )
    # --full: the opposite end of --quick. Forces duplicate/stale scans
    # on even if --quick was also passed, and removes the --top row cap
    # (shows every match instead of the top N) -- but an explicit --top
    # still wins over --full, same rule sarand's own --full uses for
    # --max-depth/--max-entries (see config.py).
    #
    # --full: نقطه‌ی مقابل --quick. حتی اگر --quick هم داده شده باشد،
    # اسکن duplicate/stale را روشن می‌کند، و سقف ردیف --top را حذف
    # می‌کند (همه‌ی موارد را نشان می‌دهد نه فقط N تای برتر) -- اما یک
    # --top صریح همچنان بر --full غالب است، دقیقاً همان قاعده‌ای که
    # --full خودِ sarand برای --max-depth/--max-entries دارد.
    parser.add_argument(
        "--full",
        action="store_true",
        help=(
            "Maximum-completeness report: always runs duplicate and "
            "stale-file scans (overrides --quick) and removes the --top "
            "row cap so every match is listed, not just the top N"
        ),
    )
    parser.add_argument(
        "-n", "--top", type=int, metavar="N", help="Number of rows in top-space tables"
    )
    parser.add_argument(
        "-d", "--old-days", type=int, metavar="N", help="Stale-file threshold in days"
    )
    parser.add_argument(
        "-m",
        "--min-file-size",
        type=float,
        metavar="MB",
        help="Minimum large-file size",
    )
    parser.add_argument(
        "-u",
        "--dup-min-size",
        type=float,
        metavar="MB",
        help="Minimum duplicate-scan size",
    )
    parser.add_argument(
        "-D",
        "--max-depth",
        type=int,
        metavar="N",
        help="Maximum scan depth (0 = unlimited)",
    )
    # Feedback-driven flags (sarand-report-feedback.md): a real run
    # produced a 5+ MiB report, ~95% of it noise (thousands of tiny
    # __pycache__-style cache dirs listed one by one, and negligible
    # KB-sized entries cluttering the Executive Summary table).
    #
    # فلگ‌های برخاسته از بازخورد (sarand-report-feedback.md): یک اجرای
    # واقعی گزارشی ۵+ مگابایتی تولید کرد، حدود ۹۵٪ آن نویز بود (هزاران
    # پوشه‌ی کش کوچک شبیه __pycache__ که تک‌تک لیست شده بودند، و
    # موارد چند-کیلوبایتیِ ناچیز که جدول Executive Summary را شلوغ
    # کرده بودند).
    parser.add_argument(
        "--min-top-space",
        type=float,
        metavar="MB",
        help=(
            "Minimum size for an entry in the Executive Summary's Top "
            "Space Users table, 0 = no filter (default 1.0)"
        ),
    )
    parser.add_argument(
        "--expand-aggregates",
        action="store_true",
        help=(
            "List every __pycache__/.mypy_cache/.pytest_cache/.ruff_cache "
            "instance individually instead of one aggregated summary line "
            "per pattern"
        ),
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help=(
            "Only render section 1 (System Overview) and section 12 "
            "(Executive Summary) -- all scanning still happens so the "
            "summary is accurate, but the detailed per-section listings "
            "are omitted from the output. Mutually exclusive with --full."
        ),
    )
    return parser


def resolve_config(args: argparse.Namespace) -> DeviceReportConfig:
    full = bool(args.full)
    summary_only = bool(args.summary_only)
    if full and summary_only:
        raise ValueError(
            "--full and --summary-only are mutually exclusive "
            "(--full asks for maximum detail, --summary-only for minimum)."
        )

    roots = [Path(r).expanduser() for r in (args.roots or [])]
    if not roots:
        home = Path.home()
        if home.is_dir():
            roots.append(home)
        sdcard = Path("/sdcard")
        if sdcard.is_dir():
            roots.append(sdcard)
    roots = [r for r in roots if r.is_dir()]
    if not roots:
        raise ValueError("No valid scan roots were found.")

    if args.output:
        output_file = Path(args.output).expanduser()
    else:
        from datetime import datetime, timezone

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        output_file = Path.home() / f"device-report-{timestamp}.md"

    top_n = args.top if args.top is not None else (UNLIMITED if full else DEFAULT_TOP_N)
    max_depth = args.max_depth if args.max_depth is not None else UNLIMITED
    min_top_space_mb = (
        args.min_top_space
        if args.min_top_space is not None
        else (0.0 if full else DEFAULT_MIN_TOP_SPACE_MB)
    )

    return DeviceReportConfig(
        output_file=output_file,
        scan_roots=roots,
        exclude_paths=list(args.excludes or []),
        quick_mode=False if full else bool(args.quick),
        top_n=top_n,
        old_days=args.old_days if args.old_days is not None else DEFAULT_OLD_DAYS,
        min_file_size_mb=(
            args.min_file_size
            if args.min_file_size is not None
            else DEFAULT_MIN_FILE_SIZE_MB
        ),
        dup_min_size_mb=(
            args.dup_min_size
            if args.dup_min_size is not None
            else DEFAULT_DUP_MIN_SIZE_MB
        ),
        max_depth=max_depth,
        min_top_space_mb=min_top_space_mb,
        expand_aggregates=bool(args.expand_aggregates) or full,
        summary_only=summary_only,
    )
