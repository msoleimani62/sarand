"""RC session identity: session_id and report_id, and the fingerprint
chain that keeps a resumed transfer bound to the exact source content
it started against.

Identity hierarchy (RC constitution §50): SOURCE -> REPORT -> SESSION
-> CHUNK. This module owns the SESSION/REPORT layer only; SOURCE
fingerprinting stays in state.py (it already existed there and is
reused, not duplicated), CHUNK hashing stays in protocol.py.

هویت نشست RC: session_id و report_id، و زنجیره‌ی fingerprint که یک
انتقال ازسرگیری‌شده را به همان محتوای دقیق منبعی که با آن شروع شده
مقید نگه می‌دارد.

سلسله‌مراتب هویت (بخش ۵۰ قانون RC): SOURCE -> REPORT -> SESSION ->
CHUNK. این ماژول فقط لایه‌ی SESSION/REPORT را مالک است.
"""

from __future__ import annotations

import uuid


def new_session_id() -> str:
    return str(uuid.uuid4())


def report_id_from_hash(report_hash: str) -> str:
    """report_hash looks like 'sha256:<hex>' -- report_id is a short,
    human-pasteable prefix of the hex digest, not a separate identity."""
    digest = report_hash.split(":", 1)[-1]
    return digest[:16]
