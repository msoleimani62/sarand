"""Tests for AGENTS.md 5.68, part C2: TODO markers that are not tasks
(golden/fixture directories, Markdown prose, `[todo] exclude_globs`)."""

from __future__ import annotations

import tempfile
from datetime import UTC
from pathlib import Path

from _helpers import write
from sarand.core.todo_config import (
    TodoConfigError,
    load_exclude_globs,
    parse_exclude_globs,
)
from sarand.models.results import TodoItem
from sarand.renderers import json_renderer, markdown
from sarand.scanners.todos import filter_todos, is_todo_excluded


def _item(path: str) -> TodoItem:
    return TodoItem(path=path, line_number=1, kind="TODO", content="TODO: x")


def test_default_places_are_excluded() -> None:
    for path in (
        "tests/golden/hybrid.md",
        "tests/Fixtures/data.py",
        "app/__snapshots__/a.snap",
        "docs/snapshots/x.txt",
        "AGENTS.md",
        "docs/notes.MD",
        "docs/guide.rst",
        "docs\\guide.mdx",
    ):
        assert is_todo_excluded(path), path


def test_ordinary_source_is_not_excluded() -> None:
    for path in (
        "src/main.py",
        "tests/test_health.py",
        "golden.py",
        "fixtures.py",
        "src/lib.rs",
        "README",
    ):
        assert not is_todo_excluded(path), path


def test_extra_globs_apply_with_fnmatch_semantics() -> None:
    assert is_todo_excluded("tests/test_health.py", ["tests/test_health.py"])
    assert is_todo_excluded("vendor/a/b/c.py", ["vendor/*"])
    assert not is_todo_excluded("Vendor/a.py", ["vendor/*"])
    assert not is_todo_excluded("src/a.py", [])


def test_filter_todos_returns_kept_items_and_the_count() -> None:
    items = [_item("src/a.py"), _item("tests/golden/x.md"), _item("README.md")]
    kept, suppressed = filter_todos(items, [])
    assert [i.path for i in kept] == ["src/a.py"]
    assert suppressed == 2
    kept, suppressed = filter_todos(items, ["src/*"])
    assert kept == []
    assert suppressed == 3


def test_no_table_means_no_extra_globs() -> None:
    assert parse_exclude_globs("") == ()
    assert parse_exclude_globs('[secrets]\nfixture_paths = ["a.py"]\n') == ()


def test_globs_are_read_and_normalised() -> None:
    text = '[todo]\nexclude_globs = ["tests/test_health.py", " vendor\\\\* "]\n'
    assert parse_exclude_globs(text) == ("tests/test_health.py", "vendor/*")


def test_a_bad_todo_table_is_an_error() -> None:
    bad = {
        "[todo]\nbogus = 1\n": "unknown key",
        '[todo]\nexclude_globs = "a"\n': "list of strings",
        "[todo]\nexclude_globs = [1]\n": "non-empty strings",
        '[todo]\nexclude_globs = ["*"]\n': "every file",
        'todo = "x"\n': "must be a table",
        "[todo\n": "invalid TOML",
    }
    for text, expected in bad.items():
        try:
            parse_exclude_globs(text)
        except TodoConfigError as exc:
            assert expected in str(exc), text
        else:
            raise AssertionError(f"expected an error for {text!r}")


def test_load_without_a_file_and_with_a_bad_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert load_exclude_globs(root) == ()
        write(root / ".sarand.toml", "[todo]\nbogus = 1\n")
        try:
            load_exclude_globs(root)
        except TodoConfigError as exc:
            assert str(exc).startswith(".sarand.toml:")
        else:
            raise AssertionError("expected TodoConfigError")


def _report(todos: list[TodoItem], suppressed: int) -> object:
    from datetime import datetime

    from sarand.models.results import (
        EnvironmentInfo,
        GitSnapshot,
        ProjectStats,
        ReportData,
    )

    return ReportData(
        project_root=Path("fixture-project"),
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        environment=EnvironmentInfo(),
        git=GitSnapshot(),
        stats=ProjectStats(),
        todos=todos,
        todos_suppressed=suppressed,
    )


def test_the_report_says_how_many_markers_were_suppressed() -> None:
    kept = [_item("src/a.py")]
    output = markdown.render(_report(kept, 7), include_source=False)  # type: ignore[arg-type]
    assert "7 marker(s) suppressed" in output
    # Even when every marker was suppressed the section must not vanish.
    only_suppressed = markdown.render(_report([], 3), include_source=False)  # type: ignore[arg-type]
    assert "## TODO / FIXME markers" in only_suppressed
    assert "3 marker(s) suppressed" in only_suppressed
    nothing = markdown.render(_report(kept, 0), include_source=False)  # type: ignore[arg-type]
    assert "suppressed" not in nothing


def test_the_json_key_appears_only_when_something_was_suppressed() -> None:
    import json

    some = json.loads(json_renderer.render(_report([], 4), include_source=False))  # type: ignore[arg-type]
    assert some["todos_suppressed"] == 4
    none = json.loads(json_renderer.render(_report([], 0), include_source=False))  # type: ignore[arg-type]
    assert "todos_suppressed" not in none
