"""Symbols, relations and entry points of the repository structure (R14-A2).

Synthetic trees written into `tmp_path`, one focused group per kind of construct named
in docs/R14A_PLAN.md section 11. Every confidence asserted here is a rule of
docs/STRUCTURE.md, not an observation.
"""

from __future__ import annotations

import json
from pathlib import Path

from _structure_helpers import build, write_tree
from sarand.structure import build_structure
from sarand.structure import facts as facts_module
from sarand.structure.model import Relation, StructureData, Symbol
from sarand.structure.serialize import structure_payload, summary


def sym(data: StructureData, qualname: str, module: str | None = None) -> Symbol:
    found = [
        s
        for s in data.symbols
        if s.qualname == qualname and (module is None or s.module == module)
    ]
    assert len(found) == 1, (qualname, [(s.module, s.qualname) for s in data.symbols])
    return found[0]


def relations(
    data: StructureData,
    source: str | None = None,
    target: str | None = None,
    kind: str | None = None,
) -> list[Relation]:
    """Relations by the qualified names of their ends (`module:qualname`)."""
    out = []
    for r in data.relations:
        if kind is not None and r.kind != kind:
            continue
        if source is not None:
            by_id = {s.id: f"{s.module}:{s.qualname}" for s in data.symbols}
            label = by_id.get(r.source, r.source)
            if label != source:
                continue
        if target is not None and r.target_name != target:
            continue
        out.append(r)
    return out


def one(data: StructureData, source: str, target: str, kind: str = "calls") -> Relation:
    found = relations(data, source, target, kind)
    assert len(found) == 1, (source, target, [(r.kind, r.target_name) for r in found])
    return found[0]


# --- symbols -------------------------------------------------------------------------


def test_definitions_get_kinds_qualified_names_and_parents(tmp_path: Path) -> None:
    data = build(
        tmp_path,
        {
            "m.py": (
                "LIMIT = 3\n"
                "name = 'x'\n"
                "def f():\n"
                "    def inner():\n"
                "        pass\n"
                "class C:\n"
                "    attr = 1\n"
                "    def m(self):\n"
                "        pass\n"
                "    @property\n"
                "    def p(self):\n"
                "        return 1\n"
            )
        },
    )
    kinds = {s.qualname: s.kind for s in data.symbols}
    assert kinds == {
        "LIMIT": "constant",
        "name": "variable",
        "f": "function",
        "f.<locals>.inner": "function",
        "C": "class",
        "C.attr": "variable",
        "C.m": "method",
        "C.p": "property",
    }
    assert "nested" in sym(data, "f.<locals>.inner").flags
    assert sym(data, "C.m").parent == sym(data, "C").id
    assert sym(data, "f").parent == ""
    assert all(s.id.startswith("sym:") and len(s.id) == 16 for s in data.symbols)


def test_ids_survive_formatting_and_line_shifts(tmp_path: Path) -> None:
    first = build(tmp_path / "a", {"m.py": "def f():\n    pass\nclass C:\n    pass\n"})
    second = build(
        tmp_path / "b",
        {
            "m.py": "# header\n\n\n\ndef f( ):\n\n    pass  # c\n\n\nclass C :\n    pass\n"
        },
    )
    assert {s.qualname: s.id for s in first.symbols} == {
        s.qualname: s.id for s in second.symbols
    }
    assert sym(first, "f").location.line != sym(second, "f").location.line


def test_a_redefinition_gets_its_own_id_and_the_name_becomes_ambiguous(
    tmp_path: Path,
) -> None:
    data = build(
        tmp_path,
        {
            "m.py": (
                "if True:\n"
                "    def f(): pass\n"
                "else:\n"
                "    def f(): pass\n"
                "def g():\n"
                "    return f()\n"
            )
        },
    )
    ids = [s.id for s in data.symbols if s.qualname == "f"]
    assert len(ids) == 2 and len(set(ids)) == 2
    assert all("conditional" in s.flags for s in data.symbols if s.qualname == "f")
    rel = relations(data, "m:g", kind="calls")
    assert [(r.target_kind, r.confidence, r.resolution_method) for r in rel] == [
        ("unresolved", "unknown", "ambiguous-binding")
    ]


