"""RC CLI orchestration: wires chunker + state + session + protocol +
transport together and exposes the paste_chunks.py command surface
(now RC-protocol-aware).

Behavior preserved from the original scripts/paste_chunks.py:
- resumable state across invocations (next/back/history/jump-to-block)
- deep-copy rollback on save failure
- "plain continue" auto-advances to the next unfinished chunk of the
  current block before moving to a new block

New in this layer: every emitted chunk is now wrapped in the RC
protocol envelope (SARAND RC START/CHUNK/END, session_id, report_hash,
chunk_hash) instead of being pasted as bare text with only a
human-readable info banner.

هماهنگ‌سازی CLI برای RC: chunker + state + session + protocol +
transport را به هم متصل می‌کند و همان سطح دستورات paste_chunks.py را
عرضه می‌کند (اکنون آگاه از پروتکل RC).
"""

from __future__ import annotations

import argparse
import copy
import datetime
import shutil
import sys
from typing import Any

from . import chunker, protocol, session, transport
from . import state as state_mod


def prepare_state(paths: state_mod.Paths, lines: list[str]) -> dict[str, Any]:
    state = state_mod.load_state(paths, lines)
    if state["source_fingerprint"] is None:
        state["source_fingerprint"] = state_mod.source_fingerprint(paths.source)
        state["session_id"] = session.new_session_id()
        state_mod.save_state(paths, state, lines)
    else:
        state_mod.ensure_source_consistent(paths, state)
        if state.get("session_id") is None:
            # Defensive: state predates the session_id field but the
            # config_fingerprint check above should already have
            # forced a --reset in that case. Never emit protocol
            # framing with a missing identity.
            print(
                "ERROR: state has no session_id -- run with --reset to start a fresh RC session.",
                file=sys.stderr,
            )
            raise SystemExit(1)
    return state


def _global_position(lines: list[str], block: int, chunk: int) -> tuple[int, int]:
    flat = chunker.all_chunks(lines)
    for index, (b, c, _content) in enumerate(flat):
        if b == block and c == chunk:
            return index + 1, len(flat)
    print(
        f"ERROR: internal: could not locate (block={block}, chunk={chunk}) in the source.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def emit_block(
    paths: state_mod.Paths,
    state: dict[str, Any],
    lines: list[str],
    block: int,
    chunk: int,
    *,
    record_run: bool,
    advance_next: bool,
) -> int:
    chunks = chunker.block_chunks(lines, block)

    if chunk < 0 or chunk >= len(chunks):
        print(
            f"ERROR: chunk {chunk} is out of range (0-{len(chunks) - 1}) for block {block}.",
            file=sys.stderr,
        )
        return 1

    start_line = block * chunker.BLOCK_SIZE + 1
    end_line = min((block + 1) * chunker.BLOCK_SIZE, len(lines))
    content = chunks[chunk]
    global_index, total_chunks_all = _global_position(lines, block, chunk)

    # Deep copy, not a shallow dict() copy: `history` is a mutable list
    # nested inside state, and append_history() below mutates it in
    # place. A shallow copy would leave old_state["history"] aliasing
    # the same (now-mutated) list, silently defeating the rollback.
    old_state = copy.deepcopy(state)

    state["current_block"] = block
    state["current_chunk"] = chunk

    if record_run:
        state_mod.append_history(state, block, chunk)
        state["runs"] += 1

    if advance_next:
        state["next_block"] = block if chunk + 1 < len(chunks) else block + 1

    try:
        state_mod.save_state(paths, state, lines)
    except SystemExit:
        state.clear()
        state.update(old_state)
        raise

    report_hash = state["source_fingerprint"]
    session_id = state["session_id"]
    report_id = session.report_id_from_hash(report_hash)

    envelope = ""
    if global_index == 1:
        envelope += protocol.build_start(
            session_id=session_id,
            report_id=report_id,
            source=str(paths.source),
            source_fingerprint=state["source_fingerprint"],
            generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            report_format="text",
            total_chunks=total_chunks_all,
            report_hash=report_hash,
        )
        envelope += "\n"

    envelope += protocol.build_chunk_header(
        session_id=session_id,
        report_id=report_id,
        chunk_index=global_index,
        total_chunks=total_chunks_all,
        block=block,
        total_blocks=chunker.total_blocks(len(lines)),
        start_line=start_line,
        end_line=end_line,
        content=content,
    )
    envelope += content
    envelope += protocol.CHUNK_FOOTER

    if global_index == total_chunks_all:
        envelope += "\n"
        envelope += protocol.build_end(
            session_id=session_id,
            report_id=report_id,
            total_chunks_sent=total_chunks_all,
            report_hash=report_hash,
        )

    chunk_path = state_mod.write_chunk(paths, block, chunk, envelope)
    clipboard_ok = transport.clipboard_copy(envelope)

    # The envelope is the only thing that goes to stdout -- it is
    # exactly what must be pasted. All human-facing status goes to
    # stderr so copying terminal stdout never pollutes the
    # transmission with banner text.
    sys.stdout.write(envelope)

    history_position = state["history_index"] + 1 if state["history_index"] >= 0 else 0
    print(
        "================================================================",
        file=sys.stderr,
    )
    print("SARAND RC (status)", file=sys.stderr)
    print(
        "================================================================",
        file=sys.stderr,
    )
    print(f"source={paths.source}", file=sys.stderr)
    print(f"session_id={session_id}", file=sys.stderr)
    print(f"run={state['runs']}", file=sys.stderr)
    print(
        f"history_position={history_position}/{len(state['history'])}", file=sys.stderr
    )
    print(f"global_chunk={global_index}/{total_chunks_all}", file=sys.stderr)
    print(
        f"block={block} chunk={chunk} (block has {len(chunks)} chunk(s))",
        file=sys.stderr,
    )
    print(f"lines_in_block={end_line - start_line + 1}", file=sys.stderr)
    print(f"chunk_bytes={len(content.encode('utf-8'))}", file=sys.stderr)
    print(f"chunk_file={chunk_path}", file=sys.stderr)
    print(f"remaining_lines={chunker.remaining_lines(lines, block)}", file=sys.stderr)
    print(f"clipboard={'OK' if clipboard_ok else 'UNAVAILABLE'}", file=sys.stderr)
    print(
        "================================================================",
        file=sys.stderr,
    )

    if chunk + 1 < len(chunks):
        print(
            f"NEXT: run again with no flags (auto-continues to chunk {chunk + 1}), "
            f"or: --chunk {chunk + 1}",
            file=sys.stderr,
        )
    elif global_index < total_chunks_all:
        print("NEXT: run again with no flags for the next block", file=sys.stderr)
    else:
        print(
            "DONE: all blocks collected -- SARAND RC END was just emitted.",
            file=sys.stderr,
        )
    print(
        "================================================================",
        file=sys.stderr,
    )
    return 0


