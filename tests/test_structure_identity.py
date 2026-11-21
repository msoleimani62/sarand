"""Stable identity, fingerprints and match classes (R14-A3, docs/R14A_PLAN.md section 8).

The fixtures change a tree in one harmless or real way and check what survives:
line shifts, reformatting, comments, docstrings (harmless), a changed body, a moved
file, a renamed symbol, a duplicated name (real).
"""

from __future__ import annotations

import ast
import json
import random
from pathlib import Path

from _structure_helpers import build
from sarand.structure.fingerprint import (
    FINGERPRINT_PATTERN,
    fingerprint,
    fingerprint_basis,
)
from sarand.structure.identity import (
    MATCH_AMBIGUOUS,
    MATCH_CLASSES,
    MATCH_EXACT,
    MATCH_PROBABLE,
    MATCH_UNMATCHED,
    REASON_ADDED,
    REASON_DUPLICATE_NAME,
    REASON_LANGUAGE,
    REASON_MOVED,
    REASON_REMOVED,
    REASON_SAME_ID,
    REASON_SEVERAL_CANDIDATES,
    MatchResult,
    SymbolRecord,
    match_symbols,
    records_from_payload,
    records_from_symbols,
)
from sarand.structure.model import ModelError, SourceLocation, StructureData, Symbol
from sarand.structure.serialize import structure_payload

BASIS = "fp1/python-3.12"


def fp_of(source: str) -> str:
    return fingerprint([ast.parse(source).body[0]])


def symbol(data: StructureData, qualname: str, path: str | None = None) -> Symbol:
    found = [
        s
        for s in data.symbols
        if s.qualname == qualname and (path is None or s.path == path)
    ]
    assert len(found) == 1, (qualname, [(s.path, s.qualname) for s in data.symbols])
    return found[0]


def match(old: StructureData, new: StructureData) -> MatchResult:
    return match_symbols(
        records_from_symbols(old.symbols),
        records_from_symbols(new.symbols),
        old_basis=str(old.meta["fingerprint_basis"]),
        new_basis=str(new.meta["fingerprint_basis"]),
    )


def rec(
    ident: str,
    qualname: str,
    path: str,
    fp: str = "fp1:000000000001",
    kind: str = "function",
) -> SymbolRecord:
    return SymbolRecord(ident, kind, path, qualname, fp)


# --- the fingerprint ---------------------------------------------------------------


def test_fingerprint_has_the_versioned_shape() -> None:
    value = fp_of("def f(x):\n    return x\n")
    assert FINGERPRINT_PATTERN.match(value)
    assert value.startswith("fp1:") and len(value) == 16


def test_fingerprint_ignores_formatting_comments_and_docstrings() -> None:
    plain = fp_of("def f(x):\n    return x + 1\n")
    spaced = fp_of("def f( x ):\n\n\n    # a comment\n    return (x   +   1)\n")
    documented = fp_of('def f(x):\n    """Does a thing."""\n    return x + 1\n')
    other_quotes = fp_of("def f(x):\n    '''Other.'''\n    return x+1\n")
    assert plain == spaced == documented == other_quotes


def test_fingerprint_ignores_quote_style_and_trailing_commas() -> None:
    assert fp_of("X = ['a', 'b',]\n") == fp_of('X = ["a", "b"]\n')


def test_fingerprint_changes_with_the_content() -> None:
    base = fp_of("def f(x):\n    return x + 1\n")
    assert fp_of("def f(x):\n    return x + 2\n") != base
    assert fp_of("def f(x, y):\n    return x + 1\n") != base
    assert fp_of("def f(x):\n    return x - 1\n") != base
    assert fp_of("@cache\ndef f(x):\n    return x + 1\n") != base
    assert fp_of("async def f(x):\n    return x + 1\n") != base
    assert fp_of("def f(x=1):\n    return x + 1\n") != base


