"""Regression tests for Quick Context R11c: layer L4, the relevant source subset
(`core/relevant_source.py`, docs/QUICK_CONTEXT_DESIGN.md section 5, decisions
D-QC6 and D-QC7).

Dependency-free like the other tests (no `import pytest`).
تست‌های رگرسیون R11c: لایه‌ی L4، زیرمجموعه‌ی کد منبع مرتبط.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from html import escape
from pathlib import Path

from _golden_fixtures import FIXTURES
from sarand.cli import build_parser
from sarand.config import SarandConfig
from sarand.core import relevant_source as rs_module
from sarand.core.relevant_source import (
    BYTES_PER_TOKEN,
    TOKENS_DEFAULT,
    TOKENS_MAX,
    TOKENS_MIN,
    WRAPPER_BYTES,
    relevant_source_payload,
    select_relevant_source,
    tokens_argument,
)
from sarand.models.results import (
    GitSnapshot,
    ReportData,
    SecretFinding,
    TodoItem,
)
from sarand.renderers import html, json_renderer, markdown, text

# Built at run time so this file holds no token-shaped string.
# در زمان اجرا ساخته می‌شود تا این فایل رشته‌ی شبیه توکن نداشته باشد.
_FAKE_SECRET = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"


@contextmanager
def _project() -> Iterator[tuple[Path, ReportData]]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "proj"
        root.mkdir()
        data = FIXTURES["minimal"](root)
        data.project_root = root
        data.included_files = []
        yield root, data


def _add(root: Path, data: ReportData, rel: str, body: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    data.included_files.append(Path(rel))


def _numbered(count: int, prefix: str = "line") -> str:
    return "\n".join(f"{prefix} {i}" for i in range(1, count + 1)) + "\n"


def _todo(path: str, line: int) -> TodoItem:
    return TodoItem(path=path, line_number=line, kind="TODO", content="x")


def _paths(result: rs_module.RelevantSource) -> list[str]:
    return [f.path for f in result.files]


def test_the_flag_is_off_by_default_and_const_is_the_documented_default() -> None:
    parser = build_parser()
    assert parser.parse_args([]).relevant_source is None
    assert parser.parse_args(["--relevant-source"]).relevant_source == 6000
    assert parser.parse_args(["--relevant-source=3000"]).relevant_source == 3000
    assert TOKENS_DEFAULT == 6000 and BYTES_PER_TOKEN == 3


def test_token_counts_outside_the_range_or_not_numbers_are_rejected() -> None:
    for bad in ("0", "-5", str(TOKENS_MIN - 1), str(TOKENS_MAX + 1), "abc", "", "1.5"):
        try:
            tokens_argument(bad)
        except argparse.ArgumentTypeError:
            continue
        raise AssertionError(f"accepted {bad!r}")
    assert tokens_argument(str(TOKENS_MIN)) == TOKENS_MIN
    assert tokens_argument(str(TOKENS_MAX)) == TOKENS_MAX


def test_config_carries_the_tokens_and_the_focus_and_defaults_to_off() -> None:
    parser = build_parser()
    off = SarandConfig.from_args(parser.parse_args([]))
    assert off.relevant_source_tokens is None and off.focus == ""
    on = SarandConfig.from_args(
        parser.parse_args(["--relevant-source=900", "--focus", "auth login"])
    )
    assert on.relevant_source_tokens == 900 and on.focus == "auth login"


def test_a_default_report_has_no_trace_of_layer_l4() -> None:
    with _project() as (_, data):
        assert data.relevant_source is None
        assert "Relevant Source" not in markdown.render(data)
        assert "Relevant Source" not in text.render(data)
        assert "Relevant Source" not in html.render(data)
        assert "relevant_source" not in json.loads(json_renderer.render(data))


def test_bytes_used_never_exceeds_the_cap_for_a_range_of_budgets_and_files() -> None:
    with _project() as (root, data):
        _add(root, data, "src/huge.py", _numbered(5000, "x" * 150))
        _add(
            root,
            data,
            "src/persian.py",
            "\n".join("خط برنامه " * 10 for _ in range(300)),
        )
        _add(root, data, "src/a.py", _numbered(80))
        data.detection.entry_points = ["src/huge.py", "src/persian.py", "src/a.py"]
        data.todos = [_todo("src/a.py", 40), _todo("src/huge.py", 100)]
        for tokens in (1, 5, 50, TOKENS_MIN, 300, 1000, 6000, 20000):
            result = select_relevant_source(data, tokens)
            assert result.bytes_used <= result.bytes_cap == tokens * 3, tokens
            if result.text:
                assert (
                    len(result.text.encode("utf-8")) + WRAPPER_BYTES
                    == result.bytes_used
                )


def test_a_budget_too_small_for_one_header_gives_an_empty_result_within_the_cap() -> (
    None
):
    with _project() as (root, data):
        _add(root, data, "src/a.py", _numbered(10))
        data.detection.entry_points = ["src/a.py"]
        result = select_relevant_source(data, 1)
        assert result.text == "" and result.files == [] and result.bytes_used == 0
        data.relevant_source = result
        assert "too small" in markdown.render(data)


def test_a_file_larger_than_the_whole_budget_is_clipped_to_snippets() -> None:
    with _project() as (root, data):
        _add(root, data, "big.py", _numbered(5000, "y" * 100))
        data.detection.entry_points = ["big.py"]
        result = select_relevant_source(data, 400)
        assert result.bytes_used <= result.bytes_cap
        assert _paths(result) == ["big.py"] and result.files[0].snippets
        assert "(trimmed)" in result.files[0].snippets[0].reason
        assert len(result.text.splitlines()) < 60
        tiny = select_relevant_source(data, TOKENS_MIN)
        assert tiny.bytes_used <= tiny.bytes_cap and _paths(tiny) == ["big.py"]


def test_headers_are_kept_before_snippets_when_space_is_short() -> None:
    with _project() as (root, data):
        for name in ("a", "b", "c"):
            _add(root, data, f"src/{name}.py", _numbered(60, name))
        data.detection.entry_points = ["src/a.py", "src/b.py", "src/c.py"]
        result = select_relevant_source(data, 250)
        assert result.bytes_used <= result.bytes_cap
        assert len(result.files) == 3
        assert sum(len(s.lines) for f in result.files for s in f.snippets) < 90


def test_the_files_shown_are_always_a_subset_of_included_files() -> None:
    with _project() as (root, data):
        _add(root, data, "src/ok.py", _numbered(20))
        (root / "src/skipped.py").write_text(_numbered(20))
        (root / "src/leaked.py").write_text(_numbered(20))
        data.excluded_secret_files = [Path("src/leaked.py")]
        data.detection.entry_points = ["src/ok.py", "src/skipped.py", "src/leaked.py"]
        data.todos = [_todo("src/skipped.py", 3), _todo("src/leaked.py", 3)]
        data.git = GitSnapshot(
            branch="m", commit="c", status="?? src/skipped.py\n M src/leaked.py"
        )
        data.secret_findings = [
            SecretFinding(path="src/leaked.py", line_number=2, pattern_name="K")
        ]
        result = select_relevant_source(data, 6000, focus="skipped leaked")
        included = {p.as_posix() for p in data.included_files}
        assert set(_paths(result)) <= included == {"src/ok.py"}
        assert "skipped.py" not in result.text and "leaked.py" not in result.text


def test_paths_that_look_like_secrets_are_never_candidates() -> None:
    with _project() as (root, data):
        _add(root, data, ".env", "A=1\n")
        _add(root, data, "keys/id_rsa", "x\n")
        _add(root, data, "src/a.py", _numbered(5))
        data.detection.entry_points = [".env", "keys/id_rsa", "src/a.py"]
        assert _paths(select_relevant_source(data, 6000)) == ["src/a.py"]


def test_a_planted_secret_in_a_selected_file_is_withheld_in_every_renderer() -> None:
    with _project() as (root, data):
        body = "a = 1\nb = 2\n# TODO rotate\ntoken = '" + _FAKE_SECRET + "'\nc = 3\n"
        _add(root, data, "src/config.py", body)
        data.todos = [_todo("src/config.py", 3)]
        data.relevant_source = select_relevant_source(data, 6000)
        assert data.relevant_source.withheld_lines == 1
        assert 'matches pattern "GitHub Token"' in data.relevant_source.text
        outputs = {
            "markdown": markdown.render(data, include_source=False),
            "text": text.render(data, include_source=False),
            "html": html.render(data, include_source=False),
            "json": json_renderer.render(data, include_source=False),
        }
        for name, out in outputs.items():
            assert "src/config.py" in out, name
            assert _FAKE_SECRET not in out, name
            assert _FAKE_SECRET[:12] not in out, name


def test_the_output_never_names_a_secret_value_or_reads_an_excluded_file() -> None:
    with _project() as (root, data):
        (root / "src").mkdir()
        (root / "src/secret.py").write_text("k = '" + _FAKE_SECRET + "'\n")
        data.excluded_secret_files = [Path("src/secret.py")]
        data.included_files = [Path("src/secret.py")]
        reads: list[str] = []
        original = rs_module._read_lines

        def spy(root: Path, rel: str) -> list[str] | None:
            reads.append(rel)
            return original(root, rel)

        rs_module._read_lines = spy
        try:
            select_relevant_source(data, 6000)
        finally:
            rs_module._read_lines = original
        assert reads == []


def test_the_same_input_gives_the_same_bytes_twice_and_data_is_not_mutated() -> None:
    with _project() as (root, data):
        for i in range(6):
            _add(root, data, f"src/f{i}.py", _numbered(30))
        data.todos = [_todo(f"src/f{i}.py", 10 + i) for i in range(6)]
        before = [p for p in data.included_files], list(data.todos)
        first = select_relevant_source(data, 800)
        second = select_relevant_source(data, 800)
        assert first == second and first.text == second.text
        assert (list(data.included_files), list(data.todos)) == before


def test_score_order_is_focus_git_entry_point_secret_path_todo_then_path() -> None:
    with _project() as (root, data):
        for name in ("zz_todo", "aa_todo", "entry", "git", "focusme", "secret"):
            _add(root, data, f"src/{name}.py", _numbered(20))
        data.todos = [_todo("src/zz_todo.py", 5), _todo("src/aa_todo.py", 5)]
        data.detection.entry_points = ["src/entry.py"]
        data.git = GitSnapshot(branch="m", commit="c", status=" M src/git.py")
        data.secret_findings = [
            SecretFinding(path="src/secret.py", line_number=3, pattern_name="K")
        ]
        result = select_relevant_source(data, 20000, focus="focusme")
        assert _paths(result) == [
            "src/focusme.py",
            "src/git.py",
            "src/entry.py",
            "src/secret.py",
            "src/aa_todo.py",
            "src/zz_todo.py",
        ]


def test_files_with_identical_content_count_once_and_the_unique_file_survives() -> None:
    with _project() as (root, data):
        same = _numbered(30, "dup")
        _add(root, data, "src/a_copy.py", same)
        _add(root, data, "src/b_copy.py", same)
        _add(root, data, "src/unique.py", _numbered(30, "uniq"))
        data.stats.duplicate_files = [("h", ["src/a_copy.py", "src/b_copy.py"])]
        data.todos = [
            _todo("src/a_copy.py", 5),
            _todo("src/b_copy.py", 5),
            _todo("src/unique.py", 5),
        ]
        data.detection.entry_points = ["src/a_copy.py", "src/b_copy.py"]
        result = select_relevant_source(data, 1500)
        assert "src/unique.py" in _paths(result)
        assert _paths(result).count("src/a_copy.py") == 1
        assert "src/b_copy.py" not in _paths(result)
        assert "(same content: src/b_copy.py)" in result.text
        assert result.files[0].same_as == ["src/b_copy.py"]


def test_only_the_selected_files_are_read_from_disk() -> None:
    with _project() as (root, data):
        for i in range(300):
            _add(root, data, f"src/m{i:03d}.py", _numbered(40))
        data.todos = [_todo(f"src/m{i:03d}.py", 7) for i in range(300)]
        reads: list[str] = []
        original = rs_module._read_lines

        def spy(root: Path, rel: str) -> list[str] | None:
            reads.append(rel)
            return original(root, rel)

        rs_module._read_lines = spy
        try:
            result = select_relevant_source(data, 1200)
        finally:
            rs_module._read_lines = original
        assert len(reads) == len(result.files) <= rs_module.MAX_FILES == 20
        assert result.omitted_files == 300 - len(result.files)


def test_a_link_that_leaves_the_project_is_not_read() -> None:
    with _project() as (root, data), tempfile.TemporaryDirectory() as outside:
        target = Path(outside) / "private.txt"
        target.write_text("outside secret\n")
        (root / "src").mkdir()
        try:
            os.symlink(target, root / "src/link.py")
        except (OSError, NotImplementedError):
            return
        data.included_files = [Path("src/link.py")]
        data.detection.entry_points = ["src/link.py"]
        result = select_relevant_source(data, 6000)
        assert result.files == [] and result.unreadable_files == 1
        assert "outside secret" not in result.text


def test_binary_files_are_skipped_and_huge_files_are_read_only_to_the_cap() -> None:
    with _project() as (root, data):
        (root / "a.bin").write_bytes(b"\x00\x01\x02" * 100)
        (root / "huge.txt").write_text("x" * (rs_module.MAX_READ_BYTES * 4))
        data.included_files = [Path("a.bin"), Path("huge.txt")]
        data.detection.entry_points = ["a.bin", "huge.txt"]
        result = select_relevant_source(data, 6000)
        assert _paths(result) == ["huge.txt"] and result.unreadable_files == 1
        assert result.bytes_used <= result.bytes_cap
        assert max(len(line) for line in result.text.splitlines()) < 260


def test_focus_words_match_the_path_case_insensitively() -> None:
    with _project() as (root, data):
        _add(root, data, "src/Auth/Login.py", _numbered(10))
        _add(root, data, "src/other.py", _numbered(10))
        result = select_relevant_source(data, 6000, focus="login")
        assert _paths(result) == ["src/Auth/Login.py"]
        assert select_relevant_source(data, 6000).files == []


def test_snippets_state_file_lines_and_reason_and_use_the_fixed_context() -> None:
    with _project() as (root, data):
        _add(root, data, "src/a.py", _numbered(100))
        data.todos = [_todo("src/a.py", 50)]
        result = select_relevant_source(data, 6000)
        snippet = result.files[0].snippets[0]
        assert (snippet.start, snippet.end) == (
            47,
            53,
        ) and snippet.reason == "TODO marker"
        assert "-- lines 47-53: TODO marker" in result.text
        assert "50| line 50" in result.text


def test_long_lines_are_clipped_and_persian_text_counts_in_bytes() -> None:
    with _project() as (root, data):
        _add(root, data, "src/a.py", "ا" * 1000 + "\n" + _numbered(3))
        data.detection.entry_points = ["src/a.py"]
        result = select_relevant_source(data, 6000)
        longest = max(len(line) for line in result.text.splitlines())
        assert longest <= rs_module.MAX_LINE_CHARS + 10
        assert result.bytes_used > len(result.text)


def test_markdown_html_text_and_json_all_carry_the_same_block() -> None:
    with _project() as (root, data):
        _add(root, data, "src/a.py", "x = '<b>&'\n" + _numbered(5))
        data.detection.entry_points = ["src/a.py"]
        data.relevant_source = select_relevant_source(data, 6000)
        block = data.relevant_source.text
        md = markdown.render(data, include_source=False)
        assert f"```text\n{block}\n```" in md
        assert block in text.render(data, include_source=False)
        assert escape(block) in html.render(data, include_source=False)
        payload = json.loads(json_renderer.render(data, include_source=False))
        assert payload["relevant_source"]["text"] == block
        budget = payload["relevant_source"]["budget"]
        assert set(budget) == {
            "tokens",
            "bytes_cap",
            "bytes_used",
            "bytes_per_token",
            "wrapper_bytes",
        }
        assert (
            budget["bytes_used"] <= budget["bytes_cap"]
            and budget["bytes_per_token"] == 3
        )
        assert (
            relevant_source_payload(data.relevant_source)["files"][0]["path"]
            == "src/a.py"
        )


def test_the_wrapper_reserve_covers_what_each_renderer_adds() -> None:
    with _project() as (root, data):
        _add(root, data, "src/a.py", _numbered(400))
        data.detection.entry_points = ["src/a.py"]
        data.relevant_source = select_relevant_source(data, 600)
        block = data.relevant_source.text
        assert (
            len(f"## Relevant Source\n\n```text\n{block}\n```\n".encode())
            - len(block.encode())
            <= WRAPPER_BYTES
        )
        assert len(block.encode()) + WRAPPER_BYTES == data.relevant_source.bytes_used


def test_a_source_line_that_looks_like_a_fence_cannot_break_the_markdown_block() -> (
    None
):
    with _project() as (root, data):
        _add(root, data, "src/a.md", "```\nfence\n```\n")
        data.detection.entry_points = ["src/a.md"]
        data.relevant_source = select_relevant_source(data, 6000)
        for line in data.relevant_source.text.splitlines():
            assert not line.startswith("```")


def test_the_parser_rejects_focus_without_the_flag() -> None:
    from sarand import cli

    try:
        cli.main(["--focus", "x", "--project", "."])
    except SystemExit as exc:
        assert exc.code == 2
        return
    raise AssertionError("--focus alone was accepted")