def test_property_setter_is_one_binding_and_overloads_are_skipped(
    tmp_path: Path,
) -> None:
    data = build(
        tmp_path,
        {
            "m.py": (
                "from typing import overload\n"
                "class C:\n"
                "    @property\n"
                "    def p(self): return 1\n"
                "    @p.setter\n"
                "    def p(self, v): pass\n"
                "    def use(self):\n"
                "        return self.p\n"
                "@overload\n"
                "def f(x: int) -> int: ...\n"
                "@overload\n"
                "def f(x: str) -> str: ...\n"
                "def f(x): return x\n"
                "def g(): return f(1)\n"
            )
        },
    )
    use = one(data, "m:C.use", "m:C.p", "references")
    assert use.confidence == "probable" and use.resolution_method == "self-member"
    assert one(data, "m:g", "m:f").confidence == "definite"


def test_extensions_record_async_generator_and_star_args(tmp_path: Path) -> None:
    data = build(
        tmp_path,
        {
            "m.py": (
                "async def a(*args, **kw): pass\n"
                "def g():\n"
                "    yield 1\n"
                "class M(type): pass\n"
                "class C(metaclass=M): pass\n"
            )
        },
    )
    assert dict(sym(data, "a").extensions)["is_async"] is True
    assert dict(sym(data, "a").extensions)["has_star_args"] is True
    assert dict(sym(data, "g").extensions)["is_generator"] is True
    assert dict(sym(data, "C").extensions)["has_metaclass"] is True
    assert "dynamic" in sym(data, "C").flags
    file = next(f for f in data.files if f.path == "m.py")
    assert "dynamic_construct_seen" in file.provenance.limitations


# --- imports and cross-module relations ----------------------------------------------


def test_from_import_and_module_attribute_resolve_definitely(tmp_path: Path) -> None:
    data = build(
        tmp_path,
        {
            "lib.py": "def f(): pass\nCONST = 1\n",
            "a.py": "from lib import f\ndef go(): return f()\n",
            "b.py": "import lib\ndef go(): return lib.f(), lib.CONST\n",
            "c.py": "import lib as L\ndef go(): return L.f()\n",
        },
    )
    assert one(data, "a:go", "lib:f").confidence == "definite"
    assert one(data, "b:go", "lib:f").confidence == "definite"
    assert one(data, "c:go", "lib:f").confidence == "definite"
    ref = one(data, "b:go", "lib:CONST", "references")
    assert ref.confidence == "definite" and "lazy" in ref.flags


def test_relative_imports_and_reexports_through_a_package(tmp_path: Path) -> None:
    data = build(
        tmp_path,
        {
            "pkg/__init__.py": "from .core import helper\n",
            "pkg/core.py": "def helper(): pass\n",
            "pkg/user.py": "from . import helper\ndef go(): return helper()\n",
            "app.py": "from pkg import helper\ndef run(): return helper()\n",
        },
    )
    assert one(data, "pkg.user:go", "pkg.core:helper").confidence == "definite"
    assert one(data, "app:run", "pkg.core:helper").confidence == "definite"


def test_a_submodule_is_a_module_not_a_symbol(tmp_path: Path) -> None:
    data = build(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/sub.py": "def f(): pass\n",
            "a.py": "from pkg import sub\ndef go(): return sub.f()\n",
        },
    )
    assert one(data, "a:go", "pkg.sub:f").confidence == "definite"


def test_a_name_both_defined_and_a_submodule_is_probable(tmp_path: Path) -> None:
    data = build(
        tmp_path,
        {
            "pkg/__init__.py": "def sub(): pass\n",
            "pkg/sub.py": "x = 1\n",
            "a.py": "from pkg import sub\ndef go(): return sub()\n",
        },
    )
    assert one(data, "a:go", "pkg:sub").confidence == "probable"


def test_star_import_with_static_all_is_probable_without_it_unknown(
    tmp_path: Path,
) -> None:
    data = build(
        tmp_path,
        {
            "with_all.py": "__all__ = ['f']\ndef f(): pass\ndef h(): pass\n",
            "no_all.py": "def g(): pass\n",
            "a.py": "from with_all import *\ndef go(): return f()\n",
            "b.py": "from no_all import *\ndef go(): return g()\n",
        },
    )
    probable = one(data, "a:go", "with_all:f")
    assert probable.confidence == "probable"
    assert probable.resolution_method == "star-import-all"
    unknown = relations(data, "b:go", kind="calls")
    assert [(r.target_kind, r.confidence, r.resolution_method) for r in unknown] == [
        ("unresolved", "unknown", "star-import-without-static-all")
    ]