def run_next(paths: state_mod.Paths) -> int:
    lines = state_mod.read_source(paths)
    state = prepare_state(paths, lines)
    blocks = chunker.total_blocks(len(lines))

    if blocks == 0:
        print("DONE: source file is empty.", file=sys.stderr)
        return 0

    current_block = state["current_block"]
    if current_block is not None:
        chunks_in_current = chunker.block_chunks(lines, current_block)
        if state["current_chunk"] + 1 < len(chunks_in_current):
            return emit_block(
                paths,
                state,
                lines,
                current_block,
                state["current_chunk"] + 1,
                record_run=True,
                advance_next=True,
            )

    block = state["next_block"]
    if block >= blocks:
        print("DONE: all blocks have been collected.", file=sys.stderr)
        return 0
    return emit_block(paths, state, lines, block, 0, record_run=True, advance_next=True)


def run_number(paths: state_mod.Paths, number: int) -> int:
    if number < 0:
        print("ERROR: block number must be >= 0.", file=sys.stderr)
        return 1
    lines = state_mod.read_source(paths)
    state = prepare_state(paths, lines)
    return emit_block(
        paths, state, lines, number, 0, record_run=True, advance_next=False
    )


def execute_chunk(paths: state_mod.Paths, chunk_number: int) -> int:
    if chunk_number < 0:
        print("ERROR: chunk number must be >= 0.", file=sys.stderr)
        return 1
    lines = state_mod.read_source(paths)
    state = prepare_state(paths, lines)
    block = state["current_block"]
    if block is None:
        print("ERROR: no current block exists.", file=sys.stderr)
        return 1
    return emit_block(
        paths, state, lines, block, chunk_number, record_run=True, advance_next=True
    )


