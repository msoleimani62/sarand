"""Findings baseline: what is new, fixed, unchanged or changed since a reference report
(R14-D1, slice F1; contract in docs/FINDINGS_BASELINE.md).

The reference is a previous JSON report. A finding is told apart by its R13 identity
(`core/finding_identity.py`, built from structured fields, never from text), so the same
problem stays the same finding when its wording, its order or its line number changes.

The one rule that matters: **a finding is `fixed` only when the check that reports it
ran to a verdict in the current run.** A check that was skipped, was inconclusive, could
not be run, or is simply absent gives no verdict; what depends on it is `not_checked`,
never `fixed` and never `new`. The same holds the other way round: a finding that the
reference could not have seen (its check did not run there) is not called `new`.

States (a finding is in exactly one):

- `new`          in the current run, not in the reference, and the reference could
                 have seen it;
- `fixed`        in the reference, not in the current run, and the current run checked;
- `unchanged`    in both, with the same evidence;
- `changed`      in both, with other evidence (`direction`: `worse`, `better` or
                 `neutral` where an order exists);
- `not_checked`  no verdict is possible, with the reason.

A class of findings that the reference schema did not record (for example advisories in
a 1.2 report) is `not_checked` as a class: everything in the current run of that class
is `not_checked`, nothing is `new`.

This module reads reports and results only. It never imports `sarand.structure`: the
cost of the structural comparison is not paid by this path (a test enforces it).

باز‌شناسی یافته‌ها نسبت به گزارش مرجع: «fixed» فقط وقتی که چکِ منبعِ آن در اجرای فعلی به
حکم رسیده باشد؛ وگرنه «not_checked». هیچ‌چیز به‌خاطر نبودِ داده «fixed» یا «new» نمی‌شود.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sarand.core.check_states import (
    EXECUTED_STATES,
    STATE_FAILED,
    STATE_INCONCLUSIVE,
    STATE_PASSED,
    STATE_SKIPPED,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    check_state,
)
from sarand.core.failures import GROUP_QUALITY, GROUP_SECURITY, GROUP_TEST
from sarand.core.finding_identity import (
    KIND_ADVISORY,
    KIND_SECRETS,
    failure_id,
    finding_id,
)
from sarand.models.results import CommandResult, Failure

COMPARISON_SCHEMA = 1
# A report is a few MB (more with embedded source); this stops a wrong file from being
# read whole.
# گزارش چند مگابایت است؛ این سقف جلوی خواندنِ کاملِ فایل اشتباه را می‌گیرد.
MAX_REFERENCE_BYTES = 512 * 1024 * 1024

STATE_NEW = "new"
STATE_FIXED = "fixed"
STATE_UNCHANGED = "unchanged"
STATE_CHANGED = "changed"
STATE_NOT_CHECKED = "not_checked"
STATES: tuple[str, ...] = (
    STATE_NEW,
    STATE_FIXED,
    STATE_UNCHANGED,
    STATE_CHANGED,
    STATE_NOT_CHECKED,
)

DIRECTION_WORSE = "worse"
DIRECTION_BETTER = "better"
DIRECTION_NEUTRAL = "neutral"

CLASS_FAILURES = "failures"
CLASS_ADVISORIES = "advisories"
CLASS_SECRETS = "secrets"
CLASSES: tuple[str, ...] = (CLASS_FAILURES, CLASS_ADVISORIES, CLASS_SECRETS)

# The first report schema that records each class completely: failures carry their id
# from 1.5, advisories exist from 1.3, secret findings were always in the report.
# اولین نسخه‌ی schema که هر دسته را کامل ثبت می‌کند.
MIN_SCHEMA: dict[str, tuple[int, int]] = {
    CLASS_FAILURES: (1, 5),
    CLASS_ADVISORIES: (1, 3),
    CLASS_SECRETS: (1, 0),
}

REASON_CLASS_NOT_RECORDED = "class_not_recorded_in_reference"
REASON_NO_SOURCE = "no_source_recorded"
REASON_FILE_NOT_SCANNED = "file_not_scanned"
REASON_FILE_SKIPPED = "file_skipped"
REFERENCE_PREFIX = "reference_"

PROBLEM_INVALID = "invalid"
PROBLEM_INCOMPATIBLE = "incompatible"

_SEVERITY_RANK = {
    "none": 0,
    "informational": 0,
    "low": 1,
    "medium": 2,
    "moderate": 2,
    "high": 3,
    "critical": 4,
}
_VERSION = re.compile(r"^(\d+)\.(\d+)$")

_RESULT_GROUPS: tuple[tuple[str, str], ...] = (
    ("test_results", GROUP_TEST),
    ("quality_results", GROUP_QUALITY),
    ("security_results", GROUP_SECURITY),
)


_KNOWN_STATES = frozenset(
    {
        STATE_PASSED,
        STATE_FAILED,
        STATE_SKIPPED,
        STATE_INCONCLUSIVE,
        STATE_UNAVAILABLE,
        STATE_UNKNOWN,
    }
)


class BaselineReferenceError(ValueError):
    """The reference report cannot be used (`kind` is `invalid` or `incompatible`)."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class FindingsView:
    """The findings of one report and what that report actually checked."""

    schema: tuple[int, int]
    failures: Mapping[str, Mapping[str, Any]]
    advisories: Mapping[str, Mapping[str, Any]]
    secrets: Mapping[str, Mapping[str, Any]]
    check_states: Mapping[str, str]  # "<group>/<check>" -> state
    scanned_files: frozenset[str]  # files whose content was scanned for secrets
    skipped_files: frozenset[str]  # files not scanned because they were too large
    source: str = "report"

    def records(self, name: str) -> bool:
        """Whether this report recorded the class completely."""
        return self.schema >= MIN_SCHEMA[name]

    def items(self, name: str) -> Mapping[str, Mapping[str, Any]]:
        return {
            CLASS_FAILURES: self.failures,
            CLASS_ADVISORIES: self.advisories,
            CLASS_SECRETS: self.secrets,
        }[name]


