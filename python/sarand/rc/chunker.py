"""Deterministic, byte-safe splitting of source lines into blocks and chunks.

This module preserves the exact UTF-8 bytes of the input text, including
LF, CRLF, and the absence of a final newline.

شکستن قطعی و امن-بایتی خطوط منبع به بلاک‌ها و تکه‌ها.

این ماژول بایت‌های دقیق متن UTF-8 را حفظ می‌کند، از جمله LF، CRLF و
نبودن newline نهایی.
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
        line_size = len(line.encode("utf-8"))

        if line_size > CHUNK_SIZE:
            if current:
                chunks.append("".join(current))
                current = []
                current_size = 0

            chunks.append(line)

            print(
                f"WARNING: line exceeds CHUNK_SIZE ({line_size} > {CHUNK_SIZE})",
                file=sys.stderr,
            )
            continue

        if current and current_size + line_size > CHUNK_SIZE:
            chunks.append("".join(current))
            current = []
            current_size = 0

        current.append(line)
        current_size += line_size

    if current:
        chunks.append("".join(current))

    return chunks or [""]


def block_chunks(lines: list[str], block: int) -> list[str]:
    blocks = total_blocks(len(lines))
    if block < 0 or block >= blocks:
        upper = max(0, blocks - 1)
        print(
            f"ERROR: block {block} is out of range (0-{upper}).",
            file=sys.stderr,
        )
        raise SystemExit(1)

    start = block * BLOCK_SIZE
    end = min(start + BLOCK_SIZE, len(lines))

    return make_chunks(lines[start:end])


def remaining_lines(lines: list[str], block: int) -> int:
    consumed = min((block + 1) * BLOCK_SIZE, len(lines))
    return max(0, len(lines) - consumed)


def all_chunks(lines: list[str]) -> list[tuple[int, int, str]]:
    """Return every chunk in deterministic transfer order.

    هر تکه را در ترتیب قطعی انتقال برمی‌گرداند.
    """
    result: list[tuple[int, int, str]] = []

    for block in range(total_blocks(len(lines))):
        for index, content in enumerate(block_chunks(lines, block)):
            result.append((block, index, content))

    return result
