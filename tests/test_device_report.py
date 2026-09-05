"""Tests for the device_report subsystem (ported from device-audit.sh)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sarand.device_report.classify import (
    DO_NOT_DELETE_AUTOMATICALLY,
    LIKELY_RECLAIMABLE,
    REQUIRES_REVIEW,
    SAFE_TO_REVIEW,
    SYSTEM_CRITICAL,
    classify_path,
)
from sarand.device_report.config import UNLIMITED, build_parser, resolve_config
from sarand.device_report.walking import (
    find_dirs_named,
    is_excluded,
    path_size_bytes,
    sha256_file,
    walk_pruned,
)

# --- classify_path -----------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/home/user/.cache/pip", LIKELY_RECLAIMABLE),
        ("/home/user/project/node_modules/x", LIKELY_RECLAIMABLE),
        ("/home/user/project/target/debug", LIKELY_RECLAIMABLE),
        ("/home/user/.cargo/registry/src", SAFE_TO_REVIEW),
        ("/home/user/.cargo/git/checkouts", SAFE_TO_REVIEW),
        ("/home/user/Downloads", SAFE_TO_REVIEW),
        ("/home/user/project/.git", DO_NOT_DELETE_AUTOMATICALLY),
        ("/home/user/project/.git/objects/ab", DO_NOT_DELETE_AUTOMATICALLY),
        ("/system/bin/sh", SYSTEM_CRITICAL),
        ("/data/app/com.foo", SYSTEM_CRITICAL),
        ("/data/misc/wifi", SYSTEM_CRITICAL),
        ("/home/user/random/stuff", REQUIRES_REVIEW),
    ],
)
def test_classify_path(path: str, expected: str) -> None:
    assert classify_path(path) == expected


# --- config: --full / --quick / --top interaction --------------------------


def test_full_overrides_quick_and_removes_top_cap() -> None:
    parser = build_parser()
    args = parser.parse_args(["--quick", "--full", "-r", "/tmp"])
    config = resolve_config(args)
    assert config.quick_mode is False
    assert config.top_n == UNLIMITED


def test_explicit_top_beats_full() -> None:
    parser = build_parser()
    args = parser.parse_args(["--full", "--top", "5", "-r", "/tmp"])
    config = resolve_config(args)
    assert config.top_n == 5


def test_plain_quick_without_full() -> None:
    parser = build_parser()
    args = parser.parse_args(["--quick", "-r", "/tmp"])
    config = resolve_config(args)
    assert config.quick_mode is True


def test_missing_scan_root_raises() -> None:
    parser = build_parser()
    args = parser.parse_args(["-r", "/this/path/does/not/exist/xyz"])
    with pytest.raises(ValueError, match="No valid scan roots"):
        resolve_config(args)


def test_default_top_n_when_neither_full_nor_explicit() -> None:
    parser = build_parser()
    args = parser.parse_args(["-r", "/tmp"])
    config = resolve_config(args)
    assert config.top_n == 30


# --- walking: portable primitives -------------------------------------


def test_path_size_bytes_file(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_bytes(b"hello world")
    assert path_size_bytes(f) == 11


def test_path_size_bytes_directory_sums_children(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_bytes(b"12345")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_bytes(b"1234567890")
    assert path_size_bytes(tmp_path) == 15


def test_path_size_bytes_missing_path_is_zero(tmp_path: Path) -> None:
    assert path_size_bytes(tmp_path / "does-not-exist") == 0


def test_sha256_file_matches_known_hash(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_bytes(b"")
    # SHA-256 of the empty string, a well-known constant value.
    assert (
        sha256_file(f)
        == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"[:64]
    )


def test_sha256_file_missing_path_returns_none(tmp_path: Path) -> None:
    assert sha256_file(tmp_path / "does-not-exist") is None


def test_is_excluded_matches_exact_and_children() -> None:
    assert is_excluded(Path("/a/b"), ["/a/b"]) is True
    assert is_excluded(Path("/a/b/c"), ["/a/b"]) is True
    assert is_excluded(Path("/a/bc"), ["/a/b"]) is False
    assert is_excluded(Path("/a/other"), ["/a/b"]) is False


def test_walk_pruned_respects_max_depth(tmp_path: Path) -> None:
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (tmp_path / "a" / "shallow.txt").write_text("x")
    (deep / "deepfile.txt").write_text("x")

    shallow_files = {
        name
        for _root, _dirs, files in walk_pruned(tmp_path, max_depth=2)
        for name in files
    }
    assert "shallow.txt" in shallow_files
    assert "deepfile.txt" not in shallow_files

    all_files = {
        name
        for _root, _dirs, files in walk_pruned(tmp_path, max_depth=0)
        for name in files
    }
    assert "deepfile.txt" in all_files


def test_walk_pruned_respects_excludes(tmp_path: Path) -> None:
    excluded_dir = tmp_path / "skip_me"
    excluded_dir.mkdir()
    (excluded_dir / "secret.txt").write_text("x")
    (tmp_path / "keep.txt").write_text("x")

    seen_files = {
        name
        for _root, _dirs, files in walk_pruned(
            tmp_path, exclude_paths=[str(excluded_dir)]
        )
        for name in files
    }
    assert "keep.txt" in seen_files
    assert "secret.txt" not in seen_files


def test_find_dirs_named_prunes_matched_subtree(tmp_path: Path) -> None:
    nm = tmp_path / "project" / "node_modules"
    nm.mkdir(parents=True)
    (nm / "nested_pkg").mkdir()
    (nm / "nested_pkg" / "node_modules").mkdir()

    found = list(find_dirs_named(tmp_path, {"node_modules"}))
    # Only the outer node_modules should be reported -- its own subtree
    # (including the nested node_modules inside it) must be pruned.
    assert found == [nm]


# --- environment: run_tool_checked (present-but-broken binaries) ----------


def test_run_tool_checked_treats_nonzero_exit_as_not_ok(tmp_path: Path) -> None:
    # Regression test: lscpu is commonly installed but still exits
    # non-zero under a Termux/Kali proot (confirmed live on-device --
    # `/sys/devices/system/cpu/possible` isn't reachable there). A
    # present-but-failing binary must be treated the same as a missing
    # one so callers fall back to their portable /proc reader instead
    # of printing the raw error text into the report.
    from sarand.device_report import environment as env

    ok, _output = env.run_tool_checked(tmp_path, "false")
    assert ok is False


def test_run_tool_checked_treats_zero_exit_with_output_as_ok(tmp_path: Path) -> None:
    from sarand.device_report import environment as env

    ok, output = env.run_tool_checked(tmp_path, "echo", "hello")
    assert ok is True
    assert "hello" in output


def test_run_tool_checked_missing_binary_is_not_ok(tmp_path: Path) -> None:
    from sarand.device_report import environment as env

    ok, _output = env.run_tool_checked(tmp_path, "this-binary-does-not-exist-xyz")
    assert ok is False
