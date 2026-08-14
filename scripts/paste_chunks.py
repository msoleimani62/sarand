#!/usr/bin/env python3
"""Chunked-paste helper for chat UIs that don't accept file uploads.

Splits any text file (typically a sarand-generated report) into
sequential, size-bounded chunks and "emits" one chunk per invocation:
prints it, writes it to a file, and copies it to the clipboard if a
supported clipboard tool is available -- so you can paste each chunk
into a chat one at a time, with resumable state across invocations
(next/back/history/jump-to-block).

Originally written against a hardcoded README.md and BiMarz-specific
naming; generalized here to work on any file (sarand report or
otherwise) and fixed three real bugs found on review:

1. Dead code: `ensure_source_consistent(initialize=True)` was never
   actually called with `initialize=True` anywhere -- both branches of
   that parameter did the same thing. Removed the unused parameter.
2. Fragile rollback: `emit_block`'s failure-rollback used a *shallow*
   `dict(state)` copy, so `old_state["history"]` aliased the same list
   object as `state["history"]` -- only correct because a separate
   `old_history` variable happened to be kept too. Replaced with
   `copy.deepcopy(state)`, which is correct regardless of what mutable
   fields state gains in the future.
3. UX trap: if a block has multiple chunks and you run this with no
   flags (instead of `-c N+1`) before finishing them, the old version
   silently re-emitted chunk 0 of the *same* block with no warning.
   Plain "continue" now auto-advances to the next unfinished chunk of
   the current block first, before moving to a new block.

ابزار پیست تکه‌ای برای رابط‌های چتی که فایل آپلود قبول نمی‌کنند.

هر فایل متنی (معمولاً یک گزارش تولیدشده توسط sarand) را به تکه‌های
ترتیبی و اندازه‌محدود می‌شکند و در هر اجرا یک تکه را «صادر» می‌کند: آن
را چاپ می‌کند، در یک فایل می‌نویسد، و در صورت وجود ابزار کلیپ‌بورد
پشتیبانی‌شده، در کلیپ‌بورد کپی می‌کند -- تا بتوانی هر تکه را یکی‌یکی در
یک چت پیست کنی، با وضعیت قابل‌ازسرگیری بین اجراها.

اصالتاً روی یک README.md هاردکد و برندینگ اختصاصی بیمرز نوشته شده بود؛
اینجا عمومی شده تا روی هر فایلی (گزارش sarand یا هر چیز دیگر) کار کند،
و سه باگ واقعی که در بازبینی پیدا شد رفع شده‌اند (بالا توضیح داده شد).
"""

from __future__ import annotations

import argparse
import base64
import copy
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# Raw text size ceiling for OSC52, applied BEFORE base64 -- not the
# final escape-sequence length. Empirically tested and proven reliable
# on this specific hardware/terminal combo (non-rooted Android,
# Termux/Kali NetHunter proot, no X11/Wayland session -- OSC52 is the
# only clipboard mechanism that works at all here, since it operates
# purely through terminal output rather than talking to a display
# server or an external clipboard tool). Base64 inflates ~4000 raw
# bytes to ~5336, well inside terminals' typical OSC52 buffer limits;
# 6000 raw was the tested ceiling, kept here as a hard safety check in
# case a single long line ever pushes one chunk above the normal
# CHUNK_SIZE cap (see make_chunks()'s over-length-line path).
#
# سقف اندازه‌ی متن خام برای OSC52، پیش از base64 اعمال می‌شود -- نه طول
# نهایی escape sequence. تجربی روی همین ترکیب سخت‌افزار/ترمینال تست و
# اثبات شده (اندروید بدون روت، Termux/Kali NetHunter proot، بدون نشست
# X11/Wayland -- OSC52 تنها مکانیزم کلیپ‌بوردی است که اصلاً اینجا کار
# می‌کند، چون صرفاً از طریق خروجی ترمینال عمل می‌کند، نه صحبت با یک
# display server یا یک ابزار کلیپ‌بورد خارجی).
OSC52_MAX_BYTES = 6000