def test_fingerprint_of_a_class_includes_its_methods() -> None:
    one = fp_of("class C:\n    def m(self):\n        return 1\n")
    two = fp_of("class C:\n    def m(self):\n        return 2\n")
    assert one != two


def test_fingerprint_of_a_non_docstring_string_statement_counts() -> None:
    # Only the FIRST statement of a def/class body is a docstring.
    with_second = fp_of('def f():\n    x = 1\n    "not a docstring"\n')
    without = fp_of("def f():\n    x = 1\n")
    assert with_second != without


def test_a_string_literal_cannot_forge_a_delimiter() -> None:
    first = ast.parse('x = "\\x03"\n').body[0]
    second = ast.parse('x = "\\x05"\n').body[0]
    assert fingerprint([first]) != fingerprint([second])


def test_fingerprint_survives_deep_nesting_without_recursion_error() -> None:
    # ast.parse may refuse such input on some interpreters: build the tree directly.
    node: ast.expr = ast.Constant(1)
    for _ in range(4000):
        node = ast.UnaryOp(ast.USub(), node)
    assert FINGERPRINT_PATTERN.match(fingerprint([node]))


def test_fingerprint_basis_names_the_interpreter_minor_version() -> None:
    assert fingerprint_basis("3.12.3") == "fp1/python-3.12"
    assert fingerprint_basis("3.14.0rc1") == "fp1/python-3.14"
    assert fingerprint_basis("3.12.3") != fingerprint_basis("3.13.0")


def test_a_symbol_rejects_a_malformed_fingerprint() -> None:
    try:
        Symbol(
            id="sym:000000000001",
            kind="function",
            name="f",
            qualname="f",
            module="m",
            path="m.py",
            parent="",
            location=SourceLocation("m.py", 1, 0, 1, 1),
            fingerprint="fp2:nothex",
        )
    except ModelError:
        return
    raise AssertionError("a malformed fingerprint must be rejected")


# --- fingerprints inside a built structure ----------------------------------------


def test_every_built_symbol_carries_a_fingerprint_and_the_meta_a_basis(
    tmp_path: Path,
) -> None:
    data = build(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/a.py": "LIMIT = 10\nclass C:\n    def m(self):\n        return 1\n"
            "def f():\n    pass\n",
        },
    )
    assert data.symbols
    assert all(FINGERPRINT_PATTERN.match(s.fingerprint) for s in data.symbols)
    assert str(data.meta["fingerprint_basis"]).startswith("fp1/python-")
    payload = structure_payload(data)
    assert payload["schema"] == 4
    assert all("fingerprint" in s for s in payload["symbols"])


def test_a_variable_fingerprint_follows_its_value_not_its_neighbours(
    tmp_path: Path,
) -> None:
    first = build(tmp_path, {"m.py": "A = B = 1\n"})
    a_old = symbol(first, "A").fingerprint
    second_dir = tmp_path / "second"
    second_dir.mkdir()
    second = build(second_dir, {"m.py": "A = C = 1\n"})
    assert symbol(second, "A").fingerprint == a_old
    third_dir = tmp_path / "third"
    third_dir.mkdir()
    third = build(third_dir, {"m.py": "A = B = 2\n"})
    assert symbol(third, "A").fingerprint != a_old


def test_a_value_annotation_changes_a_variable_fingerprint(tmp_path: Path) -> None:
    plain = build(tmp_path, {"m.py": "A = 1\n"})
    other = tmp_path / "o"
    other.mkdir()
    annotated = build(other, {"m.py": "A: int = 1\n"})
    assert symbol(plain, "A").fingerprint != symbol(annotated, "A").fingerprint


# --- identity under harmless changes ----------------------------------------------

BASE = {
    "pkg/__init__.py": "",
    "pkg/core.py": (
        "import os\n\n\nclass Engine:\n    def run(self, n):\n        return n * 2\n\n"
        "    def stop(self):\n        return os.getcwd()\n\n\n"
        "def helper(x):\n    return x + 1\n\n\nLIMIT = 10\n"
    ),
}


