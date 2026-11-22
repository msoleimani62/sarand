"""Parity between the two scan engines (AGENTS.md 5.69).

The compiled Rust core and the pure-Python fallback must report the same files
for the same tree. Two bugs broke that: the Rust walker matched the ignore list
against *every component of the absolute path* (a project living under `build/`
lost all its files), and the Python fallback dropped every directory whose name
starts with `.git` (including `.github/`). The fallback also stored `rel_path`
with the platform separator, unlike Rust.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sarand import rust_bridge
from sarand.constants import HASH_MAX_BYTES, IGNORE_DIRS, MAX_HASH_FILES

_EXPECTED = {
    ".github/workflows/ci.yml",
    "README.md",
    "dist",  # a FILE named like an ignored directory is kept
    "src/a.py",
}


def _make_project(root: Path) -> None:
    files = [
        ".github/workflows/ci.yml",
        "README.md",
        "dist",
        "src/a.py",
        "src/build/gen.py",  # inside an ignored directory: pruned
        "node_modules/pkg/index.js",  # ignored directory: pruned
    ]
    for rel in files:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x = 1\n", encoding="utf-8")


def _fallback_paths(root: Path) -> set[str]:
    records = rust_bridge._pure_python_scan(
        root, IGNORE_DIRS, HASH_MAX_BYTES, MAX_HASH_FILES
    )
    return {record["rel_path"] for record in records}


def test_fallback_keeps_dot_github_and_prunes_only_ignored_directories(
    tmp_path: Path,
) -> None:
    _make_project(tmp_path)
    assert _fallback_paths(tmp_path) == _EXPECTED


def test_fallback_uses_posix_relative_paths(tmp_path: Path) -> None:
    _make_project(tmp_path)
    assert all("\\" not in path for path in _fallback_paths(tmp_path))


def test_fallback_scans_a_project_that_lives_under_an_ignored_name(
    tmp_path: Path,
) -> None:
    root = tmp_path / "build" / "proj"
    _make_project(root)
    assert _fallback_paths(root) == _EXPECTED


def test_rust_core_and_fallback_return_the_same_files(tmp_path: Path) -> None:
    if not rust_bridge.RUST_CORE_AVAILABLE:
        pytest.skip("compiled Rust core is not available in this environment")
    for base in (tmp_path / "plain", tmp_path / "build" / "dist" / "proj"):
        _make_project(base)
        rust = {record["rel_path"] for record in rust_bridge.scan_project(base)}
        assert rust == _fallback_paths(base) == _EXPECTED, base


def test_fallback_applies_gitignore_patterns_and_negation(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("*.log\n!keep.log\nbuild/\n", encoding="utf-8")
    for rel in ("drop.log", "keep.log", "build/generated.py", "src/main.py"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x = 1\n", encoding="utf-8")

    assert _fallback_paths(tmp_path) == {
        ".gitignore",
        "keep.log",
        "src/main.py",
    }


def test_fallback_applies_nested_ignore_files_and_parent_rules(tmp_path: Path) -> None:
    project = tmp_path / "workspace" / "project"
    project.mkdir(parents=True)
    (tmp_path / "workspace" / ".gitignore").write_text(
        "parent.secret\n", encoding="utf-8"
    )
    (project / ".gitignore").write_text("*.tmp\n", encoding="utf-8")
    (project / "src").mkdir()
    (project / "src" / ".ignore").write_text("!keep.tmp\n", encoding="utf-8")

    for rel in ("parent.secret", "drop.tmp", "src/keep.tmp", "src/drop.tmp", "main.py"):
        path = project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x = 1\n", encoding="utf-8")

    assert _fallback_paths(project) == {
        ".gitignore",
        "main.py",
        "src/.ignore",
        "src/keep.tmp",
    }


def test_fallback_reads_repository_info_exclude(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git"
    (git_dir / "info").mkdir(parents=True)
    (git_dir / "info" / "exclude").write_text("local-only.txt\n", encoding="utf-8")
    (tmp_path / "local-only.txt").write_text("secret-ish\n", encoding="utf-8")
    (tmp_path / "tracked.py").write_text("x = 1\n", encoding="utf-8")

    assert _fallback_paths(tmp_path) == {"tracked.py"}


def test_fallback_hash_selection_is_stable_and_lexicographic(tmp_path: Path) -> None:
    for rel in ("z.py", "a.py", "m.py"):
        (tmp_path / rel).write_text(f"value = {rel!r}\n", encoding="utf-8")

    records = rust_bridge._pure_python_scan(tmp_path, IGNORE_DIRS, HASH_MAX_BYTES, 2)
    hashes = {record["rel_path"] for record in records if record["content_hash"]}

    assert hashes == {"a.py", "m.py"}


def test_fallback_hash_failure_consumes_file_quota(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "a.py"
    second = tmp_path / "b.py"
    first.write_text("a = 1\n", encoding="utf-8")
    second.write_text("b = 1\n", encoding="utf-8")

    original_read_bytes = Path.read_bytes

    def fail_first_read(path: Path) -> bytes:
        if path.resolve() == first.resolve():
            raise OSError("simulated hash read failure")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fail_first_read)

    problems = rust_bridge.ScanProblems()
    records = rust_bridge._pure_python_scan(
        tmp_path,
        IGNORE_DIRS,
        HASH_MAX_BYTES,
        1,
        problems=problems,
    )
    by_path = {record["rel_path"]: record for record in records}

    assert by_path["a.py"]["content_hash"] is None
    assert by_path["b.py"]["content_hash"] is None
    assert problems.skipped == 1
    assert problems.samples[0].startswith("a.py:")


def test_fallback_hashes_only_non_empty_files_within_size_limit(
    tmp_path: Path,
) -> None:
    (tmp_path / "empty.txt").write_bytes(b"")
    (tmp_path / "exact.txt").write_bytes(b"abcd")
    (tmp_path / "above.txt").write_bytes(b"abcde")

    fallback = rust_bridge._pure_python_scan(tmp_path, IGNORE_DIRS, 4, 5000)
    by_path = {record["rel_path"]: record for record in fallback}

    assert by_path["empty.txt"]["content_hash"] is None
    assert by_path["exact.txt"]["content_hash"] == (
        "88d4266fd4e6338d13b845fcf289579d209c897823b9217da3e161936f031589"
    )
    assert by_path["above.txt"]["content_hash"] is None

    if rust_bridge.RUST_CORE_AVAILABLE:
        native = rust_bridge.scan_project(
            tmp_path,
            hash_max_bytes=4,
            max_hash_files=5000,
        )
        native_by_path = {record["rel_path"]: record for record in native}

        assert {
            path: record["content_hash"]
            for path, record in native_by_path.items()
            if path in {"empty.txt", "exact.txt", "above.txt"}
        } == {path: record["content_hash"] for path, record in by_path.items()}


def test_rust_and_python_match_complex_ignore_precedence(
    tmp_path: Path,
) -> None:
    if not rust_bridge.RUST_CORE_AVAILABLE:
        pytest.skip("compiled Rust core is not available")

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    root = workspace / "project"
    root.mkdir()

    def write(rel: str, content: str = "x = 1\n") -> None:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    (workspace / ".gitignore").write_text(
        "*.secret\n",
        encoding="utf-8",
    )
    (workspace / ".ignore").write_text(
        "*.cache\n",
        encoding="utf-8",
    )

    git_info = workspace / ".git" / "info"
    git_info.mkdir(parents=True)
    (git_info / "exclude").write_text(
        "exclude-only.txt\nexclude-overridden.txt\n",
        encoding="utf-8",
    )

    write(
        ".gitignore",
        "*.log\n"
        "!keep.log\n"
        "conflict.txt\n"
        "!exclude-overridden.txt\n"
        "!ignore-wins.txt\n"
        "build/\n"
        "blocked/\n"
        "!blocked/keep.py\n",
    )
    write(
        ".ignore",
        "private.txt\n!conflict.txt\nignore-wins.txt\n",
    )
    write("src/.gitignore", "!keep.secret\n")
    write("src/.ignore", "!keep.cache\n")

    for rel in (
        "drop.log",
        "keep.log",
        "conflict.txt",
        "private.txt",
        "ignore-wins.txt",
        "exclude-only.txt",
        "exclude-overridden.txt",
        "local.secret",
        "local.cache",
        "build/generated.py",
        "blocked/keep.py",
        "src/keep.secret",
        "src/drop.secret",
        "src/keep.cache",
        "src/drop.cache",
        "src/main.py",
    ):
        write(rel)

    rust_paths = {record["rel_path"] for record in rust_bridge.scan_project(root)}
    python_paths = _fallback_paths(root)

    expected = {
        ".gitignore",
        ".ignore",
        "conflict.txt",
        "exclude-overridden.txt",
        "keep.log",
        "src/.gitignore",
        "src/.ignore",
        "src/keep.secret",
        "src/keep.cache",
        "src/main.py",
    }

    assert rust_paths == python_paths
    assert rust_paths == expected


def test_rust_and_python_match_linked_worktree_info_exclude(
    tmp_path: Path,
) -> None:
    if not rust_bridge.RUST_CORE_AVAILABLE:
        pytest.skip("compiled Rust core is not available")

    common_git_dir = tmp_path / "repository" / ".git"
    info_dir = common_git_dir / "info"
    worktrees_dir = common_git_dir / "worktrees"
    info_dir.mkdir(parents=True)

    (info_dir / "exclude").write_text(
        "project/excluded.local\n",
        encoding="utf-8",
    )

    for name, commondir in (
        ("relative", "../.."),
        ("absolute", str(common_git_dir)),
    ):
        git_dir = worktrees_dir / name
        git_dir.mkdir(parents=True)

        (git_dir / "commondir").write_text(
            commondir + "\n",
            encoding="utf-8",
        )

        worktree = tmp_path / f"worktree-{name}"
        worktree.mkdir()

        (worktree / ".git").write_text(
            f"gitdir: {git_dir}\n",
            encoding="utf-8",
        )
        (worktree / ".gitignore").write_text(
            "parent.secret\n",
            encoding="utf-8",
        )

        root = worktree / "project"
        root.mkdir()

        for rel in ("excluded.local", "parent.secret", "keep.py"):
            (root / rel).write_text("content\n", encoding="utf-8")

        rust_paths = {record["rel_path"] for record in rust_bridge.scan_project(root)}
        python_paths = _fallback_paths(root)

        assert rust_paths == python_paths, name
        assert rust_paths == {"keep.py"}, name
