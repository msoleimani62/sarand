"""R14-A1 audit remediation: the contracts the first delivery left implicit.

Each group states a contract and proves it through the public behaviour (the model, the
builder, the serializer and the renderers), not through helper internals. The groups
follow the audit findings (A model, B extraction, C roots, D cycles, E builder,
F serialization, G renderers).
R14-A1: قراردادهایی که تحویل اول ضمنی گذاشته بود، از طریق رفتار عمومی اثبات می‌شوند.
"""

from __future__ import annotations

import ast
import json
import random
from dataclasses import replace
from itertools import pairwise
from pathlib import Path
from typing import Any

from _structure_helpers import STDLIB, build, edge_to, edges_of, write_tree
from sarand.structure import build_structure, python_extract
from sarand.structure.cycles import find_cycles
from sarand.structure.model import (
    SCHEMA_VERSION,
    Cycle,
    Edge,
    ExternalRef,
    FileEntity,
    ModelError,
    ModuleEntity,
    Provenance,
    SourceLocation,
    StructureData,
)
from sarand.structure.roots import (
    declared_roots,
    file_root,
    module_name,
    normalise_root,
)
from sarand.structure.serialize import canonical, structure_payload, summary

LOC = SourceLocation("a.py", 1, 0, 1, 5)


def _edge(source: str, target: str, flags: tuple[str, ...] = (), line: int = 1) -> Edge:
    return Edge(
        kind="imports",
        source=source,
        requested=target,
        target=target,
        target_class="internal",
        confidence="definite",
        resolution_method="absolute-module",
        evidence=f"import {target}",
        location=SourceLocation("a.py", line, 0, line, 9),
        original_type="import",
        flags=flags,
    )


# --- A: the model ----------------------------------------------------------------------------


def test_model_objects_cannot_be_changed_after_construction(tmp_path: Path) -> None:
    data = build(tmp_path, {"a.py": "import os\n"})
    for target in (data.meta, data.files[0].extensions):
        try:
            target["x"] = 1  # type: ignore[index]
        except TypeError:
            continue
        raise AssertionError("a nested mapping accepted a write")
    assert isinstance(data.meta["source_roots"], tuple)


def test_nested_inputs_are_copied_not_shared(tmp_path: Path) -> None:
    source: dict[str, Any] = {"b": ["x", "y"], "a": 1}
    entity = FileEntity(
        path="a.py",
        language="python",
        size=1,
        sha256="",
        module="a",
        provenance=Provenance("python-ast", "3", "", "full"),
        extensions=source,
    )
    source["b"].append("z")
    source["a"] = 2
    assert dict(entity.extensions) == {"a": 1, "b": ("x", "y")}


def test_invalid_values_are_rejected_at_construction_with_a_clear_message() -> None:
    cases = [
        lambda: Provenance("python-ast", "3", "", "mostly"),
        lambda: Provenance("python-ast", "3", "", "full", ("made_up",)),
        lambda: ExternalRef("x", "internal"),
        lambda: ExternalRef("x", "stdlib", ("pyproject.toml",)),
        lambda: replace(_edge("a", "b"), target_class="nowhere"),
        lambda: replace(_edge("a", "b"), confidence="certain"),
        lambda: replace(_edge("a", "b"), kind="calls"),
        lambda: replace(_edge("a", "b"), flags=("sparkly",)),
        lambda: replace(_edge("a", "b"), target=""),
        lambda: SourceLocation("/abs/a.py", 1, 0, 1, 1),
        lambda: SourceLocation("a\\b.py", 1, 0, 1, 1),
        lambda: SourceLocation("../a.py", 1, 0, 1, 1),
        lambda: SourceLocation("a.py", -1, 0, 1, 1),
        lambda: SourceLocation("a.py", True, 0, 1, 1),  # type: ignore[arg-type]
        lambda: ModuleEntity("", "a.py", False, False, ""),
        lambda: ModuleEntity("ns", "x.py", True, True, ""),
        lambda: Cycle((), True, ()),
        lambda: FileEntity(
            "a.py", "python", -3, "", "a", Provenance("p", "3", "", "full")
        ),
        lambda: FileEntity(
            "a.py", "python", 1, "XYZ", "a", Provenance("p", "3", "", "full")
        ),
    ]
    for make in cases:
        try:
            make()
        except ModelError as exc:
            assert str(exc)
            continue
        raise AssertionError("an invalid value was accepted")


def test_a_dynamic_or_unresolved_edge_may_have_an_empty_target() -> None:
    edge = replace(
        _edge("a", "b"), target="", target_class="dynamic", confidence="unknown"
    )
    assert edge.target == ""
    assert replace(edge, target_class="internal_unresolved").target == ""


def test_the_summary_cannot_fail_on_a_bad_value_because_it_cannot_be_built() -> None:
    try:
        replace(_edge("a", "b"), target_class="mystery")
    except ModelError:
        pass
    else:
        raise AssertionError("a bad class reached the model")


def test_the_inner_and_outer_schema_versions_are_independent(tmp_path: Path) -> None:
    from _golden_fixtures import FIXTURES
    from sarand.renderers import json_renderer

    root = tmp_path / "p"
    root.mkdir()
    data = FIXTURES["minimal"](root)
    data.structure = build_structure(
        root, write_tree(root, {"a.py": "import os\n"}), stdlib=STDLIB
    )
    payload = json.loads(json_renderer.render(data, include_source=False))
    assert payload["schema_version"] == "1.10"
    assert payload["structure"]["schema"] == SCHEMA_VERSION == 4
    assert isinstance(payload["structure"]["schema"], int)


def test_an_unreadable_file_has_an_unknown_size_not_zero(tmp_path: Path) -> None:
    data = build_structure(
        tmp_path, [Path("ghost.py")], stdlib=STDLIB, reader=lambda _root, _rel: None
    )
    only = data.files[0]
    assert only.size is None and only.sha256 == ""
    assert only.provenance.completeness == "failed"
    assert only.provenance.limitations == ("unreadable",)
    assert structure_payload(data)["files"][0]["size"] is None


