"""Regression tests for backlog item 7 (Makefile, detection-only first
scope) -- see AGENTS.md section 5.39 and `core/makefile.py`'s module
docstring for the audit and design rationale.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from _helpers import write
from sarand.core.makefile import _parse, detect_makefiles
from sarand.models.results import (
    EnvironmentInfo,
    GitSnapshot,
    MakefileEntry,
    MakefileInfo,
    ProjectStats,
    ReportData,
)
from sarand.renderers import json_renderer, markdown

_TYPICAL = (
    "CC := gcc\n"
    "CFLAGS ::= -O2\n"
    "OBJS = a.o b.o\n"
    ".PHONY: all clean test\n"
    "\n"
    "all: app\n"
    "\tcc -o app $(OBJS)\n"
    "\n"
    "app: $(OBJS)\n"
    "\t$(CC) $^ -o $@\n"
    "\n"
    "%.o: %.c\n"
    "\t$(CC) -c $<\n"
    "\n"
    "clean:\n"
    "\trm -f app\n"
    "\n"
    "test: app\n"
    "\t./app --selftest\n"
)


def test_typical_makefile_targets_phony_and_default() -> None:
    targets, phony, default = _parse(_TYPICAL)
    assert targets == ["all", "app", "clean", "test"]
    assert phony == ["all", "clean", "test"]
    assert default == "all"


def test_variable_assignments_are_never_targets() -> None:
    text = "A := 1\nB ::= 2\nC ?= 3\nD += 4\nE = x:y\nF != echo a:b\nreal: A\n"
    assert _parse(text)[0] == ["real"]


def test_pattern_special_and_expanded_targets_are_skipped() -> None:
    text = "%.o: %.c\n.SUFFIXES:\n$(BIN): x\n$(DIR)/out: y\nok: z\n"
    assert _parse(text)[0] == ["ok"]


def test_multiple_targets_double_colon_and_dedup() -> None:
    text = "a b: x\nc:: y\na: z\n"
    assert _parse(text)[0] == ["a", "b", "c"]


def test_continuation_lines_are_joined() -> None:
    text = ".PHONY: one \\\n  two \\\n  three\none:\ntwo:\nthree:\n"
    targets, phony, _ = _parse(text)
    assert targets == ["one", "two", "three"]
    assert phony == ["one", "two", "three"]


def test_recipes_comments_define_blocks_and_conditionals_are_skipped() -> None:
    text = (
        "# build: not a target\n"
        "define HELP\n"
        "fake: inside define\n"
        "endef\n"
        "ifeq ($(OS),a:b)\n"
        "include other.mk\n"
        "endif\n"
        "real:\n"
        "\techo not-a-target: nope\n"
    )
    assert _parse(text)[0] == ["real"]


def test_default_goal_overrides_first_target() -> None:
    text = ".DEFAULT_GOAL := build\nfirst:\nbuild:\n"
    assert _parse(text)[2] == "build"


def test_dot_prefixed_first_target_is_not_the_default() -> None:
    assert _parse(".hidden:\nreal:\n")[2] == "real"


def test_target_specific_variable_still_lists_the_target() -> None:
    assert _parse("debug: CFLAGS = -g\n")[0] == ["debug"]


def test_empty_and_garbage_input_do_not_crash() -> None:
    assert _parse("") == ([], [], "")
    assert _parse("\x00\x01 garbage ::: ===\n\n\t\n") == ([], [], "")


def test_project_without_makefile_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "app.py", "print('hi')\n")
        write(root / "Makefile.PL", "all:\n")
        write(root / "makefile.bak", "all:\n")
        write(root / "rules.mk", "all:\n")
        assert detect_makefiles(root) is None


def test_all_three_gnu_names_are_found_in_separate_dirs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "a" / "Makefile", "x:\n")
        write(root / "b" / "makefile", "y:\n")
        write(root / "c" / "GNUmakefile", "z:\n")
        info = detect_makefiles(root)
        assert info is not None
        assert [f.path for f in info.files] == [
            "a/Makefile",
            "b/makefile",
            "c/GNUmakefile",
        ]
        assert info.total_files == 3


def test_only_the_makefile_make_would_pick_is_used_per_directory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "GNUmakefile", "gnu:\n")
        write(root / "Makefile", "plain:\n")
        info = detect_makefiles(root)
        assert info is not None
        assert [(f.path, f.targets) for f in info.files] == [("GNUmakefile", ["gnu"])]


def test_build_and_dependency_directories_are_never_searched() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for skipped in (".venv", "target", "node_modules", ".git"):
            write(root / skipped / "vendored" / "Makefile", "all:\n")
        assert detect_makefiles(root) is None


def test_file_and_target_caps_keep_the_true_totals() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for i in range(30):
            write(root / f"d{i:02d}" / "Makefile", "all:\n")
        write(root / "Makefile", "".join(f"t{i}:\n" for i in range(150)))
        info = detect_makefiles(root)
        assert info is not None
        assert info.total_files == 31
        assert len(info.files) == 25
        top = info.files[0]
        assert top.path == "Makefile"
        assert top.total_targets == 150
        assert len(top.targets) == 100


def test_unreadable_or_undecodable_file_does_not_crash() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "Makefile").write_bytes(b"ok:\n\t\xff\xfe\nlater:\n")
        info = detect_makefiles(root)
        assert info is not None
        assert info.files[0].targets == ["ok", "later"]


def _data(root: Path, makefile: MakefileInfo | None) -> ReportData:
    return ReportData(
        project_root=root,
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        environment=EnvironmentInfo(),
        git=GitSnapshot(),
        stats=ProjectStats(),
        makefile=makefile,
    )


def _sample() -> MakefileInfo:
    return MakefileInfo(
        files=[
            MakefileEntry(
                path="Makefile",
                targets=["all", "clean"],
                phony=["clean"],
                default_target="all",
                total_targets=5,
            ),
            MakefileEntry(path="docs/Makefile"),
        ],
        total_files=3,
    )


def test_markdown_has_no_makefile_section_when_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = _data(Path(tmp), makefile=None)
        assert "## Makefile" not in markdown.render(data, include_source=False)


def test_markdown_renders_targets_phony_truncation_and_hidden_files() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        rendered = markdown.render(_data(Path(tmp), _sample()), include_source=False)
        assert "## Makefile" in rendered
        assert "### `Makefile`" in rendered
        assert "- **Default target:** `all`" in rendered
        assert "- **Targets (5):** `all`, `clean` (+3 more)" in rendered
        assert "- **Phony:** `clean`" in rendered
        assert "_No targets found._" in rendered
        assert "_1 more Makefile(s) not shown._" in rendered


def test_json_has_no_makefile_key_when_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        payload = json.loads(
            json_renderer.render(_data(Path(tmp), None), include_source=False)
        )
        assert "makefile" not in payload


def test_json_renders_makefile_key_when_present() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        payload = json.loads(
            json_renderer.render(_data(Path(tmp), _sample()), include_source=False)
        )
        assert payload["makefile"]["total_files"] == 3
        assert payload["makefile"]["files"][0] == {
            "path": "Makefile",
            "targets": ["all", "clean"],
            "phony": ["clean"],
            "default_target": "all",
            "total_targets": 5,
        }
