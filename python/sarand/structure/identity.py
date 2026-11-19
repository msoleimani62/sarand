"""Matching the symbols of two repository states (R14-A3, plan section 8).

The question: given the symbols of an older output and of a newer one, which symbol
of the new state *is* which symbol of the old one? A baseline (R14-D) needs this; R14-A
only establishes and tests the design. Four answers exist and none is allowed to turn
into a stronger one silently:

- `exact`: the same symbol id (language, kind, repo-relative path, qualified name,
  `#n` ordinal) and nothing makes it doubtful. `content_changed` says whether the
  fingerprint differs (`None` when fingerprints cannot be compared).
- `probable`: the same kind, qualified name and `fp1` fingerprint at a *different*
  path (a move), with exactly one candidate on each side.
- `ambiguous`: more than one candidate on at least one side (a duplicated qualified
  name, or several equally good move candidates). Every candidate id is listed; none
  is chosen.
- `unmatched`: nothing on the other side (`removed` or `added`). A rename of a symbol
  is an unmatched pair on purpose: R14-A does not guess renames.

Fingerprints are compared only when both outputs carry the same
`meta.fingerprint_basis` (`fp1/python-<minor>`); otherwise only ids can match and
`comparable` is false in the result. Every old and every new symbol appears in exactly
one row.

مطابقت نمادهای دو وضعیت مخزن؛ چهار پاسخ و هیچ‌کدام بی‌صدا قوی‌تر نمی‌شود.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

MATCH_EXACT = "exact"
MATCH_PROBABLE = "probable"
MATCH_AMBIGUOUS = "ambiguous"
MATCH_UNMATCHED = "unmatched"
MATCH_CLASSES: tuple[str, ...] = (
    MATCH_EXACT,
    MATCH_PROBABLE,
    MATCH_AMBIGUOUS,
    MATCH_UNMATCHED,
)

REASON_SAME_ID = "same_id"
REASON_MOVED = "same_content_other_path"
REASON_DUPLICATE_NAME = "duplicate_qualified_name"
REASON_SEVERAL_CANDIDATES = "several_candidates"
REASON_REMOVED = "removed"
REASON_ADDED = "added"
REASON_LANGUAGE = "language_differs"
MATCH_REASONS: tuple[str, ...] = (
    REASON_SAME_ID,
    REASON_MOVED,
    REASON_DUPLICATE_NAME,
    REASON_SEVERAL_CANDIDATES,
    REASON_REMOVED,
    REASON_ADDED,
    REASON_LANGUAGE,
)


@dataclass(frozen=True)
class SymbolRecord:
    """What matching needs from a symbol (so it also works on a stored JSON output)."""

    id: str
    kind: str
    path: str
    qualname: str
    fingerprint: str = ""


@dataclass(frozen=True)
class SymbolMatch:
    """One row of a match result. `old` and `new` hold the symbol ids involved: one
    each for `exact` and `probable`, one side empty for `unmatched`, the whole
    candidate set for `ambiguous`."""

    match: str
    reason: str
    old: tuple[str, ...]
    new: tuple[str, ...]
    content_changed: bool | None = None


@dataclass(frozen=True)
class MatchResult:
    rows: tuple[SymbolMatch, ...]
    comparable: bool
    old_basis: str
    new_basis: str

    def counts(self) -> dict[str, int]:
        """Rows per match class (every class present, in the closed order)."""
        out = {name: 0 for name in MATCH_CLASSES}
        for row in self.rows:
            out[row.match] += 1
        return out

    def of(self, match: str) -> tuple[SymbolMatch, ...]:
        return tuple(row for row in self.rows if row.match == match)


def records_from_symbols(symbols: Iterable[Any]) -> list[SymbolRecord]:
    """Records from `Symbol` objects (anything with the same attributes)."""
    return [
        SymbolRecord(s.id, s.kind, s.path, s.qualname, s.fingerprint) for s in symbols
    ]


def records_from_payload(payload: Mapping[str, Any]) -> tuple[list[SymbolRecord], str]:
    """Records and the fingerprint basis from a `structure` JSON payload.

    A payload that predates schema 3 has no fingerprints and no basis: its records get
    an empty fingerprint and the basis is empty, so only ids can match.
    """
    meta = payload.get("meta") or {}
    basis = str(meta.get("fingerprint_basis", "")) if isinstance(meta, Mapping) else ""
    records = [
        SymbolRecord(
            str(s["id"]),
            str(s["kind"]),
            str(s["path"]),
            str(s["qualname"]),
            str(s.get("fingerprint", "")),
        )
        for s in payload.get("symbols", [])
    ]
    return records, basis


def match_symbols(
    old: Sequence[SymbolRecord],
    new: Sequence[SymbolRecord],
    *,
    old_basis: str = "",
    new_basis: str = "",
    old_language: str = "python",
    new_language: str = "python",
) -> MatchResult:
    """Match two symbol lists. Deterministic: the result does not depend on the order
    of the inputs."""
    old_sorted = sorted(old, key=_record_key)
    new_sorted = sorted(new, key=_record_key)
    if old_language != new_language:
        other_language = [
            SymbolMatch(MATCH_UNMATCHED, REASON_LANGUAGE, (r.id,), ())
            for r in old_sorted
        ] + [
            SymbolMatch(MATCH_UNMATCHED, REASON_LANGUAGE, (), (r.id,))
            for r in new_sorted
        ]
        return MatchResult(tuple(other_language), False, old_basis, new_basis)
    comparable = bool(old_basis) and old_basis == new_basis

    rows: list[SymbolMatch] = []
    old_by_id = {r.id: r for r in old_sorted}
    new_by_id = {r.id: r for r in new_sorted}
    pool_old: dict[str, SymbolRecord] = dict(old_by_id)
    pool_new: dict[str, SymbolRecord] = dict(new_by_id)

    # Step 1: the same id. A (kind, path, qualified name) that occurs more than once on
    # either side can pair only by equal content; the rest is ambiguous.
    # گام ۱: همان شناسه؛ نام تکراری فقط با محتوای برابر جفت می‌شود.
    groups_old = _group(old_sorted, lambda r: (r.kind, r.path, r.qualname))
    groups_new = _group(new_sorted, lambda r: (r.kind, r.path, r.qualname))
    for key in sorted(set(groups_old) | set(groups_new)):
        olds = groups_old.get(key, [])
        news = groups_new.get(key, [])
        duplicated = len(olds) > 1 or len(news) > 1
        left_old: list[SymbolRecord] = []
        left_new_ids = {r.id for r in news}
        for rec in olds:
            twin = new_by_id.get(rec.id)
            if twin is not None and (key == (twin.kind, twin.path, twin.qualname)):
                same = (
                    comparable
                    and bool(rec.fingerprint)
                    and rec.fingerprint == twin.fingerprint
                )
                if not duplicated or same:
                    rows.append(
                        SymbolMatch(
                            MATCH_EXACT,
                            REASON_SAME_ID,
                            (rec.id,),
                            (twin.id,),
                            _changed(rec, twin, comparable),
                        )
                    )
                    pool_old.pop(rec.id, None)
                    pool_new.pop(twin.id, None)
                    left_new_ids.discard(twin.id)
                    continue
            left_old.append(rec)
        left_new = [r for r in news if r.id in left_new_ids]
        if duplicated and left_old and left_new:
            rows.append(
                SymbolMatch(
                    MATCH_AMBIGUOUS,
                    REASON_DUPLICATE_NAME,
                    tuple(r.id for r in left_old),
                    tuple(r.id for r in left_new),
                )
            )
            for rec in left_old:
                pool_old.pop(rec.id, None)
            for rec in left_new:
                pool_new.pop(rec.id, None)

    # Step 2: a move, by kind + qualified name + fingerprint.
    # گام ۲: جابه‌جایی؛ با نوع + نام کامل + بصمت.
    if comparable:
        by_content_old = _group(
            [r for r in pool_old.values() if r.fingerprint],
            lambda r: (r.kind, r.qualname, r.fingerprint),
        )
        by_content_new = _group(
            [r for r in pool_new.values() if r.fingerprint],
            lambda r: (r.kind, r.qualname, r.fingerprint),
        )
        for key in sorted(set(by_content_old) & set(by_content_new)):
            olds = by_content_old[key]
            news = by_content_new[key]
            if len(olds) == 1 and len(news) == 1:
                if olds[0].path == news[0].path:
                    continue
                rows.append(
                    SymbolMatch(
                        MATCH_PROBABLE,
                        REASON_MOVED,
                        (olds[0].id,),
                        (news[0].id,),
                        False,
                    )
                )
            else:
                if not any(old.path != new.path for old in olds for new in news):
                    continue
                rows.append(
                    SymbolMatch(
                        MATCH_AMBIGUOUS,
                        REASON_SEVERAL_CANDIDATES,
                        tuple(r.id for r in olds),
                        tuple(r.id for r in news),
                    )
                )
            for rec in olds:
                pool_old.pop(rec.id, None)
            for rec in news:
                pool_new.pop(rec.id, None)

    # Step 3: whatever is left has no counterpart.
    # گام ۳: باقی‌مانده بدون جفت است.
    for rec in sorted(pool_old.values(), key=_record_key):
        rows.append(SymbolMatch(MATCH_UNMATCHED, REASON_REMOVED, (rec.id,), ()))
    for rec in sorted(pool_new.values(), key=_record_key):
        rows.append(SymbolMatch(MATCH_UNMATCHED, REASON_ADDED, (), (rec.id,)))

    rows.sort(key=_row_key)
    return MatchResult(tuple(rows), comparable, old_basis, new_basis)


def _changed(old: SymbolRecord, new: SymbolRecord, comparable: bool) -> bool | None:
    if not comparable or not old.fingerprint or not new.fingerprint:
        return None
    return old.fingerprint != new.fingerprint


def _record_key(record: SymbolRecord) -> tuple[str, str, str, str, str]:
    return (record.path, record.qualname, record.kind, record.id, record.fingerprint)


def _row_key(row: SymbolMatch) -> tuple[int, tuple[str, ...], tuple[str, ...], str]:
    return (MATCH_CLASSES.index(row.match), row.old, row.new, row.reason)


def _group(
    records: Iterable[SymbolRecord], key: Any
) -> dict[tuple[str, ...], list[SymbolRecord]]:
    out: dict[tuple[str, ...], list[SymbolRecord]] = {}
    for record in records:
        out.setdefault(key(record), []).append(record)
    return out
