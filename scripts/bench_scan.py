#!/usr/bin/env python3
"""Measure the Rust scan core against the pure-Python scan (audit finding B7).

The question this script answers with data, not opinion: how much faster is
`sarand._core.scan_project` than `rust_bridge._pure_python_scan` on a real
machine, and what does each one cost in memory? The result feeds owner
decision D3 (keep the Rust core or not). It changes nothing in the package.

Each engine runs in its own fresh process, so the peak memory of one never
pollutes the other. Per target: one warm-up run, then N timed runs (default 5),
and the median is reported.

Targets:
  * a synthetic tree built in a temporary directory (default 10000 small files,
    nested directories, plus ignored directories that both engines must skip);
  * every `--path DIR` you give (for example the sarand repository itself).

Usage (inside the project's virtual environment, after `maturin develop`):

    python3 scripts/bench_scan.py
    python3 scripts/bench_scan.py --path . --runs 5
    python3 scripts/bench_scan.py --files 20000 --json

Run it on each device and paste the whole output back.

Note on file counts: the Rust walker also honours the project's own `.gitignore`
files and the fallback does not, so on a real project the two lists can differ;
the table says so instead of hiding it. The synthetic tree has no `.gitignore`,
so there the two lists must be identical.

این اسکریپت با داده جواب می‌دهد که هسته‌ی Rust چقدر از اسکن پایتونی سریع‌تر است
و هرکدام چقدر حافظه می‌خواهند؛ نتیجه به تصمیم D3 (نگه‌داشتن هسته‌ی Rust) کمک
می‌کند. هیچ‌چیز در بسته را تغییر نمی‌دهد. هر موتور در پردازش جداگانه اجرا می‌شود
تا اوج حافظه‌ی یکی دیگری را آلوده نکند. روی هر دستگاه اجرا کنید و کل خروجی را
بفرستید.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess  # nosec B404
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

DEFAULT_FILES = 10_000
DEFAULT_RUNS = 5
ENGINES = ("rust", "python")

# Directories both engines must prune; they get extra files that must never show up.
# دایرکتوری‌هایی که هر دو موتور باید هرس کنند؛ فایل‌هایشان نباید در نتیجه بیاید.
_IGNORED_DIRS = ("node_modules", "target", "__pycache__")
_IGNORED_FILES_EACH = 200

_BODY = (
    "# sample file for the scan benchmark\n"
    "\n"
    "def handler(value):\n"
    "    # a comment line\n"
    "    return value + 1\n"
)


def build_tree(root: Path, files: int) -> int:
    """Create `files` small files in nested directories; return how many are visible.

    Deterministic: no randomness, so two devices scan the same tree.
    ساخت قطعی (بدون تصادف) تا دو دستگاه یک درخت یکسان را اسکن کنند.
    """
    for index in range(files):
        directory = root / f"pkg{index % 10}" / f"mod{index % 50}" / f"sub{index % 7}"
        directory.mkdir(parents=True, exist_ok=True)
        suffix = (".py", ".rs", ".md", ".txt")[index % 4]
        body = _BODY + f"# file number {index}\n"
        (directory / f"file{index}{suffix}").write_text(body, encoding="utf-8")

    for name in _IGNORED_DIRS:
        directory = root / name
        directory.mkdir(parents=True, exist_ok=True)
        for index in range(_IGNORED_FILES_EACH):
            (directory / f"ignored{index}.txt").write_text("x\n", encoding="utf-8")
    return files


def median(values: list[float]) -> float:
    """Median of a non-empty list.

    میانه‌ی یک فهرست ناتهی.
    """
    return statistics.median(values)


def _peak_rss_mib() -> float | None:
    """Peak resident memory of this process in MiB, or None where unavailable.

    اوج حافظه‌ی این پردازش به MiB؛ جایی که در دسترس نیست None.
    """
    # Windows has no `resource` module; the platform check is also the form
    # mypy understands.
    # ویندوز ماژول resource ندارد؛ mypy هم همین شکل بررسی را می‌فهمد.
    if sys.platform == "win32":
        return None
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux reports KiB, macOS reports bytes.
    # لینوکس KiB می‌دهد، macOS بایت.
    if sys.platform == "darwin":
        return peak / (1024 * 1024)
    return peak / 1024


def run_worker(engine: str, root: Path, runs: int) -> dict[str, Any]:
    """Time one engine inside this process and describe the outcome as a dict.

    زمان‌گیری یک موتور داخل همین پردازش؛ خروجی یک dict.
    """
    from sarand import rust_bridge
    from sarand.constants import HASH_MAX_BYTES, IGNORE_DIRS, MAX_HASH_FILES

    ignore = frozenset(IGNORE_DIRS)

    def scan() -> list[Any]:
        if engine == "rust":
            core = rust_bridge._core
            names = sorted(ignore)
            return list(
                core.scan_project(str(root), names, HASH_MAX_BYTES, MAX_HASH_FILES)
            )
        return list(
            rust_bridge._pure_python_scan(root, ignore, HASH_MAX_BYTES, MAX_HASH_FILES)
        )

    if engine == "rust" and not rust_bridge.RUST_CORE_AVAILABLE:
        return {"engine": engine, "available": False}

    scan()  # warm-up: fills the OS file cache for both engines alike
    timings: list[float] = []
    records: list[Any] = []
    for _ in range(runs):
        start = time.perf_counter()
        records = scan()
        timings.append(time.perf_counter() - start)

    paths = sorted(str(record["rel_path"]) for record in records)
    digest = hashlib.sha256("\n".join(paths).encode("utf-8")).hexdigest()
    return {
        "engine": engine,
        "available": True,
        "timings": timings,
        "median": median(timings),
        "files": len(records),
        "paths_sha256": digest,
        "peak_rss_mib": _peak_rss_mib(),
    }


def measure(engine: str, root: Path, runs: int) -> dict[str, Any]:
    """Run one engine in a fresh child process and parse its JSON answer.

    اجرای یک موتور در پردازش فرزند تازه و خواندن پاسخ JSON آن.
    """
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        engine,
        "--root",
        str(root),
        "--runs",
        str(runs),
    ]
    # Fixed argument list, our own interpreter and our own file: nothing external.
    # فهرست آرگومان ثابت، مفسر و فایل خودمان: هیچ ورودی بیرونی نیست.
    completed = subprocess.run(  # nosec B603
        command, capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or "no error output"
        return {"engine": engine, "available": False, "error": message}
    result: dict[str, Any] = json.loads(completed.stdout)
    return result


def compare(rust: dict[str, Any], python: dict[str, Any]) -> dict[str, Any]:
    """Speed-up and whether both engines listed the same files.

    ضریب سرعت و اینکه هر دو موتور یک فهرست فایل داده‌اند یا نه.
    """
    if not (rust.get("available") and python.get("available")):
        return {"speedup": None, "same_files": None}
    speedup = python["median"] / rust["median"] if rust["median"] > 0 else None
    same = (
        rust["files"] == python["files"]
        and rust["paths_sha256"] == python["paths_sha256"]
    )
    return {"speedup": speedup, "same_files": same}


def _cell(value: float | None, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def render_table(results: list[dict[str, Any]]) -> str:
    """Markdown table for pasting into chat or AGENTS history.

    جدول مارک‌داون برای چسباندن در گفتگو یا تاریخچه.
    """
    lines = [
        "| Target | Engine | Files | Median s | Min s | Max s | Peak RSS MiB |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for entry in results:
        for engine in ENGINES:
            row = entry[engine]
            if not row.get("available"):
                reason = row.get("error", "core not built")
                lines.append(f"| {entry['target']} | {engine} | - | {reason} | | | |")
                continue
            timings = row["timings"]
            lines.append(
                f"| {entry['target']} | {engine} | {row['files']} "
                f"| {_cell(row['median'])} | {_cell(min(timings))} "
                f"| {_cell(max(timings))} | {_cell(row['peak_rss_mib'], 1)} |"
            )
    lines.append("")
    for entry in results:
        verdict = entry["comparison"]
        speedup = verdict["speedup"]
        same = verdict["same_files"]
        speed_text = "n/a" if speedup is None else f"{speedup:.1f}x"
        same_text = "n/a" if same is None else ("yes" if same else "NO")
        lines.append(
            f"- {entry['target']}: Rust speed-up over the fallback: "
            f"{speed_text}; same file list: {same_text}"
        )
    return "\n".join(lines)


def environment() -> dict[str, Any]:
    """Facts that make a pasted result self-describing.

    اطلاعاتی که خروجی چسبانده‌شده را خودتوضیح می‌کند.
    """
    return {
        "python": platform.python_version(),
        "machine": platform.machine(),
        "system": platform.system(),
        "cpus": os.cpu_count(),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").split("\n", maxsplit=1)[0]
    )
    parser.add_argument("--files", type=int, default=DEFAULT_FILES)
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--path", action="append", default=[], metavar="DIR")
    parser.add_argument("--no-synthetic", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--worker", choices=ENGINES, help=argparse.SUPPRESS)
    parser.add_argument("--root", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.runs < 1 or args.files < 1:
        parser.error("--runs and --files must be at least 1")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.worker:
        print(json.dumps(run_worker(args.worker, args.root, args.runs)))
        return 0

    targets: list[tuple[str, Path]] = [
        (str(Path(item)), Path(item).resolve()) for item in args.path
    ]
    for label, path in targets:
        if not path.is_dir():
            print(f"not a directory: {label}", file=sys.stderr)
            return 2

    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="sarand-bench-") as temp:
        if not args.no_synthetic:
            root = Path(temp)
            count = build_tree(root, args.files)
            targets.insert(0, (f"synthetic {count} files", root))
        for label, path in targets:
            rows = {engine: measure(engine, path, args.runs) for engine in ENGINES}
            results.append(
                {
                    "target": label,
                    **rows,
                    "comparison": compare(rows["rust"], rows["python"]),
                }
            )

    if args.as_json:
        print(json.dumps({"environment": environment(), "results": results}, indent=2))
    else:
        info = environment()
        print(
            f"Python {info['python']} on {info['system']} {info['machine']}, "
            f"{info['cpus']} CPUs, {args.runs} timed runs after 1 warm-up"
        )
        print()
        print(render_table(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
