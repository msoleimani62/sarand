"""Tests for the Markdown analyzer."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

import pytest
from _helpers import write
from sarand.analyzers.markdown_analyzer import MarkdownAnalyzer
from sarand.analyzers.registry import discover_analyzers, matching_analyzers


def test_markdown_analyzer_matches_on_top_level_md_file() -> None:
    analyzer = MarkdownAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        assert analyzer.matches(root) is False

        write(root / "README.md", "# Title\n")

        assert analyzer.matches(root) is True


def test_markdown_analyzer_does_not_match_nested_md_without_root_signal() -> None:
    analyzer = MarkdownAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "docs" / "guide.md", "# Guide\n")

        assert analyzer.matches(root) is False


def test_markdown_analyzer_matches_alongside_other_language_markers() -> None:
    """A README.md sits alongside a Cargo.toml in a normal repo --
    MarkdownAnalyzer complements the language analyzer, same shape as
    YamlAnalyzer matching pubspec.yaml alongside DartAnalyzer."""

    analyzer = MarkdownAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Cargo.toml", "[package]\nname='x'\n")
        write(root / "README.md", "# Title\n")

        assert analyzer.matches(root) is True


def test_markdown_analyzer_entry_points() -> None:
    analyzer = MarkdownAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "README.md", "# Title\n")
        write(root / "CHANGELOG.md", "# Changelog\n")

        assert analyzer.entry_points(root) == ["README.md", "CHANGELOG.md"]


def test_markdown_analyzer_run_tests_is_always_none() -> None:
    analyzer = MarkdownAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "README.md", "# Title\n")

        result = asyncio.run(analyzer.run_tests(root))

    assert result is None


def test_markdown_analyzer_run_quality_skips_cleanly_without_markdownlint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    analyzer = MarkdownAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "README.md", "# Title\n")

        results = asyncio.run(analyzer.run_quality(root))

    assert len(results) == 1
    assert results[0].kind == "markdownlint"
    assert results[0].skipped is True
    assert "not installed" in results[0].skip_reason


def test_markdown_analyzer_run_quality_runs_markdownlint_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sarand.analyzers.markdown_analyzer as markdown_analyzer_module

    captured_cmds: list[list[str]] = []

    async def fake_run_cmd_async(cmd, cwd, timeout):
        captured_cmds.append(cmd)
        return 0, "ok", 0.1

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(markdown_analyzer_module, "run_cmd_async", fake_run_cmd_async)
    analyzer = MarkdownAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "README.md", "# Title\n")

        results = asyncio.run(analyzer.run_quality(root))

    assert results[0].skipped is False
    assert captured_cmds == [["markdownlint", "README.md"]]


def test_markdown_analyzer_run_security_is_always_empty() -> None:
    analyzer = MarkdownAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "README.md", "# Title\n")

        results = asyncio.run(analyzer.run_security(root))

    assert results == []


def test_markdown_analyzer_in_discover_and_matching() -> None:
    analyzers = discover_analyzers()
    assert any(a.name == "Markdown" for a in analyzers)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "README.md", "# Title\n")

        matched = matching_analyzers(root, analyzers)

    assert any(a.name == "Markdown" for a in matched)


def test_markdown_analyzer_does_not_match_empty_tree() -> None:
    analyzer = MarkdownAnalyzer()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert analyzer.matches(root) is False