def test_an_empty_file_has_a_real_size_of_zero(tmp_path: Path) -> None:
    data = build(tmp_path, {"empty.py": ""})
    assert data.files[0].size == 0


# --- B: import extraction ---------------------------------------------------------------------


def test_builtin_dunder_import_reads_its_level_from_index_four_or_the_keyword(
    tmp_path: Path,
) -> None:
    data = build(
        tmp_path,
        {
            "p/__init__.py": "",
            "p/a.py": (
                "__import__('b', globals(), locals(), [], 1)\n"
                "__import__('b', globals(), level=1)\n"
                "__import__('b', globals(), locals(), [], 0)\n"
            ),
            "p/b.py": "",
        },
    )
    got = [(e.requested, e.target_class) for e in edges_of(data, "p.a")]
    assert got == [
        ("p.b", "internal"),
        ("p.b", "internal"),
        ("b", "external_unmatched"),
    ]


def test_a_relative_dunder_import_without_a_plain_globals_is_unresolved(
    tmp_path: Path,
) -> None:
    data = build(
        tmp_path,
        {
            "p/__init__.py": "",
            "p/a.py": "__import__('b', {}, None, (), 1)\n",
            "p/b.py": "",
        },
    )
    edge = edges_of(data, "p.a")[0]
    assert (edge.target_class, edge.confidence) == ("internal_unresolved", "unknown")


def test_an_aliased_builtin_dunder_import_is_recognised_and_a_lookalike_is_not(
    tmp_path: Path,
) -> None:
    data = build(
        tmp_path,
        {
            "a.py": (
                "from builtins import __import__ as ci\nci('os')\n"
                "import builtins as bi\nbi.__import__('sys')\n"
            ),
            "b.py": "def __import__(x): ...\n__import__('os')\n",
        },
    )
    assert {
        e.requested for e in edges_of(data, "a") if e.original_type == "dynamic_call"
    } == {
        "os",
        "sys",
    }
    assert [e for e in edges_of(data, "b") if e.original_type == "dynamic_call"] == []


def test_importlib_module_and_member_aliases_are_recognised(tmp_path: Path) -> None:
    data = build(
        tmp_path,
        {
            "a.py": (
                "import importlib as il\nil.import_module('os')\n"
                "from importlib import import_module as im\nim('sys')\n"
                "from importlib import import_module\nimport_module('types')\n"
            )
        },
    )
    got = {
        e.requested for e in edges_of(data, "a") if e.original_type == "dynamic_call"
    }
    assert got == {"os", "sys", "types"}


def test_an_alias_does_not_leak_into_another_scope_or_survive_reassignment(
    tmp_path: Path,
) -> None:
    data = build(
        tmp_path,
        {
            "a.py": (
                "def f():\n    from importlib import import_module\n    import_module('os')\n"
                "def g():\n    import_module('sys')\n"
                "def h():\n    import_module = print\n    import_module('types')\n"
                "import importlib\nimportlib = None\nimportlib.import_module('re')\n"
            )
        },
    )
    got = [
        e.requested for e in edges_of(data, "a") if e.original_type == "dynamic_call"
    ]
    assert got == ["os"]


def test_a_name_bound_two_different_ways_is_ambiguous_and_not_recognised(
    tmp_path: Path,
) -> None:
    data = build(
        tmp_path,
        {
            "a.py": (
                "from importlib import import_module\nimport_module = print\n"
                "import_module('os')\n"
            )
        },
    )
    assert [e for e in data.edges if e.original_type == "dynamic_call"] == []


def test_type_checking_is_recognised_only_from_the_typing_sentinel(
    tmp_path: Path,
) -> None:
    data = build(
        tmp_path,
        {
            "a.py": (
                "import custom\nif custom.TYPE_CHECKING:\n    import os\n"
                "TYPE_CHECKING = True\nif TYPE_CHECKING:\n    import sys\n"
            ),
            "b.py": (
                "from typing import TYPE_CHECKING as T\nimport typing as t\n"
                "if T:\n    import os\nif t.TYPE_CHECKING:\n    import sys\n"
                "if not T:\n    import types\nelse:\n    import json\n"
            ),
            "c.py": "TYPE_CHECKING = False\nif TYPE_CHECKING:\n    import os\n",
            "d.py": "from other import TYPE_CHECKING\nif TYPE_CHECKING:\n    import os\n",
            "e.py": (
                "from typing import TYPE_CHECKING\n"
                "def f(TYPE_CHECKING):\n    if TYPE_CHECKING:\n        import os\n"
            ),
        },
    )
    flags = {(e.source, e.requested): set(e.flags) for e in data.edges}
    assert flags[("a", "os")] == {"conditional"}
    assert flags[("a", "sys")] == {"conditional"}
    assert flags[("b", "os")] == {"conditional", "type_only"}
    assert flags[("b", "sys")] == {"conditional", "type_only"}
    assert flags[("b", "types")] == {"conditional"}
    assert flags[("b", "json")] == {"conditional", "type_only"}
    assert flags[("c", "os")] == {"conditional", "type_only"}
    assert flags[("d", "os")] == {"conditional"}
    assert flags[("e", "os")] == {"conditional", "lazy"}


def test_try_sections_have_their_own_control_flow(tmp_path: Path) -> None:
    data = build(
        tmp_path,
        {
            "a.py": (
                "try:\n    import os\nexcept ImportError:\n    import sys\n"
                "else:\n    import types\nfinally:\n    import typing\n"
            ),
            "b.py": "try:\n    import os\nfinally:\n    import sys\n",
        },
    )
    a = {e.requested: set(e.flags) for e in edges_of(data, "a")}
    assert a == {
        "os": {"conditional"},
        "sys": {"conditional"},
        "types": {"conditional"},
        "typing": set(),
    }
    b = {e.requested: set(e.flags) for e in edges_of(data, "b")}
    assert b == {"os": set(), "sys": set()}


