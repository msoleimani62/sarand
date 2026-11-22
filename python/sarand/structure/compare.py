"""Comparing two structure snapshots (R14-D1, slice S1; contract in docs/STRUCTURE_BASELINE.md).

The question: what changed in the structure of a project between an older reference
(`old`) and the current state (`new`)? The answer keeps three things apart that are
easy to confuse:

- **identity and content**: symbols are matched with the match classes of
  `identity.py` (`exact`, `probable`, `ambiguous`, `unmatched`); a symbol with the same
  id and another fingerprint is `content_changed`, never removed plus added;
- **a real change and a change in coverage**: a file that is not fully parsed in one of
  the two snapshots, a path that moved into or out of the secret exclusion, and files
  that depend on a different size limit are *uncertain paths*. Whatever depends on such
  a path is reported `uncertain`, never as added or removed. Absence is not removal;
- **what can be compared**: the first field of the answer is a verdict.

Verdicts, in order of precedence (the first that applies wins; the facts behind the
lower ones stay in `reasons`, `fingerprints_comparable` and `uncertain_paths`):

1. `invalid`: a side is not a usable snapshot (the reason says which and why);
2. `incompatible`: a side is well formed but of a structure schema, snapshot format or
   language this code does not compare, or the two sides differ in them;
3. `partial`: there is at least one uncertain path, or the size limits differ;
4. `ids_only`: the fingerprint bases differ (another Python minor, or no fingerprints):
   symbols match by id only and no `content_changed` is claimed;
5. `comparable`.

With `invalid` and `incompatible` nothing is compared and the payload has no changes.
Output is deterministic: the same two references give the same bytes whatever the order
of the items inside them. Source lines and columns are evidence, never identity.

مقایسه‌ی دو عکس لحظه‌ای ساختار: هویت جدا از محتوا، تغییر واقعی جدا از تغییر پوشش، و حکم
اولِ پاسخ؛ نبودِ داده هرگز «حذف» حساب نمی‌شود.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sarand.structure.identity import (
    MATCH_AMBIGUOUS,
    MATCH_EXACT,
    MATCH_PROBABLE,
    REASON_REMOVED,
    SymbolRecord,
    match_symbols,
    records_from_payload,
)
from sarand.structure.snapshot import (
    PROBLEM_INCOMPATIBLE,
    Reference,
)

COMPARISON_SCHEMA = 1

VERDICT_COMPARABLE = "comparable"
VERDICT_IDS_ONLY = "ids_only"
VERDICT_PARTIAL = "partial"
VERDICT_INCOMPATIBLE = "incompatible"
VERDICT_INVALID = "invalid"
VERDICTS: tuple[str, ...] = (
    VERDICT_COMPARABLE,
    VERDICT_IDS_ONLY,
    VERDICT_PARTIAL,
    VERDICT_INCOMPATIBLE,
    VERDICT_INVALID,
)

ADDED = "added"
REMOVED = "removed"
CHANGED = "changed"
UNCERTAIN = "uncertain"
UNCHANGED = "unchanged"
CONTENT_CHANGED = "content_changed"
CONTENT_UNKNOWN = "content_unknown"
MOVED = "moved"
AMBIGUOUS = "ambiguous"
SYMBOL_STATUSES: tuple[str, ...] = (
    UNCHANGED,
    CONTENT_CHANGED,
    CONTENT_UNKNOWN,
    MOVED,
    AMBIGUOUS,
    ADDED,
    REMOVED,
    UNCERTAIN,
)
GENERIC_STATUSES: tuple[str, ...] = (UNCHANGED, ADDED, REMOVED, CHANGED, UNCERTAIN)
PARTS: tuple[str, ...] = (
    "files",
    "modules",
    "externals",
    "edges",
    "cycles",
    "symbols",
    "relations",
    "entry_points",
)

REASON_NOT_FULL = "not_fully_parsed"
REASON_EXCLUSION = "secret_exclusion_changed"
REASON_AMBIGUOUS_SYMBOL = "ambiguous_symbol"
REASON_UNCERTAIN_SYMBOL = "symbol_in_uncertain_file"
REASON_UNCERTAIN_PATH = "path_is_uncertain"
REASON_EXTERNALS = "coverage_is_incomplete"


@dataclass(frozen=True)
class StructureComparison:
    """The verdict and the full, canonical payload of one comparison."""

    verdict: str
    payload: Mapping[str, Any]

    def to_json(self) -> str:
        return (
            json.dumps(self.payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
        )


def compare_structures(old: Reference, new: Reference) -> StructureComparison:
    """Compare the reference `old` with the current state `new`."""
    reasons: list[str] = []
    for label, side in (("reference", old), ("current", new)):
        if not side.usable:
            reasons.append(f"{label}: {side.problem}")
    if reasons:
        invalid = any(
            side.problem_kind != PROBLEM_INCOMPATIBLE
            for side in (old, new)
            if not side.usable
        )
        verdict = VERDICT_INVALID if invalid else VERDICT_INCOMPATIBLE
        return _refusal(verdict, reasons, old, new)

    differ: list[str] = []
    for key, label in (("schema", "structure schema"), ("language", "language")):
        if old.structure[key] != new.structure[key]:
            differ.append(
                f"{label} differs: {old.structure[key]} and {new.structure[key]}; build "
                "the reference again with the same version"
            )
    if differ:
        return _refusal(VERDICT_INCOMPATIBLE, differ, old, new)

    old_records, old_basis = records_from_payload(old.structure)
    new_records, new_basis = records_from_payload(new.structure)
    match = match_symbols(
        old_records, new_records, old_basis=old_basis, new_basis=new_basis
    )

    uncertain = _uncertain_paths(old, new)
    reasons = []
    if uncertain:
        reasons.append(
            f"{len(uncertain)} path(s) are not comparable (see uncertain_paths)"
        )
    if (
        old.max_file_size is not None
        and new.max_file_size is not None
        and old.max_file_size != new.max_file_size
    ):
        reasons.append(
            f"the file size limits differ ({old.max_file_size} and {new.max_file_size})"
        )
    if not match.comparable:
        reasons.append(
            "the fingerprint bases differ or are missing "
            f"({old_basis or 'none'} and {new_basis or 'none'}): symbols match by id only"
        )
    if uncertain or any(r.startswith("the file size limits") for r in reasons):
        verdict = VERDICT_PARTIAL
    elif not match.comparable:
        verdict = VERDICT_IDS_ONLY
    else:
        verdict = VERDICT_COMPARABLE

    parts: dict[str, dict[str, Any]] = {}
    parts["files"] = _files(old, new, uncertain)
    parts["modules"] = _modules(old, new, uncertain)
    symbols, states = _symbols(old_records, new_records, match.rows, uncertain)
    parts["symbols"] = symbols
    parts["relations"] = _relations(old, new, states, uncertain)
    parts["edges"] = _edges(old, new, uncertain)
    parts["cycles"] = _cycles(old, new, uncertain)
    parts["entry_points"] = _entry_points(old, new, uncertain)
    parts["externals"] = _externals(old, new, bool(uncertain))

    payload: dict[str, Any] = {
        "schema": COMPARISON_SCHEMA,
        "verdict": verdict,
        "reasons": reasons,
        "fingerprints_comparable": match.comparable,
        "old": _side(old, old_basis),
        "new": _side(new, new_basis),
        "uncertain_paths": [
            {"path": path, "reasons": sorted(why)}
            for path, why in sorted(uncertain.items())
        ],
        "summary": {name: parts[name]["counts"] for name in PARTS},
        "changes": {name: parts[name]["entries"] for name in PARTS},
    }
    return StructureComparison(verdict, payload)


# ------------------------------------------------------------------- helpers


def _refusal(
    verdict: str, reasons: Sequence[str], old: Reference, new: Reference
) -> StructureComparison:
    payload = {
        "schema": COMPARISON_SCHEMA,
        "verdict": verdict,
        "reasons": list(reasons),
        "fingerprints_comparable": False,
        "old": _side(old, ""),
        "new": _side(new, ""),
        "uncertain_paths": [],
        "summary": {},
        "changes": {},
    }
    return StructureComparison(verdict, payload)


def _side(ref: Reference, basis: str) -> dict[str, Any]:
    if not ref.usable:
        return {"source": ref.source, "usable": False}
    meta = ref.structure.get("meta") or {}
    return {
        "source": ref.source,
        "usable": True,
        "structure_schema": ref.structure["schema"],
        "language": ref.structure["language"],
        "fingerprint_basis": basis,
        "interpreter": str(meta.get("interpreter", "")),
        "max_file_size": ref.max_file_size,
        "files": len(ref.structure["files"]),
        "symbols": len(ref.structure["symbols"]),
    }


def _uncertain_paths(old: Reference, new: Reference) -> dict[str, set[str]]:
    """Paths whose absence or change cannot be read as a real change."""
    out: dict[str, set[str]] = {}
    for side, ref in (("old", old), ("new", new)):
        for item in ref.structure["files"]:
            completeness = str(item["provenance"]["completeness"])
            if completeness != "full":
                out.setdefault(str(item["path"]), set()).add(
                    f"{REASON_NOT_FULL}:{side}:{completeness}"
                )
    for path in set(old.excluded_secret_files) ^ set(new.excluded_secret_files):
        out.setdefault(path, set()).add(REASON_EXCLUSION)
    return out


def _location_path(item: Mapping[str, Any]) -> str:
    location = item.get("location")
    return str(location.get("path", "")) if isinstance(location, Mapping) else ""


def _entry(status: str, key: Mapping[str, Any], **extra: Any) -> dict[str, Any]:
    return {"status": status, **key, **extra}


def _counts(
    statuses: Iterable[str], names: Sequence[str], unchanged: int
) -> dict[str, int]:
    counter = Counter(statuses)
    out = {name: counter.get(name, 0) for name in names}
    out[UNCHANGED] = unchanged
    return out


def _sorted(entries: list[dict[str, Any]], *keys: str) -> list[dict[str, Any]]:
    return sorted(
        entries, key=lambda e: tuple(json.dumps(e.get(k), sort_keys=True) for k in keys)
    )


def _part(
    entries: list[dict[str, Any]], unchanged: int, names: Sequence[str], *sort: str
) -> dict[str, Any]:
    ordered = _sorted(entries, *sort)
    return {
        "counts": _counts((e["status"] for e in ordered), names, unchanged),
        "entries": ordered,
    }


# --------------------------------------------------------------------- files


def _files(
    old: Reference, new: Reference, uncertain: Mapping[str, set[str]]
) -> dict[str, Any]:
    old_by = {str(f["path"]): f for f in old.structure["files"]}
    new_by = {str(f["path"]): f for f in new.structure["files"]}
    entries: list[dict[str, Any]] = []
    unchanged = 0
    for path in sorted(set(old_by) | set(new_by)):
        before, after = old_by.get(path), new_by.get(path)
        key: dict[str, Any] = {"path": path}
        if before is None or after is None:
            status = ADDED if before is None else REMOVED
        else:
            fields = [
                name
                for name, differs in (
                    ("content", before["sha256"] != after["sha256"]),
                    (
                        "completeness",
                        before["provenance"]["completeness"]
                        != after["provenance"]["completeness"],
                    ),
                    ("language", before.get("language") != after.get("language")),
                )
                if differs
            ]
            if not fields:
                unchanged += 1
                continue
            status = CHANGED
            key["fields"] = fields
        if path in uncertain:
            entries.append(_entry(UNCERTAIN, key, reasons=sorted(uncertain[path])))
        else:
            entries.append(_entry(status, key))
    return _part(entries, unchanged, GENERIC_STATUSES[1:], "path", "status")


def _modules(
    old: Reference, new: Reference, uncertain: Mapping[str, set[str]]
) -> dict[str, Any]:
    def index(ref: Reference) -> dict[tuple[str, str], Mapping[str, Any]]:
        return {(str(m["name"]), str(m["root"])): m for m in ref.structure["modules"]}

    old_by, new_by = index(old), index(new)
    entries: list[dict[str, Any]] = []
    unchanged = 0
    for ident in sorted(set(old_by) | set(new_by)):
        before, after = old_by.get(ident), new_by.get(ident)
        key: dict[str, Any] = {"name": ident[0], "root": ident[1]}
        paths = {str(m["path"]) for m in (before, after) if m is not None}
        if before is None or after is None:
            status = ADDED if before is None else REMOVED
        else:
            fields = [
                f
                for f in ("path", "is_package", "is_namespace")
                if before.get(f) != after.get(f)
            ]
            if not fields:
                unchanged += 1
                continue
            status = CHANGED
            key["fields"] = fields
        if paths & set(uncertain):
            entries.append(_entry(UNCERTAIN, key, reasons=[REASON_UNCERTAIN_PATH]))
        else:
            entries.append(_entry(status, key))
    return _part(entries, unchanged, GENERIC_STATUSES[1:], "name", "root", "status")


# ------------------------------------------------------------------- symbols


def _symbols(
    old_records: Sequence[SymbolRecord],
    new_records: Sequence[SymbolRecord],
    rows: Sequence[Any],
    uncertain: Mapping[str, set[str]],
) -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    """The symbol part and, for the relations, what happened to every symbol id."""
    old_by = {r.id: r for r in old_records}
    new_by = {r.id: r for r in new_records}
    states: dict[str, dict[str, str]] = {"old": {}, "new": {}, "map": {}}
    entries: list[dict[str, Any]] = []
    unchanged = 0
    for row in rows:
        old_ids, new_ids = tuple(row.old), tuple(row.new)
        recs = [old_by[i] for i in old_ids] + [new_by[i] for i in new_ids]
        first = min((r.path, r.qualname, r.kind) for r in recs)
        key: dict[str, Any] = {
            "path": first[0],
            "qualname": first[1],
            "kind": first[2],
            "old": list(old_ids),
            "new": list(new_ids),
        }
        shaky = bool({r.path for r in recs} & set(uncertain))
        if row.match in (MATCH_EXACT, MATCH_PROBABLE):
            states["old"][old_ids[0]] = "mapped"
            states["new"][new_ids[0]] = "mapped"
            states["map"][old_ids[0]] = new_ids[0]
            if row.match == MATCH_PROBABLE:
                status = MOVED
            elif row.content_changed is None:
                status = CONTENT_UNKNOWN
            elif row.content_changed:
                status = CONTENT_CHANGED
            else:
                unchanged += 1
                continue
            if shaky and status in (MOVED, CONTENT_CHANGED):
                entries.append(_entry(UNCERTAIN, key, reason=REASON_UNCERTAIN_PATH))
            else:
                entries.append(_entry(status, key, reason=row.reason))
        elif row.match == MATCH_AMBIGUOUS:
            for i in old_ids:
                states["old"][i] = "ambiguous"
            for i in new_ids:
                states["new"][i] = "ambiguous"
            entries.append(_entry(AMBIGUOUS, key, reason=row.reason))
        else:
            removed = row.reason == REASON_REMOVED
            side = "old" if removed else "new"
            ids = old_ids if removed else new_ids
            if shaky:
                for i in ids:
                    states[side][i] = UNCERTAIN
                entries.append(_entry(UNCERTAIN, key, reason=REASON_UNCERTAIN_PATH))
            else:
                for i in ids:
                    states[side][i] = REMOVED if removed else ADDED
                entries.append(
                    _entry(REMOVED if removed else ADDED, key, reason=row.reason)
                )
    part = _part(
        entries, unchanged, SYMBOL_STATUSES[1:], "path", "qualname", "kind", "status"
    )
    return part, states


# ----------------------------------------------------------------- relations


def _resolve(
    kind: str, value: str, side: str, states: Mapping[str, Mapping[str, str]]
) -> tuple[tuple[str, str] | None, str]:
    """A relation end in the space of the new snapshot, or why it has no place there."""
    if kind != "symbol":
        return ("name", value), ""
    state = states[side].get(value, UNCERTAIN)
    if state == "mapped":
        return ("symbol", states["map"][value] if side == "old" else value), ""
    if state in (ADDED, REMOVED):
        return None, "follows_symbol"
    return (
        None,
        REASON_AMBIGUOUS_SYMBOL if state == "ambiguous" else REASON_UNCERTAIN_SYMBOL,
    )


def _variant(item: Mapping[str, Any], *fields: str) -> tuple[Any, ...]:
    return tuple(
        tuple(sorted(item.get(f, []))) if f == "flags" else item.get(f, "")
        for f in fields
    )


_REL_FIELDS = ("confidence", "resolution_method", "original_type", "flags", "count")


def _relations(
    old: Reference,
    new: Reference,
    states: Mapping[str, Mapping[str, str]],
    uncertain: Mapping[str, set[str]],
) -> dict[str, Any]:
    names = {s["id"]: str(s["qualname"]) for s in old.structure["symbols"]}
    names.update({s["id"]: str(s["qualname"]) for s in new.structure["symbols"]})

    def label(end: tuple[str, str]) -> str:
        return names.get(end[1], end[1]) if end[0] == "symbol" else end[1]

    grouped: dict[str, dict[tuple[Any, ...], Counter[tuple[Any, ...]]]] = {
        "old": {},
        "new": {},
    }
    paths: dict[tuple[Any, ...], set[str]] = {}
    follows = {"old": 0, "new": 0}
    doubtful: Counter[tuple[str, str, str, str, str]] = Counter()
    for side, ref in (("old", old), ("new", new)):
        for rel in ref.structure["relations"]:
            source, why_s = _resolve(
                str(rel["source_kind"]), str(rel["source"]), side, states
            )
            target, why_t = _resolve(
                str(rel["target_kind"]), str(rel["target"]), side, states
            )
            reasons = [w for w in (why_s, why_t) if w and w != "follows_symbol"]
            if reasons:
                doubtful[
                    (
                        side,
                        str(rel["kind"]),
                        str(rel["source"]),
                        str(rel["target"]),
                        min(reasons),
                    )
                ] += 1
            elif source is None or target is None:
                follows[side] += 1
            else:
                key = (str(rel["kind"]), source, target)
                grouped[side].setdefault(key, Counter())[
                    _variant(rel, *_REL_FIELDS)
                ] += 1
                paths.setdefault(key, set()).add(_location_path(rel))

    def variants(counter: Counter[tuple[Any, ...]] | None) -> list[dict[str, Any]]:
        if counter is None:
            return []
        return [
            dict(zip(_REL_FIELDS, v, strict=True))
            for v in sorted(counter.elements(), key=repr)
        ]

    entries: list[dict[str, Any]] = []
    unchanged = 0
    for key in sorted(set(grouped["old"]) | set(grouped["new"]), key=repr):
        before, after = grouped["old"].get(key), grouped["new"].get(key)
        if before is not None and after is not None and before == after:
            unchanged += 1
            continue
        status = ADDED if before is None else REMOVED if after is None else CHANGED
        ident = {"kind": key[0], "source": label(key[1]), "target": label(key[2])}
        extra = {"old": variants(before), "new": variants(after)}
        if paths[key] & set(uncertain):
            entries.append(
                _entry(UNCERTAIN, ident, reason=REASON_UNCERTAIN_PATH, **extra)
            )
        else:
            entries.append(_entry(status, ident, **extra))
    for (d_side, d_kind, d_source, d_target, d_reason), count in sorted(
        doubtful.items()
    ):
        ident = {
            "kind": d_kind,
            "source": names.get(d_source, d_source),
            "target": names.get(d_target, d_target),
            "side": d_side,
        }
        entries.append(_entry(UNCERTAIN, ident, reason=d_reason, count=count))
    part = _part(
        entries,
        unchanged,
        GENERIC_STATUSES[1:],
        "kind",
        "source",
        "target",
        "side",
        "status",
    )
    part["counts"]["removed_with_symbol"] = follows["old"]
    part["counts"]["added_with_symbol"] = follows["new"]
    return part


# --------------------------------------------------------------------- edges


def _edges(
    old: Reference, new: Reference, uncertain: Mapping[str, set[str]]
) -> dict[str, Any]:
    fields = (
        "target",
        "target_class",
        "confidence",
        "resolution_method",
        "flags",
        "original_type",
    )
    grouped: dict[str, dict[tuple[str, str, str], set[tuple[Any, ...]]]] = {
        "old": {},
        "new": {},
    }
    paths: dict[tuple[str, str, str], set[str]] = {}
    for side, ref in (("old", old), ("new", new)):
        for edge in ref.structure["edges"]:
            key = (str(edge["kind"]), str(edge["source"]), str(edge["requested"]))
            grouped[side].setdefault(key, set()).add(_variant(edge, *fields))
            paths.setdefault(key, set()).add(_location_path(edge))

    def variants(items: set[tuple[Any, ...]] | None) -> list[dict[str, Any]]:
        return [
            dict(zip(fields, v, strict=True)) for v in sorted(items or (), key=repr)
        ]

    entries: list[dict[str, Any]] = []
    unchanged = 0
    for key in sorted(set(grouped["old"]) | set(grouped["new"])):
        before, after = grouped["old"].get(key), grouped["new"].get(key)
        if before is not None and before == after:
            unchanged += 1
            continue
        status = ADDED if before is None else REMOVED if after is None else CHANGED
        ident = {"kind": key[0], "source": key[1], "requested": key[2]}
        extra = {"old": variants(before), "new": variants(after)}
        if paths[key] & set(uncertain):
            entries.append(
                _entry(UNCERTAIN, ident, reason=REASON_UNCERTAIN_PATH, **extra)
            )
        else:
            entries.append(_entry(status, ident, **extra))
    return _part(
        entries,
        unchanged,
        GENERIC_STATUSES[1:],
        "kind",
        "source",
        "requested",
        "status",
    )


# ------------------------------------------------- cycles, entry points, externals


def _cycles(
    old: Reference, new: Reference, uncertain: Mapping[str, set[str]]
) -> dict[str, Any]:
    module_paths: dict[str, set[str]] = {}
    for ref in (old, new):
        for module in ref.structure["modules"]:
            module_paths.setdefault(str(module["name"]), set()).add(str(module["path"]))

    def index(ref: Reference) -> dict[tuple[str, ...], bool]:
        return {
            tuple(sorted(map(str, c["modules"]))): bool(c["eager"])
            for c in ref.structure["cycles"]
        }

    old_by, new_by = index(old), index(new)
    entries: list[dict[str, Any]] = []
    unchanged = 0
    for key in sorted(set(old_by) | set(new_by)):
        before, after = old_by.get(key), new_by.get(key)
        if before is not None and before == after:
            unchanged += 1
            continue
        status = ADDED if before is None else REMOVED if after is None else CHANGED
        ident = {"modules": list(key), "old_eager": before, "new_eager": after}
        member_paths: set[str] = set()
        for member in key:
            member_paths |= module_paths.get(member, set())
        if member_paths & set(uncertain):
            entries.append(_entry(UNCERTAIN, ident, reason=REASON_UNCERTAIN_PATH))
        else:
            entries.append(_entry(status, ident))
    return _part(entries, unchanged, GENERIC_STATUSES[1:], "modules", "status")


def _entry_points(
    old: Reference, new: Reference, uncertain: Mapping[str, set[str]]
) -> dict[str, Any]:
    fields = ("resolved", "confidence", "method")

    def index(ref: Reference) -> dict[tuple[str, str, str], tuple[Any, ...]]:
        return {
            (str(e["type"]), str(e["name"]), str(e["target"])): _variant(e, *fields)
            for e in ref.structure["entry_points"]
        }

    where: dict[tuple[str, str, str], set[str]] = {}
    for ref in (old, new):
        for e in ref.structure["entry_points"]:
            where.setdefault(
                (str(e["type"]), str(e["name"]), str(e["target"])), set()
            ).add(_location_path(e))
    old_by, new_by = index(old), index(new)
    entries: list[dict[str, Any]] = []
    unchanged = 0
    for key in sorted(set(old_by) | set(new_by)):
        before, after = old_by.get(key), new_by.get(key)
        if before is not None and before == after:
            unchanged += 1
            continue
        status = ADDED if before is None else REMOVED if after is None else CHANGED
        ident = {"type": key[0], "name": key[1], "target": key[2]}
        extra = {
            "old": dict(zip(fields, before, strict=True)) if before else None,
            "new": dict(zip(fields, after, strict=True)) if after else None,
        }
        if where[key] & set(uncertain):
            entries.append(
                _entry(UNCERTAIN, ident, reason=REASON_UNCERTAIN_PATH, **extra)
            )
        else:
            entries.append(_entry(status, ident, **extra))
    return _part(
        entries, unchanged, GENERIC_STATUSES[1:], "type", "name", "target", "status"
    )


def _externals(old: Reference, new: Reference, any_uncertain: bool) -> dict[str, Any]:
    def index(ref: Reference) -> dict[str, tuple[str, tuple[str, ...]]]:
        return {
            str(x["name"]): (
                str(x["target_class"]),
                tuple(sorted(map(str, x.get("declared_in", [])))),
            )
            for x in ref.structure["externals"]
        }

    old_by, new_by = index(old), index(new)
    entries: list[dict[str, Any]] = []
    unchanged = 0
    for name in sorted(set(old_by) | set(new_by)):
        before, after = old_by.get(name), new_by.get(name)
        if before is not None and before == after:
            unchanged += 1
            continue
        status = ADDED if before is None else REMOVED if after is None else CHANGED
        ident = {"name": name}
        extra = {
            "old": {"target_class": before[0], "declared_in": list(before[1])}
            if before
            else None,
            "new": {"target_class": after[0], "declared_in": list(after[1])}
            if after
            else None,
        }
        # With files that were not read in full, an external package that is no longer
        # imported may simply not have been seen.
        # با فایل‌های ناقص، بسته‌ی خارجیِ دیده‌نشده لزوماً حذف نشده است.
        if status == REMOVED and any_uncertain:
            entries.append(_entry(UNCERTAIN, ident, reason=REASON_EXTERNALS, **extra))
        else:
            entries.append(_entry(status, ident, **extra))
    return _part(entries, unchanged, GENERIC_STATUSES[1:], "name", "status")