# ----------------------------------------------------------------- building views


def _merge_state(states: dict[str, str], key: str, state: str) -> None:
    """One key can have several results (one per package): it counts as executed only
    if every result was; otherwise the first non-executed state stays visible.
    یک کلید می‌تواند چند نتیجه داشته باشد؛ فقط وقتی «اجراشده» است که همه اجرا شده باشند."""
    known = states.get(key)
    if (
        known is None
        or (known in EXECUTED_STATES and state not in EXECUTED_STATES)
        or known in EXECUTED_STATES
        and state in EXECUTED_STATES
        and state == "failed"
    ):
        states[key] = state


def _states(groups: Iterable[tuple[str, Iterable[CommandResult]]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for group, results in groups:
        for result in results:
            _merge_state(out, f"{group}/{result.kind}", check_state(result))
    return out


def _failure_item(f: Failure, fid: str) -> dict[str, Any]:
    return {
        "id": fid,
        "tool": f.tool,
        "group": f.group,
        "category": f.category,
        "cause": f.cause,
        "subject": f.subject,
        "returncode": f.returncode,
        "signals": sorted(f.signals),
    }


def _advisory_item(
    advisory_id: str,
    package: str,
    version: str,
    severity: str | None,
    fixed_versions: Iterable[str],
    sources: Iterable[str],
) -> dict[str, Any]:
    return {
        "id": finding_id(KIND_ADVISORY, advisory_id, package, version),
        "advisory_id": advisory_id,
        "package": package,
        "version": version,
        "severity": severity,
        "fixed_versions": sorted(fixed_versions),
        "sources": sorted(sources),
    }


def _secret_items(pairs: Iterable[tuple[str, str]]) -> dict[str, dict[str, Any]]:
    counts: dict[tuple[str, str], int] = {}
    for pair in pairs:
        counts[pair] = counts.get(pair, 0) + 1
    return {
        finding_id(KIND_SECRETS, path, name): {
            "id": finding_id(KIND_SECRETS, path, name),
            "path": path,
            "pattern_name": name,
            "count": count,
        }
        for (path, name), count in sorted(counts.items())
    }


def current_view(
    *,
    schema: tuple[int, int],
    failures: Sequence[Failure],
    advisories: Iterable[Any],
    secret_findings: Iterable[Any],
    test_results: Iterable[CommandResult],
    quality_results: Iterable[CommandResult],
    security_results: Iterable[CommandResult],
    included_files: Iterable[str],
    excluded_secret_files: Iterable[str],
    skipped_files: Iterable[str],
) -> FindingsView:
    """The view of the run that has just finished, built from its result objects."""
    return FindingsView(
        schema=schema,
        failures={failure_id(f): _failure_item(f, failure_id(f)) for f in failures},
        advisories={
            item["id"]: item
            for item in (
                _advisory_item(
                    a.id, a.package, a.version, a.severity, a.fixed_versions, a.sources
                )
                for a in advisories
            )
        },
        secrets=_secret_items((s.path, s.pattern_name) for s in secret_findings),
        check_states=_states(
            (
                (GROUP_TEST, test_results),
                (GROUP_QUALITY, quality_results),
                (GROUP_SECURITY, security_results),
            )
        ),
        scanned_files=frozenset(included_files) | frozenset(excluded_secret_files),
        skipped_files=frozenset(skipped_files),
        source="current",
    )


# --------------------------------------------------------------- reading a report


def parse_schema(value: Any) -> tuple[int, int]:
    """`"1.10"` as (1, 10). Raises `BaselineReferenceError`."""
    match = _VERSION.match(value) if isinstance(value, str) else None
    if match is None:
        raise BaselineReferenceError(
            PROBLEM_INVALID, "the reference has no usable schema_version"
        )
    major, minor = int(match.group(1)), int(match.group(2))
    if major != 1:
        raise BaselineReferenceError(
            PROBLEM_INCOMPATIBLE,
            f"report schema {value} is not one this version reads (it reads 1.x)",
        )
    return major, minor


def _list(data: Mapping[str, Any], key: str) -> list[Any]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise BaselineReferenceError(PROBLEM_INVALID, f"{key} is not a list")
    return value


def _mapping(item: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(item, Mapping):
        raise BaselineReferenceError(PROBLEM_INVALID, f"{where} is not an object")
    return item


def _text(item: Mapping[str, Any], key: str, where: str) -> str:
    value = item.get(key)
    if not isinstance(value, str):
        raise BaselineReferenceError(PROBLEM_INVALID, f"{where} has no text `{key}`")
    return value


def read_report_view(data: Any) -> FindingsView:
    """The findings view of a parsed JSON report. Raises `BaselineReferenceError`."""
    if not isinstance(data, Mapping):
        raise BaselineReferenceError(
            PROBLEM_INVALID, "the reference is not a JSON object"
        )
    schema = parse_schema(data.get("schema_version"))

    failures: dict[str, dict[str, Any]] = {}
    if schema >= MIN_SCHEMA[CLASS_FAILURES]:
        for index, raw in enumerate(_list(data, "failures")):
            item = _mapping(raw, f"failures[{index}]")
            failure = Failure(
                tool=_text(item, "tool", f"failures[{index}]"),
                group=_text(item, "group", f"failures[{index}]"),
                category=_text(item, "category", f"failures[{index}]"),
                cause=str(item.get("cause", "exit_code")),
                subject=str(item.get("subject", "")),
                returncode=int(item.get("returncode", 0)),
                signals=tuple(str(s) for s in item.get("signals", [])),
            )
            failures[failure_id(failure)] = _failure_item(failure, failure_id(failure))

    advisories: dict[str, dict[str, Any]] = {}
    if schema >= MIN_SCHEMA[CLASS_ADVISORIES]:
        for index, raw in enumerate(_list(data, "advisories")):
            item = _mapping(raw, f"advisories[{index}]")
            where = f"advisories[{index}]"
            entry = _advisory_item(
                _text(item, "id", where),
                _text(item, "package", where),
                str(item.get("version", "")),
                item.get("severity") if isinstance(item.get("severity"), str) else None,
                (str(v) for v in item.get("fixed_versions", [])),
                (str(s) for s in item.get("sources", [])),
            )
            advisories[entry["id"]] = entry

    pairs = []
    for index, raw in enumerate(_list(data, "secret_findings")):
        item = _mapping(raw, f"secret_findings[{index}]")
        where = f"secret_findings[{index}]"
        pairs.append((_text(item, "path", where), _text(item, "pattern_name", where)))

    check_states: dict[str, str] = {}
    for key, group in _RESULT_GROUPS:
        for index, raw in enumerate(_list(data, key)):
            item = _mapping(raw, f"{key}[{index}]")
            kind = _text(item, "kind", f"{key}[{index}]")
            # The report's own `state` (schema 1.6) is the shared reading of the check;
            # older reports are derived with the same function from the raw fields.
            # `state` خودِ گزارش (شمای ۱٫۶) برداشت مشترک است؛ گزارش‌های قدیمی‌تر با همان
            # تابع از فیلدهای خام استنتاج می‌شوند.
            stored = item.get("state")
            if isinstance(stored, str) and stored in _KNOWN_STATES:
                state = stored
            else:
                state = check_state(
                    CommandResult(
                        kind=kind,
                        returncode=int(item.get("returncode", 0)),
                        summary=str(item.get("summary", "")),
                        raw_output=str(item.get("raw_output", "")),
                        skipped=bool(item.get("skipped", False)),
                        skip_reason=str(item.get("skip_reason", "")),
                        inconclusive_reason=str(item.get("inconclusive_reason", "")),
                    )
                )
            _merge_state(check_states, f"{group}/{kind}", state)

    skipped = []
    for raw in _list(data, "skipped_files"):
        if isinstance(raw, list) and raw and isinstance(raw[0], str):
            skipped.append(raw[0])
    return FindingsView(
        schema=schema,
        failures=failures,
        advisories=advisories,
        secrets=_secret_items(pairs),
        check_states=check_states,
        scanned_files=frozenset(str(p) for p in _list(data, "included_files"))
        | frozenset(str(p) for p in _list(data, "excluded_secret_files")),
        skipped_files=frozenset(skipped),
    )


def read_baseline_file(path: Path) -> FindingsView:
    """The findings view of the report in `path`. Raises `BaselineReferenceError`
    (never anything else) when the file cannot be used."""
    try:
        info = path.stat()
        if not path.is_file():
            raise BaselineReferenceError(
                PROBLEM_INVALID, f"{path} is not a regular file"
            )
        if info.st_size > MAX_REFERENCE_BYTES:
            raise BaselineReferenceError(
                PROBLEM_INVALID, f"{path} is larger than {MAX_REFERENCE_BYTES} bytes"
            )
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BaselineReferenceError(PROBLEM_INVALID, f"{path} does not exist") from exc
    except OSError as exc:
        raise BaselineReferenceError(
            PROBLEM_INVALID, f"{path} cannot be read: {exc.strerror or exc}"
        ) from exc
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise BaselineReferenceError(
            PROBLEM_INVALID, f"{path} is not valid JSON: {exc}"
        ) from exc
    return read_report_view(data)


# ------------------------------------------------------------------- comparing


def _check(view: FindingsView, key: str) -> tuple[bool, str]:
    """Did the check run to a verdict in this report? (and why not, if it did not)"""
    state = view.check_states.get(key)
    if state is None:
        return False, "check_not_run"
    return (True, "") if state in EXECUTED_STATES else (False, f"check_{state}")


def _all_checks(view: FindingsView, keys: Sequence[str]) -> tuple[bool, str]:
    if not keys:
        return False, REASON_NO_SOURCE
    for key in keys:
        ran, why = _check(view, key)
        if not ran:
            return False, why
    return True, ""


def _failure_gone(old: Mapping[str, Any], current: FindingsView) -> tuple[str, str]:
    ran, why = _check(current, f"{old['group']}/{old['tool']}")
    return (STATE_FIXED, "") if ran else (STATE_NOT_CHECKED, why)


def _failure_appeared(
    new: Mapping[str, Any], reference: FindingsView
) -> tuple[str, str]:
    ran, why = _check(reference, f"{new['group']}/{new['tool']}")
    return (STATE_NEW, "") if ran else (STATE_NOT_CHECKED, REFERENCE_PREFIX + why)


def _advisory_keys(item: Mapping[str, Any]) -> list[str]:
    return [f"{GROUP_SECURITY}/{source}" for source in item["sources"]]


def _advisory_gone(old: Mapping[str, Any], current: FindingsView) -> tuple[str, str]:
    ran, why = _all_checks(current, _advisory_keys(old))
    return (STATE_FIXED, "") if ran else (STATE_NOT_CHECKED, why)


def _advisory_appeared(
    new: Mapping[str, Any], reference: FindingsView
) -> tuple[str, str]:
    ran, why = _all_checks(reference, _advisory_keys(new))
    return (STATE_NEW, "") if ran else (STATE_NOT_CHECKED, REFERENCE_PREFIX + why)


def _secret_gone(old: Mapping[str, Any], current: FindingsView) -> tuple[str, str]:
    path = str(old["path"])
    if path in current.scanned_files:
        return STATE_FIXED, ""
    if path in current.skipped_files:
        return STATE_NOT_CHECKED, REASON_FILE_SKIPPED
    return STATE_NOT_CHECKED, REASON_FILE_NOT_SCANNED


def _secret_appeared(
    new: Mapping[str, Any], reference: FindingsView
) -> tuple[str, str]:
    if str(new["path"]) in reference.skipped_files:
        return STATE_NOT_CHECKED, REFERENCE_PREFIX + REASON_FILE_SKIPPED
    return STATE_NEW, ""


def _failure_changed(old: Mapping[str, Any], new: Mapping[str, Any]) -> str | None:
    if old["returncode"] != new["returncode"] or old["signals"] != new["signals"]:
        return DIRECTION_NEUTRAL
    return None


def _severity_rank(value: str | None) -> int | None:
    return None if value is None else _SEVERITY_RANK.get(value.strip().lower())


def _advisory_changed(old: Mapping[str, Any], new: Mapping[str, Any]) -> str | None:
    before, after = _severity_rank(old["severity"]), _severity_rank(new["severity"])
    if before is not None and after is not None:
        # Known labels compare by rank: `medium` and `moderate` are the same level.
        # برچسب‌های شناخته با رتبه سنجیده می‌شوند: `medium` و `moderate` یک سطح‌اند.
        if before != after:
            return DIRECTION_WORSE if after > before else DIRECTION_BETTER
    elif old["severity"] != new["severity"]:
        return DIRECTION_NEUTRAL
    if old["fixed_versions"] != new["fixed_versions"]:
        return DIRECTION_NEUTRAL
    return None


def _secret_changed(old: Mapping[str, Any], new: Mapping[str, Any]) -> str | None:
    if old["count"] == new["count"]:
        return None
    return DIRECTION_WORSE if new["count"] > old["count"] else DIRECTION_BETTER


_RULES: dict[str, tuple[Any, Any, Any]] = {
    CLASS_FAILURES: (_failure_gone, _failure_appeared, _failure_changed),
    CLASS_ADVISORIES: (_advisory_gone, _advisory_appeared, _advisory_changed),
    CLASS_SECRETS: (_secret_gone, _secret_appeared, _secret_changed),
}
_LABEL_FIELDS: dict[str, tuple[str, ...]] = {
    CLASS_FAILURES: ("tool", "group", "category", "subject"),
    CLASS_ADVISORIES: ("advisory_id", "package", "version"),
    CLASS_SECRETS: ("path", "pattern_name"),
}


def _entry(
    name: str,
    fid: str,
    state: str,
    reason: str,
    old: Mapping[str, Any] | None,
    new: Mapping[str, Any] | None,
    direction: str | None = None,
) -> dict[str, Any]:
    shown = new if new is not None else old
    entry: dict[str, Any] = {"id": fid, "state": state}
    if shown is not None:
        entry.update({k: shown[k] for k in _LABEL_FIELDS[name]})
    if reason:
        entry["reason"] = reason
    if direction:
        entry["direction"] = direction
    entry["old"] = dict(old) if old is not None else None
    entry["new"] = dict(new) if new is not None else None
    return entry


def _compare_class(
    name: str, old: FindingsView, new: FindingsView
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    gone, appeared, changed = _RULES[name]
    entries: list[dict[str, Any]] = []
    counts = dict.fromkeys(STATES, 0)
    old_items, new_items = old.items(name), new.items(name)
    if not old.records(name):
        for fid in sorted(new_items):
            entries.append(
                _entry(
                    name,
                    fid,
                    STATE_NOT_CHECKED,
                    REASON_CLASS_NOT_RECORDED,
                    None,
                    new_items[fid],
                )
            )
            counts[STATE_NOT_CHECKED] += 1
        return entries, counts
    for fid in sorted(set(old_items) | set(new_items)):
        before, after = old_items.get(fid), new_items.get(fid)
        if before is not None and after is not None:
            direction = changed(before, after)
            if direction is None:
                counts[STATE_UNCHANGED] += 1
                continue
            counts[STATE_CHANGED] += 1
            entries.append(
                _entry(name, fid, STATE_CHANGED, "", before, after, direction)
            )
        elif before is not None:
            state, reason = gone(before, new)
            counts[state] += 1
            entries.append(_entry(name, fid, state, reason, before, None))
        elif after is not None:
            state, reason = appeared(after, old)
            counts[state] += 1
            entries.append(_entry(name, fid, state, reason, None, after))
    return entries, counts


def compare_findings(old: FindingsView, new: FindingsView) -> dict[str, Any]:
    """Compare the reference `old` with the current run `new`. Pure and deterministic."""
    findings: dict[str, list[dict[str, Any]]] = {}
    summary: dict[str, dict[str, int]] = {}
    for name in CLASSES:
        findings[name], summary[name] = _compare_class(name, old, new)
    return {
        "schema": COMPARISON_SCHEMA,
        "reference": {
            "schema_version": f"{old.schema[0]}.{old.schema[1]}",
            "classes_not_recorded": [c for c in CLASSES if not old.records(c)],
        },
        "current": {"schema_version": f"{new.schema[0]}.{new.schema[1]}"},
        "summary": summary,
        "findings": findings,
    }