def _tree(tmp_path: Path, name: str, files: dict[str, str]) -> StructureData:
    root = tmp_path / name
    root.mkdir()
    return build(root, files)


def test_ids_and_fingerprints_survive_line_shifts_and_reformatting(
    tmp_path: Path,
) -> None:
    old = _tree(tmp_path, "old", BASE)
    shifted = {
        **BASE,
        "pkg/core.py": (
            '"""A new module docstring."""\n# header comment\n\n\n\n'
            "import os\n\n\nclass Engine:\n"
            '    """Now documented."""\n\n'
            "    def run( self,n ):\n        return (n*2)\n\n\n"
            "    def stop(self):\n        # a comment\n        return os.getcwd()\n\n\n\n"
            "def helper( x ):\n    return x+1\n\n\nLIMIT=10\n"
        ),
    }
    new = _tree(tmp_path, "new", shifted)
    assert {s.id for s in old.symbols} == {s.id for s in new.symbols}
    by_old = {s.id: s.fingerprint for s in old.symbols}
    assert by_old == {s.id: s.fingerprint for s in new.symbols}
    result = match(old, new)
    assert result.comparable
    assert result.counts() == {
        MATCH_EXACT: len(old.symbols),
        MATCH_PROBABLE: 0,
        MATCH_AMBIGUOUS: 0,
        MATCH_UNMATCHED: 0,
    }
    assert all(row.content_changed is False for row in result.of(MATCH_EXACT))


def test_ids_survive_an_unrelated_file_being_added(tmp_path: Path) -> None:
    old = _tree(tmp_path, "old", BASE)
    new = _tree(tmp_path, "new", {**BASE, "pkg/other.py": "def other():\n    pass\n"})
    result = match(old, new)
    assert result.counts()[MATCH_EXACT] == len(old.symbols)
    assert result.counts()[MATCH_UNMATCHED] == 1
    only = result.of(MATCH_UNMATCHED)[0]
    assert only.reason == REASON_ADDED and not only.old and len(only.new) == 1


def test_a_changed_body_is_exact_with_content_changed(tmp_path: Path) -> None:
    old = _tree(tmp_path, "old", BASE)
    changed = BASE["pkg/core.py"].replace("return x + 1", "return x + 100")
    new = _tree(tmp_path, "new", {**BASE, "pkg/core.py": changed})
    result = match(old, new)
    rows = {row.old[0]: row for row in result.of(MATCH_EXACT)}
    helper = rows[symbol(old, "helper").id]
    engine = rows[symbol(old, "Engine").id]
    assert helper.content_changed is True
    assert engine.content_changed is False
    assert result.counts()[MATCH_EXACT] == len(old.symbols)


def test_a_moved_file_is_probable_never_exact(tmp_path: Path) -> None:
    old = _tree(tmp_path, "old", BASE)
    moved = {
        "pkg/__init__.py": "",
        "pkg/engine/core.py": BASE["pkg/core.py"],
        "pkg/engine/__init__.py": "",
    }
    new = _tree(tmp_path, "new", moved)
    result = match(old, new)
    counts = result.counts()
    assert counts[MATCH_EXACT] == 0
    assert counts[MATCH_PROBABLE] == len(old.symbols)
    assert counts[MATCH_UNMATCHED] == 0
    assert all(row.reason == REASON_MOVED for row in result.of(MATCH_PROBABLE))
    assert all(row.content_changed is False for row in result.of(MATCH_PROBABLE))


def test_a_move_with_a_changed_body_is_not_matched(tmp_path: Path) -> None:
    old = _tree(tmp_path, "old", BASE)
    edited = BASE["pkg/core.py"].replace("return x + 1", "return x + 9")
    new = _tree(tmp_path, "new", {"pkg/__init__.py": "", "pkg/moved.py": edited})
    result = match(old, new)
    helper_old = symbol(old, "helper").id
    rows = [r for r in result.rows if helper_old in r.old]
    assert len(rows) == 1
    assert rows[0].match == MATCH_UNMATCHED and rows[0].reason == REASON_REMOVED