def test_a_missing_member_and_a_module_getattr_are_unknown(tmp_path: Path) -> None:
    data = build(
        tmp_path,
        {
            "lib.py": "def f(): pass\n",
            "dyn.py": "def __getattr__(name): return 1\n",
            "a.py": (
                "import lib, dyn\ndef go():\n    lib.nope()\n    dyn.anything()\n"
            ),
        },
    )
    methods = sorted(r.resolution_method for r in relations(data, "a:go", kind="calls"))
    assert methods == ["member-missing", "module-getattr"]
    assert all(r.confidence == "unknown" for r in relations(data, "a:go"))


# --- scopes ----------------------------------------------------------------------------


def test_a_parameter_shadows_a_module_function(tmp_path: Path) -> None:
    data = build(
        tmp_path,
        {"m.py": "def f(): pass\ndef g(f):\n    return f()\n"},
    )
    assert relations(data, "m:g", kind="calls") == []
    assert data.sites["untracked_by_reason"]["local_binding"] == 1


def test_a_class_body_is_not_visible_from_its_methods(tmp_path: Path) -> None:
    data = build(
        tmp_path,
        {
            "m.py": (
                "def helper(): pass\n"
                "class C:\n"
                "    def helper(self): pass\n"
                "    def m(self):\n"
                "        return helper()\n"
            )
        },
    )
    assert one(data, "m:C.m", "m:helper").confidence == "definite"


def test_global_rebinding_makes_a_module_name_ambiguous(tmp_path: Path) -> None:
    data = build(
        tmp_path,
        {
            "m.py": (
                "def f(): pass\n"
                "def swap():\n"
                "    global f\n"
                "    f = lambda: 1\n"
                "def go(): return f()\n"
            )
        },
    )
    rel = relations(data, "m:go", kind="calls")
    assert [(r.resolution_method, r.confidence) for r in rel] == [
        ("ambiguous-binding", "unknown")
    ]


def test_context_flags_lazy_conditional_type_only_annotation(tmp_path: Path) -> None:
    data = build(
        tmp_path,
        {
            "lib.py": "class T: pass\ndef f(): pass\n",
            "m.py": (
                "from typing import TYPE_CHECKING\n"
                "from lib import f, T\n"
                "if TYPE_CHECKING:\n"
                "    from lib import T as U\n"
                "    x: T = f()\n"
                "def go(a: T) -> None:\n"
                "    if a:\n"
                "        f()\n"
            ),
        },
    )
    flags = {(r.kind, r.original_type): r.flags for r in relations(data, "m:go")}
    assert flags[("references", "name")] == ("annotation",)
    calls = [
        r for r in data.relations if r.kind == "calls" and r.target_name == "lib:f"
    ]
    by_flags = sorted(r.flags for r in calls)
    assert by_flags == [("conditional", "lazy"), ("conditional", "type_only")]


# --- classes ---------------------------------------------------------------------------


def test_inheritance_is_definite_and_external_bases_are_counted(
    tmp_path: Path,
) -> None:
    data = build(
        tmp_path,
        {
            "base.py": "class Base: pass\n",
            "m.py": (
                "from base import Base\n"
                "import yaml\n"
                "class A(Base): pass\n"
                "class B(yaml.YAMLObject, Base): pass\n"
                "class E(Exception): pass\n"
            ),
        },
    )
    assert one(data, "m:A", "base:Base", "inherits").confidence == "definite"
    assert one(data, "m:B", "base:Base", "inherits").confidence == "definite"
    names = {u.name: u for u in data.external_use}
    assert names["yaml.YAMLObject"].inherits == 1
    assert data.sites["builtin"] == 1


