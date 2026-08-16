"""Tests for SARAND RC state locking.

Tests for cross-platform SARAND RC state locking.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sarand.rc import state


def test_acquire_lock_creates_and_releases_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    source = tmp_path / "README.md"
    source.write_text("alpha\n", encoding="utf-8")

    paths = state.Paths(source)

    lock = state.acquire_lock(paths)

    try:
        assert paths.lock_file.exists()
        assert lock.is_locked
    finally:
        state.release_lock(lock)

    assert not lock.is_locked


def test_acquire_lock_rejects_contention(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    source = tmp_path / "README.md"
    source.write_text("alpha\n", encoding="utf-8")

    paths = state.Paths(source)
    first = state.acquire_lock(paths)

    try:
        with pytest.raises(SystemExit) as exc_info:
            state.acquire_lock(paths)

        assert exc_info.value.code == 1
        assert first.is_locked
    finally:
        state.release_lock(first)


def test_lock_can_be_reacquired_after_release(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    source = tmp_path / "README.md"
    source.write_text("alpha\n", encoding="utf-8")

    paths = state.Paths(source)

    first = state.acquire_lock(paths)
    state.release_lock(first)

    second = state.acquire_lock(paths)

    try:
        assert second.is_locked
    finally:
        state.release_lock(second)


def test_different_sources_use_different_lock_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    first_source = tmp_path / "first.md"
    second_source = tmp_path / "second.md"

    first_source.write_text("first\n", encoding="utf-8")
    second_source.write_text("second\n", encoding="utf-8")

    first_paths = state.Paths(first_source)
    second_paths = state.Paths(second_source)

    assert first_paths.lock_file != second_paths.lock_file

    first_lock = state.acquire_lock(first_paths)
    second_lock = state.acquire_lock(second_paths)

    try:
        assert first_lock.is_locked
        assert second_lock.is_locked
    finally:
        state.release_lock(second_lock)
        state.release_lock(first_lock)
