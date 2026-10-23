"""Guards for scripts/bench_scan.py (audit R8b, finding B7) and .benchmarks/ (C5).

The script measures the Rust core against the pure-Python scan. These tests
check the parts that must be right without a compiled core: the synthetic tree,
the statistics, the comparison and the table, and the Python engine itself.

گاردهای اسکریپت بنچمارک (R8b)؛ بدون هسته‌ی کامپایل‌شده هم اجرا می‌شوند.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "bench_scan", _ROOT / "scripts" / "bench_scan.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_benchmarks_directory_is_git_ignored() -> None:
    lines = (_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".benchmarks/" in [line.strip() for line in lines]


def test_build_tree_makes_visible_files_and_ignored_dirs(tmp_path: Path) -> None:
    script = _load_script()
    visible = script.build_tree(tmp_path, 120)
    assert visible == 120
    assert len([p for p in tmp_path.rglob("file*") if p.is_file()]) == 120
    for name in ("node_modules", "target", "__pycache__"):
        assert (tmp_path / name).is_dir()


def test_python_engine_prunes_ignored_dirs(tmp_path: Path) -> None:
    script = _load_script()
    script.build_tree(tmp_path, 60)
    result = script.run_worker("python", tmp_path, 1)
    assert result["available"] is True
    assert result["files"] == 60
    assert len(result["timings"]) == 1
    assert len(result["paths_sha256"]) == 64


def test_median_is_the_middle_value() -> None:
    script = _load_script()
    assert script.median([3.0, 1.0, 2.0]) == 2.0
    assert script.median([4.0, 1.0, 3.0, 2.0]) == 2.5


def _row(median: float, files: int, digest: str) -> dict[str, Any]:
    return {
        "available": True,
        "timings": [median],
        "median": median,
        "files": files,
        "paths_sha256": digest,
        "peak_rss_mib": 12.5,
    }


def test_compare_reports_speedup_and_same_file_list() -> None:
    script = _load_script()
    verdict = script.compare(_row(1.0, 10, "a"), _row(4.0, 10, "a"))
    assert verdict["speedup"] == 4.0
    assert verdict["same_files"] is True
    other = script.compare(_row(1.0, 10, "a"), _row(4.0, 10, "b"))
    assert other["same_files"] is False


def test_compare_is_unknown_when_the_core_is_missing() -> None:
    script = _load_script()
    verdict = script.compare({"available": False}, _row(4.0, 10, "a"))
    assert verdict == {"speedup": None, "same_files": None}


def test_table_names_a_missing_core_instead_of_hiding_it() -> None:
    script = _load_script()
    python = _row(2.0, 10, "a")
    entry = {
        "target": "demo",
        "rust": {"available": False},
        "python": python,
        "comparison": script.compare({"available": False}, python),
    }
    table = script.render_table([entry])
    assert "core not built" in table
    assert "| demo | python | 10 |" in table
    assert "speed-up over the fallback: n/a" in table