def test_import_error_handlers_are_recognised_by_binding_not_by_spelling(
    tmp_path: Path,
) -> None:
    data = build(
        tmp_path,
        {
            "a.py": (
                "import foo\ntry:\n    import os\nexcept foo.ImportError:\n    pass\n"
                "IE = ImportError\ntry:\n    import sys\nexcept IE:\n    pass\n"
                "try:\n    import types\nexcept (ValueError, ModuleNotFoundError):\n    pass\n"
                "try:\n    import json\nexcept:\n    pass\n"
                "try:\n    import re\nexcept ValueError:\n    pass\n"
            ),
            "b.py": (
                "ImportError = ValueError\ntry:\n    import os\nexcept ImportError:\n    pass\n"
            ),
            "c.py": (
                "import builtins\ntry:\n    import os\nexcept builtins.ImportError:\n    pass\n"
            ),
        },
    )
    a = {
        e.requested: "conditional" in e.flags
        for e in edges_of(data, "a")
        if e.requested != "foo"
    }
    assert a == {"os": False, "sys": True, "types": True, "json": True, "re": False}
    assert "conditional" not in edge_to(data, "b", "os").flags
    assert "conditional" in edge_to(data, "c", "os").flags


def test_conditional_means_a_control_flow_decision_in_the_same_scope(
    tmp_path: Path,
) -> None:
    data = build(
        tmp_path,
        {
            "a.py": (
                "import importlib\n"
                "if x:\n    import os\nelse:\n    import sys\n"
                "for i in y:\n    import types\n"
                "while z:\n    import json\n"
                "match q:\n    case 1:\n        import re\n"
                "with ctx():\n    import typing\n"
                "import collections\n"
                "v = flag and importlib.import_module('os')\n"
                "w = importlib.import_module('sys') if flag else None\n"
                "u = [importlib.import_module('types') for _ in y]\n"
                "plain = importlib.import_module('json')\n"
            )
        },
    )
    flags = {
        (e.requested, e.original_type): "conditional" in e.flags
        for e in edges_of(data, "a")
    }
    assert flags[("os", "import")] and flags[("sys", "import")]
    assert (
        flags[("types", "import")]
        and flags[("json", "import")]
        and flags[("re", "import")]
    )
    assert not flags[("typing", "import")]  # `with` is not a decision
    assert not flags[("collections", "import")]
    assert flags[("os", "dynamic_call")]  # right side of `and`
    assert flags[("sys", "dynamic_call")]  # branch of a conditional expression
    assert flags[("types", "dynamic_call")]  # comprehension body
    assert not flags[("json", "dynamic_call")]  # plain statement


def test_decorators_and_defaults_are_not_lazy_but_the_body_is(tmp_path: Path) -> None:
    data = build(
        tmp_path,
        {
            "a.py": (
                "import importlib\n"
                "@importlib.import_module('os').deco\n"
                "def f(x=importlib.import_module('sys')):\n"
                "    importlib.import_module('types')\n"
            )
        },
    )
    flags = {
        e.requested: "lazy" in e.flags
        for e in edges_of(data, "a")
        if e.requested != "importlib"
    }
    assert flags == {"os": False, "sys": False, "types": True}


def test_return_annotations_are_traversed(tmp_path: Path) -> None:
    data = build(
        tmp_path,
        {"a.py": "import importlib\ndef f() -> importlib.import_module('os').T: ...\n"},
    )
    assert "os" in {e.requested for e in edges_of(data, "a")}


def test_import_module_resolves_a_relative_name_against_its_package_argument(
    tmp_path: Path,
) -> None:
    data = build(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/sub/__init__.py": "",
            "pkg/sub/mod.py": "",
            "pkg/top.py": "",
            "pkg/m.py": (
                "import importlib\n"
                "importlib.import_module('.top', package='pkg')\n"
                "importlib.import_module('.mod', 'pkg.sub')\n"
                "importlib.import_module('..top', package='pkg.sub')\n"
                "importlib.import_module('.top')\n"
                "importlib.import_module('..top', package='pkg')\n"
                "importlib.import_module('.top', package=name)\n"
                "importlib.import_module('pkg.top')\n"
            ),
        },
    )
    got = [
        (e.requested, e.target_class, e.confidence, e.resolution_method)
        for e in edges_of(data, "pkg.m")
        if e.original_type == "dynamic_call"
    ]
    assert got == [
        ("pkg.top", "internal", "probable", "importlib-literal"),
        ("pkg.sub.mod", "internal", "probable", "importlib-literal"),
        ("pkg.top", "internal", "probable", "importlib-literal"),
        (".top", "internal_unresolved", "unknown", "relative-name-without-package"),
        ("..top", "internal_unresolved", "unknown", "relative-beyond-top-level"),
        (".top", "dynamic", "unknown", "non-literal-package"),
        ("pkg.top", "internal", "probable", "importlib-literal"),
    ]


def test_dynamic_arguments_that_cannot_be_read_stay_unknown(tmp_path: Path) -> None:
    data = build(
        tmp_path,
        {
            "a.py": "import importlib\nimportlib.import_module(*args)\nimportlib.import_module(**kw)\n"
        },
    )
    dynamic = [e for e in data.edges if e.original_type == "dynamic_call"]
    assert [(e.target_class, e.confidence) for e in dynamic] == [
        ("dynamic", "unknown")
    ] * 2


def test_exec_and_eval_mark_the_file_only_when_they_are_the_builtins(
    tmp_path: Path,
) -> None:
    data = build(
        tmp_path,
        {"a.py": "exec('x')\n", "b.py": "def exec(x): ...\nexec('x')\n"},
    )
    limits = {f.path: f.provenance.limitations for f in data.files}
    assert "dynamic_construct_seen" in limits["a.py"]
    assert "dynamic_construct_seen" not in limits["b.py"]


