"""Evaluate the repository structure on a real project (R14-A3 gate, plan section 12).

What it does, with no network and without running any repository code:

1. builds the structure of PROJECT several times and records wall time, the peak
   Python allocation (tracemalloc, one extra run) and the process peak RSS;
2. checks that every run serialises to the same bytes (determinism);
3. draws seeded random samples for manual review and writes one TSV per sample:
   stored `Definite` relations, stored `Probable` relations, stored `Unknown`
   relations, and usage sites that were counted but not stored (the false-negative
   sample); each row carries its source line so anyone can check it;
4. with `--verdicts FILE`, fills the verdict column from a reviewer's file and prints
   the tally. A verdict file has one `<sample> <row> <verdict> [note...]` per line,
   where verdict is `correct`, `wrong` or `undecidable` (for the false-negative
   sample: `missed` when the site points at a repository symbol, `outside` when it
   does not, `undecidable`).

The sample is a function of the structure and the seed only: the same repository
state and seed give the same rows. Samples this small give estimates, not accuracy.

Usage:
    python scripts/structure_eval.py PROJECT --out DIR [--seed 14] [--sample 50]
        [--runs 5] [--verdicts FILE]

ارزیابی ساختار روی یک پروژه‌ی واقعی: زمان، حافظه، تکرارپذیری و نمونه‌های بازبینی با seed ثابت.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import random
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from typing import TypeVar

from sarand.structure import build_structure
from sarand.structure.model import StructureData
from sarand.structure.serialize import structure_payload

T = TypeVar("T")

SKIPPED_DIRS = frozenset(
    {".git", "__pycache__", "node_modules", "target", ".venv", "venv", ".tox", "build"}
)
SIZE_LIMIT = 1_000_000
SAMPLES = ("definite", "probable", "unknown", "untracked")
VERDICTS = {
    "definite": ("correct", "wrong", "undecidable"),
    "probable": ("correct", "wrong", "undecidable"),
    "unknown": ("correct", "wrong", "undecidable"),
    "untracked": ("missed", "outside", "undecidable"),
}


def collect(root: Path) -> tuple[list[Path], list[tuple[Path, int]]]:
    """Every file below `root` (relative paths), the over-size ones apart."""
    included: list[Path] = []
    skipped: list[tuple[Path, int]] = []
    for current, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIPPED_DIRS)
        for name in sorted(names):
            path = Path(current, name)
            rel = path.relative_to(root)
            size = path.stat().st_size
            if size > SIZE_LIMIT:
                skipped.append((rel, size))
            else:
                included.append(rel)
    return included, skipped


def digest(data: StructureData) -> str:
    text = json.dumps(structure_payload(data), sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def peak_rss_kb() -> int:
    """The process peak resident set in KB (0 where the platform has no `resource`)."""
    try:
        resource = importlib.import_module("resource")
    except ImportError:
        return 0
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value // 1024 if sys.platform == "darwin" else value


def measure(
    root: Path, runs: int
) -> tuple[StructureData, list[tuple[str, str, str]], dict[str, object]]:
    included, skipped = collect(root)
    times: list[float] = []
    digests: list[str] = []
    data: StructureData | None = None
    for _ in range(runs):
        start = time.perf_counter()
        data = build_structure(root, included, skipped)
        times.append(time.perf_counter() - start)
        digests.append(digest(data))
    untracked: list[tuple[str, str, str]] = []
    tracemalloc.start()
    data = build_structure(root, included, skipped, untracked=untracked)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    digests.append(digest(data))
    rss = peak_rss_kb()
    payload_bytes = len(json.dumps(structure_payload(data), sort_keys=True))
    report: dict[str, object] = {
        "files_listed": len(included) + len(skipped),
        "runs": runs,
        "seconds_median": round(statistics.median(times), 3),
        "seconds_min": round(min(times), 3),
        "seconds_max": round(max(times), 3),
        "tracemalloc_peak_kb": peak // 1024,
        "process_peak_rss_kb": rss,
        "structure_json_bytes": payload_bytes,
        "runs_identical": len(set(digests)) == 1,
        "sha256": digests[0],
        "interpreter": sys.version.split()[0],
    }
    return data, untracked, report


def source_lines(root: Path, cache: dict[str, list[str]], rel: str) -> list[str]:
    if rel not in cache:
        try:
            cache[rel] = (root / rel).read_text(encoding="utf-8").split("\n")
        except (OSError, UnicodeDecodeError):
            cache[rel] = []
    return cache[rel]


def context(root: Path, cache: dict[str, list[str]], rel: str, line: int) -> str:
    lines = source_lines(root, cache, rel)
    if not 1 <= line <= len(lines):
        return ""
    low = max(0, line - 2)
    high = min(len(lines), line + 1)
    picked = [f"{n + 1}: {lines[n].strip()}".rstrip() for n in range(low, high)]
    return " | ".join(picked)


def draw(rows: list[tuple[str, T]], count: int, seed: int) -> list[tuple[str, T]]:
    """`count` rows drawn with a fixed seed from the rows sorted by their key."""
    pool = sorted(rows, key=lambda r: r[0])
    # A seeded generator on purpose: a reproducible review sample, not a secret.
    generator = random.Random(seed)  # nosec B311
    return generator.sample(pool, min(count, len(pool)))


def clean(text: str) -> str:
    return text.replace("\t", " ").replace("\n", " ").replace("\r", " ")


def write_samples(
    root: Path,
    data: StructureData,
    untracked: list[tuple[str, str, str]],
    out: Path,
    seed: int,
    count: int,
) -> dict[str, int]:
    symbols = {s.id: s for s in data.symbols}
    cache: dict[str, list[str]] = {}
    sizes: dict[str, int] = {}
    header = "row\tlocation\tkind\tconfidence\tmethod\tverdict\tnote\tsource\ttarget\tevidence\tcontext"
    for level in ("definite", "probable", "unknown"):
        rel_rows = []
        for r in data.relations:
            if r.confidence != level:
                continue
            loc = r.location
            key = f"{loc.path}:{loc.line:06d}:{loc.col:04d}:{r.kind}:{r.source}:{r.target}"
            rel_rows.append((key, r))
        chosen = draw(rel_rows, count, seed)
        lines = [header]
        for index, (_, r) in enumerate(chosen, 1):
            src = symbols.get(r.source)
            tgt = symbols.get(r.target)
            source_text = f"{src.path}::{src.qualname}" if src else r.source
            target_text = (
                f"{tgt.path}:{tgt.location.line}::{tgt.qualname}"
                if tgt
                else r.target_name
            )
            loc = r.location
            lines.append(
                "\t".join(
                    [
                        str(index),
                        f"{loc.path}:{loc.line}:{loc.col}",
                        r.kind,
                        r.confidence,
                        r.resolution_method,
                        "",
                        "",
                        clean(source_text),
                        clean(target_text),
                        clean(r.evidence),
                        clean(context(root, cache, loc.path, loc.line)),
                    ]
                )
            )
        (out / f"sample_{level}.tsv").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
        sizes[level] = len(chosen)
    rows = [
        (f"{loc}\t{reason}\t{ev}", (reason, loc, ev)) for reason, loc, ev in untracked
    ]
    chosen_sites = draw(rows, count, seed)
    lines = [header]
    for index, (_, (reason, site, ev)) in enumerate(chosen_sites, 1):
        path, line, _col = site.rsplit(":", 2)
        lines.append(
            "\t".join(
                [
                    str(index),
                    site,
                    "site",
                    "",
                    reason,
                    "",
                    "",
                    "",
                    "",
                    clean(ev),
                    clean(context(root, cache, path, int(line))),
                ]
            )
        )
    (out / "sample_untracked.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    sizes["untracked"] = len(chosen_sites)
    return sizes


def apply_verdicts(out: Path, verdict_file: Path) -> dict[str, dict[str, int]]:
    given: dict[tuple[str, int], tuple[str, str]] = {}
    for raw in verdict_file.read_text(encoding="utf-8").splitlines():
        parts = raw.strip().split(None, 3)
        if len(parts) < 3 or raw.lstrip().startswith("#"):
            continue
        sample, row, verdict = parts[0], int(parts[1]), parts[2]
        if sample not in VERDICTS or verdict not in VERDICTS[sample]:
            raise SystemExit(f"bad verdict line: {raw!r}")
        given[(sample, row)] = (verdict, parts[3] if len(parts) > 3 else "")
    tally: dict[str, dict[str, int]] = {}
    for sample in SAMPLES:
        path = out / f"sample_{sample}.tsv"
        lines = path.read_text(encoding="utf-8").split("\n")
        counts = {name: 0 for name in VERDICTS[sample]}
        counts["unreviewed"] = 0
        for number, text in enumerate(lines[1:], 1):
            if not text:
                continue
            cells = text.split("\t")
            found = given.get((sample, int(cells[0])))
            if found is None:
                counts["unreviewed"] += 1
                continue
            cells[5], cells[6] = found[0], clean(found[1])
            counts[found[0]] += 1
            lines[number] = "\t".join(cells)
        path.write_text("\n".join(lines), encoding="utf-8")
        tally[sample] = counts
    return tally


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("project", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=14)
    parser.add_argument("--sample", type=int, default=50)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--verdicts", type=Path)
    args = parser.parse_args(argv)
    root = args.project.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    data, untracked, report = measure(root, args.runs)
    report["seed"] = args.seed
    report["summary"] = json.loads(
        json.dumps(structure_payload(data)["summary"], sort_keys=True)
    )
    report["sites"] = json.loads(json.dumps(structure_payload(data)["sites"]))
    report["sample_sizes"] = write_samples(
        root, data, untracked, args.out, args.seed, args.sample
    )
    if args.verdicts is not None:
        report["tally"] = apply_verdicts(args.out, args.verdicts)
    (args.out / "summary.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["runs_identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
