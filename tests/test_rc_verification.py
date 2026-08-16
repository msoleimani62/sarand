"""Tests for SARAND RC transfer verification.

تست‌های اعتبارسنجی انتقال SARAND RC.
"""

from __future__ import annotations

import hashlib

import pytest
from sarand.rc import protocol, verification


def _report_hash(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def make_chunk(
    *,
    content: str,
    index: int,
    total: int,
    session_id: str = "session-1",
    report_id: str = "report-1",
    start: bool = False,
    end: bool = False,
) -> str:
    envelope = ""

    if start:
        envelope += protocol.build_start(
            session_id=session_id,
            report_id=report_id,
            source="README.md",
            source_fingerprint="sha256:" + ("1" * 64),
            generated_at="2026-08-16T00:00:00+00:00",
            report_format="text",
            total_chunks=total,
            report_hash=_report_hash(content),
        )
        envelope += "\n"

    envelope += protocol.build_chunk_header(
        session_id=session_id,
        report_id=report_id,
        chunk_index=index,
        total_chunks=total,
        block=0,
        total_blocks=1,
        start_line=1,
        end_line=1,
        content=content,
    )
    envelope += content
    envelope += protocol.CHUNK_FOOTER

    if end:
        envelope += "\n"
        envelope += protocol.build_end(
            session_id=session_id,
            report_id=report_id,
            total_chunks_sent=total,
            report_hash=_report_hash(content),
        )

    return envelope


def make_transfer(
    contents: list[str],
    *,
    session_id: str = "session-1",
    report_id: str = "report-1",
) -> list[str]:
    total = len(contents)
    full_content = "".join(contents)
    report_hash = _report_hash(full_content)
    chunks: list[str] = []

    for index, content in enumerate(contents, start=1):
        envelope = ""

        if index == 1:
            envelope += protocol.build_start(
                session_id=session_id,
                report_id=report_id,
                source="README.md",
                source_fingerprint="sha256:" + ("1" * 64),
                generated_at="2026-08-16T00:00:00+00:00",
                report_format="text",
                total_chunks=total,
                report_hash=report_hash,
            )
            envelope += "\n"

        envelope += protocol.build_chunk_header(
            session_id=session_id,
            report_id=report_id,
            chunk_index=index,
            total_chunks=total,
            block=0,
            total_blocks=1,
            start_line=index,
            end_line=index,
            content=content,
        )
        envelope += content
        envelope += protocol.CHUNK_FOOTER

        if index == total:
            envelope += "\n"
            envelope += protocol.build_end(
                session_id=session_id,
                report_id=report_id,
                total_chunks_sent=total,
                report_hash=report_hash,
            )

        chunks.append(envelope)

    return chunks


def test_verify_transfer_accepts_valid_chunks() -> None:
    chunks = make_transfer(["alpha\n", "beta\n"])

    assert (
        verification.verify_transfer(
            chunks,
            expected_report_hash=_report_hash("alpha\nbeta\n"),
        )
        == "alpha\nbeta\n"
    )


def test_verify_transfer_preserves_final_newline() -> None:
    chunks = make_transfer(["alpha\n", "beta\n"])

    assert verification.verify_transfer(chunks) == "alpha\nbeta\n"


def test_verify_transfer_preserves_missing_final_newline() -> None:
    chunks = make_transfer(["alpha\n", "beta"])

    assert verification.verify_transfer(chunks) == "alpha\nbeta"


def test_verify_transfer_preserves_crlf() -> None:
    source = "alpha\r\nbeta\r\n"
    chunks = make_transfer(["alpha\r\n", "beta\r\n"])

    assert verification.verify_transfer(chunks) == source


def test_verify_transfer_accepts_out_of_order_chunks() -> None:
    chunks = make_transfer(["alpha\n", "beta\n", "gamma\n"])

    assert verification.verify_transfer([chunks[2], chunks[0], chunks[1]]) == (
        "alpha\nbeta\ngamma\n"
    )


def test_verify_transfer_rejects_duplicate_chunks() -> None:
    chunks = make_transfer(["alpha\n", "beta\n"])

    with pytest.raises(verification.RCVerificationError, match="duplicate"):
        verification.verify_transfer([chunks[0], chunks[1], chunks[1]])


def test_verify_transfer_rejects_missing_chunks() -> None:
    chunks = make_transfer(["alpha\n", "beta\n", "gamma\n"])

    with pytest.raises(verification.RCVerificationError, match="missing"):
        verification.verify_transfer([chunks[0], chunks[2]])


def test_verify_transfer_rejects_mixed_sessions() -> None:
    chunks = make_transfer(["alpha\n", "beta\n"])

    mixed = [
        chunks[0],
        chunks[1].replace("session-1", "session-2", 1),
    ]

    with pytest.raises(
        verification.RCVerificationError,
        match="different sessions|does not match",
    ):
        verification.verify_transfer(mixed)


def test_verify_transfer_rejects_report_hash_mismatch() -> None:
    chunks = make_transfer(["alpha\n"])

    wrong_hash = "sha256:" + ("0" * 64)

    with pytest.raises(
        verification.RCVerificationError,
        match="does not match report_hash",
    ):
        verification.verify_transfer(
            chunks,
            expected_report_hash=wrong_hash,
        )


def test_parse_chunk_rejects_body_hash_mismatch() -> None:
    chunk = make_transfer(["alpha\n"])[0]
    corrupted = chunk.replace("alpha\n", "ALPHA\n", 1)

    with pytest.raises(
        verification.RCVerificationError,
        match="chunk_hash mismatch",
    ):
        verification.parse_chunk(corrupted)


def test_parse_chunk_rejects_byte_count_mismatch() -> None:
    chunk = make_transfer(["alpha\n"])[0]
    corrupted = chunk.replace("chunk_bytes=6", "chunk_bytes=7", 1)

    with pytest.raises(
        verification.RCVerificationError,
        match="exceeds available chunk data|chunk_bytes mismatch|CHUNK-END",
    ):
        verification.parse_chunk(corrupted)


def test_parse_chunk_rejects_garbage_before_start() -> None:
    chunk = make_transfer(["alpha\n"])[0]

    with pytest.raises(
        verification.RCVerificationError,
        match="invalid SARAND RC START envelope",
    ):
        verification.parse_chunk("GARBAGE\n" + chunk)


def test_parse_chunk_rejects_garbage_after_end() -> None:
    chunk = make_transfer(["alpha\n"])[0]

    with pytest.raises(
        verification.RCVerificationError,
        match="invalid SARAND RC END envelope",
    ):
        verification.parse_chunk(chunk + "GARBAGE\n")


def test_parse_chunk_rejects_start_on_nonfirst_chunk() -> None:
    chunk = make_chunk(
        content="beta\n",
        index=2,
        total=2,
        start=True,
    )

    with pytest.raises(
        verification.RCVerificationError,
        match="START envelope is only valid on chunk 1",
    ):
        verification.parse_chunk(chunk)


def test_parse_chunk_rejects_end_on_nonfinal_chunk() -> None:
    chunk = make_chunk(
        content="alpha\n",
        index=1,
        total=2,
        end=True,
    )

    with pytest.raises(
        verification.RCVerificationError,
        match="END envelope is only valid on the final chunk",
    ):
        verification.parse_chunk(chunk)


def test_verify_transfer_requires_start() -> None:
    chunks = [
        make_chunk(content="alpha\n", index=1, total=2),
        make_chunk(content="beta\n", index=2, total=2, end=True),
    ]

    with pytest.raises(
        verification.RCVerificationError,
        match="exactly one START",
    ):
        verification.verify_transfer(chunks)


def test_verify_transfer_requires_end() -> None:
    chunks = [
        make_chunk(content="alpha\n", index=1, total=2, start=True),
        make_chunk(content="beta\n", index=2, total=2),
    ]

    with pytest.raises(
        verification.RCVerificationError,
        match="exactly one END",
    ):
        verification.verify_transfer(chunks)


def test_verify_transfer_rejects_invalid_expected_hash_format() -> None:
    chunks = make_transfer(["alpha\n"])

    with pytest.raises(
        verification.RCVerificationError,
        match="invalid expected report_hash format",
    ):
        verification.verify_transfer(
            chunks,
            expected_report_hash="not-a-hash",
        )


def test_parse_chunk_rejects_invalid_start_hash() -> None:
    chunk = make_transfer(["alpha\n"])[0]
    corrupted = chunk.replace(
        "report_hash=" + _report_hash("alpha\n"),
        "report_hash=invalid",
        1,
    )

    with pytest.raises(
        verification.RCVerificationError,
        match="invalid SARAND RC START envelope",
    ):
        verification.parse_chunk(corrupted)


def test_parse_chunk_rejects_start_metadata_mismatch() -> None:
    chunk = make_transfer(["alpha\n"])[0]
    corrupted = chunk.replace(
        "report_id=report-1",
        "report_id=wrong-report",
        1,
    )

    with pytest.raises(
        verification.RCVerificationError,
        match="START report_id does not match chunk",
    ):
        verification.parse_chunk(corrupted)


def test_parse_chunk_rejects_end_metadata_mismatch() -> None:
    chunk = make_transfer(["alpha\n"])[0]
    corrupted = chunk.replace(
        "report_id=report-1",
        "report_id=wrong-report",
        2,
    )

    with pytest.raises(
        verification.RCVerificationError,
        match="END report_id does not match chunk",
    ):
        verification.parse_chunk(corrupted)


def test_parse_chunk_accepts_footer_text_inside_body() -> None:
    content = "alpha\n----- SARAND RC CHUNK-END -----\nbeta\n"
    chunks = make_transfer([content])

    parsed = verification.parse_chunk(chunks[0])

    assert parsed.body == content


def test_parse_chunk_accepts_multibyte_utf8_body() -> None:
    content = "سلام دنیا\n"
    chunk = make_transfer([content])[0]

    parsed = verification.parse_chunk(chunk)

    assert parsed.body == content
    assert parsed.declared_bytes == len(content.encode("utf-8"))


def test_parse_chunk_rejects_declared_bytes_inside_utf8_character() -> None:
    content = "سلام\n"
    chunk = make_transfer([content])[0]
    declared_bytes = len(content.encode("utf-8"))
    corrupted = chunk.replace(
        f"chunk_bytes={declared_bytes}",
        f"chunk_bytes={declared_bytes - 1}",
        1,
    )

    with pytest.raises(
        verification.RCVerificationError,
        match="UTF-8 character|CHUNK-END|chunk_bytes",
    ):
        verification.parse_chunk(corrupted)


def test_parse_chunk_rejects_declared_body_longer_than_available_data() -> None:
    chunk = make_transfer(["alpha\n"])[0]
    corrupted = chunk.replace("chunk_bytes=6", "chunk_bytes=7", 1)

    with pytest.raises(
        verification.RCVerificationError,
        match="exceeds available chunk data|CHUNK-END|chunk_bytes",
    ):
        verification.parse_chunk(corrupted)


def test_parse_chunk_preserves_embedded_footer_text() -> None:
    content = "alpha\n----- SARAND RC CHUNK-END -----\nbeta\n"
    chunk = make_transfer([content])[0]

    parsed = verification.parse_chunk(chunk)

    assert parsed.body == content