def test_evidence_is_the_statement_text_bounded_and_without_a_trailing_comment(
    tmp_path: Path,
) -> None:
    long_names = ", ".join(f"name_{i:03d}" for i in range(80))
    data = build(
        tmp_path,
        {
            "a.py": (
                "import os  # <b>note</b>\n"
                "from sys import (\n    path,  # inner\n    argv,\n)\n"
                f"from json import {long_names}\n"
            )
        },
    )
    evidence = [e.evidence for e in edges_of(data, "a")]
    assert evidence[0] == "import os"
    assert evidence[1] == "from sys import ( path,  # inner argv, )"
    assert len(evidence[2]) == 240 and evidence[2].endswith("...")
    assert evidence[2].startswith("from json import name_000, name_001")


def test_columns_are_utf8_byte_offsets_for_ast_and_for_syntax_errors(
    tmp_path: Path,
) -> None:
    data = build(
        tmp_path,
        {"a.py": "x = 'é'; import os\n", "bad.py": "x = 'é'; def f(:\n    pass\n"},
    )
    edge = edges_of(data, "a")[0]
    assert edge.location.col == len("x = 'é'; ".encode())  # 10 bytes, 9 characters
    assert edge.location.end_col == edge.location.col + len("import os")
    error = next(f for f in data.files if f.path == "bad.py").error
    assert error is not None
    assert error.line == 1
    assert (
        error.col >= len("x = 'é'; ".encode()) - 1
    )  # byte based, same unit as the AST
    assert error.col >= 10 and error.end_col >= error.col


def test_a_form_feed_does_not_shift_line_numbers(tmp_path: Path) -> None:
    data = build(tmp_path, {"a.py": "x = 1\n\x0c\nimport os\n"})
    assert edges_of(data, "a")[0].location.line == 3
    assert edges_of(data, "a")[0].evidence == "import os"


def test_syntax_error_files_are_failed_without_guessing_the_grammar(
    tmp_path: Path,
) -> None:
    data = build(tmp_path, {"a.py": "x = f'{'\n", "b.py": "match x:\n  case 1: pass\n"})
    first = next(f for f in data.files if f.path == "a.py")
    assert first.provenance.completeness == "failed"
    assert first.provenance.limitations == ("syntax_error",)
    assert first.provenance.rules == ""


def test_a_walk_failure_loses_only_its_statement(tmp_path: Path) -> None:
    original = python_extract._Walker.call

    def boom(self: python_extract._Walker, node: ast.Call) -> None:
        if getattr(node.func, "id", "") == "boom":
            raise RecursionError
        original(self, node)

    python_extract._Walker.call = boom  # type: ignore[method-assign]
    try:
        data = build(tmp_path, {"a.py": "import os\nboom()\nimport sys\n"})
    finally:
        python_extract._Walker.call = original  # type: ignore[method-assign]
    only = data.files[0]
    assert only.provenance.completeness == "partial"
    assert "recursion_limit" in only.provenance.limitations
    assert [e.requested for e in data.edges] == ["os", "sys"]


def test_a_memory_failure_while_walking_is_a_resource_limit(tmp_path: Path) -> None:
    original = python_extract._Walker.call

    def boom(self: python_extract._Walker, node: ast.Call) -> None:
        raise MemoryError

    python_extract._Walker.call = boom  # type: ignore[method-assign]
    try:
        data = build(tmp_path, {"a.py": "import os\nf()\nimport sys\n"})
    finally:
        python_extract._Walker.call = original  # type: ignore[method-assign]
    only = data.files[0]
    assert only.provenance.completeness == "partial"
    assert "resource_limit" in only.provenance.limitations
    assert [e.requested for e in data.edges] == ["os"]


def test_a_deep_expression_never_crashes_and_keeps_earlier_imports(
    tmp_path: Path,
) -> None:
    deep = "x = " + "+".join(["1"] * 4000) + "\n"
    data = build(tmp_path, {"a.py": f"import os\n{deep}import sys\n"})
    only = data.files[0]
    assert only.provenance.completeness in ("full", "partial", "failed")
    if only.provenance.completeness != "failed":
        assert {"os", "sys"} <= {e.requested for e in data.edges}
    assert only.provenance.completeness == "full" or only.provenance.limitations


def test_the_node_cap_keeps_the_imports_found_before_it(tmp_path: Path) -> None:
    original = python_extract.MAX_NODES_PER_FILE
    python_extract.MAX_NODES_PER_FILE = 12
    try:
        data = build(
            tmp_path, {"a.py": "import os\n" + "x = 1\n" * 50 + "import sys\n"}
        )
    finally:
        python_extract.MAX_NODES_PER_FILE = original
    only = data.files[0]
    assert only.provenance.completeness == "partial"
    assert only.provenance.limitations == ("node_cap",)
    assert [e.requested for e in data.edges] == ["os"]


# --- C: source roots and module names -------------------------------------------------------------


def test_a_named_package_dir_mapping_renames_the_package(tmp_path: Path) -> None:
    data = build(
        tmp_path,
        {
            "pyproject.toml": '[tool.setuptools]\npackage-dir = {"mypkg" = "lib/other"}\n',
            "lib/other/__init__.py": "from . import util\n",
            "lib/other/util.py": "",
            "tools/run.py": "import mypkg.util\n",
        },
    )
    names = {m.name for m in data.modules if not m.is_namespace}
    assert {"mypkg", "mypkg.util"} <= names
    assert edge_to(data, "run", "mypkg.util").target == "mypkg.util"
    assert data.meta["declared_roots"] == ("mypkg=lib/other",)


def test_the_empty_and_named_package_dir_keys_work_together(tmp_path: Path) -> None:
    roots, rejected = declared_roots(
        "", '[tool.setuptools]\npackage-dir = {"" = "src", "extra" = "vendor/extra"}\n'
    )
    assert [(r.path, r.prefix) for r in roots] == [
        ("src", ""),
        ("vendor/extra", "extra"),
    ]
    assert rejected == []


