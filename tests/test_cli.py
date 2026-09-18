"""Tests for sarand CLI cache controls and cache-aware execution."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from sarand import cli
from sarand.core.cache import _cache_path, save_cache


async def _no_git_snapshot(root: Path) -> None:
    # collect_git_snapshot is async (see scanners/git.py); a plain sync
    # lambda returning None here would make `await collect_git_snapshot(root)`
    # in cli.run() raise TypeError (can't await None) -- this stays an
    # actual coroutine function so the real await still works.
    #
    # collect_git_snapshot اکنون async است؛ یک lambda سینک ساده که None
    # برمی‌گرداند باعث می‌شد `await collect_git_snapshot(root)` در
    # cli.run() خطای TypeError بدهد (نمی‌شود None را await کرد) -- این
    # همچنان یک coroutine function واقعی است تا await واقعی درست کار کند.
    return None


def test_parser_accepts_cache_flags() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(["--cache"])
    assert args.cache is True
    assert args.clear_cache is False

    args = parser.parse_args(["--clear-cache"])
    assert args.cache is False
    assert args.clear_cache is True


def test_clear_cache_removes_existing_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_root = tmp_path / "project"
    output_dir = tmp_path / "output"
    project_root.mkdir()

    save_cache(
        output_dir,
        project_root,
        {"a.py": {"hash": "hash-a", "todos": [], "secrets": []}},
    )

    cache_file = _cache_path(output_dir, project_root)
    assert cache_file.exists()

    monkeypatch.chdir(project_root)

    result = cli.main(
        [
            "--project",
            str(project_root),
            "--output-dir",
            str(output_dir),
            "--clear-cache",
        ]
    )

    captured = capsys.readouterr()

    assert result == 0
    assert not cache_file.exists()
    assert "Cleared cache:" in captured.err


def test_clear_cache_succeeds_when_cache_does_not_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_root = tmp_path / "project"
    output_dir = tmp_path / "output"
    project_root.mkdir()

    monkeypatch.chdir(project_root)

    result = cli.main(
        [
            "--project",
            str(project_root),
            "--output-dir",
            str(output_dir),
            "--clear-cache",
        ]
    )

    captured = capsys.readouterr()

    assert result == 0
    assert "No cache found at" in captured.err


def test_run_uses_cache_hits_for_todos_and_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    output_dir = tmp_path / "output"
    project_root.mkdir()

    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "--project",
            str(project_root),
            "--output-dir",
            str(output_dir),
            "--cache",
            "--skip-tests",
            "--no-health",
            "--no-source",
        ]
    )
    config = cli.SarandConfig.from_args(args)

    records = [
        {
            "rel_path": "a.py",
            "size": 10,
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
            "content_hash": "stable-hash",
        }
    ]

    todo = SimpleNamespace(
        path="a.py",
        line_number=1,
        kind="TODO",
        content="cached todo",
    )
    secret = SimpleNamespace(
        path="a.py",
        line_number=1,
        pattern_name="GitHub Token",
    )

    monkeypatch.setattr(cli, "scan_project", lambda root: records)
    monkeypatch.setattr(cli, "build_tree_text", lambda *args, **kwargs: "")
    monkeypatch.setattr(
        cli,
        "collect_essential_files",
        lambda *args, **kwargs: ([project_root / "a.py"], [], []),
    )
    monkeypatch.setattr(
        cli,
        "collect_project_stats",
        lambda *args, **kwargs: SimpleNamespace(
            temporary_files=[],
            unused_cache_files=[],
        ),
    )
    monkeypatch.setattr(
        cli,
        "detect_project",
        lambda root: SimpleNamespace(
            is_recognized=False,
            languages=[],
            build_system="unknown",
        ),
    )
    monkeypatch.setattr(cli, "collect_environment_info", lambda root: None)
    monkeypatch.setattr(cli, "collect_git_snapshot", _no_git_snapshot)
    monkeypatch.setattr(cli, "discover_analyzers", list)
    monkeypatch.setattr(cli, "matching_analyzers", lambda root, analyzers: [])
    monkeypatch.setattr(
        cli,
        "scan_todos",
        lambda *args, **kwargs: pytest.fail(
            "TODO scanner must not run when all files are cache hits"
        ),
    )
    monkeypatch.setattr(
        cli,
        "scan_for_secrets",
        lambda *args, **kwargs: pytest.fail(
            "Secret scanner must not run when all files are cache hits"
        ),
    )
    monkeypatch.setattr(cli, "generate_ai_summary", lambda data: None)
    monkeypatch.setattr(
        cli,
        "suggest_reading_order",
        lambda root, included: [],
    )
    monkeypatch.setattr(cli, "remove_previous_report", lambda path: None)
    monkeypatch.setattr(cli, "write_sha256", lambda path: "test-digest")
    monkeypatch.setattr(
        cli,
        "_RENDERERS",
        {
            "markdown": SimpleNamespace(
                render=lambda data, include_source=False, full_output=False: "report"
            )
        },
    )

    save_cache(
        output_dir,
        project_root,
        {
            "a.py": {
                "hash": "stable-hash",
                "todos": [todo.__dict__],
                "secrets": [secret.__dict__],
            }
        },
    )

    result = asyncio.run(cli.run(config))

    assert result == 0


def test_run_scans_changed_files_with_cache_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    output_dir = tmp_path / "output"
    project_root.mkdir()

    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "--project",
            str(project_root),
            "--output-dir",
            str(output_dir),
            "--cache",
            "--skip-tests",
            "--no-health",
            "--no-source",
        ]
    )
    config = cli.SarandConfig.from_args(args)

    records = [
        {
            "rel_path": "a.py",
            "size": 10,
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
            "content_hash": "new-hash",
        }
    ]

    scan_calls: list[set[str] | None] = []

    monkeypatch.setattr(cli, "scan_project", lambda root: records)
    monkeypatch.setattr(cli, "build_tree_text", lambda *args, **kwargs: "")
    monkeypatch.setattr(
        cli,
        "collect_essential_files",
        lambda *args, **kwargs: ([project_root / "a.py"], [], []),
    )
    monkeypatch.setattr(
        cli,
        "collect_project_stats",
        lambda *args, **kwargs: SimpleNamespace(
            temporary_files=[],
            unused_cache_files=[],
        ),
    )
    monkeypatch.setattr(
        cli,
        "detect_project",
        lambda root: SimpleNamespace(
            is_recognized=False,
            languages=[],
            build_system="unknown",
        ),
    )
    monkeypatch.setattr(cli, "collect_environment_info", lambda root: None)
    monkeypatch.setattr(cli, "collect_git_snapshot", _no_git_snapshot)
    monkeypatch.setattr(cli, "discover_analyzers", list)
    monkeypatch.setattr(cli, "matching_analyzers", lambda root, analyzers: [])

    def fake_scan_todos(*args: object, **kwargs: object) -> list[object]:
        only = kwargs.get("only")
        scan_calls.append(only if isinstance(only, set) else None)
        return []

    monkeypatch.setattr(cli, "scan_todos", fake_scan_todos)
    monkeypatch.setattr(cli, "scan_for_secrets", lambda *args, **kwargs: [])
    monkeypatch.setattr(cli, "generate_ai_summary", lambda data: None)
    monkeypatch.setattr(
        cli,
        "suggest_reading_order",
        lambda root, included: [],
    )
    monkeypatch.setattr(cli, "remove_previous_report", lambda path: None)
    monkeypatch.setattr(cli, "write_sha256", lambda path: "test-digest")
    monkeypatch.setattr(
        cli,
        "_RENDERERS",
        {
            "markdown": SimpleNamespace(
                render=lambda data, include_source=False, full_output=False: "report"
            )
        },
    )

    save_cache(
        output_dir,
        project_root,
        {
            "a.py": {
                "hash": "old-hash",
                "todos": [],
                "secrets": [],
            }
        },
    )

    result = asyncio.run(cli.run(config))

    assert result == 0
    assert scan_calls == [{"a.py"}]