def test_self_calls_are_probable_inherited_members_too(tmp_path: Path) -> None:
    data = build(
        tmp_path,
        {
            "m.py": (
                "class Base:\n"
                "    def step(self): pass\n"
                "    @classmethod\n"
                "    def make(cls): return cls()\n"
                "class Child(Base):\n"
                "    def run(self):\n"
                "        self.step()\n"
                "        Base.step(self)\n"
                "        Child.make()\n"
                "        super().step()\n"
            )
        },
    )
    step = relations(data, "m:Child.run", "m:Base.step")
    by_method = sorted((r.resolution_method, r.confidence) for r in step)
    assert by_method == [
        ("definition", "definite"),
        ("inherited-member", "probable"),
        ("super-call", "probable"),
    ]
    assert one(data, "m:Child.run", "m:Base.make").confidence == "probable"
    ctor = one(data, "m:Base.make", "m:Base")
    assert ctor.resolution_method == "cls-constructor" and ctor.confidence == "probable"


def test_a_class_with_getattr_or_unresolved_base_is_unknown_for_missing_members(
    tmp_path: Path,
) -> None:
    data = build(
        tmp_path,
        {
            "m.py": (
                "def make(): pass\n"
                "class Hook:\n"
                "    def __getattr__(self, n): return 1\n"
                "    def run(self): return self.missing()\n"
                "class Odd(make()):\n"
                "    def run(self): return self.other()\n"
                "class Plain:\n"
                "    def run(self): return self.other()\n"
            )
        },
    )
    assert [r.resolution_method for r in relations(data, "m:Hook.run")] == [
        "getattr-hook"
    ]
    assert [r.resolution_method for r in relations(data, "m:Odd.run")] == [
        "unresolved-base"
    ]
    assert relations(data, "m:Plain.run") == []
    assert data.sites["untracked_by_reason"]["instance_attribute"] == 1


# --- decorators, patches, dynamic -------------------------------------------------------


def test_transparent_decorators_keep_definite_others_make_it_probable(
    tmp_path: Path,
) -> None:
    data = build(
        tmp_path,
        {
            "m.py": (
                "import functools\n"
                "from functools import lru_cache\n"
                "def wrap(f): return f\n"
                "@lru_cache(maxsize=None)\n"
                "def a(): pass\n"
                "@functools.wraps(a)\n"
                "def b(): pass\n"
                "@wrap\n"
                "def c(): pass\n"
                "def go():\n"
                "    a(); b(); c()\n"
            )
        },
    )
    assert one(data, "m:go", "m:a").confidence == "definite"
    assert one(data, "m:go", "m:b").confidence == "definite"
    c = one(data, "m:go", "m:c")
    assert (c.confidence, c.resolution_method) == ("probable", "decorated")
    deco = one(data, "m:c", "m:wrap", "references")
    assert deco.original_type == "decorator" and deco.confidence == "definite"


def test_an_assigned_module_attribute_makes_resolution_probable(tmp_path: Path) -> None:
    data = build(
        tmp_path,
        {
            "lib.py": "def f(): pass\ndef g(): pass\ndef h(): pass\n",
            "patch.py": (
                "import lib\n"
                "def other(): pass\n"
                "lib.f = other\n"
                "setattr(lib, 'g', other)\n"
            ),
            "use.py": "import lib\ndef go():\n    lib.f(); lib.g(); lib.h()\n",
        },
    )
    assert one(data, "use:go", "lib:f").resolution_method == "patched"
    assert one(data, "use:go", "lib:g").resolution_method == "patched"
    assert one(data, "use:go", "lib:h").confidence == "definite"


def test_getattr_with_a_computed_name_is_stored_as_dynamic_unknown(
    tmp_path: Path,
) -> None:
    data = build(
        tmp_path,
        {
            "m.py": (
                "def go(o, n):\n"
                "    getattr(o, n)\n"
                "    getattr(o, 'fixed')\n"
                "    setattr(o, n, 1)\n"
            )
        },
    )
    dynamic = relations(data, "m:go", kind="calls")
    assert [(r.target_kind, r.target_name, r.confidence) for r in dynamic] == [
        ("dynamic", "getattr", "unknown"),
        ("dynamic", "setattr", "unknown"),
    ]
    assert data.sites["untracked_by_reason"]["attribute_by_constant_name"] == 1
    assert "dynamic_construct_seen" in data.files[0].provenance.limitations