def test_a_renamed_symbol_is_an_unmatched_pair_not_a_guess(tmp_path: Path) -> None:
    old = _tree(tmp_path, "old", BASE)
    renamed = BASE["pkg/core.py"].replace("helper", "assist")
    new = _tree(tmp_path, "new", {**BASE, "pkg/core.py": renamed})
    result = match(old, new)
    old_id = symbol(old, "helper").id
    new_id = symbol(new, "assist").id
    removed = [r for r in result.of(MATCH_UNMATCHED) if r.old == (old_id,)]
    added = [r for r in result.of(MATCH_UNMATCHED) if r.new == (new_id,)]
    assert len(removed) == 1 and removed[0].reason == REASON_REMOVED
    assert len(added) == 1 and added[0].reason == REASON_ADDED


def test_same_path_with_a_different_id_is_not_a_move() -> None:
    old = [rec("sym:aaaaaaaaaaaa", "helper", "same.py")]
    new = [rec("sym:bbbbbbbbbbbb", "helper", "same.py")]

    result = match_symbols(old, new, old_basis=BASIS, new_basis=BASIS)

    assert not result.of(MATCH_PROBABLE)
    assert not result.of(MATCH_AMBIGUOUS)
    unmatched = result.of(MATCH_UNMATCHED)
    assert len(unmatched) == 2
    assert {row.reason for row in unmatched} == {REASON_REMOVED, REASON_ADDED}


def test_same_path_candidate_prevents_a_probable_move() -> None:
    old = [rec("sym:aaaaaaaaaaaa", "helper", "a.py")]
    new = [
        rec("sym:bbbbbbbbbbbb", "helper", "a.py"),
        rec("sym:cccccccccccc", "helper", "b.py"),
    ]

    result = match_symbols(old, new, old_basis=BASIS, new_basis=BASIS)

    rows = result.of(MATCH_AMBIGUOUS)
    assert len(rows) == 1
    assert rows[0].reason == REASON_SEVERAL_CANDIDATES
    assert rows[0].old == ("sym:aaaaaaaaaaaa",)
    assert set(rows[0].new) == {"sym:bbbbbbbbbbbb", "sym:cccccccccccc"}
    assert not result.of(MATCH_PROBABLE)


def test_same_path_old_candidate_prevents_a_probable_move() -> None:
    old = [
        rec("sym:aaaaaaaaaaaa", "helper", "a.py"),
        rec("sym:bbbbbbbbbbbb", "helper", "b.py"),
    ]
    new = [rec("sym:cccccccccccc", "helper", "a.py")]

    result = match_symbols(old, new, old_basis=BASIS, new_basis=BASIS)

    rows = result.of(MATCH_AMBIGUOUS)
    assert len(rows) == 1
    assert rows[0].reason == REASON_SEVERAL_CANDIDATES
    assert set(rows[0].old) == {"sym:aaaaaaaaaaaa", "sym:bbbbbbbbbbbb"}
    assert rows[0].new == ("sym:cccccccccccc",)
    assert not result.of(MATCH_PROBABLE)


def test_two_equally_good_move_candidates_are_ambiguous() -> None:
    old = [rec("sym:aaaaaaaaaaaa", "helper", "a.py")]
    new = [
        rec("sym:bbbbbbbbbbbb", "helper", "b.py"),
        rec("sym:cccccccccccc", "helper", "c.py"),
    ]
    result = match_symbols(old, new, old_basis=BASIS, new_basis=BASIS)
    rows = result.of(MATCH_AMBIGUOUS)
    assert len(rows) == 1
    assert rows[0].reason == REASON_SEVERAL_CANDIDATES
    assert rows[0].old == ("sym:aaaaaaaaaaaa",)
    assert set(rows[0].new) == {"sym:bbbbbbbbbbbb", "sym:cccccccccccc"}
    assert not result.of(MATCH_PROBABLE) and not result.of(MATCH_EXACT)