def test_root_declarations_that_leave_the_project_are_rejected_and_reported(
    tmp_path: Path,
) -> None:
    data = build(
        tmp_path,
        {
            "pyproject.toml": (
                '[tool.setuptools]\npackage-dir = {"" = "../outside", "a" = "/abs", "b" = "x\\\\y"}\n'
                '[tool.maturin]\npython-source = "py"\n'
            ),
            "py/m.py": "",
        },
    )
    assert data.meta["declared_roots"] == ("py",)
    assert data.meta["rejected_roots"] == ("../outside", "a = /abs", "b = x\\y")


def test_root_paths_are_normalised_inside_the_project() -> None:
    assert normalise_root("", "./src/") == "src"
    assert normalise_root("sub", "../x") == "x"
    assert normalise_root("", ".") == ""
    assert normalise_root("", "a/../b") == "b"
    assert normalise_root("sub", "../..") is None
    assert normalise_root("", "../up") is None
    assert normalise_root("", "/etc") is None
    assert normalise_root("", "C:/x") is None
    assert normalise_root("", "a\\b") is None
    assert normalise_root("", "   ") is None


def test_a_module_name_needs_the_path_to_be_inside_its_root() -> None:
    assert module_name("other/x.py", "lib") == ("", False)
    assert module_name("libx/y.py", "lib") == ("", False)
    assert module_name("lib/x.py", "lib") == ("x", False)
    assert module_name("lib/pkg/__init__.py", "lib") == ("pkg", True)
    assert module_name("lib", "lib") == ("", False)
    assert module_name("lib/not-a-name/x.py", "lib") == ("", False)
    assert module_name("x.py", "") == ("x", False)


def test_a_root_level_init_has_no_importable_name(tmp_path: Path) -> None:
    data = build(tmp_path, {"__init__.py": "import os\n", "a.py": "import sys\n"})
    init = next(f for f in data.files if f.path == "__init__.py")
    assert init.module == ""
    assert {e.source for e in data.edges} == {
        "__init__.py",
        "a",
    }  # still listed, by path
    assert all(m.name != "" for m in data.modules)


def test_regular_namespace_and_mixed_packages_resolve_like_python(
    tmp_path: Path,
) -> None:
    data = build(
        tmp_path,
        {
            "src/reg/__init__.py": "",
            "src/reg/mod.py": "",
            "src/ns/inner/mod.py": "",
            "src/mix/__init__.py": "",
            "src/mix/sub/leaf.py": "",
            "app/main.py": "import reg.mod\nimport ns.inner.mod\nimport mix.sub.leaf\n",
            "pyproject.toml": '[tool.setuptools]\npackage-dir = {"" = "src"}\n',
        },
    )
    got = {e.requested: (e.target, e.target_class) for e in edges_of(data, "main")}
    assert got["reg.mod"] == ("reg.mod", "internal")
    assert got["ns.inner.mod"] == ("ns.inner.mod", "internal")
    assert got["mix.sub.leaf"] == ("mix.sub.leaf", "internal")
    kinds = {m.name: m.is_namespace for m in data.modules}
    assert kinds["ns"] and kinds["ns.inner"] and kinds["mix.sub"]
    assert not kinds["reg"] and not kinds["mix"]


def test_a_namespace_package_keeps_every_root_it_has_a_portion_in(
    tmp_path: Path,
) -> None:
    data = build(
        tmp_path,
        {
            "pyproject.toml": (
                '[tool.setuptools]\npackage-dir = {"" = "a"}\n'
                '[tool.maturin]\npython-source = "b"\n'
            ),
            "a/ns/x.py": "",
            "b/ns/y.py": "",
            "b/user.py": "import ns.x\nimport ns.y\n",
        },
    )
    portions = sorted(m.root for m in data.modules if m.name == "ns" and m.is_namespace)
    assert portions == ["a", "b"]
    assert edge_to(data, "user", "ns.x").target == "ns.x"
    assert edge_to(data, "user", "ns.y").target == "ns.y"
    assert (
        summary(data)["namespace_packages"] == 1
    )  # one namespace package, two portions


def test_the_longest_declared_root_wins(tmp_path: Path) -> None:
    roots, _ = declared_roots(
        "",
        '[tool.maturin]\npython-source = "a"\n[tool.setuptools]\npackage-dir = {"" = "a/b"}\n',
    )
    assert file_root("a/b/x.py", roots, frozenset()) == ("a/b", "")
    assert file_root("a/x.py", roots, frozenset()) == ("a", "")


def test_the_path_contract_rejects_absolute_and_parent_paths(tmp_path: Path) -> None:
    for bad in (Path("/etc/x.py"), Path("../x.py"), Path("a/../../x.py")):
        for call in (
            lambda p=bad: build_structure(tmp_path, [p], stdlib=STDLIB),
            lambda p=bad: build_structure(tmp_path, [], [(p, 5)], stdlib=STDLIB),
        ):
            try:
                call()
            except ValueError as exc:
                assert "relative" in str(exc)
                continue
            raise AssertionError(f"{bad} was accepted")


def test_nested_relative_paths_are_normalised(tmp_path: Path) -> None:
    write_tree(tmp_path, {"a/b.py": "import os\n"})
    data = build_structure(tmp_path, [Path("a/./b.py"), Path("a//b.py")], stdlib=STDLIB)
    assert [f.path for f in data.files] == ["a/b.py"]


def test_files_the_secret_steps_exclude_never_reach_the_structure(
    tmp_path: Path,
) -> None:
    from sarand.core.secrets import exclude_flagged_files, exclude_paths
    from sarand.models.results import SecretFinding

    write_tree(
        tmp_path,
        {
            "ok.py": "import os\n",
            "leaky.py": "import sys\n",
            "also.py": "import json\n",
        },
    )
    included = [Path("also.py"), Path("leaky.py"), Path("ok.py")]
    # the same two steps the CLI runs before it builds the structure
    kept, excluded = exclude_flagged_files(
        included, [], [SecretFinding("leaky.py", 1, "aws")]
    )
    kept, excluded = exclude_paths(kept, excluded, [Path("also.py")])
    data = build_structure(tmp_path, kept, stdlib=STDLIB)
    assert sorted(excluded) == [Path("also.py"), Path("leaky.py")]
    assert [f.path for f in data.files] == ["ok.py"]
    dumped = json.dumps(structure_payload(data))
    assert "leaky" not in dumped and "also.py" not in dumped


