"""RC state: on-disk paths, load/save/validate, locking, and the
history log used for back/back-run navigation.

Extends the original scripts/paste_chunks.py state schema (bumped to
STATE_VERSION=4) with a `session_id` field for the RC protocol layer.
Adding `protocol_version` into config_fingerprint() means a future
protocol change auto-invalidates old state through the exact same
"config changed -- run with --reset" path that already existed for
BLOCK_SIZE/CHUNK_SIZE changes, instead of a second invalidation
mechanism.

state RC: مسیرهای روی دیسک، بارگذاری/ذخیره/اعتبارسنجی، قفل، و تاریخچه‌ی
استفاده‌شده برای ناوبری back/back-run.

طرح state اصلی scripts/paste_chunks.py را گسترش می‌دهد (به
STATE_VERSION=4 ارتقا یافته) با یک فیلد `session_id` برای لایه‌ی
پروتکل RC.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from . import chunker, protocol

DEFAULT_SOURCE_FILE = Path("README.md")
STATE_DIR = Path(".sarand-rc")

STATE_VERSION = 4  # bumped: added session_id for the RC protocol layer


def source_file(explicit: str | None) -> Path:
    """Resolve the source file: --source flag > SARAND_RC_SOURCE env > default."""
    if explicit:
        return Path(explicit).expanduser()
    configured = os.environ.get("SARAND_RC_SOURCE")
    return Path(configured).expanduser() if configured else DEFAULT_SOURCE_FILE


def _source_slug(path: Path) -> str:
    """Stable, filesystem-safe identifier for a source file's state.

    Namespacing state per source file (instead of one fixed state file)
    means switching which report you're pasting doesn't clobber
    progress on another one -- same pattern as sarand's own
    core/cache.py, which namespaces its cache per project.
    """
    resolved = str(path.expanduser().resolve())
    return hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:16]


class Paths:
    """Every on-disk path this run touches, resolved once from the source file."""

    def __init__(self, source: Path) -> None:
        slug = _source_slug(source)
        self.source = source
        self.state_file = STATE_DIR / f"{slug}.state.json"
        self.lock_file = STATE_DIR / f"{slug}.lock"
        self.chunk_dir = STATE_DIR / f"{slug}-chunks"


def config_fingerprint() -> str:
    payload = {
        "block_size": chunker.BLOCK_SIZE,
        "chunk_size": chunker.CHUNK_SIZE,
        "protocol_version": protocol.PROTOCOL_VERSION,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def default_state() -> dict[str, Any]:
    return {
        "state_version": STATE_VERSION,
        "next_block": 0,
        "current_block": None,
        "current_chunk": 0,
        "runs": 0,
        "history": [],
        "history_index": -1,
        "source_fingerprint": None,
        "session_id": None,
        "config_fingerprint": config_fingerprint(),
    }


def source_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        print(f"ERROR: unable to fingerprint source {path}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    return "sha256:" + digest.hexdigest()


def validate_state(state: dict[str, Any], lines: list[str] | None = None) -> None:
    if type(state) is not dict:
        raise ValueError("state must be a dict")

    required = {
        "state_version": int,
        "next_block": int,
        "current_chunk": int,
        "runs": int,
        "history": list,
        "history_index": int,
        "config_fingerprint": str,
    }
    for key, expected in required.items():
        if key not in state:
            raise ValueError(f"missing key: {key}")
        if type(state[key]) is not expected:
            raise ValueError(f"invalid type for {key}: {type(state[key]).__name__}")

    if state["state_version"] != STATE_VERSION:
        raise ValueError(
            f"unsupported state_version={state['state_version']} (expected {STATE_VERSION}) "
            "-- run with --reset to start fresh"
        )

    current_block = state.get("current_block")
    if current_block is not None and type(current_block) is not int:
        raise ValueError("current_block must be int or None")
    if current_block is not None and current_block < 0:
        raise ValueError("current_block must be >= 0")

    if state["next_block"] < 0:
        raise ValueError("next_block must be >= 0")
    if state["current_chunk"] < 0:
        raise ValueError("current_chunk must be >= 0")
    if state["runs"] < 0:
        raise ValueError("runs must be >= 0")

    if state["config_fingerprint"] != config_fingerprint():
        raise ValueError("collector configuration changed -- run with --reset")

    fingerprint = state.get("source_fingerprint")
    if fingerprint is not None and (type(fingerprint) is not str or not fingerprint):
        raise ValueError("source_fingerprint must be None or non-empty str")

    session_id = state.get("session_id")
    if session_id is not None and (type(session_id) is not str or not session_id):
        raise ValueError("session_id must be None or non-empty str")

    history = state["history"]
    history_index = state["history_index"]
    if history_index < -1:
        raise ValueError("history_index must be >= -1")
    if not history and history_index != -1:
        raise ValueError("history_index must be -1 when history is empty")
    if history and history_index >= len(history):
        raise ValueError("history_index out of range")

    for index, entry in enumerate(history):
        if type(entry) is not dict:
            raise ValueError(f"history[{index}] must be a dict")
        if "block" not in entry or "chunk" not in entry:
            raise ValueError(f"history[{index}] missing block/chunk")
        if type(entry["block"]) is not int or entry["block"] < 0:
            raise ValueError(f"history[{index}].block invalid")
        if type(entry["chunk"]) is not int or entry["chunk"] < 0:
            raise ValueError(f"history[{index}].chunk invalid")

    if lines is None:
        return

    blocks = chunker.total_blocks(len(lines))
    if state["next_block"] > blocks:
        raise ValueError(
            f"next_block={state['next_block']} exceeds total_blocks={blocks}"
        )
    if current_block is not None and current_block >= blocks:
        raise ValueError(f"current_block={current_block} exceeds total_blocks={blocks}")
    if current_block is not None:
        chunks = chunker.block_chunks(lines, current_block)
        if state["current_chunk"] >= len(chunks):
            raise ValueError(
                f"current_chunk={state['current_chunk']} exceeds available chunks={len(chunks)}"
            )


def load_state(paths: Paths, lines: list[str] | None = None) -> dict[str, Any]:
    if not paths.state_file.exists():
        return default_state()

    try:
        raw = paths.state_file.read_text(encoding="utf-8")
        state = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: invalid collector state: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if type(state) is not dict:
        print("ERROR: collector state must be a JSON object.", file=sys.stderr)
        raise SystemExit(1)

    state.setdefault("state_version", STATE_VERSION)
    state.setdefault("current_chunk", state.get("chunk", 0))
    state.setdefault("config_fingerprint", config_fingerprint())
    state.setdefault("source_fingerprint", None)
    state.setdefault("session_id", None)

    try:
        validate_state(state, lines)
    except ValueError as exc:
        print(f"ERROR: corrupted collector state: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    return state


def save_state(
    paths: Paths, state: dict[str, Any], lines: list[str] | None = None
) -> None:
    validate_state(state, lines)
    paths.state_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = paths.state_file.with_name(f"{paths.state_file.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        os.replace(temporary, paths.state_file)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        print(f"ERROR: unable to save collector state: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def acquire_lock(paths: Paths) -> Any:
    try:
        paths.lock_file.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = paths.lock_file.open("a+")
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_fd
    except (OSError, BlockingIOError) as exc:
        print(
            f"ERROR: another instance is running for this source file: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


def release_lock(lock_fd: Any) -> None:
    try:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
    finally:
        lock_fd.close()


def read_source(paths: Paths) -> list[str]:
    if not paths.source.is_file():
        print(f"ERROR: source file not found: {paths.source}", file=sys.stderr)
        raise SystemExit(1)
    try:
        with paths.source.open("r", encoding="utf-8", newline="") as handle:
            return handle.read().splitlines(keepends=True)
    except OSError as exc:
        print(f"ERROR: unable to read {paths.source}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def ensure_source_consistent(paths: Paths, state: dict[str, Any]) -> None:
    """Verify the source file hasn't changed since state was created."""
    fingerprint = source_fingerprint(paths.source)
    previous = state["source_fingerprint"]
    if previous is None:
        state["source_fingerprint"] = fingerprint
        return
    if previous != fingerprint:
        print(
            f"ERROR: source file changed since collector state was created.\n"
            f"Run '{Path(sys.argv[0]).name} --reset --source {paths.source}' before continuing.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def write_chunk(paths: Paths, block: int, chunk: int, content: str) -> Path:
    paths.chunk_dir.mkdir(parents=True, exist_ok=True)
    path = paths.chunk_dir / f"block-{block}-chunk-{chunk}.txt"
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        print(f"ERROR: unable to write chunk file: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    return path


def truncate_future_history(state: dict[str, Any]) -> None:
    index = state["history_index"]
    if index < 0:
        state["history"] = []
        state["history_index"] = -1
        return
    state["history"] = state["history"][: index + 1]


def append_history(state: dict[str, Any], block: int, chunk: int) -> None:
    truncate_future_history(state)
    state["history"].append({"block": block, "chunk": chunk})
    state["history_index"] = len(state["history"]) - 1