def test_one_new_symbol_with_two_old_twins_is_ambiguous_too() -> None:
    old = [
        rec("sym:aaaaaaaaaaaa", "logger", "a.py", kind="variable"),
        rec("sym:bbbbbbbbbbbb", "logger", "b.py", kind="variable"),
    ]
    new = [rec("sym:cccccccccccc", "logger", "c.py", kind="variable")]
    result = match_symbols(old, new, old_basis=BASIS, new_basis=BASIS)
    assert [r.match for r in result.rows] == [MATCH_AMBIGUOUS]


def test_a_duplicated_qualified_name_keeps_equal_content_exact_and_flags_the_rest(
    tmp_path: Path,
) -> None:
    source = "import sys\nif sys.platform == 'a':\n    def f():\n        return 1\nelse:\n    def f():\n        return 2\n"
    old = _tree(tmp_path, "old", {"m.py": source})
    new = _tree(tmp_path, "new", {"m.py": source})
    assert len({s.id for s in old.symbols if s.qualname == "f"}) == 2
    assert match(old, new).counts()[MATCH_EXACT] == len(old.symbols)

    swapped = source.replace("return 1", "return 3")
    newer = _tree(tmp_path, "newer", {"m.py": swapped})
    result = match(old, newer)
    ambiguous = result.of(MATCH_AMBIGUOUS)
    assert len(ambiguous) == 1
    assert ambiguous[0].reason == REASON_DUPLICATE_NAME
    assert len(ambiguous[0].old) == 1 and len(ambiguous[0].new) == 1
    # The unchanged `f` is still paired exactly; only the changed one is in doubt:
    # it may have kept its place, or the two definitions may have swapped.
    # `f` بدون تغییر هنوز دقیق است؛ فقط `f` تغییرکرده مشکوک است.
    assert result.counts()[MATCH_EXACT] == len(old.symbols) - 1


def test_ids_only_when_the_basis_differs() -> None:
    old = [rec("sym:aaaaaaaaaaaa", "f", "a.py", fp="fp1:000000000001")]
    same = [rec("sym:aaaaaaaaaaaa", "f", "a.py", fp="fp1:000000000002")]
    moved = [rec("sym:bbbbbbbbbbbb", "f", "b.py", fp="fp1:000000000001")]
    a = match_symbols(
        old, same, old_basis="fp1/python-3.12", new_basis="fp1/python-3.14"
    )
    assert not a.comparable
    assert a.rows[0].match == MATCH_EXACT and a.rows[0].content_changed is None
    b = match_symbols(
        old, moved, old_basis="fp1/python-3.12", new_basis="fp1/python-3.14"
    )
    assert [r.match for r in b.rows] == [MATCH_UNMATCHED, MATCH_UNMATCHED]


def test_an_output_without_a_basis_matches_ids_only() -> None:
    old = [rec("sym:aaaaaaaaaaaa", "f", "a.py")]
    result = match_symbols(old, list(old), old_basis="", new_basis="")
    assert not result.comparable
    assert (
        result.rows[0].match == MATCH_EXACT and result.rows[0].content_changed is None
    )


def test_a_different_language_matches_nothing() -> None:
    old = [rec("sym:aaaaaaaaaaaa", "f", "a.py")]
    result = match_symbols(
        old, list(old), old_basis=BASIS, new_basis=BASIS, new_language="rust"
    )
    assert {r.reason for r in result.rows} == {REASON_LANGUAGE}
    assert result.counts()[MATCH_UNMATCHED] == 2