# --- D: cycles ---------------------------------------------------------------------------------------


def _modules(cycles: tuple[Cycle, ...]) -> list[tuple[str, ...]]:
    return [c.modules for c in cycles]


def test_disconnected_components_and_several_sccs_are_all_found() -> None:
    edges = [
        _edge("a", "b"), _edge("b", "a"),
        _edge("c", "d"), _edge("d", "e"), _edge("e", "c"),
        _edge("x", "y"),
        _edge("p", "p"),
    ]  # fmt: skip
    assert _modules(find_cycles(edges)) == [("a", "b"), ("c", "d", "e"), ("p",)]


def test_a_node_between_two_cycles_joins_them_into_one_component() -> None:
    edges = [
        _edge("a", "b"),
        _edge("b", "a"),
        _edge("b", "c"),
        _edge("c", "d"),
        _edge("d", "b"),
    ]
    assert _modules(find_cycles(edges)) == [("a", "b", "c", "d")]


def test_parallel_edges_do_not_change_the_cycle_set_but_are_all_reported() -> None:
    edges = [_edge("a", "b", line=1), _edge("a", "b", line=2), _edge("b", "a", line=3)]
    (cycle,) = find_cycles(edges)
    assert cycle.modules == ("a", "b") and len(cycle.edges) == 3


def test_a_self_import_is_a_cycle_and_a_plain_chain_is_not() -> None:
    assert _modules(find_cycles([_edge("a", "a")])) == [("a",)]
    assert find_cycles([_edge("a", "b"), _edge("b", "c")]) == ()


def test_low_link_values_propagate_through_a_deep_chain_with_a_back_edge() -> None:
    names = [f"m{i}" for i in range(3000)]
    edges = [_edge(a, b) for a, b in pairwise(names)]
    edges.append(_edge(names[-1], names[0]))
    (cycle,) = find_cycles(edges)
    assert len(cycle.modules) == 3000


def test_the_cycle_output_does_not_depend_on_the_order_of_the_edges() -> None:
    edges = [
        _edge("a", "b"), _edge("b", "c"), _edge("c", "a"),
        _edge("x", "y"), _edge("y", "x"), _edge("c", "x"),
    ]  # fmt: skip
    first = find_cycles(edges)
    shuffled = edges[:]
    random.Random(3).shuffle(shuffled)
    assert find_cycles(shuffled) == first


def test_cycle_edges_are_every_internal_edge_with_its_own_flags() -> None:
    edges = [
        _edge("a", "b"),
        _edge("b", "a", flags=("lazy",)),
        _edge("a", "c"),  # leaves the cycle: not included
    ]
    (cycle,) = find_cycles(edges)
    assert [(e.source, e.target, e.flags) for e in cycle.edges] == [
        ("a", "b", ()),
        ("b", "a", ("lazy",)),
    ]
    assert cycle.eager is False  # the only way back is lazy


def test_eager_needs_an_eager_cycle_among_the_non_lazy_non_type_only_edges() -> None:
    mixed = [
        _edge("a", "b"), _edge("b", "a", flags=("lazy",)),
        _edge("c", "d"), _edge("d", "c"), _edge("c", "a"), _edge("a", "c", flags=("type_only",)),
    ]  # fmt: skip
    cycles = {c.modules: c.eager for c in find_cycles(mixed)}
    assert cycles == {("a", "b", "c", "d"): True}  # c <-> d is eager and inside the SCC
    only_type = [_edge("a", "b", flags=("type_only", "conditional")), _edge("b", "a")]
    assert [c.eager for c in find_cycles(only_type)] == [False]
    conditional = [_edge("a", "b", flags=("conditional",)), _edge("b", "a")]
    assert [c.eager for c in find_cycles(conditional)] == [True]


def test_unknown_confidence_edges_never_make_a_cycle() -> None:
    edges = [_edge("a", "b"), replace(_edge("b", "a"), confidence="unknown")]
    assert find_cycles(edges) == ()


# --- E and F: builder metadata, canonical serialization -------------------------------------------------


def test_metadata_is_deterministic_and_names_its_environment(tmp_path: Path) -> None:
    files = {"b/y.py": "", "a/x.py": "import os\n", "pyproject.toml": ""}
    paths = write_tree(tmp_path, files)
    one = build_structure(tmp_path, paths, stdlib=STDLIB)
    two = build_structure(tmp_path, list(reversed(paths)), stdlib=STDLIB)
    assert dict(one.meta) == dict(two.meta)
    assert set(one.meta) == {
        "interpreter", "stdlib_source", "stdlib_count", "source_roots", "declared_roots",
        "rejected_roots", "parser", "fingerprint_basis",
    }  # fmt: skip
    assert one.meta["source_roots"] == ("a", "b")
    assert one.meta["stdlib_count"] == len(STDLIB)


def _shuffled_equal_model(data: StructureData, seed: int) -> StructureData:
    rng = random.Random(seed)

    def shuffled(items: tuple) -> tuple:  # type: ignore[type-arg]
        pool = list(items)
        rng.shuffle(pool)
        return tuple(pool)

    return StructureData(
        schema_version=data.schema_version,
        language=data.language,
        meta=dict(reversed(list(data.meta.items()))),
        files=shuffled(data.files),
        modules=shuffled(data.modules),
        externals=shuffled(data.externals),
        edges=shuffled(data.edges),
        cycles=tuple(
            Cycle(c.modules, c.eager, shuffled(c.edges)) for c in shuffled(data.cycles)
        ),
        symbols=shuffled(data.symbols),
        relations=shuffled(data.relations),
        entry_points=shuffled(data.entry_points),
        external_use=shuffled(data.external_use),
        sites=dict(reversed(list(data.sites.items()))),
    )


