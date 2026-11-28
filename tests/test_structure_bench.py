"""The benchmark script of the structure feature (`scripts/structure_bench.py`, R14-D1).

Its numbers are only worth something if the method is right: the statistics must be
what they say they are, the code versions must be interleaved and checked, every run
must be hashed, and nothing of the measured project may be executed.

محک ساختار: آمار درست، نسخه‌های کد به‌نوبت و راستی‌آزمایی‌شده، هش هر اجرا، و اجرا نشدن کد پروژه.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

_ROOT = Path(__file__).resolve().parent.parent


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "structure_bench", _ROOT / "scripts" / "structure_bench.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _project(root: Path) -> Path:
    project = root / "proj"
    (project / "pkg").mkdir(parents=True)
    (project / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (project / "pkg" / "core.py").write_text(
        "def helper(x):\n    return x + 1\n\n\nclass Box:\n"
        "    def run(self):\n        return helper(1)\n",
        encoding="utf-8",
    )
    # A file the benchmark must never import or run.
    # فایلی که محک نباید import یا اجرا کند.
    (project / "pkg" / "never.py").write_text(
        "raise SystemExit('the benchmark ran repository code')\n", encoding="utf-8"
    )
    return project


def test_percentile_is_nearest_rank() -> None:
    bench = _load()
    values = [float(n) for n in range(1, 11)]
    assert bench.percentile(values, 50) == 5.0
    assert bench.percentile(values, 95) == 10.0
    assert bench.percentile([7.0], 95) == 7.0
    assert bench.percentile([3.0, 1.0, 2.0], 0) == 1.0


def test_percentile_of_nothing_is_an_error() -> None:
    bench = _load()
    with pytest.raises(ValueError):
        bench.percentile([], 95)


def test_summarize_reports_spread_and_says_when_p95_is_the_maximum() -> None:
    bench = _load()
    summary = bench.summarize([1.0, 2.0, 3.0, 4.0, 100.0])
    assert summary["n"] == 5
    assert summary["median"] == 3.0
    assert summary["min"] == 1.0
    assert summary["max"] == 100.0
    assert summary["p95"] == 100.0
    assert summary["p95_is_max"] is True
    assert summary["spread_percent"] == 3300.0
    many = bench.summarize([float(n) for n in range(1, 41)])
    assert many["p95_is_max"] is False
    assert many["p95"] == 38.0
    assert bench.summarize([2.0])["stdev"] == 0.0


def test_change_and_overlap() -> None:
    bench = _load()
    assert bench.change_percent(10.0, 11.0) == 10.0
    assert bench.change_percent(0.0, 5.0) == 0.0
    first = {"min": 1.0, "max": 2.0}
    assert bench.ranges_overlap(first, {"min": 1.5, "max": 3.0}) is True
    assert bench.ranges_overlap(first, {"min": 2.5, "max": 3.0}) is False


def test_parse_labeled_checks_every_item(tmp_path: Path) -> None:
    bench = _load()
    parsed = bench.parse_labeled([f"a={tmp_path}", f"b={tmp_path}"], "input")
    assert [label for label, _ in parsed] == ["a", "b"]
    for bad in (["a"], ["=x"], [f"a={tmp_path}", f"a={tmp_path}"], ["a=/nope/x"], []):
        with pytest.raises(ValueError):
            bench.parse_labeled(bad, "input")


def test_collect_skips_tool_directories_and_sets_oversize_files_apart(
    tmp_path: Path,
) -> None:
    bench = _load()
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "b.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "big.py").write_text("#" * (bench.SIZE_LIMIT + 1), encoding="utf-8")
    included, skipped = bench.collect(tmp_path)
    assert [p.as_posix() for p in included] == ["a.py"]
    assert [(p.as_posix(), size) for p, size in skipped] == [
        ("big.py", bench.SIZE_LIMIT + 1)
    ]


def test_run_interleaves_codes_hashes_runs_and_executes_nothing(tmp_path: Path) -> None:
    bench = _load()
    project = _project(tmp_path)
    code = _ROOT / "python"
    log: list[str] = []
    report = bench.run(
        [("tiny", project)],
        [("A", code), ("B", code)],
        rounds=2,
        warmup=1,
        hashseed="0",
        cli=False,
        log=log.append,
    )
    # The order of the codes flips every round (A B, then B A, then A B).
    # ترتیب نسخه‌ها در هر دور برعکس می‌شود.
    assert [m.rsplit(" ", 1)[1] for m in log] == ["A", "B", "B", "A", "A", "B"]
    assert [r["code"] for r in report["results"]] == ["A", "B"]
    for entry in report["results"]:
        assert entry["runs_identical"] is True
        assert entry["seconds"]["n"] == 2
        assert entry["files"] == 3
        assert entry["basis"].startswith("fp1/python-")
        assert "fingerprint" in entry["phases"]
        assert "other" in entry["phases"]
    assert len(report["loads"]) == 3
    assert [item["warmup"] for item in report["loads"]] == [True, False, False]
    (comparison,) = report["comparisons"]
    assert comparison["same_output_hash"] is True
    assert comparison["same_python_minor"] is True
    text = bench.markdown(report)
    assert "## Comparisons" in text
    assert "tiny / A" in text
    assert "| seconds | median |" in text


def test_three_codes_give_every_pair_and_the_control_is_one_of_them(
    tmp_path: Path,
) -> None:
    bench = _load()
    project = _project(tmp_path)
    code = _ROOT / "python"
    report = bench.run(
        [("tiny", project)],
        [("A", code), ("B", code), ("C", code)],
        rounds=1,
        warmup=0,
        hashseed="0",
        cli=False,
    )
    pairs = [(c["base"], c["other"]) for c in report["comparisons"]]
    assert pairs == [("A", "B"), ("A", "C"), ("B", "C")]
    assert all(c["same_rust_core"] for c in report["comparisons"])
    codes_info = report["environment"]["codes"]
    assert all(isinstance(info["rust_core"], bool) for info in codes_info.values())


def test_a_worker_from_the_wrong_code_directory_is_refused(tmp_path: Path) -> None:
    bench = _load()
    project = _project(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(RuntimeError):
        bench.spawn_worker(empty, project, "0")


def test_main_writes_both_reports_and_rejects_bad_arguments(tmp_path: Path) -> None:
    bench = _load()
    project = _project(tmp_path)
    out = tmp_path / "out"
    code = _ROOT / "python"
    argv = [
        "run",
        "--out",
        str(out),
        "--input",
        f"tiny={project}",
        "--code",
        f"A={code}",
        "--rounds",
        "1",
        "--warmup",
        "0",
    ]
    assert bench.main(argv) == 0
    data = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert data["schema"] == 1
    assert data["environment"]["hashseed"] == "0"
    assert data["comparisons"] == []
    assert "One code version only" in (out / "results.md").read_text(encoding="utf-8")
    with pytest.raises(SystemExit):
        bench.main(["run", "--out", str(out), "--code", f"A={code}"])


def test_the_whole_command_can_be_timed(tmp_path: Path) -> None:
    if importlib.util.find_spec("rich") is None:
        pytest.skip("the sarand command needs rich")
    bench = _load()
    project = _project(tmp_path)
    result = bench.spawn_cli(_ROOT / "python", project, "0")
    assert result["exit_code"] == 0
    assert result["seconds"] > 0


# ----------------------------------------------------------------- compare mode (P)


def _row(config: str, base: str | None, median: float, rss: float = 1000.0) -> dict:
    spread = {"median": median, "min": median - 0.1, "max": median + 0.1}
    return {
        "input": "a",
        "config": config,
        "base": base,
        "seconds": spread,
        "peak_rss_kb": {"median": rss, "min": rss, "max": rss},
        "arguments": ["--structure"] if config.startswith("structure") else [],
        "exit_codes": [0],
        "probe_exit_code": 0,
        "structure_loaded": config.startswith("structure"),
    }


def test_each_option_is_measured_against_its_own_base() -> None:
    bench = _load()
    bases = {c: b for c, b, _ in bench.COMPARE_CONFIGS}
    assert bases == {
        "plain": None,
        "findings-baseline": "plain",
        "findings-gate": "findings-baseline",
        "structure": None,
        "structure-baseline": "structure",
    }


def test_added_costs_subtract_the_base_and_say_when_the_ranges_overlap() -> None:
    bench = _load()
    results = [
        _row("plain", None, 2.0, rss=1000),
        _row("findings-baseline", "plain", 2.5, rss=1200),  # ranges [1.9,2.1] [2.4,2.6]
        _row("findings-gate", "findings-baseline", 2.55, rss=1200),  # overlaps
        _row("structure", None, 5.0),
        _row("structure-baseline", "structure", 5.0),
    ]
    rows = {r["config"]: r for r in bench.added_costs(results)}
    assert set(rows) == {"findings-baseline", "findings-gate", "structure-baseline"}
    assert rows["findings-baseline"]["added_seconds_median"] == 0.5
    assert rows["findings-baseline"]["change_percent"] == 25.0
    assert rows["findings-baseline"]["ranges_overlap"] is False
    assert rows["findings-baseline"]["added_rss_kb_median"] == 200
    assert rows["findings-gate"]["ranges_overlap"] is True
    assert rows["structure-baseline"]["added_seconds_median"] == 0.0


def test_compare_problems_flag_a_failed_run_and_a_wrong_import() -> None:
    bench = _load()
    good = {"results": [_row("plain", None, 1.0), _row("structure", None, 1.0)]}
    assert bench.compare_problems(good) == []
    failed = _row("plain", None, 1.0)
    failed["exit_codes"] = [0, 4]
    leaked = _row("findings-baseline", "plain", 1.0)
    leaked["structure_loaded"] = True  # the findings path must not load the package
    missing = _row("structure", None, 1.0)
    missing["structure_loaded"] = False
    problems = bench.compare_problems({"results": [failed, leaked, missing]})
    assert len(problems) == 3
    assert "did not exit 0" in problems[0]
    assert "findings-baseline" in problems[1] and "expected False" in problems[1]
    assert "structure:" in problems[2] and "expected True" in problems[2]


def test_the_compare_report_is_readable() -> None:
    bench = _load()
    results = [_row("plain", None, 1.0), _row("findings-baseline", "plain", 1.2)]
    report = {
        "environment": {
            "python": "3.12",
            "implementation": "CPython",
            "platform": "x",
            "cpu_count": 2,
            "hashseed": "0",
            "codes": {"NOW": {"git_head": "abc", "rust_core": False}},
        },
        "settings": {"rounds": 3, "warmup": 1, "code": "NOW"},
        "results": [
            {
                **r,
                "seconds": {
                    **r["seconds"],
                    "p95": r["seconds"]["max"],
                    "p95_is_max": True,
                },
            }
            for r in results
        ],
        "added_costs": bench.added_costs(results),
    }
    text = bench.compare_markdown(report)
    assert "## Seconds of the whole command" in text
    assert "## What each option adds to its base" in text
    assert "| a | findings-baseline | plain | 0.2 | 20.0% |" in text


def test_compare_needs_exactly_one_code(tmp_path: Path) -> None:
    bench = _load()
    for argv in (
        ["compare", "--out", str(tmp_path), "--input", f"a={tmp_path}"],
        [
            "compare",
            "--out",
            str(tmp_path),
            "--input",
            f"a={tmp_path}",
            "--code",
            f"x={tmp_path}",
            "--code",
            f"y={tmp_path}",
        ],
    ):
        with pytest.raises(SystemExit) as caught:
            bench.main(argv)
        assert caught.value.code == 2


def test_compare_runs_end_to_end_and_the_findings_path_never_loads_structure(
    tmp_path: Path,
) -> None:
    if importlib.util.find_spec("rich") is None:
        pytest.skip("the sarand command needs rich")
    bench = _load()
    project = _project(tmp_path)
    out = tmp_path / "out"
    code = bench.main(
        [
            "compare",
            "--out",
            str(out),
            "--input",
            f"tiny={project}",
            "--code",
            f"NOW={_ROOT / 'python'}",
            "--rounds",
            "1",
            "--warmup",
            "0",
        ]
    )
    assert code == 0
    report = json.loads((out / "compare.json").read_text(encoding="utf-8"))
    loaded = {r["config"]: r["structure_loaded"] for r in report["results"]}
    assert loaded == {
        "plain": False,
        "findings-baseline": False,
        "findings-gate": False,
        "structure": True,
        "structure-baseline": True,
    }
    assert all(r["exit_codes"] == [0] for r in report["results"])
    assert len(report["added_costs"]) == 3
    assert "Comparison paths benchmark" in (out / "compare.md").read_text(
        encoding="utf-8"
    )
