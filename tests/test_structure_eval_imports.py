"""The import review sample (`scripts/structure_eval_imports.py`, R14-A3).

The script recomputes every sampled edge independently of the structure code, so these
tests also cross-check the structure's import classification and flags on a small
project that has each kind of import.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "structure_eval_imports", _ROOT / "scripts" / "structure_eval_imports.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _project(root: Path) -> Path:
    project = root / "proj"
    (project / "pkg").mkdir(parents=True)
    (project / "pyproject.toml").write_text(
        "[project]\nname = 'proj'\nversion = '1'\ndependencies = ['requests>=2']\n"
        "[dependency-groups]\ntests = ['pytest>=8']\n",
        encoding="utf-8",
    )
    (project / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (project / "pkg" / "b.py").write_text("thing = 1\n", encoding="utf-8")
    (project / "pkg" / "a.py").write_text(
        "from __future__ import annotations\n"
        "import os\n"
        "from typing import TYPE_CHECKING\n"
        "from . import b\n"
        "import requests\n"
        "import pytest\n"
        "try:\n"
        "    import yaml\n"
        "except ImportError:\n"
        "    yaml = None\n"
        "if TYPE_CHECKING:\n"
        "    from pkg.b import thing\n"
        "\n\n"
        "def f():\n"
        "    import json\n"
        "    return json, os, b, requests, pytest, yaml\n",
        encoding="utf-8",
    )
    return project


def test_the_independent_recomputation_agrees_on_every_kind_of_import(
    tmp_path: Path,
) -> None:
    module = _load()
    root = _project(tmp_path)
    rows = module.build_rows(root, module.load_edges(root), 14, 100)
    by_evidence = {row[12]: row for row in rows}
    assert len(rows) >= 9
    assert [row[0] for row in rows if row[8] != "agree"] == []
    classes = {row[12]: row[4] for row in rows}
    assert classes["import os"] == "stdlib"
    assert classes["import requests"] == "external_declared"
    assert classes["import pytest"] == "external_unmatched"
    assert classes["import yaml"] == "external_unmatched"
    assert "type_only" in by_evidence["from pkg.b import thing"][7]
    assert "lazy" in by_evidence["import json"][7]
    assert "relative" in by_evidence["from . import b"][7]
    assert "conditional" in by_evidence["import yaml"][7]


def test_the_sample_is_a_function_of_the_tree_and_the_seed(tmp_path: Path) -> None:
    module = _load()
    root = _project(tmp_path)
    edges = module.load_edges(root)
    first = module.build_rows(root, edges, 14, 5)
    again = module.build_rows(root, edges, 14, 5)
    other = module.build_rows(root, edges, 15, 5)
    assert first == again
    assert first != other


def test_no_row_ends_in_whitespace_even_when_verdicts_are_blank(
    tmp_path: Path,
) -> None:
    module = _load()
    root = _project(tmp_path)
    out = tmp_path / "out.tsv"
    module.main([str(root), "--out", str(out)])
    for line in out.read_text(encoding="utf-8").split("\n"):
        assert line == line.rstrip()


def test_verdicts_fill_the_tsv_and_bad_ones_are_refused(tmp_path: Path) -> None:
    module = _load()
    root = _project(tmp_path)
    out = tmp_path / "out.tsv"
    module.main([str(root), "--out", str(out)])
    verdicts = tmp_path / "verdicts.txt"
    verdicts.write_text(
        "# note\n1 correct read the import\n2 wrong declared\n", "utf-8"
    )
    tally = module.apply_verdicts(out, verdicts)
    assert tally["correct"] == 1 and tally["wrong"] == 1
    first = out.read_text(encoding="utf-8").split("\n")[1].split("\t")
    assert first[2:4] == ["correct", "read the import"]
    verdicts.write_text("1 fine\n", encoding="utf-8")
    try:
        module.apply_verdicts(out, verdicts)
    except SystemExit:
        return
    raise AssertionError("`fine` is not a verdict")


def test_the_audit_shows_where_an_unmatched_package_is_declared(
    tmp_path: Path,
) -> None:
    module = _load()
    root = _project(tmp_path)
    out = tmp_path / "out.tsv"
    assert module.main([str(root), "--out", str(out), "--audit-unmatched"]) == 0
    audit = module.audit_unmatched(root, module.load_edges(root))
    packages: Any = audit["packages"]
    assert packages["pytest"]["declared_in"] == ["group:tests"]
    assert packages["yaml"]["declared_in"] == []
    assert audit["declared_somewhere_in_pyproject"] == 1
    assert json.dumps(audit)
