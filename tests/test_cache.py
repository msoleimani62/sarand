"""Tests for sarand.core.cache (Phase E, opt-in --cache)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from sarand.core.cache import (
    build_cache_entries,
    load_cache,
    partition_cache_hits,
    reconstruct_secrets,
    reconstruct_todos,
    save_cache,
)
from sarand.models.results import SecretFinding, TodoItem


def _record(rel_path: str, content_hash: str | None) -> dict:
    return {
        "rel_path": rel_path,
        "size": 100,
        "is_symlink": False,
        "is_broken_symlink": False,
        "is_hidden": False,
        "is_binary": False,
        "is_executable": False,
        "extension": ".py",
        "total_lines": 5,
        "code_lines": 4,
        "comment_lines": 1,
        "blank_lines": 0,
        "content_hash": content_hash,
    }


def test_load_cache_returns_empty_when_no_file_exists() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = load_cache(Path(tmp), Path("/some/project"))
        assert result == {}


def test_save_then_load_round_trips() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        project_root = Path(tmp) / "proj"
        entries = {"a.py": {"hash": "abc123", "todos": [], "secrets": []}}

        save_cache(output_dir, project_root, entries)
        loaded = load_cache(output_dir, project_root)

        assert loaded == entries


def test_cache_lives_under_output_dir_not_project_dir() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp) / "out"
        project_root = Path(tmp) / "proj"
        save_cache(output_dir, project_root, {"a.py": {"hash": "x", "todos": [], "secrets": []}})

        # Nothing should have been written inside project_root.
        assert not project_root.exists()
        assert any(output_dir.rglob("*.json"))


def test_different_projects_get_different_cache_files() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        save_cache(output_dir, Path(tmp) / "proj-a", {"a.py": {"hash": "1", "todos": [], "secrets": []}})
        save_cache(output_dir, Path(tmp) / "proj-b", {"b.py": {"hash": "2", "todos": [], "secrets": []}})

        cache_a = load_cache(output_dir, Path(tmp) / "proj-a")
        cache_b = load_cache(output_dir, Path(tmp) / "proj-b")

        assert cache_a == {"a.py": {"hash": "1", "todos": [], "secrets": []}}
        assert cache_b == {"b.py": {"hash": "2", "todos": [], "secrets": []}}


def test_rules_fingerprint_change_invalidates_cache() -> None:
    """Simulate a future detection-rule change by writing a cache with
    a fake stale fingerprint -- it must be treated as empty."""
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        project_root = Path(tmp) / "proj"
        save_cache(output_dir, project_root, {"a.py": {"hash": "1", "todos": [], "secrets": []}})

        from sarand.core.cache import _cache_path

        path = _cache_path(output_dir, project_root)
        import json

        data = json.loads(path.read_text())
        data["rules_fingerprint"] = "deliberately-wrong"
        path.write_text(json.dumps(data))

        loaded = load_cache(output_dir, project_root)
        assert loaded == {}


def test_corrupt_cache_file_is_treated_as_empty() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        project_root = Path(tmp) / "proj"
        from sarand.core.cache import _cache_path

        path = _cache_path(output_dir, project_root)
        path.parent.mkdir(parents=True)
        path.write_text("{not valid json")

        assert load_cache(output_dir, project_root) == {}


def test_partition_cache_hits_matches_on_hash() -> None:
    records = [_record("a.py", "hash-a"), _record("b.py", "hash-b")]
    cache = {"a.py": {"hash": "hash-a", "todos": [], "secrets": []}}

    hits, changed = partition_cache_hits(records, cache)

    assert set(hits) == {"a.py"}
    assert changed == {"b.py"}


def test_partition_cache_hits_treats_changed_hash_as_a_miss() -> None:
    records = [_record("a.py", "new-hash")]
    cache = {"a.py": {"hash": "old-hash", "todos": [], "secrets": []}}

    hits, changed = partition_cache_hits(records, cache)

    assert hits == {}
    assert changed == {"a.py"}


def test_partition_cache_hits_never_caches_files_without_a_hash() -> None:
    """Binary files and large files have content_hash=None -- they must
    always be treated as 'changed' (i.e. always re-scanned)."""
    records = [_record("big.bin", None)]
    cache = {"big.bin": {"hash": None, "todos": [], "secrets": []}}

    hits, changed = partition_cache_hits(records, cache)

    assert hits == {}
    assert changed == {"big.bin"}


def test_build_cache_entries_only_includes_hashable_files() -> None:
    records = [_record("a.py", "hash-a"), _record("big.bin", None)]

    entries = build_cache_entries(records, todos=[], secret_findings=[])

    assert set(entries) == {"a.py"}


def test_build_cache_entries_attaches_findings_to_the_right_file() -> None:
    records = [_record("a.py", "hash-a"), _record("b.py", "hash-b")]
    todos = [TodoItem(path="a.py", line_number=3, kind="TODO", content="fix this")]
    secrets = [SecretFinding(path="b.py", line_number=1, pattern_name="AWS Access Key ID")]

    entries = build_cache_entries(records, todos, secrets)

    assert entries["a.py"]["todos"] == [{"path": "a.py", "line_number": 3, "kind": "TODO", "content": "fix this"}]
    assert entries["a.py"]["secrets"] == []
    assert entries["b.py"]["todos"] == []
    assert len(entries["b.py"]["secrets"]) == 1


def test_reconstruct_todos_rebuilds_typed_objects() -> None:
    cache_hits = {"a.py": {"hash": "x", "todos": [{"path": "a.py", "line_number": 2, "kind": "FIXME", "content": "x"}], "secrets": []}}

    todos = reconstruct_todos(cache_hits)

    assert len(todos) == 1
    assert isinstance(todos[0], TodoItem)
    assert todos[0].kind == "FIXME"


def test_reconstruct_secrets_rebuilds_typed_objects() -> None:
    cache_hits = {
        "a.py": {"hash": "x", "todos": [], "secrets": [{"path": "a.py", "line_number": 5, "pattern_name": "GitHub Token"}]}
    }

    findings = reconstruct_secrets(cache_hits)

    assert len(findings) == 1
    assert isinstance(findings[0], SecretFinding)
    assert findings[0].pattern_name == "GitHub Token"


def test_full_cache_round_trip_end_to_end() -> None:
    """Simulate two consecutive runs: first run populates the cache,
    second run (same files, same hashes) must reconstruct identical
    todos/secrets without re-scanning."""
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp) / "out"
        project_root = Path(tmp) / "proj"

        records = [_record("a.py", "hash-a")]
        todos = [TodoItem(path="a.py", line_number=1, kind="TODO", content="hello")]
        secrets: list[SecretFinding] = []

        entries = build_cache_entries(records, todos, secrets)
        save_cache(output_dir, project_root, entries)

        # "Next run": same records, load the cache back.
        cache = load_cache(output_dir, project_root)
        hits, changed = partition_cache_hits(records, cache)

        assert changed == set()
        assert set(hits) == {"a.py"}
        assert reconstruct_todos(hits) == todos
        assert reconstruct_secrets(hits) == secrets