DEFAULT_SOURCE_FILE = Path("README.md")
STATE_DIR = Path(".sarand-paste-rc")

STATE_VERSION = 3  # bumped: generalized source handling, dropped dead `initialize` param
BLOCK_SIZE = 1000
CHUNK_SIZE = 4000


def source_file(explicit: str | None) -> Path:
    """Resolve the source file: --source flag > SARAND_PASTE_SOURCE env > default."""
    if explicit:
        return Path(explicit).expanduser()
    configured = os.environ.get("SARAND_PASTE_SOURCE")
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
        "config_fingerprint": config_fingerprint(),
    }


def config_fingerprint() -> str:
    payload = {"block_size": BLOCK_SIZE, "chunk_size": CHUNK_SIZE}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


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


def total_blocks(total_lines: int) -> int:
    if total_lines <= 0:
        return 0
    return (total_lines + BLOCK_SIZE - 1) // BLOCK_SIZE


def make_chunks(lines: list[str]) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_size = 0

    for line in lines:
        text = f"{line}\n"
        line_size = len(text.encode("utf-8"))

        if line_size > CHUNK_SIZE:
            if current:
                chunks.append("".join(current))
                current = []
                current_size = 0
            chunks.append(text)
            print(f"WARNING: line exceeds CHUNK_SIZE ({line_size} > {CHUNK_SIZE})", file=sys.stderr)
            continue

        if current and current_size + line_size > CHUNK_SIZE:
            chunks.append("".join(current))
            current = []
            current_size = 0

        current.append(text)
        current_size += line_size

    if current:
        chunks.append("".join(current))

    return chunks or [""]


