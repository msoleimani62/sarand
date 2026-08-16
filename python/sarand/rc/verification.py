"""Strict verification and reconstruction for SARAND RC transfers.

اعتبارسنجی سخت‌گیرانه و بازسازی انتقال‌های SARAND RC.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


class RCVerificationError(Exception):
    """Raised when an RC transfer cannot be trusted.

    زمانی پرتاب می‌شود که انتقال RC قابل اعتماد نباشد.
    """


@dataclass(frozen=True)
class ParsedChunk:
    """Validated RC chunk.

    یک chunk معتبر و کاملاً بررسی‌شده RC.
    """

    session_id: str
    report_id: str
    chunk_index: int
    total_chunks: int
    declared_bytes: int
    declared_hash: str
    body: str
    has_start: bool
    has_end: bool
    start_values: dict[str, str] | None
    end_values: dict[str, str] | None


_START_RE = re.compile(
    r"^"
    r"==================== SARAND RC START ====================\n"
    r"protocol_version=(?P<protocol_version>[^\n]+)\n"
    r"session_id=(?P<session_id>[^\n]+)\n"
    r"report_id=(?P<report_id>[^\n]+)\n"
    r"source=(?P<source>[^\n]*)\n"
    r"source_fingerprint=(?P<source_fingerprint>[^\n]+)\n"
    r"generated_at=(?P<generated_at>[^\n]+)\n"
    r"format=(?P<format>[^\n]+)\n"
    r"total_chunks=(?P<total_chunks>\d+)\n"
    r"report_hash=(?P<report_hash>sha256:[0-9a-f]{64})\n"
    r"(?P<instructions>.*?)"
    r"==================== SARAND RC START-END ====================\n"
    r"$",
    re.DOTALL,
)

_END_RE = re.compile(
    r"^"
    r"==================== SARAND RC END ====================\n"
    r"session_id=(?P<session_id>[^\n]+)\n"
    r"report_id=(?P<report_id>[^\n]+)\n"
    r"total_chunks_sent=(?P<total_chunks_sent>\d+)\n"
    r"report_hash=(?P<report_hash>sha256:[0-9a-f]{64})\n"
    r"==================== SARAND RC END-END ====================\n"
    r"$"
)

_CHUNK_HEADER_RE = re.compile(
    r"----- SARAND RC CHUNK (?P<index>\d+)/(?P<total>\d+) -----\n"
    r"session_id=(?P<session_id>[^\n]+)\n"
    r"report_id=(?P<report_id>[^\n]+)\n"
    r"block=(?P<block>\d+)\n"
    r"total_blocks=(?P<total_blocks>\d+)\n"
    r"start_line=(?P<start_line>\d+)\n"
    r"end_line=(?P<end_line>\d+)\n"
    r"chunk_bytes=(?P<chunk_bytes>\d+)\n"
    r"chunk_hash=(?P<chunk_hash>sha256:[0-9a-f]{64})\n"
    r"----- SARAND RC CHUNK-BODY -----\n"
)

_CHUNK_FOOTER = "\n----- SARAND RC CHUNK-END -----\n"
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}")


def _sha256(text: str) -> str:
    """Return a SHA-256 hash in RC wire format.

    هش SHA-256 را با قالب مورد استفاده پروتکل RC برمی‌گرداند.
    """
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_start(prefix: str) -> dict[str, str]:
    """Parse one START envelope.

    یک envelope از نوع START را پارس می‌کند.
    """
    normalized = prefix.rstrip("\n") + "\n"
    match = _START_RE.fullmatch(normalized)

    if match is None:
        raise RCVerificationError("invalid SARAND RC START envelope")

    return match.groupdict()


def _parse_end(suffix: str) -> dict[str, str]:
    """Parse one END envelope.

    یک envelope از نوع END را پارس می‌کند.
    """
    normalized = suffix.lstrip("\n")
    match = _END_RE.fullmatch(normalized)

    if match is None:
        raise RCVerificationError("invalid SARAND RC END envelope")

    return match.groupdict()


def _split_envelopes(
    text: str,
) -> tuple[str, str, str, bool, bool]:
    """Separate optional START, chunk frame, and optional END.

    envelopeهای START و END را از قاب chunk جدا می‌کند.
    """
    chunk_marker = "----- SARAND RC CHUNK "
    chunk_start = text.find(chunk_marker)

    if chunk_start < 0:
        raise RCVerificationError("no valid SARAND RC CHUNK header found")

    prefix = text[:chunk_start]

    header_match = _CHUNK_HEADER_RE.match(text, chunk_start)
    if header_match is None:
        raise RCVerificationError("no valid SARAND RC CHUNK header found")

    body_start = header_match.end()
    declared_bytes = int(header_match.group("chunk_bytes"))
    remaining = text[body_start:]

    try:
        remaining_bytes = remaining.encode("utf-8")
        body_bytes = remaining_bytes[:declared_bytes]
        body = body_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RCVerificationError("chunk_bytes ends inside a UTF-8 character") from exc

    if len(body_bytes) != declared_bytes:
        raise RCVerificationError(
            f"chunk_bytes exceeds available chunk data "
            f"(declared={declared_bytes}, available={len(body_bytes)})"
        )

    footer_start = body_start + len(body)

    if not text.startswith(_CHUNK_FOOTER, footer_start):
        raise RCVerificationError(
            "no matching SARAND RC CHUNK-END footer found after the declared body"
        )

    suffix = text[footer_start + len(_CHUNK_FOOTER) :]

    has_start = bool(prefix)
    has_end = bool(suffix)

    return prefix, body, suffix, has_start, has_end


def parse_chunk(text: str) -> ParsedChunk:
    """Parse and validate one complete RC chunk.

    یک chunk کامل RC را پارس و تمام integrity checks آن را اجرا می‌کند.
    """
    if not text:
        raise RCVerificationError("empty RC chunk")

    prefix, body, suffix, has_start, has_end = _split_envelopes(text)

    chunk_start = text.find("----- SARAND RC CHUNK ")
    header_match = _CHUNK_HEADER_RE.match(text, chunk_start)

    if header_match is None:
        raise RCVerificationError("no valid SARAND RC CHUNK header found")

    start_values = _parse_start(prefix) if has_start else None
    end_values = _parse_end(suffix) if has_end else None

    chunk_index = int(header_match.group("index"))
    total_chunks = int(header_match.group("total"))
    declared_bytes = int(header_match.group("chunk_bytes"))
    declared_hash = header_match.group("chunk_hash")
    session_id = header_match.group("session_id")
    report_id = header_match.group("report_id")

    if chunk_index < 1:
        raise RCVerificationError(
            f"invalid chunk index: {chunk_index}; chunk indices start at 1"
        )

    if total_chunks < 1:
        raise RCVerificationError(
            f"invalid total_chunks: {total_chunks}; must be at least 1"
        )

    if chunk_index > total_chunks:
        raise RCVerificationError(
            f"chunk index {chunk_index} is outside declared range 1..{total_chunks}"
        )

    actual_bytes = len(body.encode("utf-8"))

    if declared_bytes != actual_bytes:
        raise RCVerificationError(
            f"chunk {chunk_index}/{total_chunks}: chunk_bytes mismatch "
            f"(declared={declared_bytes}, actual={actual_bytes})"
        )

    actual_hash = _sha256(body)

    if declared_hash != actual_hash:
        raise RCVerificationError(
            f"chunk {chunk_index}/{total_chunks}: chunk_hash mismatch "
            f"(declared={declared_hash}, actual={actual_hash}) -- "
            "content was altered, truncated, or corrupted in transit"
        )

    if has_start:
        if chunk_index != 1:
            raise RCVerificationError("START envelope is only valid on chunk 1")

        if start_values is None:
            raise RCVerificationError("invalid SARAND RC START envelope")

        if start_values["session_id"] != session_id:
            raise RCVerificationError("START session_id does not match chunk")

        if start_values["report_id"] != report_id:
            raise RCVerificationError("START report_id does not match chunk")

        if int(start_values["total_chunks"]) != total_chunks:
            raise RCVerificationError("START total_chunks does not match chunk")

    if has_end:
        if chunk_index != total_chunks:
            raise RCVerificationError("END envelope is only valid on the final chunk")

        if end_values is None:
            raise RCVerificationError("invalid SARAND RC END envelope")

        if end_values["session_id"] != session_id:
            raise RCVerificationError("END session_id does not match chunk")

        if end_values["report_id"] != report_id:
            raise RCVerificationError("END report_id does not match chunk")

        if int(end_values["total_chunks_sent"]) != total_chunks:
            raise RCVerificationError("END total_chunks_sent does not match chunk")

        if total_chunks == 1 and end_values["report_hash"] != actual_hash:
            raise RCVerificationError(
                "END report_hash does not match single-chunk content hash"
            )

    return ParsedChunk(
        session_id=session_id,
        report_id=report_id,
        chunk_index=chunk_index,
        total_chunks=total_chunks,
        declared_bytes=declared_bytes,
        declared_hash=declared_hash,
        body=body,
        has_start=has_start,
        has_end=has_end,
        start_values=start_values,
        end_values=end_values,
    )


def verify_transfer(
    chunk_texts: list[str],
    *,
    expected_report_hash: str | None = None,
) -> str:
    """Verify a complete RC transfer and reconstruct its original content.

    کل انتقال را اعتبارسنجی کرده و محتوای اصلی را بر اساس index بازسازی می‌کند.
    """
    if not chunk_texts:
        raise RCVerificationError("no chunks provided -- nothing to verify")

    parsed = [parse_chunk(text) for text in chunk_texts]

    session_ids = {chunk.session_id for chunk in parsed}

    if len(session_ids) != 1:
        raise RCVerificationError(
            f"chunks belong to different sessions: {sorted(session_ids)}"
        )

    report_ids = {chunk.report_id for chunk in parsed}

    if len(report_ids) != 1:
        raise RCVerificationError(
            f"chunks belong to different reports: {sorted(report_ids)}"
        )

    total_chunks_values = {chunk.total_chunks for chunk in parsed}

    if len(total_chunks_values) != 1:
        raise RCVerificationError(
            "inconsistent total_chunks declared across chunks: "
            f"{sorted(total_chunks_values)}"
        )

    total_chunks = total_chunks_values.pop()

    counts: dict[int, int] = {}

    for chunk in parsed:
        counts[chunk.chunk_index] = counts.get(chunk.chunk_index, 0) + 1

    duplicates = sorted(index for index, count in counts.items() if count > 1)

    if duplicates:
        raise RCVerificationError(f"duplicate chunk index(es): {duplicates}")

    start_count = sum(chunk.has_start for chunk in parsed)
    end_count = sum(chunk.has_end for chunk in parsed)

    if start_count != 1:
        raise RCVerificationError(
            f"expected exactly one START envelope, found {start_count}"
        )

    if end_count != 1:
        raise RCVerificationError(
            f"expected exactly one END envelope, found {end_count}"
        )

    start_chunk = next(chunk for chunk in parsed if chunk.has_start)
    end_chunk = next(chunk for chunk in parsed if chunk.has_end)

    if start_chunk.chunk_index != 1:
        raise RCVerificationError("START envelope is only valid on chunk 1")

    if end_chunk.chunk_index != total_chunks:
        raise RCVerificationError("END envelope is only valid on the final chunk")

    if start_chunk.start_values is None:
        raise RCVerificationError("invalid SARAND RC START envelope")

    if end_chunk.end_values is None:
        raise RCVerificationError("invalid SARAND RC END envelope")

    start_report_hash = start_chunk.start_values["report_hash"]
    end_report_hash = end_chunk.end_values["report_hash"]

    if start_report_hash != end_report_hash:
        raise RCVerificationError("START and END report_hash values do not match")

    if expected_report_hash is not None:
        if _HASH_RE.fullmatch(expected_report_hash) is None:
            raise RCVerificationError(
                f"invalid expected report_hash format: {expected_report_hash}"
            )

        if expected_report_hash != start_report_hash:
            raise RCVerificationError(
                "expected report_hash does not match report_hash in transfer envelope "
                f"(expected={expected_report_hash}, envelope={start_report_hash})"
            )

    present = set(counts)
    expected = set(range(1, total_chunks + 1))

    missing = sorted(expected - present)

    if missing:
        raise RCVerificationError(
            f"missing chunk index(es): {missing} (expected 1..{total_chunks})"
        )

    unexpected = sorted(present - expected)

    if unexpected:
        raise RCVerificationError(
            f"unexpected chunk index(es) outside 1..{total_chunks}: {unexpected}"
        )

    if len(parsed) != total_chunks:
        raise RCVerificationError(
            f"received {len(parsed)} chunks but expected {total_chunks}"
        )

    ordered = sorted(parsed, key=lambda chunk: chunk.chunk_index)
    reconstructed = "".join(chunk.body for chunk in ordered)
    actual_report_hash = _sha256(reconstructed)

    if actual_report_hash != start_report_hash:
        raise RCVerificationError(
            "reconstructed content hash does not match report_hash "
            f"(expected={start_report_hash}, actual={actual_report_hash}) -- "
            "reconstruction is not trustworthy, do not analyze"
        )

    if expected_report_hash is not None and actual_report_hash != expected_report_hash:
        raise RCVerificationError(
            "reconstructed content hash does not match report_hash "
            f"(expected={expected_report_hash}, actual={actual_report_hash}) -- "
            "reconstruction is not trustworthy, do not analyze"
        )

    return reconstructed
