"""R14-A1: the repository structure (imports, classification, cycles, provenance).

Synthetic trees written to `tmp_path`, one focused group per fixture class of the
R14 master plan (4.9): import resolution, relative imports, cycles, external
classification, dynamic imports, parser limitations, determinism, serialization,
the opt-in surface. Dependency-free like the other tests; the standard-library name
list is injected so the results do not depend on the interpreter running them.
R14-A1: ساختار مخزن؛ فهرست stdlib تزریق می‌شود تا نتیجه به مفسر وابسته نباشد.
"""

from __future__ import annotations

import json
import random
from collections.abc import Mapping
from pathlib import Path

from sarand.cli import build_parser
from sarand.config import SarandConfig
from sarand.core.report_views import (
    structure_attention_rows,
    structure_cycle_lines,
    structure_external_rows,
    structure_lines,
)
from sarand.models.results import ReportData
from sarand.structure import build_structure, python_extract
from sarand.structure.model import (
    CONF_DEFINITE,
    CONF_PROBABLE,
    CONF_UNKNOWN,
    TARGET_DYNAMIC,
    TARGET_EXTERNAL_DECLARED,
    TARGET_EXTERNAL_UNMATCHED,
    TARGET_INTERNAL,
    TARGET_INTERNAL_UNRESOLVED,
    TARGET_STDLIB,
    StructureData,
)
from sarand.structure.serialize import structure_payload, summary

STDLIB = frozenset(
    {"os", "sys", "json", "re", "typing", "importlib", "collections", "types"}
)


def _write(root: Path, files: Mapping[str, str | bytes]) -> list[Path]:
    paths: list[Path] = []
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
        paths.append(Path(rel))
    return paths


def _build(
    tmp_path: Path,
    files: Mapping[str, str | bytes],
    skipped: tuple[tuple[Path, int], ...] = (),
    order: list[str] | None = None,
) -> StructureData:
    paths = _write(tmp_path, files)
    if order is not None:
        paths = [Path(p) for p in order]
    return build_structure(tmp_path, paths, skipped, stdlib=STDLIB)


def _edge(data: StructureData, source: str, requested: str):
    found = [e for e in data.edges if e.source == source and e.requested == requested]
    assert len(found) == 1, (
        source,
        requested,
        [(e.source, e.requested) for e in data.edges],
    )
    return found[0]


# --- import resolution ----------------------------------------------------------------


def test_absolute_imports_of_repository_modules_are_definite(tmp_path: Path) -> None:
    data = _build(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/a.py": "import pkg.b\nfrom pkg.b import f\n",
            "pkg/b.py": "def f(): ...\n",
        },
    )
    edges = [e for e in data.edges if e.source == "pkg.a"]
    assert [(e.requested, e.target, e.target_class, e.confidence) for e in edges] == [
        ("pkg.b", "pkg.b", TARGET_INTERNAL, CONF_DEFINITE),
        ("pkg.b", "pkg.b", TARGET_INTERNAL, CONF_DEFINITE),
    ]
    assert {e.resolution_method for e in edges} == {"absolute-module"}


def test_from_import_of_a_submodule_points_at_the_submodule(tmp_path: Path) -> None:
    data = _build(
        tmp_path,
        {"pkg/__init__.py": "", "pkg/a.py": "from pkg import b\n", "pkg/b.py": ""},
    )
    edge = _edge(data, "pkg.a", "pkg.b")
    assert (edge.target, edge.confidence) == ("pkg.b", CONF_DEFINITE)
    # the package itself is not a dependency when only submodules are imported
    assert not [e for e in data.edges if e.source == "pkg.a" and e.requested == "pkg"]


def test_from_import_of_a_symbol_depends_on_the_package(tmp_path: Path) -> None:
    data = _build(
        tmp_path,
        {"pkg/__init__.py": "VALUE = 1\n", "pkg/a.py": "from pkg import VALUE\n"},
    )
    edge = _edge(data, "pkg.a", "pkg")
    assert (edge.target, edge.target_class) == ("pkg", TARGET_INTERNAL)