def block_chunks(lines: list[str], block: int) -> list[str]:
    blocks = total_blocks(len(lines))
    if block < 0 or block >= blocks:
        upper = max(0, blocks - 1)
        print(f"ERROR: block {block} is out of range (0-{upper}).", file=sys.stderr)
        raise SystemExit(1)
    start = block * BLOCK_SIZE
    end = min(start + BLOCK_SIZE, len(lines))
    return make_chunks(lines[start:end])


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

    blocks = total_blocks(len(lines))
    if state["next_block"] > blocks:
        raise ValueError(f"next_block={state['next_block']} exceeds total_blocks={blocks}")
    if current_block is not None and current_block >= blocks:
        raise ValueError(f"current_block={current_block} exceeds total_blocks={blocks}")
    if current_block is not None:
        chunks = block_chunks(lines, current_block)
        if state["current_chunk"] >= len(chunks):
            raise ValueError(f"current_chunk={state['current_chunk']} exceeds available chunks={len(chunks)}")


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

    try:
        validate_state(state, lines)
    except ValueError as exc:
        print(f"ERROR: corrupted collector state: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    return state


def save_state(paths: Paths, state: dict[str, Any], lines: list[str] | None = None) -> None:
    validate_state(state, lines)
    paths.state_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = paths.state_file.with_name(f"{paths.state_file.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
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
        print(f"ERROR: another instance is running for this source file: {exc}", file=sys.stderr)
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
        return paths.source.read_text(encoding="utf-8").splitlines()
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


def _osc52_copy(text: str) -> bool:
    """Set the system clipboard via the OSC52 terminal escape sequence.

    Works purely through terminal output -- no external clipboard tool
    and no X11/Wayland session needed. On a non-rooted Android phone
    running Termux/Kali NetHunter proot, this is the *only* reliable
    clipboard mechanism (xclip/xsel/wl-copy have no display server to
    talk to; termux-clipboard-set needs Termux:API, which may not be
    reachable from inside a proot). Tried first for exactly that
    reason; the subprocess-based tools below remain as a fallback for
    running this on a machine that does have a graphical session.

    تنظیم کلیپ‌بورد سیستم از طریق دنباله‌ی escape ترمینال OSC52. صرفاً
    از طریق خروجی ترمینال کار می‌کند -- بدون نیاز به ابزار کلیپ‌بورد
    خارجی یا نشست X11/Wayland. روی گوشی اندروید بدون روت با Termux/Kali
    NetHunter proot، این تنها مکانیزم کلیپ‌بورد قابل‌اعتماد است.
    """
    payload = text.encode("utf-8")
    if len(payload) > OSC52_MAX_BYTES:
        # Refuse rather than send a sequence some terminals would
        # truncate or reject outright -- caller falls back to
        # "clipboard unavailable" and the user copies chunk_file by hand.
        # رد می‌کنیم به‌جای ارسال دنباله‌ای که برخی ترمینال‌ها آن را
        # قطع یا کلاً رد می‌کنند -- فراخوان به «کلیپ‌بورد در دسترس نیست»
        # برمی‌گردد و کاربر chunk_file را دستی کپی می‌کند.
        return False

    b64 = base64.b64encode(payload).decode("ascii")
    sequence = f"\x1b]52;c;{b64}\x07"

    # Inside tmux/screen the multiplexer swallows a bare OSC52 sequence
    # before it reaches the real terminal -- wrap it in the relevant
    # passthrough sequence instead.
    # داخل tmux/screen، مالتی‌پلکسر یک دنباله‌ی OSC52 خام را پیش از
    # رسیدن به ترمینال واقعی می‌بلعد -- به‌جایش در دنباله‌ی passthrough
    # مربوطه بسته‌بندی می‌شود.
    if os.environ.get("TMUX"):
        sequence = "\x1bPtmux;" + sequence.replace("\x1b", "\x1b\x1b") + "\x1b\\"
    elif os.environ.get("STY"):
        sequence = "\x1bP" + sequence + "\x1b\\"

    try:
        with open("/dev/tty", "w") as tty:
            tty.write(sequence)
            tty.flush()
        return True
    except OSError:
        return False


def clipboard_copy(text: str) -> bool:
    if _osc52_copy(text):
        return True

    commands = (
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
        ["termux-clipboard-set"],
        ["wl-copy"],
    )
    for command in commands:
        if shutil.which(command[0]) is None:
            continue
        try:
            result = subprocess.run(
                command, input=text, text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
            )
        except OSError:
            continue
        if result.returncode == 0:
            return True
    return False


def remaining_lines(lines: list[str], block: int) -> int:
    consumed = min((block + 1) * BLOCK_SIZE, len(lines))
    return max(0, len(lines) - consumed)


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


def emit_block(
    paths: Paths,
    state: dict[str, Any],
    lines: list[str],
    block: int,
    chunk: int,
    *,
    record_run: bool,
    advance_next: bool,
) -> int:
    chunks = block_chunks(lines, block)

    if chunk < 0 or chunk >= len(chunks):
        print(f"ERROR: chunk {chunk} is out of range (0-{len(chunks) - 1}) for block {block}.", file=sys.stderr)
        return 1

    start_line = block * BLOCK_SIZE + 1
    end_line = min((block + 1) * BLOCK_SIZE, len(lines))
    content = chunks[chunk]
    chunk_path = write_chunk(paths, block, chunk, content)

    # Deep copy, not a shallow dict() copy: `history` is a mutable list
    # nested inside state, and append_history() below mutates it in
    # place. A shallow copy would leave old_state["history"] aliasing
    # the same (now-mutated) list, silently defeating the rollback.
    # کپی عمیق، نه یک کپی سطحی dict(): «history» یک لیست mutable تودرتو
    # در state است، و append_history() زیر آن را جای‌به‌جا mutate
    # می‌کند. یک کپی سطحی باعث می‌شد old_state["history"] به همان لیست
    # (که حالا mutate شده) اشاره کند و rollback را بی‌صدا خنثی کند.
    old_state = copy.deepcopy(state)

    state["current_block"] = block
    state["current_chunk"] = chunk

    if record_run:
        append_history(state, block, chunk)
        state["runs"] += 1

    if advance_next:
        state["next_block"] = block if chunk + 1 < len(chunks) else block + 1

    try:
        save_state(paths, state, lines)
    except SystemExit:
        state.clear()
        state.update(old_state)
        raise

    clipboard_ok = clipboard_copy(content)
    history_position = state["history_index"] + 1 if state["history_index"] >= 0 else 0

    print("========================================")
    print("SARAND PASTE-CHUNKS")
    print("========================================")
    print(f"source={paths.source}")
    print(f"run={state['runs']}")
    print(f"history_position={history_position}/{len(state['history'])}")
    print(f"block={block}")
    print(f"total_blocks={total_blocks(len(lines))}")
    print(f"total_lines={len(lines)}")
    print(f"start_line={start_line}")
    print(f"end_line={end_line}")
    print(f"lines_in_block={end_line - start_line + 1}")
    print(f"chunk={chunk}")
    print(f"total_chunks={len(chunks)}")
    print(f"chunk_bytes={len(content.encode('utf-8'))}")
    print(f"chunk_file={chunk_path}")
    print(f"remaining_lines={remaining_lines(lines, block)}")
    print(f"clipboard={'OK' if clipboard_ok else 'UNAVAILABLE'}")
    print("========================================")

    if chunk + 1 < len(chunks):
        print(f"NEXT: run again with no flags (auto-continues to chunk {chunk + 1}), or: --chunk {chunk + 1}")
    elif state["next_block"] < total_blocks(len(lines)):
        print("NEXT: run again with no flags for the next block")
    else:
        print("DONE: all blocks collected.")
    print("========================================")
    return 0


def prepare_state(paths: Paths, lines: list[str]) -> dict[str, Any]:
    state = load_state(paths, lines)
    if state["source_fingerprint"] is None:
        state["source_fingerprint"] = source_fingerprint(paths.source)
        save_state(paths, state, lines)
    else:
        ensure_source_consistent(paths, state)
    return state


def run_next(paths: Paths) -> int:
    lines = read_source(paths)
    state = prepare_state(paths, lines)
    blocks = total_blocks(len(lines))

    if blocks == 0:
        print("DONE: source file is empty.")
        return 0

    # If the current block still has unfinished chunks, continue it
    # instead of jumping to next_block -- this is the fix for the
    # "plain re-run silently repeats chunk 0" trap (see module docstring).
    # اگر بلاک فعلی هنوز تکه‌های ناتمام دارد، آن را ادامه بده به‌جای پرش
    # به next_block -- رفع همان تله‌ی «اجرای ساده بی‌صدا تکه صفر را
    # تکرار می‌کند» (به docstring ماژول نگاه کنید).
    current_block = state["current_block"]
    if current_block is not None:
        chunks_in_current = block_chunks(lines, current_block)
        if state["current_chunk"] + 1 < len(chunks_in_current):
            return emit_block(
                paths, state, lines, current_block, state["current_chunk"] + 1, record_run=True, advance_next=True
            )

    block = state["next_block"]
    if block >= blocks:
        print("DONE: all blocks have been collected.")
        return 0
    return emit_block(paths, state, lines, block, 0, record_run=True, advance_next=True)


def run_number(paths: Paths, number: int) -> int:
    if number < 0:
        print("ERROR: block number must be >= 0.", file=sys.stderr)
        return 1
    lines = read_source(paths)
    state = prepare_state(paths, lines)
    return emit_block(paths, state, lines, number, 0, record_run=True, advance_next=False)


def execute_chunk(paths: Paths, chunk_number: int) -> int:
    if chunk_number < 0:
        print("ERROR: chunk number must be >= 0.", file=sys.stderr)
        return 1
    lines = read_source(paths)
    state = prepare_state(paths, lines)
    block = state["current_block"]
    if block is None:
        print("ERROR: no current block exists.", file=sys.stderr)
        return 1
    return emit_block(paths, state, lines, block, chunk_number, record_run=True, advance_next=True)


def run_back(paths: Paths) -> int:
    lines = read_source(paths)
    state = prepare_state(paths, lines)
    current = state["current_block"]
    if current is None:
        print("ERROR: no current block exists.", file=sys.stderr)
        return 1
    if current <= 0:
        print("ERROR: already at the first block.", file=sys.stderr)
        return 1
    return emit_block(paths, state, lines, current - 1, 0, record_run=False, advance_next=False)


def run_back_run(paths: Paths) -> int:
    lines = read_source(paths)
    state = prepare_state(paths, lines)
    index = state["history_index"]
    if index <= 0:
        print("ERROR: no previous run exists.", file=sys.stderr)
        return 1
    target = state["history"][index - 1]
    state["history_index"] = index - 1
    return emit_block(paths, state, lines, target["block"], target["chunk"], record_run=False, advance_next=False)


def clean(paths: Paths) -> int:
    removed: list[str] = []
    if paths.state_file.exists():
        try:
            paths.state_file.unlink()
            removed.append(str(paths.state_file))
        except OSError as exc:
            print(f"ERROR: unable to remove {paths.state_file}: {exc}", file=sys.stderr)
            return 1
    if paths.chunk_dir.exists():
        try:
            shutil.rmtree(paths.chunk_dir)
            removed.append(str(paths.chunk_dir))
        except OSError as exc:
            print(f"ERROR: unable to remove {paths.chunk_dir}: {exc}", file=sys.stderr)
            return 1

    print("========================================")
    print("SARAND PASTE-CHUNKS RESET")
    print("========================================")
    print(f"source={paths.source}")
    print(f"removed={', '.join(removed) if removed else 'none'}")
    print("========================================")
    return 0


def show_info(paths: Paths) -> int:
    lines = read_source(paths)
    state = load_state(paths, lines)
    if state["source_fingerprint"] is not None:
        ensure_source_consistent(paths, state)

    print("========================================")
    print("SARAND PASTE-CHUNKS INFO")
    print("========================================")
    print(f"source={paths.source}")
    print(f"total_lines={len(lines)}")
    print(f"block_size={BLOCK_SIZE}")
    print(f"total_blocks={total_blocks(len(lines))}")
    print(f"chunk_size={CHUNK_SIZE}")
    print(f"state_file={paths.state_file}")
    print(f"lock_file={paths.lock_file}")
    print(f"chunk_dir={paths.chunk_dir}")
    print(f"next_block={state['next_block']}")
    print(f"current_block={state['current_block']}")
    print(f"current_chunk={state['current_chunk']}")
    print(f"runs={state['runs']}")
    print(f"history_len={len(state['history'])}")
    print(f"history_index={state['history_index']}")
    print("========================================")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Split a file (typically a sarand report) into paste-sized chunks for chat UIs without file upload."
    )
    parser.add_argument("--source", metavar="PATH", help="File to chunk (default: README.md, or $SARAND_PASTE_SOURCE)")
    parser.add_argument("-b", "--back", action="store_true", help="move back one block")
    parser.add_argument("-br", "--back-run", action="store_true", help="move back one history entry")
    parser.add_argument("--reset", "--clean", action="store_true", help="remove collector state and chunks")
    parser.add_argument("-n", type=int, metavar="N", help="select block N")
    parser.add_argument("--chunk", "-c", type=int, metavar="N", help="emit chunk N of current block")
    parser.add_argument("-i", "--info", action="store_true", help="show collector information")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    selected = sum(
        value is not None and value is not False
        for value in (args.n, args.chunk, args.back, args.back_run, args.reset, args.info)
    )
    if selected > 1:
        parser.error("options -b, -br, --reset, -n, --chunk and --info are mutually exclusive")

    paths = Paths(source_file(args.source))

    if args.info:
        lock_fd = acquire_lock(paths)
        try:
            return show_info(paths)
        finally:
            release_lock(lock_fd)

    lock_fd = acquire_lock(paths)
    try:
        if args.reset:
            return clean(paths)
        if args.n is not None:
            return run_number(paths, args.n)
        if args.chunk is not None:
            return execute_chunk(paths, args.chunk)
        if args.back_run:
            return run_back_run(paths)
        if args.back:
            return run_back(paths)
        return run_next(paths)
    finally:
        release_lock(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