def test_the_serializer_orders_every_collection_itself(tmp_path: Path) -> None:
    data = build(
        tmp_path,
        {
            "pkg/__init__.py": "from . import a\nimport yaml\n",
            "pkg/a.py": "import pkg.b\nimport os\nimport requests\n",
            "pkg/b.py": "import pkg.a\nfrom pkg import c\n",
            "pkg/c.py": "def f():\n    import pkg.a\n",
            "ns/deep/m.py": "",
        },
    )
    reference = json.dumps(structure_payload(data))
    for seed in range(5):
        assert (
            json.dumps(structure_payload(_shuffled_equal_model(data, seed)))
            == reference
        )


def test_nested_metadata_and_extensions_are_canonical_and_the_model_is_untouched() -> (
    None
):
    extensions: dict[str, Any] = {"z": {"b": 1, "a": (3, 1, 2)}, "a": True}
    meta: dict[str, Any] = {"seq": ("b", "a"), "map": {"y": ("2", "1"), "x": 1}}
    entity = FileEntity(
        path="a.py",
        language="python",
        size=3,
        sha256="",
        module="a",
        provenance=Provenance("python-ast", "3", "", "full"),
        extensions=extensions,
    )
    data = StructureData(1, "python", meta, (entity,), (), (), (), ())
    before = repr(data)
    payload = structure_payload(data)
    assert list(payload["meta"]) == ["map", "seq"]
    assert payload["meta"]["seq"] == ["a", "b"]
    assert list(payload["meta"]["map"]) == ["x", "y"]
    assert payload["meta"]["map"]["y"] == ["1", "2"]
    extensions = payload["files"][0]["extensions"]
    assert list(extensions) == ["a", "z"]
    assert list(extensions["z"]) == ["a", "b"]
    assert extensions["z"]["a"] == [
        3,
        1,
        2,
    ]  # the order of an extension sequence is kept
    assert repr(data) == before
    assert json.loads(json.dumps(payload)) == payload


def test_canonical_is_plain_json_for_the_supported_value_types() -> None:
    value = {"b": (1, [2, {"d": 1, "c": 2}]), "a": None, "e": {3, 1}}
    result = canonical(value)
    assert list(result) == ["a", "b", "e"]
    assert result["b"] == [1, [2, {"c": 2, "d": 1}]]
    assert canonical({"s": {"q", "p"}}, sort_sequences=True) == {"s": ["p", "q"]}


def test_summary_counts_for_empty_and_mixed_models(tmp_path: Path) -> None:
    empty = build_structure(tmp_path, [], stdlib=STDLIB)
    info = summary(empty)
    assert (info["files"], info["modules"], info["packages"], info["imports"]) == (
        0,
        0,
        0,
        0,
    )
    assert info["namespace_packages"] == 0 and info["cycles"] == 0
    data = build(
        tmp_path,
        {"pkg/__init__.py": "", "pkg/a.py": "import os\n", "ns/x.py": "", "top.py": ""},
    )
    mixed = summary(data)
    assert (
        mixed["modules"] == 4
    )  # pkg, pkg.a, ns.x? no: ns/x.py is module x under root ns
    assert mixed["packages"] == 1


# --- G: renderers --------------------------------------------------------------------------------------


def _report(tmp_path: Path, structure: StructureData):  # type: ignore[no-untyped-def]
    from _golden_fixtures import FIXTURES

    root = tmp_path / "proj"
    root.mkdir(exist_ok=True)
    data = FIXTURES["minimal"](root)
    data.structure = structure
    return data


def _cycle_files(count: int) -> dict[str, str]:
    files: dict[str, str] = {}
    for i in range(count):
        files[f"a{i:02d}.py"] = f"import b{i:02d}\n"
        files[f"b{i:02d}.py"] = f"import a{i:02d}\n"
    return files


def _markdown(data) -> str:  # type: ignore[no-untyped-def]
    from sarand.renderers import markdown

    return markdown.render(data, include_source=False)


def _html(data) -> str:  # type: ignore[no-untyped-def]
    from sarand.renderers import html

    return html.render(data, include_source=False)


def test_the_cycle_list_is_cut_at_ten_and_says_how_many_are_hidden(
    tmp_path: Path,
) -> None:
    for count, hidden in ((9, 0), (10, 0), (11, 1), (25, 15)):
        sub = tmp_path / f"c{count}"
        sub.mkdir()
        data = _report(sub, build(sub, _cycle_files(count)))
        md = _markdown(data)
        assert md.count(" <-> ") == min(count, 10), count
        assert f"- Import cycles: {count} (" in md
        assert (f"- ... and {hidden} more (see the JSON report)" in md) == (
            hidden > 0
        ), count
        page = _html(data)
        assert page.count(" &lt;-&gt; ") == min(count, 10)
        assert (f"... and {hidden} more" in page) == (hidden > 0)


def test_the_unresolved_list_is_cut_at_twenty_and_the_total_stays_true(
    tmp_path: Path,
) -> None:
    for count, hidden in ((19, 0), (20, 0), (21, 1), (30, 10)):
        sub = tmp_path / f"u{count}"
        sub.mkdir()
        body = "".join(f"import pkg.missing{i:02d}\n" for i in range(count))
        data = _report(sub, build(sub, {"pkg/__init__.py": "", "app.py": body}))
        md = _markdown(data)
        assert md.count("| app | `import pkg.missing") == min(count, 20), count
        assert f"unresolved {count}," in md
        assert (f"{hidden} more not shown (see the JSON report)." in md) == (
            hidden > 0
        ), count
        assert (f"{hidden} more not shown" in _html(data)) == (hidden > 0)


