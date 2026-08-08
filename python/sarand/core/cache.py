"""Incremental-scan cache (AGENTS.md Phase E) -- opt-in via --cache.

Scope, deliberately: this lets sarand skip re-scanning file *content*
for TODOs and secrets when a file's hash hasn't changed since the last
run against the same project (and the detection rules themselves
haven't changed either -- see `_rules_fingerprint`). It does NOT change
how the Rust walker works -- walker.rs still hashes/counts every file
on every run, since teaching it to consult a cache map is a more
invasive Rust change that can't be compile-verified without a local
toolchain (AGENTS.md §4.8). This phase stays on the Python side of
`rust_bridge.py`'s boundary and reuses the `content_hash` Rust/the
fallback already compute for free.

Opt-in, not default: a stale-cache bug's failure mode is a silently
wrong report (a real TODO or secret finding not shown because the
cache claimed "unchanged"), which is exactly the kind of regression
AGENTS.md §4.8 exists to prevent. The safe direction to fail is doing
more work than necessary, not less -- same reasoning as the
`slow_external` pytest marker being opt-in-to-skip rather than
opt-in-to-run.

محدوده‌ی این کش، عمداً: به sarand اجازه می‌دهد اسکن *محتوای* فایل برای
TODO و secret را وقتی هش فایل از اجرای قبلی روی همان پروژه (و
قوانین تشخیص) تغییر نکرده، رد کند. تغییری در کار خودِ واکر Rust
نمی‌دهد. اختیاری است، نه پیش‌فرض: مسیر شکستِ یک باگ کش قدیمی، یک
گزارش بی‌صدا نادرست است -- دقیقاً همان کلاس ریگرشنی که §4.8 برای
جلوگیری از آن وجود دارد.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from sarand.constants import SECRET_FILENAME_PATTERNS, TODO_PATTERNS
from sarand.core.secrets import content_pattern_names
from sarand.models.results import SecretFinding, TodoItem
from sarand.rust_bridge import FileRecord
from sarand.utils.fs import slugify_project_name
from sarand.utils.logging import get_logger

logger = get_logger("cache")

_CACHE_SUBDIR = ".sarand-cache"
_CACHE_VERSION = 1


def _rules_fingerprint() -> str:
    """Hash of every pattern that affects TODO/secret detection.

    If a future phase adds a new secret pattern or TODO keyword, this
    fingerprint changes, and every existing cache is treated as stale
    automatically -- a cache must never silently miss a finding that a
    rule change would have caught in unchanged files.

    اگر یک فاز آینده الگوی secret یا کلیدواژه‌ی TODO جدیدی اضافه کند،
    این fingerprint تغییر می‌کند و هر کش موجود به‌صورت خودکار منقضی
    تلقی می‌شود -- یک کش هرگز نباید بی‌صدا یافته‌ای را که تغییر یک
    قانون در فایل‌های بدون‌تغییر پیدا می‌کرد، از قلم بیندازد.
    """
    parts = sorted(TODO_PATTERNS) + sorted(SECRET_FILENAME_PATTERNS) + sorted(content_pattern_names())
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _cache_path(output_dir: Path, project_root: Path) -> Path:
    """Cache lives under the *output* dir, never inside the scanned
    project, namespaced per project (a persisted/shared output dir can
    hold caches for multiple projects without collisions)."""
    slug = slugify_project_name(project_root.name)
    path_hash = hashlib.sha256(str(project_root.resolve()).encode()).hexdigest()[:10]
    return output_dir / _CACHE_SUBDIR / f"{slug}-{path_hash}.json"


def load_cache(output_dir: Path, project_root: Path) -> dict[str, dict[str, Any]]:
    """Load the previous run's cache. Never raises, and treats a stale
    rules fingerprint or a missing/corrupt file as an empty cache --
    both simply mean "do a full scan," same as a first run."""
    path = _cache_path(output_dir, project_root)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if data.get("version") != _CACHE_VERSION or data.get("rules_fingerprint") != _rules_fingerprint():
        logger.info("Cache invalidated (version or detection rules changed)")
        return {}
    return data.get("files", {})


def save_cache(output_dir: Path, project_root: Path, files: dict[str, dict[str, Any]]) -> None:
    """Persist this run's per-file hash + TODO/secret findings."""
    path = _cache_path(output_dir, project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": _CACHE_VERSION, "rules_fingerprint": _rules_fingerprint(), "files": files}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def partition_cache_hits(
    records: list[FileRecord],
    cache: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    """Split this run's files into cache hits vs. needs-a-real-scan.

    A file is a cache hit only if it has a usable content hash (large
    files and binaries never get one -- they always need a real scan)
    AND that hash matches what's stored from last time.

    Returns:
        (cache_hits: rel_path -> stored entry, changed_or_new: set of
        rel_paths that must be scanned for real this run)
    """
    hits: dict[str, dict[str, Any]] = {}
    changed: set[str] = set()
    for rec in records:
        rel_path = rec["rel_path"]
        current_hash = rec.get("content_hash")
        cached_entry = cache.get(rel_path)
        if current_hash and cached_entry and cached_entry.get("hash") == current_hash:
            hits[rel_path] = cached_entry
        else:
            changed.add(rel_path)
    return hits, changed


def reconstruct_todos(cache_hits: dict[str, dict[str, Any]]) -> list[TodoItem]:
    return [TodoItem(**item) for entry in cache_hits.values() for item in entry.get("todos", [])]


def reconstruct_secrets(cache_hits: dict[str, dict[str, Any]]) -> list[SecretFinding]:
    return [SecretFinding(**item) for entry in cache_hits.values() for item in entry.get("secrets", [])]


def build_cache_entries(
    records: list[FileRecord],
    todos: list[TodoItem],
    secret_findings: list[SecretFinding],
) -> dict[str, dict[str, Any]]:
    """Build the cache payload to save for next run, from this run's results."""
    todos_by_path: dict[str, list[TodoItem]] = defaultdict(list)
    for t in todos:
        todos_by_path[t.path].append(t)
    secrets_by_path: dict[str, list[SecretFinding]] = defaultdict(list)
    for f in secret_findings:
        secrets_by_path[f.path].append(f)

    entries: dict[str, dict[str, Any]] = {}
    for rec in records:
        content_hash = rec.get("content_hash")
        if not content_hash:
            continue  # can't fingerprint this file -- never cache it
        rel_path = rec["rel_path"]
        entries[rel_path] = {
            "hash": content_hash,
            "todos": [t.__dict__ for t in todos_by_path.get(rel_path, [])],
            "secrets": [f.__dict__ for f in secrets_by_path.get(rel_path, [])],
        }
    return entries