def test_relative_imports_resolve_by_level(tmp_path: Path) -> None:
    data = _build(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/sub/__init__.py": "",
            "pkg/sub/mod.py": "from . import sibling\nfrom .sibling import g\nfrom .. import top\nfrom ..top import h\n",
            "pkg/sub/sibling.py": "",
            "pkg/top.py": "",
        },
    )
    got = {(e.requested, e.target) for e in data.edges if e.source == "pkg.sub.mod"}
    assert got == {
        ("pkg.sub.sibling", "pkg.sub.sibling"),
        ("pkg.top", "pkg.top"),
    }
    assert all(
        e.confidence == CONF_DEFINITE for e in data.edges if e.source == "pkg.sub.mod"
    )
    assert all("relative" in e.flags for e in data.edges if e.source == "pkg.sub.mod")


def test_a_relative_import_past_the_top_package_is_unresolved(tmp_path: Path) -> None:
    data = _build(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": "from ... import x\n"})
    edge = next(e for e in data.edges if e.source == "pkg.a")
    assert edge.target_class == TARGET_INTERNAL_UNRESOLVED
    assert edge.confidence == CONF_UNKNOWN


def test_a_missing_repository_submodule_is_unresolved_not_external(
    tmp_path: Path,
) -> None:
    data = _build(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": "import pkg.nothing\n"})
    edge = _edge(data, "pkg.a", "pkg.nothing")
    assert edge.target_class == TARGET_INTERNAL_UNRESOLVED
    assert edge.confidence == CONF_UNKNOWN
    assert edge.resolution_method == "missing-submodule"


def test_namespace_packages_are_modules_without_a_file(tmp_path: Path) -> None:
    data = _build(
        tmp_path,
        {
            "pyproject.toml": '[tool.maturin]\npython-source = "python"\n',
            "python/ns/deep/mod.py": "x = 1\n",
            "python/app.py": "import ns.deep.mod\n",
        },
    )
    assert any(m.name == "ns" and m.is_namespace for m in data.modules)
    assert any(m.name == "ns.deep" and m.is_namespace for m in data.modules)
    edge = _edge(data, "app", "ns.deep.mod")
    assert (edge.target, edge.target_class) == ("ns.deep.mod", TARGET_INTERNAL)


def test_a_declared_root_makes_a_namespace_layout_importable(tmp_path: Path) -> None:
    data = _build(
        tmp_path,
        {
            "pyproject.toml": '[tool.maturin]\npython-source = "py"\n',
            "py/ns/mod.py": "",
            "py/ns/user.py": "import ns.mod\n",
        },
    )
    assert data.meta["declared_roots"] == ["py"]
    assert _edge(data, "ns.user", "ns.mod").target == "ns.mod"


def test_an_unreadable_pyproject_never_breaks_the_run(tmp_path: Path) -> None:
    data = _build(
        tmp_path, {"pyproject.toml": "this is = not [valid", "a.py": "import os\n"}
    )
    assert data.meta["declared_roots"] == []
    assert _edge(data, "a", "os").target_class == TARGET_STDLIB


# --- external classification ------------------------------------------------------------


def test_stdlib_declared_and_unmatched_are_three_different_classes(
    tmp_path: Path,
) -> None:
    data = _build(
        tmp_path,
        {
            "pyproject.toml": '[project]\nname = "x"\ndependencies = ["requests>=2", "PyYAML"]\n',
            "a.py": "import os\nimport requests\nimport yaml\nimport numpy\n",
        },
    )
    classes = {e.requested: (e.target_class, e.confidence) for e in data.edges}
    assert classes["os"] == (TARGET_STDLIB, CONF_DEFINITE)
    assert classes["requests"] == (TARGET_EXTERNAL_DECLARED, CONF_DEFINITE)
    # `yaml` is not `pyyaml`: sarand reads no installed metadata, so it does not guess
    assert classes["yaml"] == (TARGET_EXTERNAL_UNMATCHED, CONF_PROBABLE)
    assert classes["numpy"] == (TARGET_EXTERNAL_UNMATCHED, CONF_PROBABLE)
    declared = next(x for x in data.externals if x.name == "requests")
    assert declared.declared_in == ("pyproject.toml",)


def test_a_declared_dependency_alone_makes_no_edge(tmp_path: Path) -> None:
    data = _build(
        tmp_path,
        {
            "pyproject.toml": '[project]\nname = "x"\ndependencies = ["requests"]\n',
            "a.py": "x = 1\n",
        },
    )
    assert data.edges == ()
    assert data.externals == ()


def test_a_repository_module_shadowing_stdlib_is_only_probable(tmp_path: Path) -> None:
    data = _build(tmp_path, {"types.py": "", "a.py": "import types\n"})
    edge = _edge(data, "a", "types")
    assert (edge.target_class, edge.confidence) == (TARGET_INTERNAL, CONF_PROBABLE)
    assert edge.resolution_method == "internal-shadows-stdlib"


def test_the_same_name_in_two_roots_prefers_the_own_root_as_probable(
    tmp_path: Path,
) -> None:
    data = _build(
        tmp_path,
        {"one/util.py": "", "one/main.py": "import util\n", "two/util.py": ""},
    )
    edge = _edge(data, "main", "util")
    assert edge.resolution_method == "own-root-preferred"
    assert edge.confidence == CONF_PROBABLE


def test_an_ambiguous_name_is_unresolved(tmp_path: Path) -> None:
    data = _build(
        tmp_path,
        {"one/util.py": "", "two/util.py": "", "three/main.py": "import util\n"},
    )
    edge = _edge(data, "main", "util")
    assert (edge.target_class, edge.confidence) == (
        TARGET_INTERNAL_UNRESOLVED,
        CONF_UNKNOWN,
    )


# --- conditional, type-only and lazy imports ------------------------------------------------


def test_context_flags_do_not_lower_confidence(tmp_path: Path) -> None:
    source = (
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n    import b\n"
        "try:\n    import c\nexcept ImportError:\n    c = None\n"
        "import d\n"
        "def f():\n    import e\n"
    )
    data = _build(
        tmp_path,
        {"a.py": source, "b.py": "", "c.py": "", "d.py": "", "e.py": ""},
    )
    flags = {e.requested: set(e.flags) for e in data.edges if e.source == "a"}
    assert flags["b"] == {"type_only", "conditional"}
    assert flags["c"] == {"conditional"}
    assert flags["d"] == set()
    assert flags["e"] == {"lazy"}
    assert all(
        e.confidence == CONF_DEFINITE
        for e in data.edges
        if e.source == "a" and e.target_class == TARGET_INTERNAL
    )


def test_a_try_without_import_error_does_not_make_an_import_optional(
    tmp_path: Path,
) -> None:
    data = _build(
        tmp_path,
        {"a.py": "try:\n    import b\nfinally:\n    pass\n", "b.py": ""},
    )
    assert _edge(data, "a", "b").flags == ()


def test_star_imports_are_flagged(tmp_path: Path) -> None:
    data = _build(tmp_path, {"a.py": "from b import *\n", "b.py": ""})
    assert "star" in _edge(data, "a", "b").flags


# --- dynamic imports -------------------------------------------------------------------------


def test_importlib_with_a_literal_is_probable_and_with_an_expression_is_unknown(
    tmp_path: Path,
) -> None:
    source = (
        "import importlib\n"
        "a = importlib.import_module('b')\n"
        "name = 'x'\n"
        "c = importlib.import_module(name)\n"
        "d = __import__('b')\n"
        "e = __import__(name)\n"
    )
    data = _build(tmp_path, {"m.py": source, "b.py": ""})
    literal = [e for e in data.edges if e.target == "b"]
    assert {e.confidence for e in literal} == {CONF_PROBABLE}
    assert {e.original_type for e in literal} == {"dynamic_call"}
    dynamic = [e for e in data.edges if e.target_class == TARGET_DYNAMIC]
    assert len(dynamic) == 2
    assert all(e.confidence == CONF_UNKNOWN and e.target == "" for e in dynamic)
    limits = next(f.provenance.limitations for f in data.files if f.path == "m.py")
    assert "dynamic_construct_seen" in limits


def test_exec_and_eval_mark_the_file_without_inventing_an_edge(tmp_path: Path) -> None:
    data = _build(tmp_path, {"a.py": "exec('import os')\neval('1')\n"})
    assert data.edges == ()
    assert "dynamic_construct_seen" in data.files[0].provenance.limitations


# --- parser limitations and provenance ---------------------------------------------------------


def test_a_syntax_error_keeps_the_file_with_its_location(tmp_path: Path) -> None:
    data = _build(tmp_path, {"bad.py": "def f(:\n    pass\n", "good.py": "import os\n"})
    bad = next(f for f in data.files if f.path == "bad.py")
    assert bad.provenance.completeness == "failed"
    assert "syntax_error" in bad.provenance.limitations
    assert bad.error is not None and bad.error.line == 1
    assert [e for e in data.edges if e.source == "bad"] == []
    assert len(data.files) == 2  # never dropped silently
    assert summary(data)["files_by_completeness"]["failed"] == 1


def test_a_file_that_is_not_utf8_is_failed_with_a_reason(tmp_path: Path) -> None:
    data = _build(tmp_path, {"latin.py": b"x = '\xe9'\n"})
    only = data.files[0]
    assert only.provenance.completeness == "failed"
    assert only.provenance.limitations == ("encoding_error",)


def test_a_file_over_the_size_limit_is_listed_not_dropped(tmp_path: Path) -> None:
    _write(tmp_path, {"small.py": "import os\n", "big.py": "import sys\n"})
    data = build_structure(
        tmp_path,
        [Path("small.py")],
        [(Path("big.py"), 9_999_999)],
        stdlib=STDLIB,
    )
    big = next(f for f in data.files if f.path == "big.py")
    assert big.provenance.completeness == "skipped_size"
    assert big.provenance.limitations == ("too_large",)
    assert big.size == 9_999_999
    assert any(m.name == "big" for m in data.modules)  # still an import target
    assert [e for e in data.edges if e.source == "big"] == []


def test_the_node_cap_gives_a_partial_file_with_what_was_found(tmp_path: Path) -> None:
    original = python_extract.MAX_NODES_PER_FILE
    python_extract.MAX_NODES_PER_FILE = 12
    try:
        source = "import os\n" + "x = 1\n" * 50 + "import sys\n"
        data = _build(tmp_path, {"a.py": source})
    finally:
        python_extract.MAX_NODES_PER_FILE = original
    only = data.files[0]
    assert only.provenance.completeness == "partial"
    assert "node_cap" in only.provenance.limitations
    assert [e.requested for e in data.edges] == ["os"]


def test_very_deep_nesting_is_partial_or_failed_never_a_crash(tmp_path: Path) -> None:
    deep = "x = " + "(" * 3000 + "1" + ")" * 3000 + "\nimport os\n"
    data = _build(tmp_path, {"a.py": deep})
    assert data.files[0].provenance.completeness in ("partial", "failed")
    assert data.files[0].provenance.limitations


def test_provenance_names_the_parser_and_version(tmp_path: Path) -> None:
    data = _build(tmp_path, {"a.py": "import os\n"})
    p = data.files[0].provenance
    assert (p.parser, p.completeness) == ("python-ast", "full")
    assert p.parser_version == data.meta["interpreter"]


def test_every_edge_carries_evidence_and_a_location(tmp_path: Path) -> None:
    data = _build(tmp_path, {"a.py": "x = 1\nimport os\n", "b.py": ""})
    edge = data.edges[0]
    assert edge.evidence == "import os"
    assert (edge.location.path, edge.location.line) == ("a.py", 2)


# --- cycles ---------------------------------------------------------------------------------------


def test_a_two_module_cycle_is_found_and_eager(tmp_path: Path) -> None:
    data = _build(tmp_path, {"a.py": "import b\n", "b.py": "import a\n"})
    assert [(c.modules, c.eager) for c in data.cycles] == [(("a", "b"), True)]
    assert len(data.cycles[0].edges) == 2


def test_a_module_importing_itself_is_a_cycle(tmp_path: Path) -> None:
    data = _build(tmp_path, {"a.py": "import a\n"})
    assert [c.modules for c in data.cycles] == [("a",)]


def test_a_cycle_through_a_function_import_is_not_eager(tmp_path: Path) -> None:
    data = _build(tmp_path, {"a.py": "import b\n", "b.py": "def f():\n    import a\n"})
    assert [(c.modules, c.eager) for c in data.cycles] == [(("a", "b"), False)]


def test_a_cycle_through_type_checking_is_not_eager(tmp_path: Path) -> None:
    data = _build(
        tmp_path,
        {
            "a.py": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import b\n",
            "b.py": "import a\n",
        },
    )
    assert [(c.modules, c.eager) for c in data.cycles] == [(("a", "b"), False)]


def test_unknown_edges_never_make_a_cycle(tmp_path: Path) -> None:
    data = _build(
        tmp_path,
        {
            "a.py": "import b\n",
            "b.py": "import importlib\nimportlib.import_module(name)\n",
        },
    )
    assert data.cycles == ()


def test_a_package_and_its_submodule_are_not_a_cycle_by_themselves(
    tmp_path: Path,
) -> None:
    data = _build(
        tmp_path,
        {
            "pkg/__init__.py": "from . import a\n",
            "pkg/a.py": "from . import b\n",
            "pkg/b.py": "",
        },
    )
    assert data.cycles == ()


def test_a_long_chain_does_not_hit_the_recursion_limit(tmp_path: Path) -> None:
    files = {f"m{i}.py": f"import m{i + 1}\n" for i in range(1500)}
    files["m1500.py"] = "import m0\n"
    data = _build(tmp_path, files)
    assert len(data.cycles) == 1 and len(data.cycles[0].modules) == 1501


# --- determinism and serialization --------------------------------------------------------------------


def _tree() -> dict[str, str]:
    return {
        "pkg/__init__.py": "from . import a\n",
        "pkg/a.py": "import os\nimport pkg.b\nfrom pkg import c\nimport yaml\n",
        "pkg/b.py": "import pkg.a\n",
        "pkg/c.py": "def f():\n    import pkg.a\n",
        "tools/run.py": "import pkg.a\n",
    }


def test_the_output_does_not_depend_on_the_order_of_the_input_files(
    tmp_path: Path,
) -> None:
    names = list(_tree())
    first = _build(tmp_path, _tree(), order=names)
    shuffled = names[:]
    random.Random(7).shuffle(shuffled)
    second = build_structure(tmp_path, [Path(p) for p in shuffled], stdlib=STDLIB)
    assert json.dumps(structure_payload(first)) == json.dumps(structure_payload(second))


def test_two_runs_give_byte_identical_json(tmp_path: Path) -> None:
    _write(tmp_path, _tree())
    paths = [Path(p) for p in _tree()]
    one = json.dumps(structure_payload(build_structure(tmp_path, paths, stdlib=STDLIB)))
    two = json.dumps(structure_payload(build_structure(tmp_path, paths, stdlib=STDLIB)))
    assert one == two


def test_the_summary_counts_agree_with_the_edges(tmp_path: Path) -> None:
    data = _build(tmp_path, _tree())
    info = summary(data)
    assert info["imports"] == len(data.edges)
    assert sum(info["imports_by_class"].values()) == len(data.edges)
    assert sum(info["imports_by_confidence"].values()) == len(data.edges)
    assert sum(info["files_by_completeness"].values()) == len(data.files)
    assert info["cycles"] == len(data.cycles)


def test_the_payload_is_plain_json(tmp_path: Path) -> None:
    payload = structure_payload(_build(tmp_path, _tree()))
    assert json.loads(json.dumps(payload)) == payload
    assert set(payload) == {
        "schema",
        "language",
        "meta",
        "summary",
        "files",
        "modules",
        "externals",
        "edges",
        "cycles",
    }
    assert payload["meta"]["stdlib_source"] == "injected"


def test_paths_are_repo_relative_and_posix(tmp_path: Path) -> None:
    data = _build(tmp_path, _tree())
    assert all("\\" not in f.path and not f.path.startswith("/") for f in data.files)
    assert all("\\" not in e.location.path for e in data.edges)


def test_the_builder_reads_only_the_files_it_is_given(tmp_path: Path) -> None:
    _write(tmp_path, {"ok.py": "import os\n", "secret_key.py": "import sys\n"})
    seen: list[str] = []

    def reader(root: Path, rel: str) -> bytes | None:
        seen.append(rel)
        return (root / rel).read_bytes()

    build_structure(tmp_path, [Path("ok.py")], stdlib=STDLIB, reader=reader)
    assert seen == ["ok.py"]


# --- the report surface ----------------------------------------------------------------------------------


def _report(tmp_path: Path) -> ReportData:
    from _golden_fixtures import FIXTURES

    root = tmp_path / "proj"
    root.mkdir()
    data = FIXTURES["minimal"](root)
    paths = _write(root, _tree())
    data.structure = build_structure(root, paths, stdlib=STDLIB)
    return data


def test_the_flag_is_off_by_default_and_reaches_the_config() -> None:
    parser = build_parser()
    assert parser.parse_args([]).structure is False
    args = parser.parse_args(["--structure"])
    assert args.structure is True
    assert SarandConfig.from_args(args).structure is True
    assert SarandConfig.from_args(parser.parse_args([])).structure is False


def test_a_default_report_has_no_structure_anywhere(tmp_path: Path) -> None:
    from _golden_fixtures import FIXTURES
    from sarand.renderers import html, json_renderer, markdown, text

    root = tmp_path / "p"
    root.mkdir()
    data = FIXTURES["minimal"](root)
    assert data.structure is None
    assert "Repository structure" not in markdown.render(data, include_source=False)
    assert "Repository structure" not in html.render(data, include_source=False)
    assert "structure" not in json.loads(
        json_renderer.render(data, include_source=False)
    )
    assert "cycle(s)" not in text.render(data, include_source=False)


def test_every_format_tells_the_same_counts(tmp_path: Path) -> None:
    from sarand.renderers import html, json_renderer, markdown, text

    data = _report(tmp_path)
    assert data.structure is not None
    info = summary(data.structure)
    md = markdown.render(data, include_source=False)
    page = html.render(data, include_source=False)
    payload = json.loads(json_renderer.render(data, include_source=False))
    assert payload["schema_version"] == "1.7"
    assert payload["structure"]["summary"] == info
    for line in structure_lines(data):
        assert f"- {line}" in md
    assert f"Imports: {info['imports']} (" in page
    assert f"{info['modules']} modules, {info['imports']} imports" in text.render(
        data, include_source=False
    )
    cycle_lines, total = structure_cycle_lines(data)
    assert total == info["cycles"] and all(f"- {c}" in md for c in cycle_lines)


def test_the_rows_of_the_report_come_from_the_model(tmp_path: Path) -> None:
    data = _report(tmp_path)
    externals, total = structure_external_rows(data)
    assert [row[0] for row in externals] == ["yaml"] and total == 1
    attention, attention_total = structure_attention_rows(data)
    assert attention == [] and attention_total == 0


def test_the_unresolved_list_is_limited_but_the_total_is_not(tmp_path: Path) -> None:
    files = {
        "a.py": "".join(f"import ghost{i}.sub\n" for i in range(3)),
        "ghost0/__init__.py": "",
    }
    root = tmp_path / "proj"
    root.mkdir()
    from _golden_fixtures import FIXTURES

    data = FIXTURES["minimal"](root)
    data.structure = build_structure(root, _write(root, files), stdlib=STDLIB)
    rows, total = structure_attention_rows(data)
    assert total == 1 and len(rows) == 1