def test_the_external_list_is_cut_at_thirty_and_the_total_stays_true(
    tmp_path: Path,
) -> None:
    for count, hidden in ((29, 0), (30, 0), (31, 1), (45, 15)):
        sub = tmp_path / f"e{count}"
        sub.mkdir()
        body = "".join(f"import thirdparty{i:02d}\n" for i in range(count))
        data = _report(sub, build(sub, {"app.py": body}))
        md = _markdown(data)
        assert md.count("| external_unmatched |") == min(count, 30), count
        assert (f"{hidden} more not shown (see the JSON report)." in md) == (
            hidden > 0
        ), count


def test_empty_sections_are_not_rendered(tmp_path: Path) -> None:
    data = _report(tmp_path, build(tmp_path, {"a.py": "import os\n"}))
    md = _markdown(data)
    assert "### Import cycles" not in md
    assert "### Unresolved and dynamic imports" not in md
    assert "### External packages imported" not in md
    assert "## Repository structure" in md


def test_the_unresolved_section_is_named_for_what_it_lists(tmp_path: Path) -> None:
    data = _report(
        tmp_path,
        build(
            tmp_path,
            {
                "pkg/__init__.py": "",
                "a.py": (
                    "import pkg.nothing\nimport importlib\nimportlib.import_module(name)\n"
                    "import thirdparty\n"
                ),
            },
        ),
    )
    md = _markdown(data)
    section = md.split("### Unresolved and dynamic imports\n", 1)[1].split("\n### ", 1)[
        0
    ]
    assert "pkg.nothing" in section and "importlib.import_module(name)" in section
    assert "thirdparty" not in section  # an unmatched external is listed elsewhere
    assert "Imports that could not be resolved" not in md
    assert "Unresolved and dynamic imports" in _html(data)


def test_attention_rows_are_exactly_the_unresolved_and_dynamic_edges(
    tmp_path: Path,
) -> None:
    from sarand.core.report_views import structure_attention_rows

    data = _report(
        tmp_path,
        build(
            tmp_path,
            {
                "pkg/__init__.py": "",
                "pkg/inner.py": "from ... import x\n",
                "one/util.py": "",
                "two/util.py": "",
                "three/main.py": "import util\nimport importlib\nimportlib.import_module(n)\n",
                "ok.py": "import os\nimport thirdparty\nimport pkg.inner\n",
                "missing.py": "import pkg.gone\n",
            },
        ),
    )
    rows, total = structure_attention_rows(data)
    reasons = sorted(row[2] for row in rows)
    assert total == len(rows) == 4
    assert reasons == sorted(
        [
            "no parent package at this level",
            "several repository modules match",
            "the module name is computed at run time",
            "pkg is a repository package but pkg.gone was not found",
        ]
    )
    assert all(row[3].count(":") == 1 for row in rows)


def _hostile_structure() -> StructureData:
    nasty = "import x  | `tick` <script>alert('x')</script> & \"q\""
    edge = replace(
        _edge("m", "t"),
        target_class="dynamic",
        confidence="unknown",
        target="",
        requested="",
        evidence=nasty,
        note="why | <b>",
        location=SourceLocation("a|b<c>.py", 3, 0, 3, 9),
    )
    return StructureData(
        1,
        "python",
        {"interpreter": "3.x <i>"},
        (FileEntity("a|b<c>.py", "python", 1, "", "m", Provenance("python-ast", "3", "", "full")),),
        (ModuleEntity("m", "a|b<c>.py", False, False, ""),),
        (ExternalRef("we|ird`<name>", "external_unmatched"),),
        (edge, replace(_edge("m", "we|ird`<name>"), target_class="external_unmatched",
                       target="we|ird`<name>", confidence="probable")),
        (),
    )  # fmt: skip


def test_markdown_tables_survive_pipes_backticks_and_markup(tmp_path: Path) -> None:
    md = _markdown(_report(tmp_path, _hostile_structure()))
    section = md.split("## Repository structure\n", 1)[1].split("\n## ", 1)[0]
    table_rows = [
        line
        for line in section.splitlines()
        if line.startswith("| ") and "---" not in line
    ]
    for line in table_rows:
        # an unescaped pipe would add cells: header rows have 4, so must every row
        assert len(line.replace("\\|", "").split("|")) - 2 == 4, line
    assert "`tick`" not in section  # a backtick cannot break the code span
    assert "\n" not in "".join(table_rows)


def test_html_output_escapes_every_untrusted_value(tmp_path: Path) -> None:
    page = _html(_report(tmp_path, _hostile_structure()))
    section = page.split("<h2>Repository structure</h2>", 1)[1]
    assert "<script>" not in section and "<b>" not in section and "<i>" not in section
    assert "&lt;script&gt;" in section
    assert "&#x27;" in section or "&#39;" in section
    assert "&quot;" in section


def test_a_malformed_external_reference_cannot_reach_a_renderer() -> None:
    for bad in (
        lambda: ExternalRef("", "stdlib"),
        lambda: ExternalRef("x", ""),
        lambda: ExternalRef("x", "dynamic"),
    ):
        try:
            bad()
        except ModelError:
            continue
        raise AssertionError("a malformed external reference was accepted")


def test_every_renderer_reports_the_same_attention_and_cycle_totals(
    tmp_path: Path,
) -> None:
    from sarand.core.report_views import structure_attention_rows, structure_cycle_lines
    from sarand.renderers import json_renderer, text

    files = {**_cycle_files(3), "pkg/__init__.py": "", "app.py": "import pkg.gone\n"}
    data = _report(tmp_path, build(tmp_path, files))
    _rows, attention_total = structure_attention_rows(data)
    _lines, cycle_total = structure_cycle_lines(data)
    payload = json.loads(json_renderer.render(data, include_source=False))["structure"]
    assert payload["summary"]["cycles"] == cycle_total == 3
    assert (
        payload["summary"]["imports_by_class"]["internal_unresolved"]
        == attention_total
        == 1
    )
    assert "3 cycle(s)" in text.render(data, include_source=False)
