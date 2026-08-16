"""RC wire-protocol framing: START / CHUNK / END markers with integrity
metadata, protocol_version=1.

This module ONLY builds protocol text -- it never touches the
filesystem, state, or transport (AGENTS.md architectural ownership
rule: one capability, one file).

قاب‌بندی پروتکل RC روی سیم: نشانگرهای START / CHUNK / END به همراه
متادیتای صحت، protocol_version=1.

این ماژول فقط متن پروتکل می‌سازد -- هرگز به فایل‌سیستم، state یا
transport دست نمی‌زند.
"""

from __future__ import annotations

import hashlib

PROTOCOL_VERSION = 1


def chunk_hash(content: str) -> str:
    """SHA-256 of a chunk's exact raw content, hex, sha256:-prefixed."""
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def build_start(
    *,
    session_id: str,
    report_id: str,
    source: str,
    source_fingerprint: str,
    generated_at: str,
    report_format: str,
    total_chunks: int,
    report_hash: str,
) -> str:
    lines = [
        "==================== SARAND RC START ====================",
        f"protocol_version={PROTOCOL_VERSION}",
        f"session_id={session_id}",
        f"report_id={report_id}",
        f"source={source}",
        f"source_fingerprint={source_fingerprint}",
        f"generated_at={generated_at}",
        f"format={report_format}",
        f"total_chunks={total_chunks}",
        f"report_hash={report_hash}",
        "",
        "AI-INSTRUCTIONS:",
        f"This is a SARAND RC transmission split into {total_chunks} chunks.",
        "A chunk is not the report. Do not summarize, analyze, or act on",
        "partial content. Wait for SARAND RC END, then verify every",
        "chunk_hash and the final report_hash before treating the report",
        "as complete.",
        "==================== SARAND RC START-END ====================",
    ]
    return "\n".join(lines) + "\n"


def build_chunk_header(
    *,
    session_id: str,
    report_id: str,
    chunk_index: int,
    total_chunks: int,
    block: int,
    total_blocks: int,
    start_line: int,
    end_line: int,
    content: str,
) -> str:
    lines = [
        f"----- SARAND RC CHUNK {chunk_index}/{total_chunks} -----",
        f"session_id={session_id}",
        f"report_id={report_id}",
        f"block={block}",
        f"total_blocks={total_blocks}",
        f"start_line={start_line}",
        f"end_line={end_line}",
        f"chunk_bytes={len(content.encode('utf-8'))}",
        f"chunk_hash={chunk_hash(content)}",
        "----- SARAND RC CHUNK-BODY -----",
    ]
    return "\n".join(lines) + "\n"


CHUNK_FOOTER = "\n----- SARAND RC CHUNK-END -----\n"


def build_end(
    *,
    session_id: str,
    report_id: str,
    total_chunks_sent: int,
    report_hash: str,
) -> str:
    lines = [
        "==================== SARAND RC END ====================",
        f"session_id={session_id}",
        f"report_id={report_id}",
        f"total_chunks_sent={total_chunks_sent}",
        f"report_hash={report_hash}",
        "==================== SARAND RC END-END ====================",
    ]
    return "\n".join(lines) + "\n"