def run_back(paths: state_mod.Paths) -> int:
    lines = state_mod.read_source(paths)
    state = prepare_state(paths, lines)
    current = state["current_block"]
    if current is None:
        print("ERROR: no current block exists.", file=sys.stderr)
        return 1
    if current <= 0:
        print("ERROR: already at the first block.", file=sys.stderr)
        return 1
    return emit_block(
        paths, state, lines, current - 1, 0, record_run=False, advance_next=False
    )


def run_back_run(paths: state_mod.Paths) -> int:
    lines = state_mod.read_source(paths)
    state = prepare_state(paths, lines)
    index = state["history_index"]
    if index <= 0:
        print("ERROR: no previous run exists.", file=sys.stderr)
        return 1
    target = state["history"][index - 1]
    state["history_index"] = index - 1
    return emit_block(
        paths,
        state,
        lines,
        target["block"],
        target["chunk"],
        record_run=False,
        advance_next=False,
    )


def clean(paths: state_mod.Paths) -> int:
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

    print(
        "================================================================",
        file=sys.stderr,
    )
    print("SARAND RC RESET", file=sys.stderr)
    print(
        "================================================================",
        file=sys.stderr,
    )
    print(f"source={paths.source}", file=sys.stderr)
    print(f"removed={', '.join(removed) if removed else 'none'}", file=sys.stderr)
    print(
        "================================================================",
        file=sys.stderr,
    )
    return 0


def show_info(paths: state_mod.Paths) -> int:
    lines = state_mod.read_source(paths)
    state = state_mod.load_state(paths, lines)
    if state["source_fingerprint"] is not None:
        state_mod.ensure_source_consistent(paths, state)

    total_chunks_all = len(chunker.all_chunks(lines)) if lines else 0

    print(
        "================================================================",
        file=sys.stderr,
    )
    print("SARAND RC INFO", file=sys.stderr)
    print(
        "================================================================",
        file=sys.stderr,
    )
    print(f"source={paths.source}", file=sys.stderr)
    print(f"total_lines={len(lines)}", file=sys.stderr)
    print(f"block_size={chunker.BLOCK_SIZE}", file=sys.stderr)
    print(f"total_blocks={chunker.total_blocks(len(lines))}", file=sys.stderr)
    print(f"chunk_size={chunker.CHUNK_SIZE}", file=sys.stderr)
    print(f"total_chunks={total_chunks_all}", file=sys.stderr)
    print(f"session_id={state.get('session_id')}", file=sys.stderr)
    print(f"state_file={paths.state_file}", file=sys.stderr)
    print(f"lock_file={paths.lock_file}", file=sys.stderr)
    print(f"chunk_dir={paths.chunk_dir}", file=sys.stderr)
    print(f"next_block={state['next_block']}", file=sys.stderr)
    print(f"current_block={state['current_block']}", file=sys.stderr)
    print(f"current_chunk={state['current_chunk']}", file=sys.stderr)
    print(f"runs={state['runs']}", file=sys.stderr)
    print(f"history_len={len(state['history'])}", file=sys.stderr)
    print(f"history_index={state['history_index']}", file=sys.stderr)
    print(
        "================================================================",
        file=sys.stderr,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Split a file into RC-protocol-framed, paste-sized chunks for chat UIs without file upload."
    )
    parser.add_argument(
        "--source",
        metavar="PATH",
        help="File to chunk (default: README.md, or $SARAND_RC_SOURCE)",
    )
    parser.add_argument("-b", "--back", action="store_true", help="move back one block")
    parser.add_argument(
        "-br", "--back-run", action="store_true", help="move back one history entry"
    )
    parser.add_argument(
        "--reset",
        "--clean",
        action="store_true",
        help="remove collector state and chunks",
    )
    parser.add_argument("-n", type=int, metavar="N", help="select block N")
    parser.add_argument(
        "--chunk", "-c", type=int, metavar="N", help="emit chunk N of current block"
    )
    parser.add_argument(
        "-i", "--info", action="store_true", help="show collector information"
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    selected = sum(
        value is not None and value is not False
        for value in (
            args.n,
            args.chunk,
            args.back,
            args.back_run,
            args.reset,
            args.info,
        )
    )
    if selected > 1:
        parser.error(
            "options -b, -br, --reset, -n, --chunk and --info are mutually exclusive"
        )

    paths = state_mod.Paths(state_mod.source_file(args.source))

    if args.info:
        lock_fd = state_mod.acquire_lock(paths)
        try:
            return show_info(paths)
        finally:
            state_mod.release_lock(lock_fd)

    lock_fd = state_mod.acquire_lock(paths)
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
        state_mod.release_lock(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
