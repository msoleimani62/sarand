"""Repeatable benchmark of `--structure` (R14-D1, the duties of `docs/R14A_GATE_ACCEPTANCE.md`).

It answers one question with documented conditions: what does `build_structure` (and,
with `--cli`, the whole `sarand --structure` command) cost, on which inputs, with which
code, and how much of that cost is noise. It runs no repository code and changes nothing
in the package.

What makes a run comparable:

* every measurement runs in its own fresh interpreter (no cache or allocator state is
  carried from one run to the next); the interpreter, its minor version and the hash seed
  are the same for every code version and are recorded;
* the code versions (`--code LABEL=DIR`, the `python/` directory of a checkout or of a
  `git worktree`) are interleaved round by round and the order flips every round, so a
  slow phase of a busy phone hits all versions alike; each worker prints the file its
  `sarand` came from, and the script stops if that is not the requested directory;
* the same file list is built for every code version (same walk, same size limit);
* per (input, code): warm-up rounds are run and dropped, then N measured rounds; the
  report has median, mean, standard deviation, min, max and P95 (nearest rank: with fewer
  than 20 runs P95 is the maximum and the report says so), the spread in percent, the
  process peak RSS, and one extra run for the tracemalloc peak;
* a second, instrumented run in the same worker times the phases (imports and AST,
  symbol facts, fingerprints, cycles, resolution, entry points, declarations). The
  headline seconds never include the instrumentation. Fingerprints are inside the facts
  phase, so the phases overlap by design and `other` is what is left;
* the load average (where the platform shows it) is logged before and after every round;
* the output of every run is hashed; runs of one code version on one input must give one
  hash, otherwise the benchmark reports it as an error.

Inputs: give small, medium and large projects (`--input LABEL=PATH`, repeatable). One
input does not describe the whole project. Two versions of the code give a comparison
per input; the report says when the ranges of two versions overlap, which means the
difference is not distinguishable from noise with this many runs.

Usage:
    python scripts/structure_bench.py run --out DIR \\
        --input small=PATH --input medium=PATH --input large=PATH \\
        --code A2=/path/to/a2/python --code A3=/path/to/a3/python \\
        [--rounds 5] [--warmup 1] [--hashseed 0] [--cli]

Optimize only after a profile shows the bottleneck; this script finds where the time
goes, it does not justify a change by itself.

محک تکرارپذیر `--structure`: هر اندازه‌گیری در یک مفسر تازه، نسخه‌های کد به‌نوبت و با ترتیب
معکوس‌شونده، ورودی‌های کوچک/متوسط/بزرگ، میانه و پراکندگی و P95، فازها جدا، و ثبت محیط.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
import platform
import statistics
import subprocess  # nosec B404
import sys
import tempfile
import time
import tracemalloc
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

SIZE_LIMIT = 1_000_000
SKIPPED_DIRS = frozenset(
    {".git", "__pycache__", "node_modules", "target", ".venv", "venv", ".tox", "build"}
)
# Fewer runs than this and P95 is the maximum (nearest rank).
# با کمتر از این تعداد اجرا، P95 همان بیشینه است (nearest rank).
P95_MIN_RUNS = 20
PHASES = (
    ("declarations", "build", "python_declarations"),
    ("parse_imports", "build", "extract_imports"),
    ("facts", "build", "extract_facts"),
    ("fingerprint", "facts", "fingerprint"),
    ("cycles", "build", "find_cycles"),
    ("entry_points", "build", "find_entry_points"),
)


# ---------------------------------------------------------------- statistics


def percentile(values: Sequence[float], q: float) -> float:
    """Nearest-rank percentile `q` (0 to 100) of a non-empty sequence."""
    if not values:
        raise ValueError("percentile of an empty sequence")
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def summarize(values: Sequence[float]) -> dict[str, Any]:
    """Median, mean, stdev, min, max, P95 and the spread of a series of runs."""
    median = statistics.median(values)
    stdev = statistics.stdev(values) if len(values) > 1 else 0.0
    return {
        "n": len(values),
        "median": round(median, 4),
        "mean": round(statistics.fmean(values), 4),
        "stdev": round(stdev, 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "p95": round(percentile(values, 95), 4),
        "p95_is_max": len(values) < P95_MIN_RUNS,
        "spread_percent": round((max(values) - min(values)) / median * 100, 1)
        if median
        else 0.0,
    }


def change_percent(old: float, new: float) -> float:
    """How much `new` is above `old`, in percent of `old`."""
    return round((new - old) / old * 100, 1) if old else 0.0


def ranges_overlap(old: dict[str, Any], new: dict[str, Any]) -> bool:
    """True when the [min, max] ranges of two summaries overlap."""
    return bool(old["min"] <= new["max"] and new["min"] <= old["max"])


def parse_labeled(items: Sequence[str], kind: str) -> list[tuple[str, Path]]:
    """`LABEL=PATH` items, in order, with distinct labels and existing paths."""
    parsed: list[tuple[str, Path]] = []
    for item in items:
        label, sep, raw = item.partition("=")
        if not sep or not label or not raw:
            raise ValueError(f"--{kind} must be LABEL=PATH, got {item!r}")
        if any(label == seen for seen, _ in parsed):
            raise ValueError(f"--{kind} label {label!r} is used twice")
        path = Path(raw).resolve()
        if not path.is_dir():
            raise ValueError(f"--{kind} {label}: {path} is not a directory")
        parsed.append((label, path))
    if not parsed:
        raise ValueError(f"at least one --{kind} is required")
    return parsed


# -------------------------------------------------------------------- worker


def collect(root: Path) -> tuple[list[Path], list[tuple[Path, int]]]:
    """Every file below `root` (relative paths), the over-size ones apart."""
    included: list[Path] = []
    skipped: list[tuple[Path, int]] = []
    for current, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIPPED_DIRS)
        for name in sorted(names):
            path = Path(current, name)
            size = path.stat().st_size
            if size > SIZE_LIMIT:
                skipped.append((path.relative_to(root), size))
            else:
                included.append(path.relative_to(root))
    return included, skipped


def peak_rss_kb() -> int:
    """The process peak resident set in KB (0 where the platform has no `resource`)."""
    try:
        resource = importlib.import_module("resource")
    except ImportError:
        return 0
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value // 1024 if sys.platform == "darwin" else value


def _timed(
    function: Callable[..., Any], label: str, totals: dict[str, float]
) -> Callable[..., Any]:
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        try:
            return function(*args, **kwargs)
        finally:
            totals[label] = totals.get(label, 0.0) + time.perf_counter() - start

    return wrapper


def _instrument(totals: dict[str, float]) -> list[str]:
    """Wrap the phase functions that exist in this version of the code."""
    from sarand.structure import build, facts

    modules = {"build": build, "facts": facts}
    found: list[str] = []
    for label, module_name, name in PHASES:
        module = modules[module_name]
        original = getattr(module, name, None)
        if original is not None:
            setattr(module, name, _timed(original, label, totals))
            found.append(label)
    resolver = getattr(build, "Resolver", None)
    if resolver is not None:
        for method, label in (
            ("__init__", "resolver_init"),
            ("resolve_all", "resolve"),
        ):
            original = getattr(resolver, method, None)
            if original is not None:
                setattr(resolver, method, _timed(original, label, totals))
                found.append(label)
    return found


def worker(project: Path) -> dict[str, Any]:
    """One measurement of `build_structure` on `project` in this interpreter."""
    import sarand
    from sarand.structure import build_structure
    from sarand.structure.serialize import structure_payload

    def digest(data: Any) -> str:
        text = json.dumps(structure_payload(data), sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(text.encode("ascii")).hexdigest()

    included, skipped = collect(project)
    start = time.perf_counter()
    data = build_structure(project, included, skipped)
    seconds = time.perf_counter() - start
    rss = peak_rss_kb()
    clean_digest = digest(data)

    totals: dict[str, float] = {}
    found = _instrument(totals)
    start = time.perf_counter()
    again = build_structure(project, included, skipped)
    instrumented = time.perf_counter() - start

    nested = totals.get("fingerprint", 0.0)
    accounted = sum(v for k, v in totals.items() if k != "fingerprint")
    phases = {k: round(v, 4) for k, v in sorted(totals.items())}
    phases["other"] = round(max(instrumented - accounted, 0.0), 4)

    tracemalloc.start()
    build_structure(project, included, skipped)
    _, trace_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        "module_file": str(Path(sarand.__file__).resolve()),
        "python": platform.python_version(),
        "basis": str(data.meta.get("fingerprint_basis", "")),
        "files": len(included) + len(skipped),
        "symbols": len(data.symbols),
        "relations": len(data.relations),
        "seconds": seconds,
        "instrumented_seconds": instrumented,
        "phases": phases,
        "phases_found": found,
        "fingerprint_inside_facts": nested > 0,
        "peak_rss_kb": rss,
        "tracemalloc_peak_kb": trace_peak // 1024,
        "digest": clean_digest,
        "instrumented_digest": digest(again),
    }


# ------------------------------------------------------------------ orchestration


def _env(code_dir: Path, hashseed: str) -> dict[str, str]:
    env = dict(os.environ)
    # The requested code goes first; what was already on the path stays after it.
    # کدِ خواسته اول می‌آید و مسیرهای قبلی بعد از آن می‌مانند.
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{code_dir}{os.pathsep}{existing}" if existing else str(code_dir)
    )
    env["PYTHONHASHSEED"] = hashseed
    return env


def spawn_worker(code_dir: Path, project: Path, hashseed: str) -> dict[str, Any]:
    """Run one worker in a fresh interpreter with `code_dir` first on the path."""
    done = subprocess.run(  # nosec B603
        [sys.executable, str(Path(__file__).resolve()), "worker", str(project)],
        env=_env(code_dir, hashseed),
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise RuntimeError(
            f"worker failed (exit {done.returncode}) on {project} with {code_dir}:\n"
            f"{done.stderr.strip()[-2000:]}"
        )
    result: dict[str, Any] = json.loads(done.stdout.strip().splitlines()[-1])
    expected = (code_dir / "sarand" / "__init__.py").resolve()
    if Path(result["module_file"]) != expected:
        raise RuntimeError(
            f"the worker imported sarand from {result['module_file']}, "
            f"not from {expected}"
        )
    return result


def spawn_cli(code_dir: Path, project: Path, hashseed: str) -> dict[str, Any]:
    """Time the whole `sarand --structure` command on `project` (wall time, child RSS)."""
    with tempfile.TemporaryDirectory() as out:
        command = [
            sys.executable,
            "-m",
            "sarand",
            "--project",
            str(project),
            "--structure",
            "--skip-tests",
            "--format",
            "json",
            "--output-dir",
            out,
            "--output-name",
            "bench",
        ]
        start = time.perf_counter()
        rss = 0
        if sys.platform != "win32":
            proc = subprocess.Popen(  # nosec B603
                command,
                env=_env(code_dir, hashseed),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            stderr = proc.stderr.read() if proc.stderr else b""
            _, status, usage = os.wait4(proc.pid, 0)
            proc.returncode = os.waitstatus_to_exitcode(status)
            code = proc.returncode
            rss = (
                usage.ru_maxrss // 1024 if sys.platform == "darwin" else usage.ru_maxrss
            )
            if proc.stderr:
                proc.stderr.close()
        else:
            done = subprocess.run(  # nosec B603
                command,
                env=_env(code_dir, hashseed),
                capture_output=True,
                check=False,
            )
            code, stderr = done.returncode, done.stderr
        seconds = time.perf_counter() - start
    return {
        "seconds": seconds,
        "peak_rss_kb": int(rss),
        "exit_code": code,
        "stderr_bytes": len(stderr),
    }


def _loadavg() -> list[float] | None:
    try:
        return [float(x) for x in Path("/proc/loadavg").read_text().split()[:3]]
    except (OSError, ValueError):
        return None


def _mem_total_kb() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return None


def _git_head(directory: Path) -> str | None:
    try:
        done = subprocess.run(  # nosec B603 B607
            ["git", "-C", str(directory), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return done.stdout.strip() or None if done.returncode == 0 else None


def _has_rust_core(code_dir: Path) -> bool:
    """True when a compiled `_core` sits inside that checkout (the CLI then uses it)."""
    package = code_dir / "sarand"
    return any(package.glob("_core*.so")) or any(package.glob("_core*.pyd"))


def environment(codes: Sequence[tuple[str, Path]], hashseed: str) -> dict[str, Any]:
    """What the numbers were measured on."""
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "mem_total_kb": _mem_total_kb(),
        "hashseed": hashseed,
        "codes": {
            label: {
                "dir": str(p),
                "git_head": _git_head(p),
                "rust_core": _has_rust_core(p),
            }
            for label, p in codes
        },
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


def run(
    inputs: Sequence[tuple[str, Path]],
    codes: Sequence[tuple[str, Path]],
    *,
    rounds: int,
    warmup: int,
    hashseed: str,
    cli: bool,
    log: Callable[[str], object] = lambda _m: None,
) -> dict[str, Any]:
    """Run every (input, code) for `warmup + rounds` interleaved rounds."""
    samples: dict[tuple[str, str], list[dict[str, Any]]] = {}
    cli_samples: dict[tuple[str, str], list[dict[str, Any]]] = {}
    loads: list[dict[str, Any]] = []
    for number in range(warmup + rounds):
        order = list(codes) if number % 2 == 0 else list(reversed(codes))
        before = _loadavg()
        for input_label, project in inputs:
            for code_label, code_dir in order:
                log(f"round {number + 1}/{warmup + rounds} {input_label} {code_label}")
                result = spawn_worker(code_dir, project, hashseed)
                cli_result = spawn_cli(code_dir, project, hashseed) if cli else None
                if number >= warmup:
                    samples.setdefault((input_label, code_label), []).append(result)
                    if cli_result is not None:
                        cli_samples.setdefault((input_label, code_label), []).append(
                            cli_result
                        )
        loads.append(
            {
                "round": number + 1,
                "warmup": number < warmup,
                "load_before": before,
                "load_after": _loadavg(),
            }
        )
    results = [
        _entry(i, c, samples[(i, c)], cli_samples.get((i, c)))
        for i, _ in inputs
        for c, _ in codes
    ]
    return {
        "schema": 1,
        "environment": environment(codes, hashseed),
        "settings": {"rounds": rounds, "warmup": warmup, "cli": cli},
        "loads": loads,
        "results": results,
        "comparisons": _comparisons(
            results,
            [c for c, _ in codes],
            {label: _has_rust_core(p) for label, p in codes},
        ),
    }


def _entry(
    input_label: str,
    code_label: str,
    runs: list[dict[str, Any]],
    cli_runs: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    digests = {r["digest"] for r in runs} | {r["instrumented_digest"] for r in runs}
    phase_names = sorted({name for r in runs for name in r["phases"]})
    entry: dict[str, Any] = {
        "input": input_label,
        "code": code_label,
        "module_file": runs[0]["module_file"],
        "python": runs[0]["python"],
        "basis": runs[0]["basis"],
        "files": runs[0]["files"],
        "symbols": runs[0]["symbols"],
        "relations": runs[0]["relations"],
        "runs_identical": len(digests) == 1,
        "sha256": runs[0]["digest"],
        "seconds": summarize([r["seconds"] for r in runs]),
        "peak_rss_kb": summarize([float(r["peak_rss_kb"]) for r in runs]),
        "tracemalloc_peak_kb": summarize(
            [float(r["tracemalloc_peak_kb"]) for r in runs]
        ),
        "phases": {
            name: summarize([r["phases"].get(name, 0.0) for r in runs])
            for name in phase_names
        },
        "phases_found": runs[0]["phases_found"],
    }
    if cli_runs:
        entry["cli"] = {
            "seconds": summarize([r["seconds"] for r in cli_runs]),
            "peak_rss_kb": summarize([float(r["peak_rss_kb"]) for r in cli_runs]),
            "exit_codes": sorted({r["exit_code"] for r in cli_runs}),
            "stderr_bytes": sum(r["stderr_bytes"] for r in cli_runs),
        }
    return entry


def _comparisons(
    results: list[dict[str, Any]],
    codes: list[str],
    rust_core: dict[str, bool],
) -> list[dict[str, Any]]:
    """Every pair of code versions (the earlier one is the base), per input."""
    comparisons: list[dict[str, Any]] = []
    by_key = {(r["input"], r["code"]): r for r in results}
    for input_label in dict.fromkeys(r["input"] for r in results):
        for index, base_label in enumerate(codes):
            for other_label in codes[index + 1 :]:
                comparisons.append(
                    _compare(
                        input_label,
                        by_key[(input_label, base_label)],
                        by_key[(input_label, other_label)],
                        rust_core,
                    )
                )
    return comparisons


def _compare(
    input_label: str,
    base: dict[str, Any],
    other: dict[str, Any],
    rust_core: dict[str, bool],
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "input": input_label,
        "base": base["code"],
        "other": other["code"],
        "seconds_median_change_percent": change_percent(
            base["seconds"]["median"], other["seconds"]["median"]
        ),
        "seconds_p95_change_percent": change_percent(
            base["seconds"]["p95"], other["seconds"]["p95"]
        ),
        "ranges_overlap": ranges_overlap(base["seconds"], other["seconds"]),
        "rss_median_change_percent": change_percent(
            base["peak_rss_kb"]["median"], other["peak_rss_kb"]["median"]
        ),
        "same_python_minor": base["python"].rsplit(".", 1)[0]
        == other["python"].rsplit(".", 1)[0],
        "same_output_hash": base["sha256"] == other["sha256"],
        "same_rust_core": rust_core[base["code"]] == rust_core[other["code"]],
    }
    if "cli" in base and "cli" in other:
        row["cli_median_change_percent"] = change_percent(
            base["cli"]["seconds"]["median"], other["cli"]["seconds"]["median"]
        )
    return row


# ---------------------------------------------------------------------- report


def _row(label: str, s: dict[str, Any]) -> str:
    p95 = f"{s['p95']}{'*' if s['p95_is_max'] else ''}"
    return (
        f"| {label} | {s['median']} | {s['mean']} | {s['stdev']} | {s['min']} | "
        f"{s['max']} | {p95} | {s['spread_percent']}% |"
    )


_HEAD = (
    "| | median | mean | stdev | min | max | P95 | spread |\n"
    "|---|---|---|---|---|---|---|---|"
)


def markdown(report: dict[str, Any]) -> str:
    """A readable report of one benchmark run."""
    env = report["environment"]
    lines = [
        "# Structure benchmark",
        "",
        (
            f"Python {env['python']} ({env['implementation']}), {env['platform']}, "
            f"{env['cpu_count']} CPUs, hash seed {env['hashseed']}."
        ),
        (
            f"Rounds {report['settings']['rounds']} after "
            f"{report['settings']['warmup']} warm-up; one fresh interpreter per "
            f"measurement. `*` P95 is the maximum (fewer than {P95_MIN_RUNS} runs)."
        ),
        "",
    ]
    for label, info in env["codes"].items():
        lines.append(
            f"- code `{label}`: `{info['dir']}` (git `{info['git_head']}`, "
            f"compiled core: {info['rust_core']})"
        )
    for entry in report["results"]:
        lines += [
            "",
            f"## {entry['input']} / {entry['code']}",
            "",
            (
                f"{entry['files']} files, {entry['symbols']} symbols, "
                f"{entry['relations']} relations; basis `{entry['basis']}`; runs "
                f"identical: {entry['runs_identical']}; "
                f"sha256 `{entry['sha256'][:16]}`."
            ),
            "",
            _HEAD.replace("| |", "| seconds |", 1),
            _row("build_structure", entry["seconds"]),
            _row("peak RSS (KiB)", entry["peak_rss_kb"]),
            _row("tracemalloc peak (KiB)", entry["tracemalloc_peak_kb"]),
        ]
        if "cli" in entry:
            lines.append(_row("CLI wall time", entry["cli"]["seconds"]))
            lines.append(_row("CLI peak RSS (KiB)", entry["cli"]["peak_rss_kb"]))
        lines += [
            "",
            "Phases (seconds, instrumented run; fingerprints are inside facts):",
            "",
        ]
        lines.append(_HEAD.replace("| |", "| phase |", 1))
        lines += [_row(name, s) for name, s in entry["phases"].items()]
    lines += ["", "## Comparisons", ""]
    if not report["comparisons"]:
        lines.append("One code version only: nothing to compare.")
    for c in report["comparisons"]:
        if c["ranges_overlap"]:
            note = "ranges overlap: not distinguishable from noise"
        else:
            note = "ranges do not overlap"
        lines.append(
            f"- {c['input']}: {c['other']} against {c['base']}: median "
            f"{c['seconds_median_change_percent']:+}%, P95 "
            f"{c['seconds_p95_change_percent']:+}%, RSS "
            f"{c['rss_median_change_percent']:+}% ({note}; same Python minor: "
            f"{c['same_python_minor']}; same output hash: {c['same_output_hash']})"
        )
        if "cli_median_change_percent" in c:
            lines.append(
                f"  - whole command: median {c['cli_median_change_percent']:+}%"
            )
            if not c["same_rust_core"]:
                lines.append(
                    "  - WARNING: one version has a compiled core and the other has "
                    "not; the whole-command numbers do not compare the same engine"
                )
    lines += ["", "## Load average before and after each round", ""]
    for item in report["loads"]:
        kind = "warm-up" if item["warmup"] else "measured"
        lines.append(
            f"- round {item['round']} ({kind}): {item['load_before']} to "
            f"{item['load_after']}"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    runner = sub.add_parser("run", help="run the benchmark")
    runner.add_argument("--out", type=Path, required=True)
    runner.add_argument("--input", action="append", default=[], metavar="LABEL=PATH")
    runner.add_argument("--code", action="append", default=[], metavar="LABEL=DIR")
    runner.add_argument("--rounds", type=int, default=5)
    runner.add_argument("--warmup", type=int, default=1)
    runner.add_argument("--hashseed", default="0")
    runner.add_argument("--cli", action="store_true")
    inner = sub.add_parser("worker")
    inner.add_argument("project", type=Path)
    args = parser.parse_args(argv)

    if args.command == "worker":
        print(json.dumps(worker(args.project)))
        return 0
    if args.rounds < 1 or args.warmup < 0:
        parser.error("--rounds must be at least 1 and --warmup at least 0")
    try:
        inputs = parse_labeled(args.input, "input")
        codes = parse_labeled(args.code, "code")
    except ValueError as exc:
        parser.error(str(exc))
    args.out.mkdir(parents=True, exist_ok=True)
    report = run(
        inputs,
        codes,
        rounds=args.rounds,
        warmup=args.warmup,
        hashseed=args.hashseed,
        cli=args.cli,
        log=lambda m: print(m, file=sys.stderr, flush=True),
    )
    (args.out / "results.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.out / "results.md").write_text(markdown(report), encoding="utf-8")
    bad = [e for e in report["results"] if not e["runs_identical"]]
    for entry in bad:
        print(
            f"ERROR: {entry['input']}/{entry['code']} gave different outputs between runs",
            file=sys.stderr,
        )
    print(f"wrote {args.out / 'results.json'} and {args.out / 'results.md'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