def test_a_shadowed_getattr_is_not_the_builtin(tmp_path: Path) -> None:
    data = build(
        tmp_path,
        {"m.py": "def getattr(a, b): pass\ndef go(o, n):\n    getattr(o, n)\n"},
    )
    assert [r.target_kind for r in relations(data, "m:go")] == ["symbol"]


# --- what is stored and what is counted --------------------------------------------------


def test_every_site_is_stored_or_counted(tmp_path: Path) -> None:
    data = build(
        tmp_path,
        {
            "lib.py": "def f(): pass\n",
            "m.py": (
                "import os, requests\n"
                "import lib\n"
                "def go(x, y):\n"
                "    lib.f()\n"
                "    os.getcwd()\n"
                "    requests.get('u')\n"
                "    len(x)\n"
                "    x.method()\n"
                "    y().z()\n"
                "    lib.nope()\n"
            ),
        },
    )
    s = dict(data.sites)
    untracked = dict(s["untracked_by_reason"])
    accounted = (
        s["internal"]
        + s["external_stdlib"]
        + s["external_declared"]
        + s["external_unmatched"]
        + s["builtin"]
        + s["unresolved"]
        + s["dynamic"]
        + s["untracked"]
    )
    assert accounted == s["total"]
    assert sum(untracked.values()) == s["untracked"]
    assert s["external_stdlib"] == 1 and s["external_unmatched"] == 1
    assert s["builtin"] == 1 and s["unresolved"] == 1 and s["internal"] == 1
    assert untracked["local_binding"] == 2  # x.method() and y()
    assert untracked["expression_without_a_name"] == 1  # (y()).z()


def test_equal_relations_are_merged_with_a_count_and_the_first_location(
    tmp_path: Path,
) -> None:
    data = build(
        tmp_path,
        {"m.py": "def f(): pass\ndef go():\n    f()\n    f()\n    f()\n"},
    )
    rel = one(data, "m:go", "m:f")
    assert rel.count == 3 and rel.location.line == 3


def test_a_file_that_does_not_parse_has_no_symbols_and_is_kept(tmp_path: Path) -> None:
    data = build(tmp_path, {"bad.py": "def f(:\n", "ok.py": "def f(): pass\n"})
    bad = next(f for f in data.files if f.path == "bad.py")
    assert bad.provenance.completeness == "failed"
    assert [s.path for s in data.symbols] == ["ok.py"]


def test_the_node_cap_makes_the_symbol_pass_partial(tmp_path: Path) -> None:
    saved = facts_module.MAX_NODES_PER_FILE
    facts_module.MAX_NODES_PER_FILE = 5
    try:
        data = build(tmp_path, {"m.py": "def f():\n" + "    f()\n" * 50})
    finally:
        facts_module.MAX_NODES_PER_FILE = saved
    prov = data.files[0].provenance
    assert prov.completeness == "partial" and "node_cap" in prov.limitations


# --- entry points ------------------------------------------------------------------------


def test_main_blocks_and_main_files_are_definite_entry_points(tmp_path: Path) -> None:
    data = build(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/__main__.py": "def main(): pass\nif __name__ == '__main__':\n    main()\n",
            "tool.py": "if '__main__' == __name__:\n    pass\n",
            "no.py": "if __name__ == 'x':\n    pass\ndef f():\n    if __name__ == '__main__':\n        pass\n",
        },
    )
    found = sorted((e.type, e.target) for e in data.entry_points)
    assert found == [
        ("main_block", "pkg.__main__"),
        ("main_block", "tool"),
        ("package_main", "pkg.__main__"),
    ]
    assert all(e.confidence == "definite" for e in data.entry_points)


