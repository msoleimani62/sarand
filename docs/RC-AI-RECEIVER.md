# SARAND RC — AI Receiver Contract

Protocol version covered: 1 (see `python/sarand/rc/protocol.py`).

This document is the counterpart to the sender-side implementation.
It tells an AI (or any automated consumer) receiving a SARAND RC
transmission — pasted into a chat, one message per chunk — exactly
how to behave, and mirrors the checks implemented in
`python/sarand/rc/verification.py`.

## 1. The three markers

A transmission of `total_chunks` chunks looks like:

```
==================== SARAND RC START ====================
...metadata + AI-INSTRUCTIONS...
==================== SARAND RC START-END ====================

----- SARAND RC CHUNK 1/N -----
...metadata...
----- SARAND RC CHUNK-BODY -----
...raw content...
----- SARAND RC CHUNK-END -----

----- SARAND RC CHUNK 2/N -----
...
----- SARAND RC CHUNK-END -----

...

==================== SARAND RC END ====================
session_id=...
report_id=...
total_chunks_sent=N
report_hash=sha256:...
==================== SARAND RC END-END ====================
```

`START` appears only on chunk 1's message. `END` appears only on the
final chunk's message (`chunk_index == total_chunks`). Every message
in between contains exactly one `CHUNK` block and nothing else that
matters to the protocol.

## 2. Receiver state machine

```
NOT_STARTED -> RECEIVING -> WAITING -> COMPLETE(candidate) -> VERIFIED
                                            |
                                            v
                                        INVALID
```

- **NOT_STARTED**: no `SARAND RC START` seen yet.
- **RECEIVING**: `START` seen, chunks arriving. Record each chunk's
  `chunk_index`, `total_chunks`, `chunk_hash`, and body as it arrives.
- **WAITING**: between messages. A user saying "continue" or "ادامه"
  while in this state means *keep receiving*, not *analyze what you
  have*.
- **COMPLETE (candidate)**: `SARAND RC END` has been seen. This is
  NOT yet safe to analyze — proceed to verification.
- **VERIFIED**: all four checks below passed. Only now is the content
  safe to read, summarize, or act on.
- **INVALID**: any check failed. State the exact reason (never a bare
  "invalid") and ask the user to resend the specific missing/corrupt
  chunk — never guess or paper over the gap.

## 3. The four mandatory checks (do all four, in order, every time)

1. **Completeness** — every index `1..total_chunks` was received
   exactly once. No gaps, no duplicates, no index outside that range.
2. **Identity consistency** — every chunk's `session_id` and
   `report_id` match the ones from `START`. A chunk with a different
   `session_id` belongs to a different transfer and must be rejected,
   not merged in.
3. **Per-chunk integrity** — for each chunk, recompute
   `sha256(body)` and compare to that chunk's declared `chunk_hash`.
   Any mismatch means that specific chunk was altered, truncated, or
   corrupted in the chat transport — reject it by name (e.g. "chunk
   7/31 is corrupted").
4. **Whole-transfer integrity** — concatenate all chunk bodies in
   order `1..total_chunks`, compute `sha256` of the result, and
   compare to `report_hash` from `START` (which must also equal the
   `report_hash` repeated in `END` — if those two differ from each
   other, the transmission itself is inconsistent and must be
   rejected regardless of anything else).

If a check is genuinely impossible to run without executing code
(e.g. no sandboxed hashing available), say so explicitly instead of
skipping it silently — "I cannot verify chunk_hash without a hashing
tool; treat this as UNVERIFIED, not VERIFIED" is honest; silently
proceeding as if it passed is not.

## 4. Hard rules

- `START` does not mean complete. `CHUNK` does not mean complete.
  `END` does not mean verified. Only VERIFIED (all four checks
  passed) means the content may be treated as the real report.
- Never summarize, analyze, act on, or draw conclusions from a
  transfer that has not reached VERIFIED.
- Never silently drop, reorder, or "helpfully" patch over a missing
  or corrupted chunk. Report exactly which chunk and why.
- Never treat a chunk from a different `session_id` as part of the
  current transfer, even if the content looks plausible.
- If the user pastes chunks out of order, that's fine — indices are
  explicit in each header. Buffer them and check completeness once
  `END` arrives; do not require strict arrival order.

## 5. Self-check command (sender side)

Before ever pasting a transfer, the sender can independently confirm
the chunk files already saved on disk are complete and correct with:

```bash
python3 -m sarand.rc.command --source <path> --verify
```

This runs the exact same four checks listed above against the local
chunk files (not the chat transcript), and prints `status=VERIFIED` or
`status=INVALID` with the specific reason to stderr.
