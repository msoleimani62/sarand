"""The import review script (`scripts/structure_eval_imports.py`, R14-A3).

The script recomputes every sampled edge independently of the structure code, so these
tests also cross-check the structure's import classification, flags and declarations on
a small project that has each kind of import. They also cover the re-review mode (the
earlier rows next to the current answer) and the audit of every external package.
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
        "[project]\nname = 'proj'\nversion = '1'\ndependencies = ['requests>=2', 'PyYAML']\n"
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
        "import yaml\n"
        "try:\n"
        "    import numpy\n"
        "except ImportError:\n"
        "    numpy = None\n"
        "if TYPE_CHECKING:\n"
        "    from pkg.b import thing\n"
        "\n\n"
        "def f():\n"
        "    import json\n"
        "    return json, os, b, requests, pytest, yaml, numpy\n",
        encoding="utf-8",
    )
    return project


def test_the_independent_recomputation_agrees_on_every_kind_of_import(
    tmp_path: Path,
) -> None:
    module = _load()
    root = _project(tmp_path)
    edges, externals = module.load(root)
    rows = module.build_rows(root, edges, externals, 14, 100)
    header = list(module.HEADER)
    by_evidence = {row[header.index("evidence")]: row for row in rows}
    assert len(rows) >= 10
    assert [row[0] for row in rows if row[header.index("auto")] != "agree"] == []
    classes = {ev: row[header.index("class")] for ev, row in by_evidence.items()}
    assert classes["import os"] == "stdlib"
    assert classes["import requests"] == "external_declared"
    assert classes["import pytest"] == "external_declared"
    assert classes["import yaml"] == "external_declared"
    assert classes["import numpy"] == "external_unmatched"
    flags = header.index("flags")
    assert "type_only" in by_evidence["from pkg.b import thing"][flags]
    assert "lazy" in by_evidence["import json"][flags]
    assert "relative" in by_evidence["from . import b"][flags]
    assert "conditional" in by_evidence["import numpy"][flags]
    labels = header.index("declared_in")
    assert (
        by_evidence["import pytest"][labels] == "pyproject.toml#dependency-groups.tests"
    )
    assert by_evidence["import yaml"][labels] == "pyproject.toml#project.dependencies"
    assert by_evidence["import yaml"][header.index("confidence")] == "probable"


def test_a_declaration_the_structure_misses_is_reported_as_a_disagreement(
    tmp_path: Path,
) -> None:
    module = _load()
    root = _project(tmp_path)
    edges, externals = module.load(root)
    externals = {**externals, "pytest": []}
    rows = module.build_rows(root, edges, externals, 14, 100)
    header = list(module.HEADER)
    flagged = [r for r in rows if r[header.index("auto")] != "agree"]
    assert [r[header.index("evidence")] for r in flagged] == ["import pytest"]


def test_the_sample_is_a_function_of_the_tree_and_the_seed(tmp_path: Path) -> None:
    module = _load()
    root = _project(tmp_path)
    edges, externals = module.load(root)
    first = module.build_rows(root, edges, externals, 14, 5)
    again = module.build_rows(root, edges, externals, 14, 5)
    other = module.build_rows(root, edges, externals, 15, 5)
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


def test_the_re_review_puts_the_old_and_the_new_answer_side_by_side(
    tmp_path: Path,
) -> None:
    module = _load()
    root = _project(tmp_path)
    old = tmp_path / "old.tsv"
    module.main([str(root), "--out", str(old), "--sample", "100"])
    text = old.read_text(encoding="utf-8").split("\n")
    names = text[0].split("\t")
    rewritten = [text[0]]
    for line in text[1:]:
        if not line:
            continue
        cells = line.split("\t")
        cells[names.index("verdict")] = "correct"
        if cells[names.index("evidence")] == "import pytest":
            # as an earlier version of the structure would have said
            cells[names.index("class")] = "external_unmatched"
            cells[names.index("verdict")] = "wrong"
        rewritten.append("\t".join(cells))
    old.write_text("\n".join(rewritten) + "\n", encoding="utf-8")
    before = old.read_text(encoding="utf-8")

    new = tmp_path / "new.tsv"
    verdicts = tmp_path / "verdicts.txt"
    rows = [line.split("\t")[0] for line in rewritten[1:]]
    verdicts.write_text("".join(f"{r} correct unchanged\n" for r in rows), "utf-8")
    assert (
        module.main(
            [
                str(root),
                "--out",
                str(new),
                "--rereview",
                str(old),
                "--verdicts",
                str(verdicts),
            ]
        )
        == 0
    )
    assert old.read_text(encoding="utf-8") == before  # the earlier file is only read
    lines = new.read_text(encoding="utf-8").split("\n")
    header = lines[0].split("\t")
    assert header == list(module.REREVIEW_HEADER)
    table = [
        dict(zip(header, line.split("\t"), strict=True)) for line in lines[1:] if line
    ]
    pytest_row = next(r for r in table if r["evidence"] == "import pytest")
    assert pytest_row["old_class"] == "external_unmatched"
    assert pytest_row["class"] == "external_declared"
    assert pytest_row["old_verdict"] == "wrong"
    assert pytest_row["verdict"] == "correct" and pytest_row["reason"] == "unchanged"
    assert all(line == line.rstrip() for line in lines)


def test_the_audit_checks_every_external_package(tmp_path: Path) -> None:
    module = _load()
    root = _project(tmp_path)
    out = tmp_path / "out.tsv"
    assert module.main([str(root), "--out", str(out), "--audit-external"]) == 0
    edges, externals = module.load(root)
    audit: Any = module.audit_external(root, edges, externals)
    packages = audit["packages"]
    assert packages["pytest"]["tool_declared_in"] == [
        "pyproject.toml#dependency-groups.tests"
    ]
    assert packages["yaml"]["classes"] == {"external_declared": 1}
    assert packages["numpy"]["classes"] == {"external_unmatched": 1}
    assert audit["packages_where_structure_and_manifests_differ"] == []
    assert audit["edges_by_class"] == {"external_declared": 3, "external_unmatched": 1}
    assert audit["declared_edges_without_a_declaring_manifest_above_the_importer"] == 0
    assert json.dumps(audit)
    broken: Any = module.audit_external(root, edges, {**externals, "yaml": []})
    assert broken["packages_where_structure_and_manifests_differ"] == ["yaml"]


def test_a_manifest_in_another_part_of_the_project_is_reported_as_out_of_scope(
    tmp_path: Path,
) -> None:
    module = _load()
    root = tmp_path / "proj"
    (root / "app").mkdir(parents=True)
    (root / "tools").mkdir()
    (root / "tools" / "pyproject.toml").write_text(
        "[project]\nname = 't'\ndependencies = ['rich']\n", encoding="utf-8"
    )
    (root / "app" / "main.py").write_text("import rich\n", encoding="utf-8")
    edges, externals = module.load(root)
    audit: Any = module.audit_external(root, edges, externals)
    assert audit["edges_by_class"] == {"external_declared": 1}
    assert audit["declared_edges_without_a_declaring_manifest_above_the_importer"] == 1