def test_manifest_entry_points_resolve_or_stay_unknown_with_a_note(
    tmp_path: Path,
) -> None:
    manifest = (
        "[project]\nname='x'\n"
        "[project.scripts]\ngood='pkg.cli:main'\nmissing='pkg.cli:nope'\n"
        "outside='other.mod:go'\nmod='pkg.cli'\n"
        "[project.entry-points.'x.plugins']\nfoo='pkg.cli:Plugin.run'\n"
        "[tool.pytest.ini_options]\ntestpaths=['tests','absent']\n"
    )
    data = build(
        tmp_path,
        {
            "pyproject.toml": manifest,
            "pkg/__init__.py": "",
            "pkg/cli.py": "def main(): pass\nclass Plugin:\n    def run(self): pass\n",
            "tests/test_a.py": "",
        },
    )
    by_name = {e.name: e for e in data.entry_points if e.type != "main_block"}
    assert by_name["good"].confidence == "definite"
    assert by_name["good"].resolved == sym(data, "main", "pkg.cli").id
    assert by_name["mod"].resolved == "pkg.cli"
    assert by_name["x.plugins:foo"].resolved == sym(data, "Plugin.run").id
    for name in ("missing", "outside"):
        assert by_name[name].confidence == "unknown" and by_name[name].note
        assert by_name[name].resolved == ""
    assert by_name["tests"].confidence == "definite"
    assert by_name["absent"].confidence == "unknown"
    assert by_name["good"].location.path == "pyproject.toml"


def test_framework_objects_are_probable_and_need_the_declaration(
    tmp_path: Path,
) -> None:
    files = {
        "pyproject.toml": "[project]\nname='x'\ndependencies=['click', 'typer']\n",
        "cli.py": (
            "import click, typer, argparse\n"
            "@click.command()\n"
            "def main(): pass\n"
            "app = typer.Typer()\n"
            "parser = argparse.ArgumentParser()\n"
        ),
    }
    data = build(tmp_path / "declared", files)
    apps = {e.name: e for e in data.entry_points if e.type == "framework_app"}
    assert sorted(apps) == ["app", "main", "parser"]
    assert all(e.confidence == "probable" for e in apps.values())
    files["pyproject.toml"] = "[project]\nname='x'\n"
    undeclared = build(tmp_path / "undeclared", files)
    assert [e.name for e in undeclared.entry_points if e.type == "framework_app"] == [
        "parser"
    ]


# --- determinism and the payload ---------------------------------------------------------


def _tree() -> dict[str, str]:
    return {
        "pyproject.toml": "[project]\nname='x'\n[project.scripts]\nx='pkg.a:go'\n",
        "pkg/__init__.py": "from .a import go\n",
        "pkg/a.py": "from . import b\nclass A(b.B):\n    def go(self): return self.x()\ndef go(): return b.h()\n",
        "pkg/b.py": "class B:\n    def x(self): pass\ndef h(): pass\nif __name__ == '__main__':\n    h()\n",
    }


def test_output_is_byte_identical_whatever_the_file_order(tmp_path: Path) -> None:
    paths = write_tree(tmp_path, _tree())
    from _structure_helpers import STDLIB

    outputs = []
    for ordering in (
        paths,
        list(reversed(paths)),
        sorted(paths, key=str)[::2] + sorted(paths, key=str)[1::2],
    ):
        data = build_structure(tmp_path, ordering, stdlib=STDLIB)
        outputs.append(json.dumps(structure_payload(data)))
    assert len(set(outputs)) == 1
    again = build_structure(tmp_path, paths, stdlib=STDLIB)
    assert json.dumps(structure_payload(again)) == outputs[0]


def test_summary_and_payload_agree_and_are_plain_json(tmp_path: Path) -> None:
    data = build(tmp_path, _tree())
    info = summary(data)
    payload = structure_payload(data)
    assert json.loads(json.dumps(payload)) == payload
    assert (
        info["symbols"]
        == len(payload["symbols"])
        == sum(info["symbols_by_kind"].values())
    )
    assert info["relations"] == len(payload["relations"])
    assert sum(info["relations_by_confidence"].values()) == info["relations"]
    assert sum(info["relations_by_kind"].values()) == info["relations"]
    assert info["entry_points"] == len(payload["entry_points"])
    assert payload["schema"] == 2
    ids = [s["id"] for s in payload["symbols"]]
    assert len(ids) == len(set(ids))
    known = set(ids)
    for r in payload["relations"]:
        assert r["target_kind"] != "symbol" or r["target"] in known


def test_the_payload_holds_no_source_text_beyond_bounded_evidence(
    tmp_path: Path,
) -> None:
    secret = "AKIAIOSFODNN7EXAMPLE"
    data = build(tmp_path, {"m.py": f"KEY = '{secret}'\ndef f(): pass\n"})
    assert secret not in json.dumps(structure_payload(data))
