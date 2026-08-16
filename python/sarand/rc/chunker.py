"""Deterministic, byte-safe splitting of source lines into blocks and
chunks. Pure functions -- no filesystem, no state, no protocol framing
(AGENTS.md architectural ownership rule).

Unchanged from the original scripts/paste_chunks.py logic; only moved
here so the RC package has one file per responsibility.

شکستن قطعی و امن-بایتی خطوط منبع به بلاک‌ها و تکه‌ها. توابع خالص -- بدون
فایل‌سیستم، بدون state، بدون قاب‌بندی پروتکل.

بدون تغییر نسبت به منطق اصلی scripts/paste_chunks.py؛ فقط اینجا جابجا
شده تا بسته‌ی RC یک فایل به‌ازای هر مسئولیت داشته باشد.
"""

from __future__ import annotations

import sys

BLOCK_SIZE = 1000
CHUNK_SIZE = 4000


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
            print(
                f"WARNING: line exceeds CHUNK_SIZE ({line_size} > {CHUNK_SIZE})",
                file=sys.stderr,
            )
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


def remaining_lines(lines: list[str], block: int) -> int:
    consumed = min((block + 1) * BLOCK_SIZE, len(lines))
    return max(0, len(lines) - consumed)


def all_chunks(lines: list[str]) -> list[tuple[int, int, str]]:
    """Every chunk in the whole source, in transfer order, as
    (block, chunk_index_in_block, content).

    New in the RC protocol layer: the old per-block emission had no
    notion of a single source's total chunk count across every block.
    The protocol's total_chunks/chunk_index (RC constitution §47)
    need that global count, so it is computed here once from the
    same block_chunks() used for actual emission -- never estimated
    or cached separately, to avoid it drifting out of sync.

    هر تکه در کل منبع، به ترتیب انتقال، به‌صورت
    (بلاک، اندیس‌تکه‌درون‌بلاک، محتوا).
    """
    result: list[tuple[int, int, str]] = []
    for block in range(total_blocks(len(lines))):
        for index, content in enumerate(block_chunks(lines, block)):
            result.append((block, index, content))
    return result