def test_every_symbol_appears_in_exactly_one_row(tmp_path: Path) -> None:
    old = _tree(tmp_path, "old", BASE)
    new = _tree(
        tmp_path,
        "new",
        {
            "pkg/__init__.py": "",
            "pkg/core.py": BASE["pkg/core.py"].replace("helper", "assist"),
            "pkg/extra.py": "def helper(x):\n    return x + 1\n",
        },
    )
    result = match(old, new)
    old_seen = [i for row in result.rows for i in row.old]
    new_seen = [i for row in result.rows for i in row.new]
    assert sorted(old_seen) == sorted(s.id for s in old.symbols)
    assert sorted(new_seen) == sorted(s.id for s in new.symbols)
    assert set(result.counts()) == set(MATCH_CLASSES)


def test_matching_does_not_depend_on_input_order() -> None:
    old = [
        rec(f"sym:{i:012x}", f"f{i % 4}", f"p{i % 3}.py", fp=f"fp1:{i % 5:012x}")
        for i in range(30)
    ]
    new = [
        rec(f"sym:{i + 7:012x}", f"f{i % 4}", f"q{i % 2}.py", fp=f"fp1:{i % 5:012x}")
        for i in range(30)
    ]
    reference = match_symbols(old, new, old_basis=BASIS, new_basis=BASIS)
    rng = random.Random(7)
    for _ in range(5):
        a = old[:]
        b = new[:]
        rng.shuffle(a)
        rng.shuffle(b)
        assert match_symbols(a, b, old_basis=BASIS, new_basis=BASIS) == reference


def test_reasons_are_the_closed_vocabulary() -> None:
    from sarand.structure.identity import MATCH_REASONS

    assert set(MATCH_REASONS) == {
        REASON_SAME_ID,
        REASON_MOVED,
        REASON_DUPLICATE_NAME,
        REASON_SEVERAL_CANDIDATES,
        REASON_REMOVED,
        REASON_ADDED,
        REASON_LANGUAGE,
    }


# --- stored outputs ----------------------------------------------------------------


def test_matching_works_on_stored_json_payloads(tmp_path: Path) -> None:
    old = _tree(tmp_path, "old", BASE)
    new = _tree(
        tmp_path, "new", {**BASE, "pkg/core.py": BASE["pkg/core.py"] + "\nY = 2\n"}
    )
    old_payload = json.loads(json.dumps(structure_payload(old)))
    new_payload = json.loads(json.dumps(structure_payload(new)))
    old_records, old_basis = records_from_payload(old_payload)
    new_records, new_basis = records_from_payload(new_payload)
    result = match_symbols(
        old_records, new_records, old_basis=old_basis, new_basis=new_basis
    )
    assert result.comparable
    assert result.counts()[MATCH_EXACT] == len(old.symbols)
    assert result.counts()[MATCH_UNMATCHED] == 1


def test_an_older_payload_without_fingerprints_matches_ids_only(
    tmp_path: Path,
) -> None:
    new = _tree(tmp_path, "new", BASE)
    payload = json.loads(json.dumps(structure_payload(new)))
    old_payload = json.loads(json.dumps(payload))
    old_payload["meta"].pop("fingerprint_basis")
    for item in old_payload["symbols"]:
        item.pop("fingerprint")
    old_records, old_basis = records_from_payload(old_payload)
    new_records, new_basis = records_from_payload(payload)
    result = match_symbols(
        old_records, new_records, old_basis=old_basis, new_basis=new_basis
    )
    assert not result.comparable
    assert result.counts()[MATCH_EXACT] == len(new.symbols)
    assert all(row.content_changed is None for row in result.rows)


def test_two_builds_of_the_same_tree_give_byte_identical_fingerprints(
    tmp_path: Path,
) -> None:
    first = _tree(tmp_path, "one", BASE)
    second = _tree(tmp_path, "two", BASE)
    assert json.dumps(structure_payload(first), sort_keys=True) == json.dumps(
        structure_payload(second), sort_keys=True
    )
