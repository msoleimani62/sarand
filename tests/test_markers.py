"""R13-E: a marker keyword is found everywhere it occurs, but only a TODO / FIXME
written as a task is technical debt (core/markers.py).

Evidence behind the cases: sarand's own report listed 149 markers, 96 of them the
word TODO inside prose, names or documentation, 35 BUG notes about fixed defects,
9 SAFETY notes; `TODO-CLUSTER` flagged a file whose 16 "markers" were all prose.
Dependency-free like the other tests.
R13-E: کشف مارکر گسترده است، ولی فقط TODO/FIXME نوشته‌شده به‌شکل کار بدهی است.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from _golden_fixtures import FIXTURES
from _helpers import write
from sarand.core import cache
from sarand.core.cache import build_cache_entries, reconstruct_todos
from sarand.core.health import compute_health_score
from sarand.core.markers import (
    CATEGORIES,
    CATEGORY_ACTIONABLE,
    CATEGORY_DEVELOPMENT,
    CATEGORY_HISTORICAL,
    CATEGORY_MENTION,
    CATEGORY_SAFETY,
    category_counts,
    classify_marker_text,
    is_actionable,
    marker_category,
)
from sarand.core.risks import TODO_CLUSTER_MIN, evaluate_risks
from sarand.models.results import ReportData, TodoItem
from sarand.renderers import json_renderer, markdown, sarif
from sarand.rust_bridge import FileRecord
from sarand.scanners.todos import scan_todos


def _item(kind: str, content: str, path: str = "a.py", line: int = 1) -> TodoItem:
    return TodoItem(path=path, line_number=line, kind=kind, content=content)


def _data(todos: list[TodoItem]) -> ReportData:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "p"
        root.mkdir()
        data = FIXTURES["minimal"](root)
    data.todos = todos
    data.stats.total_files = 10
    data.health = compute_health_score(data)
    return data


def _fired(data: ReportData) -> set[str]:
    return {r.rule_id for r in evaluate_risks(data).risks}


# --- classification -----------------------------------------------------------------


def test_the_task_forms_are_actionable() -> None:
    for text in (
        "TODO: fix x",
        "TODO(ana): fix x",
        "TODO(ana) : fix x",
        "TODO - fix x",
        "TODO \u2013 fix x",
        "FIXME: x",
        "fixme: lower case",
        "TODO: `code` first",
        'TODO: "quoted"',
        "TODO: \u062a\u0633\u062a \u0641\u0627\u0631\u0633\u06cc",
    ):
        kind = text.split("(")[0].split(":")[0].split(" ")[0].upper()
        assert classify_marker_text(kind, text) == CATEGORY_ACTIONABLE, text


def test_a_todo_that_is_only_mentioned_is_not_a_task() -> None:
    for text in (
        "TODO-style markers",
        "TODO-CLUSTER",
        "TODO/FIXME tags",
        "the TODO scanner",
        "TODO: ...",
        "TODO: ..., TODO - ...",
        "TODO -- x",
        "TODO",
        "todo.kind",
    ):
        assert classify_marker_text("TODO", text) == CATEGORY_MENTION, text


def test_the_other_keywords_have_one_category_each() -> None:
    assert classify_marker_text("BUG", "BUG FIX: x") == CATEGORY_HISTORICAL
    assert classify_marker_text("BUG", "BUG: still broken") == CATEGORY_HISTORICAL
    assert (
        classify_marker_text("SAFETY", "SAFETY: the pointer is valid")
        == CATEGORY_SAFETY
    )
    assert classify_marker_text("HACK", "HACK: x") == CATEGORY_DEVELOPMENT
    assert classify_marker_text("XXX", "XXX look") == CATEGORY_DEVELOPMENT


def test_an_item_without_a_category_is_classified_from_its_content() -> None:
    assert marker_category(_item("TODO", "x = 1  # TODO: a")) == CATEGORY_ACTIONABLE
    assert marker_category(_item("TODO", "x")) == CATEGORY_MENTION
    assert marker_category(_item("BUG", "x")) == CATEGORY_HISTORICAL
    stored = TodoItem("a", 1, "TODO", "TODO: a", category=CATEGORY_SAFETY)
    assert marker_category(stored) == CATEGORY_SAFETY


def test_the_counts_name_every_category_in_a_fixed_order() -> None:
    counts = category_counts([_item("TODO", "TODO: a"), _item("BUG", "b")])
    assert list(counts) == list(CATEGORIES)
    assert counts == {
        CATEGORY_ACTIONABLE: 1,
        CATEGORY_HISTORICAL: 1,
        CATEGORY_SAFETY: 0,
        CATEGORY_DEVELOPMENT: 0,
        CATEGORY_MENTION: 0,
    }
    assert category_counts([]) == dict.fromkeys(CATEGORIES, 0)


# --- the scanner finds every marker on a line ------------------------------------------


def _scan(text: str, max_items: int = 1000) -> list[TodoItem]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "main.py", text)
        return scan_todos(root, max_items=max_items)


def test_every_marker_on_one_line_is_reported() -> None:
    found = _scan("x = 1  # TODO: a  # BUG: b  # FIXME: c\n")
    assert [(i.kind, i.category) for i in found] == [
        ("TODO", CATEGORY_ACTIONABLE),
        ("BUG", CATEGORY_HISTORICAL),
        ("FIXME", CATEGORY_ACTIONABLE),
    ]
    assert {i.line_number for i in found} == {1}


def test_two_markers_of_one_kind_on_a_line_are_judged_each_on_its_own_text() -> None:
    found = _scan("# TODO: real task, see the TODO scanner\n")
    assert [i.category for i in found] == [CATEGORY_ACTIONABLE, CATEGORY_MENTION]


def test_a_line_without_a_marker_gives_nothing() -> None:
    assert _scan("print('hello')\n# a plain comment\n") == []


def test_the_item_cap_stops_inside_a_line_too() -> None:
    found = _scan("# TODO: a TODO: b TODO: c\n# TODO: d\n", max_items=2)
    assert len(found) == 2


def test_a_marker_after_the_truncation_point_is_still_classified() -> None:
    line = "x = 1  # " + "w" * 250 + "  TODO: late task\n"
    (found,) = _scan(line)
    assert found.category == CATEGORY_ACTIONABLE
    assert found.content.endswith("...")


# --- health: only a task is debt ---------------------------------------------------------


def _code_score(todos: list[TodoItem]) -> float:
    return compute_health_score(_data(todos)).breakdown["code"]


def test_fifty_one_tasks_lower_the_code_score() -> None:
    tasks = [_item("TODO", "TODO: x", line=i) for i in range(51)]
    assert _code_score(tasks) == _code_score([]) - 5.0


def test_historical_safety_development_and_mentions_never_lower_the_score() -> None:
    for item in (
        _item("BUG", "BUG FIX: old"),
        _item("SAFETY", "SAFETY: valid"),
        _item("HACK", "HACK: x"),
        _item("XXX", "XXX x"),
        _item("TODO", "the TODO scanner"),
    ):
        many = [TodoItem(item.path, i, item.kind, item.content) for i in range(200)]
        assert _code_score(many) == _code_score([]), item.kind


def test_fifty_tasks_are_still_within_the_limit() -> None:
    tasks = [_item("TODO", "TODO: x", line=i) for i in range(50)]
    assert _code_score(tasks) == _code_score([])


# --- the TODO-CLUSTER risk counts tasks, at the unchanged threshold of 10 --------------------


def test_the_threshold_is_unchanged() -> None:
    assert TODO_CLUSTER_MIN == 10


def test_ten_tasks_in_one_file_fire_and_nine_do_not() -> None:
    nine = [_item("TODO", "TODO: x", line=i) for i in range(TODO_CLUSTER_MIN - 1)]
    ten = [_item("TODO", "TODO: x", line=i) for i in range(TODO_CLUSTER_MIN)]
    assert "TODO-CLUSTER" not in _fired(_data(nine))
    assert "TODO-CLUSTER" in _fired(_data(ten))


def test_a_file_full_of_other_markers_is_not_a_cluster() -> None:
    for kind, content in (
        ("BUG", "BUG FIX: old"),
        ("SAFETY", "SAFETY: ok"),
        ("HACK", "HACK: x"),
        ("TODO", "the TODO scanner"),
    ):
        many = [_item(kind, content, line=i) for i in range(30)]
        assert "TODO-CLUSTER" not in _fired(_data(many)), kind


def test_tasks_and_mentions_in_one_file_count_only_the_tasks() -> None:
    mixed = [_item("TODO", "TODO: x", line=i) for i in range(6)] + [
        _item("TODO", "TODO-style", line=10 + i) for i in range(20)
    ]
    assert "TODO-CLUSTER" not in _fired(_data(mixed))


def test_the_cluster_reason_says_actionable() -> None:
    ten = [_item("TODO", "TODO: x", line=i) for i in range(TODO_CLUSTER_MIN)]
    reasons = {r.rule_id: r.reason for r in evaluate_risks(_data(ten)).risks}
    assert "actionable markers" in reasons["TODO-CLUSTER"]


# --- every marker stays discoverable in the reports ---------------------------------------------


def _mixed() -> list[TodoItem]:
    return [
        _item("TODO", "TODO: a", line=1),
        _item("BUG", "BUG FIX: b", line=2),
        _item("SAFETY", "SAFETY: c", line=3),
        _item("HACK", "HACK: d", line=4),
        _item("TODO", "the TODO scanner", line=5),
    ]


def test_json_lists_every_marker_with_its_category() -> None:
    payload = json.loads(json_renderer.render(_data(_mixed())))
    assert payload["schema_version"] == "1.7"
    assert [t["category"] for t in payload["todos"]] == [
        "actionable",
        "historical",
        "safety",
        "development",
        "mention",
    ]
    assert payload["todo_categories"] == {
        "actionable": 1,
        "historical": 1,
        "safety": 1,
        "development": 1,
        "mention": 1,
    }
    assert list(payload["todo_categories"]) == list(CATEGORIES)


def test_json_has_no_category_summary_without_markers() -> None:
    assert "todo_categories" not in json.loads(json_renderer.render(_data([])))


def test_markdown_shows_the_category_column_and_the_summary() -> None:
    output = markdown.render(_data(_mixed()), include_source=False)
    assert "| File | Line | Kind | Category | Content |" in output
    assert (
        "Found 1 actionable, 1 historical, 1 safety, 1 development, 1 mention."
        in output
    )
    assert "| `a.py` | 3 | SAFETY | safety | `SAFETY: c` |" in output


def test_sarif_carries_the_category_and_keeps_safety_markers() -> None:
    run = json.loads(sarif.render(_data(_mixed())))["runs"][0]
    marker_results = [r for r in run["results"] if r["ruleId"].startswith("todo")]
    assert sorted(r["properties"]["category"] for r in marker_results) == sorted(
        ["actionable", "historical", "safety", "development", "mention"]
    )


# --- the cache -------------------------------------------------------------------------------------


def test_a_cached_marker_keeps_its_category() -> None:
    item = TodoItem("a.py", 3, "BUG", "BUG FIX: x", category=CATEGORY_HISTORICAL)
    record: FileRecord = {
        "rel_path": "a.py",
        "size": 100,
        "is_symlink": False,
        "is_broken_symlink": False,
        "is_hidden": False,
        "is_binary": False,
        "is_executable": False,
        "extension": ".py",
        "total_lines": 1,
        "code_lines": 1,
        "comment_lines": 0,
        "blank_lines": 0,
        "content_hash": "h",
    }
    entry = build_cache_entries([record], [item], [])["a.py"]
    (rebuilt,) = reconstruct_todos({"a.py": entry})
    assert rebuilt == item


def test_changing_the_marker_rules_makes_every_cache_stale() -> None:
    before = cache._rules_fingerprint()
    original = cache.MARKER_RULES_VERSION
    try:
        cache.MARKER_RULES_VERSION = original + 1
        assert cache._rules_fingerprint() != before
    finally:
        cache.MARKER_RULES_VERSION = original
    assert cache._rules_fingerprint() == before


# --- regression on the real lines that misled the old contract -----------------------------------------


def test_the_real_lines_from_sarands_own_report_are_not_tasks() -> None:
    for text in (
        "# Accepted forms: TODO: ..., TODO - ..., FIXME: ..., FIXME - ...",
        "Scan non-binary source files for TODO-style markers.",
        '"TODO-CLUSTER",',
        "for todo in data.todos:",
        'register_rule(rule_id, f"{todo.kind} marker found in source")',
        '"""A TODO / FIXME / BUG marker found in source."""',
    ):
        found = _scan(text + "\n")
        assert found, text
        assert not any(is_actionable(i) for i in found), text
