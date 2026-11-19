"""The evaluation script of the structure feature (`scripts/structure_eval.py`, R14-A3).

It must be reproducible (same tree and seed, same rows), must not run repository
code, and must apply a reviewer's verdicts without touching anything else.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

_ROOT = Path(__file__).resolve().parent.parent


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "structure_eval", _ROOT / "scripts" / "structure_eval.py"
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
        "    def run(self):\n        return helper(1)\n\n"
        "    def go(self):\n        return self.run()\n\n\n"
        "def main():\n    box = Box()\n    return box.go() + helper(2)\n",
        encoding="utf-8",
    )
    # A file the evaluation must never import or run.
    (project / "pkg" / "never.py").write_text(
        "raise SystemExit('the evaluation ran repository code')\n", encoding="utf-8"
    )
    return project


def test_context_does_not_emit_trailing_whitespace_for_blank_lines(
    tmp_path: Path,
) -> None:
    module = _load()
    (tmp_path / "sample.py").write_text(
        "first = 1\n\nlast = 2\n",
        encoding="utf-8",
    )

    result = module.context(tmp_path, {}, "sample.py", 2)

    assert result == "1: first = 1 | 2: | 3: last = 2"
    assert not result.endswith((" ", "\t"))


def test_the_script_writes_samples_and_a_summary_without_running_the_project(
    tmp_path: Path,
) -> None:
    module = _load()
    out = tmp_path / "out"
    assert module.main([str(_project(tmp_path)), "--out", str(out), "--runs", "2"]) == 0
    for name in (
        "summary.json",
        "sample_definite.tsv",
        "sample_probable.tsv",
        "sample_unknown.tsv",
        "sample_untracked.tsv",
    ):
        assert (out / name).is_file(), name
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["runs_identical"] is True
    assert summary["seed"] == 14
    assert summary["summary"]["symbols"] >= 4
    header = (out / "sample_definite.tsv").read_text(encoding="utf-8").split("\n")[0]
    assert header.split("\t")[5:7] == ["verdict", "note"]


def test_the_same_tree_and_seed_give_the_same_rows(tmp_path: Path) -> None:
    module = _load()
    project = _project(tmp_path)
    first, second = tmp_path / "a", tmp_path / "b"
    module.main([str(project), "--out", str(first), "--runs", "1", "--sample", "3"])
    module.main([str(project), "--out", str(second), "--runs", "1", "--sample", "3"])
    for name in ("sample_definite.tsv", "sample_untracked.tsv"):
        assert (first / name).read_text(encoding="utf-8") == (second / name).read_text(
            encoding="utf-8"
        )


def test_verdicts_fill_the_tsv_and_are_tallied(tmp_path: Path) -> None:
    module = _load()
    project = _project(tmp_path)
    out = tmp_path / "out"
    module.main([str(project), "--out", str(out), "--runs", "1"])
    rows = (out / "sample_definite.tsv").read_text(encoding="utf-8").split("\n")
    count = len([r for r in rows[1:] if r])
    assert count >= 1
    verdicts = tmp_path / "verdicts.txt"
    verdicts.write_text(
        "# a comment\ndefinite 1 correct checked by reading the import\n",
        encoding="utf-8",
    )
    tally = module.apply_verdicts(out, verdicts)
    assert tally["definite"]["correct"] == 1
    assert tally["definite"]["unreviewed"] == count - 1
    first = (out / "sample_definite.tsv").read_text(encoding="utf-8").split("\n")[1]
    assert first.split("\t")[5:7] == ["correct", "checked by reading the import"]


def test_a_verdict_outside_the_vocabulary_is_refused(tmp_path: Path) -> None:
    module = _load()
    out = tmp_path / "out"
    module.main([str(_project(tmp_path)), "--out", str(out), "--runs", "1"])
    verdicts = tmp_path / "verdicts.txt"
    verdicts.write_text("untracked 1 correct\n", encoding="utf-8")
    try:
        module.apply_verdicts(out, verdicts)
    except SystemExit:
        return
    raise AssertionError("`correct` is not a verdict of the untracked sample")
