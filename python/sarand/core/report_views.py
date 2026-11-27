"""R13-G: what every renderer shows, decided once.

Markdown, HTML, SARIF and Quick Context used to compute the same lists
themselves (the errors and warnings, the failure rows, the advisory rows), so
two formats could show different counts for one report. This module is the one
place that decides them; a renderer only chooses how to draw the result.
It adds no analysis: it reads `ReportData` and the shared helpers.

Pure and deterministic.

هر رندر خودش این فهرست‌ها را حساب می‌کرد؛ حالا یک جا تصمیم گرفته می‌شود و رندر
فقط نمایش را انتخاب می‌کند.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sarand.core.advisories import is_advisory_line
from sarand.core.check_states import check_state
from sarand.core.finding_identity import failure_id
from sarand.models.results import Issue, ReportData


@dataclass(frozen=True)
class IssueView:
    """The tool errors and warnings of a report, each counted once.

    A tool line that an advisory already represents (cargo audit's
    `Warning:   unsound`, cargo deny's `error[vulnerability]`) is not listed
    again: it is counted in `in_advisories`, and the check's own output still
    shows it in full.
    """

    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    in_advisories: int = 0
    # Every kept issue in the order the checks reported them (per check: its
    # warnings, then its errors); the same issues as `warnings` + `errors`.
    # همه‌ی issueهای نگه‌داشته‌شده به ترتیب گزارش چک‌ها.
    ordered: list[Issue] = field(default_factory=list)


def collect_issues(data: ReportData) -> IssueView:
    errors: list[Issue] = []
    warnings: list[Issue] = []
    ordered: list[Issue] = []
    represented = 0
    for result in data.test_results + data.quality_results + data.security_results:
        for bucket, issues in ((warnings, result.warnings), (errors, result.errors)):
            for issue in issues:
                if data.advisories and is_advisory_line(issue, data.advisories):
                    represented += 1
                else:
                    bucket.append(issue)
                    ordered.append(issue)
    return IssueView(
        errors=errors, warnings=warnings, in_advisories=represented, ordered=ordered
    )


def advisory_line_note(view: IssueView) -> str:
    """The sentence that says some tool lines are listed as advisories instead."""
    if not view.in_advisories:
        return ""
    return (
        f"{view.in_advisories} tool line(s) that restate a dependency advisory "
        "are listed under Dependency advisories, not here."
    )


FAILURE_COLUMNS: tuple[str, ...] = (
    "Tool",
    "Group",
    "Category",
    "Cause",
    "Subject",
    "Evidence",
    "Id",
)


def failure_rows(data: ReportData) -> list[tuple[str, ...]]:
    """One row per classified failure, in the order of `data.failures`."""
    return [
        (
            f.tool,
            f.group or "-",
            f.category,
            f.cause,
            f.subject or "-",
            ", ".join(f.signals) or "-",
            failure_id(f),
        )
        for f in data.failures
    ]


ADVISORY_COLUMNS: tuple[str, ...] = (
    "ID",
    "Package",
    "Version",
    "Kind",
    "Severity",
    "Fixed in",
    "Reported by",
    "Applicability",
)

ADVISORY_NOTE = (
    "These are tool results, not proof that this project is exploitable: "
    "no reachability analysis was done, so applicability is unknown for "
    "every row. Severity is shown only when the tool printed one."
)


def advisory_rows(data: ReportData) -> list[tuple[str, ...]]:
    return [
        (
            a.id,
            a.package,
            a.version,
            a.kind,
            a.severity or "-",
            ", ".join(a.fixed_versions) or "-",
            ", ".join(a.sources),
            a.applicability,
        )
        for a in data.advisories
    ]


def advisory_intro(data: ReportData) -> str:
    return (
        f"{len(data.advisories)} advisory(ies) reported by the security tools. "
        f"{ADVISORY_NOTE}"
    )


def advisory_databases(data: ReportData) -> list[str]:
    return sorted({a.database for a in data.advisories if a.database})


def check_state_rows(data: ReportData) -> list[tuple[str, str, str]]:
    """(group, check, state) for every requested check, in report order. The state
    is the shared reading of core/check_states.py (R13-D); a format that cannot
    show a badge carries these rows as metadata instead."""
    rows: list[tuple[str, str, str]] = []
    for group, results in (
        ("tests", data.test_results),
        ("quality", data.quality_results),
        ("security", data.security_results),
    ):
        rows.extend((group, r.kind, check_state(r)) for r in results)
    return rows


# --- repository structure (R14-A, `--structure`) -------------------------------------

STRUCTURE_NOTE = (
    "Read statically with `ast`; no repository code was executed. A relationship "
    "that was not detected is not proof that it does not exist at run time "
    "(dynamic imports, `getattr`, plugins)."
)


def structure_lines(data: ReportData) -> list[str]:
    """The summary lines of the structure, the same for every format."""
    if data.structure is None:
        return []
    from sarand.structure.serialize import summary

    s = summary(data.structure)
    by_file = s["files_by_completeness"]
    by_class = s["imports_by_class"]
    by_conf = s["imports_by_confidence"]
    kinds = s["symbols_by_kind"]
    rel = s["relations_by_kind"]
    rconf = s["relations_by_confidence"]
    sites = data.structure.sites
    return [
        (
            f"Python files: {s['files']} (parsed fully {by_file['full']}, partly "
            f"{by_file['partial']}, failed {by_file['failed']}, skipped as too large "
            f"{by_file['skipped_size']})"
        ),
        (
            f"Modules: {s['modules']} ({s['packages']} packages, "
            f"{s['namespace_packages']} namespace packages)"
        ),
        (
            f"Imports: {s['imports']} (repository {by_class['internal']}, standard "
            f"library {by_class['stdlib']}, declared external "
            f"{by_class['external_declared']}, unmatched external "
            f"{by_class['external_unmatched']}, unresolved "
            f"{by_class['internal_unresolved']}, dynamic {by_class['dynamic']})"
        ),
        (
            f"Confidence of imports: definite {by_conf['definite']}, probable "
            f"{by_conf['probable']}, unknown {by_conf['unknown']}"
        ),
        (
            f"Import cycles: {s['cycles']} ({s['eager_cycles']} eager, that is able to "
            "fail at import time)"
        ),
        (
            f"Symbols: {s['symbols']} (classes {kinds['class']}, functions "
            f"{kinds['function']}, methods {kinds['method']}, properties "
            f"{kinds['property']}, variables {kinds['variable']}, constants "
            f"{kinds['constant']})"
        ),
        (
            f"Relations between symbols: {s['relations']} (calls {rel['calls']}, "
            f"inherits {rel['inherits']}, references {rel['references']}); confidence "
            f"definite {rconf['definite']}, probable {rconf['probable']}, unknown "
            f"{rconf['unknown']}"
        ),
        (
            f"Usage sites read: {sites.get('total', 0)}; stored as relations or "
            "counted by reason (see the JSON report), never dropped silently"
        ),
        f"Entry points: {s['entry_points']}",
    ]


STRUCTURE_ATTENTION_COLUMNS: tuple[str, ...] = (
    "Importing module",
    "Statement",
    "Reason",
    "Location",
)
STRUCTURE_ATTENTION_LIMIT = 20


def structure_attention_rows(
    data: ReportData,
) -> tuple[list[tuple[str, str, str, str]], int]:
    """Imports the model could not resolve to a target (a missing repository
    submodule, an ambiguous name, a computed module name): the first
    `STRUCTURE_ATTENTION_LIMIT` rows and the total, never silently cut."""
    if data.structure is None:
        return [], 0
    from sarand.structure.model import TARGET_DYNAMIC, TARGET_INTERNAL_UNRESOLVED

    rows = [
        (
            e.source,
            e.evidence,
            e.note or e.resolution_method,
            f"{e.location.path}:{e.location.line}",
        )
        for e in data.structure.edges
        if e.target_class in (TARGET_INTERNAL_UNRESOLVED, TARGET_DYNAMIC)
    ]
    return rows[:STRUCTURE_ATTENTION_LIMIT], len(rows)


STRUCTURE_EXTERNAL_COLUMNS: tuple[str, ...] = (
    "Package",
    "Class",
    "Declared in",
    "Imported by (modules)",
)
STRUCTURE_EXTERNAL_LIMIT = 30


def structure_external_rows(
    data: ReportData,
) -> tuple[list[tuple[str, str, str, str]], int]:
    """External names imported by the source, most-imported first, with how many
    modules import them; the first `STRUCTURE_EXTERNAL_LIMIT` rows and the total."""
    if data.structure is None:
        return [], 0
    from sarand.structure.model import (
        TARGET_EXTERNAL_DECLARED,
        TARGET_EXTERNAL_UNMATCHED,
    )

    importers: dict[str, set[str]] = {}
    for edge in data.structure.edges:
        if edge.target_class in (TARGET_EXTERNAL_DECLARED, TARGET_EXTERNAL_UNMATCHED):
            importers.setdefault(edge.target, set()).add(edge.source)
    by_name = {x.name: x for x in data.structure.externals}
    ordered = sorted(importers, key=lambda n: (-len(importers[n]), n))
    rows = [
        (
            name,
            by_name[name].target_class,
            ", ".join(by_name[name].declared_in) or "-",
            str(len(importers[name])),
        )
        for name in ordered
    ]
    return rows[:STRUCTURE_EXTERNAL_LIMIT], len(rows)


STRUCTURE_CYCLE_LIMIT = 10


def structure_cycle_lines(data: ReportData) -> tuple[list[str], int]:
    """One line per import cycle (eager ones first): its modules and whether it can
    fail at import time; the first `STRUCTURE_CYCLE_LIMIT` lines and the total."""
    if data.structure is None:
        return [], 0
    ordered = sorted(data.structure.cycles, key=lambda c: (not c.eager, c.modules))
    lines = [
        f"{'eager' if c.eager else 'lazy or type-only'}: " + " <-> ".join(c.modules)
        for c in ordered
    ]
    return lines[:STRUCTURE_CYCLE_LIMIT], len(lines)


# ---------------------------------------------------------------- structure changes
# R14-D1 (S2): what changed between a reference snapshot and the current structure
# (`--structure-baseline`). The rows come from the comparison payload that
# `structure/compare.py` built; no format computes its own.
# R14-D1 (S2): آنچه بین snapshot مرجع و ساختار فعلی تغییر کرده؛ ردیف‌ها از payload
# مقایسه می‌آیند و هیچ قالبی خودش چیزی حساب نمی‌کند.

STRUCTURE_COMPARISON_NOTE = (
    "Two snapshots of the same project, compared by identity (not by position). A "
    "path that was not read in full in one of them, or that moved into or out of "
    "the secret exclusion, is `uncertain`: its changes are never reported as "
    "added or removed."
)
STRUCTURE_COMPARISON_COLUMNS: tuple[str, ...] = (
    "Part",
    "Added",
    "Removed",
    "Changed",
    "Uncertain",
    "Other",
    "Unchanged",
)
STRUCTURE_CHANGE_COLUMNS: tuple[str, ...] = ("Part", "Status", "What")
STRUCTURE_CHANGE_ROWS = 40
_VERDICT_MEANING = {
    "comparable": "everything was compared",
    "ids_only": "symbols were matched by id only; no content change is claimed",
    "partial": "some paths are uncertain; see the list below",
    "incompatible": "the two sides cannot be compared",
    "invalid": "a side is not a usable snapshot",
}
_COMPARISON_PARTS = (
    "files",
    "modules",
    "symbols",
    "relations",
    "edges",
    "cycles",
    "entry_points",
    "externals",
)


def _comparison(data: ReportData) -> dict[str, Any] | None:
    return data.structure_comparison


def structure_comparison_lines(data: ReportData) -> list[str]:
    """The verdict, its reasons and what each side was, the same for every format."""
    c = _comparison(data)
    if c is None:
        return []
    verdict = str(c["verdict"])
    lines = [f"Verdict: {verdict} ({_VERDICT_MEANING.get(verdict, 'see the reasons')})"]
    lines.extend(f"Reason: {reason}" for reason in c.get("reasons", []))
    for side, label in (("old", "Reference"), ("new", "Current")):
        info = c.get(side) or {}
        if info.get("usable"):
            lines.append(
                f"{label}: {info['source']}, structure schema "
                f"{info['structure_schema']}, fingerprint basis "
                f"{info['fingerprint_basis'] or 'none'}, "
                f"{info['files']} files, {info['symbols']} symbols"
            )
    return lines


def structure_comparison_summary(data: ReportData) -> list[tuple[str, ...]]:
    """One row per part: added, removed, changed, uncertain, other, unchanged."""
    c = _comparison(data)
    if c is None:
        return []
    rows: list[tuple[str, ...]] = []
    for part in _COMPARISON_PARTS:
        counts = (c.get("summary") or {}).get(part)
        if not counts:
            continue
        changed = counts.get("changed", 0) + counts.get("content_changed", 0)
        changed += counts.get("moved", 0)
        other = counts.get("ambiguous", 0) + counts.get("content_unknown", 0)
        rows.append(
            (
                part,
                str(counts.get("added", 0)),
                str(counts.get("removed", 0)),
                str(changed),
                str(counts.get("uncertain", 0)),
                str(other),
                str(counts.get("unchanged", 0)),
            )
        )
    return rows


def _describe_change(part: str, entry: dict[str, Any]) -> str:
    if part == "files":
        fields = entry.get("fields")
        return (
            f"{entry['path']} ({', '.join(fields)})" if fields else str(entry["path"])
        )
    if part == "modules":
        return str(entry["name"])
    if part == "symbols":
        return f"{entry['kind']} {entry['qualname']} ({entry['path']})"
    if part == "relations":
        return f"{entry['kind']}: {entry['source']} -> {entry['target']}"
    if part == "edges":
        return f"{entry['source']} imports {entry['requested']} ({entry['kind']})"
    if part == "cycles":
        return " -> ".join(entry["modules"])
    if part == "entry_points":
        return f"{entry['type']} {entry['name']} -> {entry['target']}"
    return str(entry.get("name", ""))


def structure_comparison_rows(
    data: ReportData, limit: int = STRUCTURE_CHANGE_ROWS
) -> tuple[list[tuple[str, ...]], int]:
    """The listed changes (part, status, what), at most `limit`, and their total."""
    c = _comparison(data)
    if c is None:
        return [], 0
    rows: list[tuple[str, ...]] = []
    total = 0
    for part in _COMPARISON_PARTS:
        for entry in (c.get("changes") or {}).get(part, []):
            total += 1
            if len(rows) < limit:
                rows.append((part, str(entry["status"]), _describe_change(part, entry)))
    return rows, total


def structure_comparison_uncertain_paths(
    data: ReportData, limit: int = 10
) -> tuple[list[str], int]:
    """The paths that could not be compared, with why, and how many there are."""
    c = _comparison(data)
    if c is None:
        return [], 0
    paths = c.get("uncertain_paths") or []
    lines = [f"{p['path']} ({', '.join(p['reasons'])})" for p in paths[:limit]]
    return lines, len(paths)


def structure_comparison_totals(data: ReportData) -> dict[str, int]:
    """The changes over all parts, for the one-line text summary."""
    totals = {"added": 0, "removed": 0, "changed": 0, "uncertain": 0}
    for row in structure_comparison_summary(data):
        for index, name in enumerate(totals, start=1):
            totals[name] += int(row[index])
    return totals


# ------------------------------------------------------------ findings baseline
# R14-D1 (F1): the findings compared with a reference report (`--baseline`). The rows
# come from the payload of `core/baseline.py`; no format computes its own.
# R14-D1 (F1): یافته‌ها در مقایسه با گزارش مرجع؛ ردیف‌ها از payload می‌آیند.

BASELINE_NOTE = (
    "The findings of this run compared with a previous report, by stable finding "
    "identity. A finding is `fixed` only when the check that reports it ran in this "
    "run; if it did not, the finding is `not_checked` (never `fixed`, never `new`)."
)
BASELINE_COLUMNS: tuple[str, ...] = (
    "Class",
    "New",
    "Fixed",
    "Unchanged",
    "Changed",
    "Not checked",
)
BASELINE_CHANGE_COLUMNS: tuple[str, ...] = ("Class", "State", "What", "Note")
BASELINE_ROWS = 40
_BASELINE_CLASSES = ("failures", "advisories", "secrets")


def baseline_lines(data: ReportData) -> list[str]:
    """What the reference was and which classes it could not tell about."""
    b = data.baseline
    if b is None:
        return []
    lines = [f"Reference report schema: {b['reference']['schema_version']}"]
    missing = b["reference"].get("classes_not_recorded", [])
    if missing:
        lines.append(
            "Not recorded by that report (so not compared): " + ", ".join(missing)
        )
    return lines


def baseline_summary(data: ReportData) -> list[tuple[str, ...]]:
    """One row per class: new, fixed, unchanged, changed, not checked."""
    b = data.baseline
    if b is None:
        return []
    rows: list[tuple[str, ...]] = []
    for name in _BASELINE_CLASSES:
        counts = b["summary"][name]
        rows.append(
            (
                name,
                str(counts["new"]),
                str(counts["fixed"]),
                str(counts["unchanged"]),
                str(counts["changed"]),
                str(counts["not_checked"]),
            )
        )
    return rows


def _baseline_what(name: str, entry: dict[str, Any]) -> str:
    if name == "failures":
        return f"{entry['tool']} {entry['category']} {entry['subject']}".strip()
    if name == "advisories":
        return f"{entry['advisory_id']} {entry['package']} {entry['version']}".strip()
    return f"{entry['path']} ({entry['pattern_name']})"


def baseline_rows(
    data: ReportData, limit: int = BASELINE_ROWS
) -> tuple[list[tuple[str, ...]], int]:
    """The findings that are not unchanged (class, state, what, note), at most `limit`,
    and how many there are."""
    b = data.baseline
    if b is None:
        return [], 0
    rows: list[tuple[str, ...]] = []
    total = 0
    for name in _BASELINE_CLASSES:
        for entry in b["findings"].get(name, []):
            total += 1
            if len(rows) < limit:
                note = entry.get("reason") or entry.get("direction") or ""
                rows.append(
                    (name, str(entry["state"]), _baseline_what(name, entry), str(note))
                )
    return rows, total


def baseline_totals(data: ReportData) -> dict[str, int]:
    """The counts over all classes, for the one-line text summary."""
    totals = {"new": 0, "fixed": 0, "changed": 0, "not_checked": 0}
    if data.baseline is not None:
        for counts in data.baseline["summary"].values():
            for name in totals:
                totals[name] += counts[name]
    return totals


# R14-D1 (F2): what the gate decided (`--baseline-gate`). Rows come from the
# `baseline.gate` object; no format computes its own.
# R14-D1 (F2): تصمیم gate؛ ردیف‌ها از `baseline.gate` می‌آیند.
GATE_COLUMNS: tuple[str, ...] = ("Result", "Class", "What", "Rule or reason")
GATE_ROWS = 40


def _gate(data: ReportData) -> dict[str, Any] | None:
    gate = None if data.baseline is None else data.baseline.get("gate")
    if gate is None or gate.get("verdict") == "not_gated":
        return None
    return dict(gate)


def baseline_gate_line(data: ReportData) -> str:
    """One sentence with the policy, the verdict and the counts; empty when there is no
    gate (no `--baseline-gate`, or `never`)."""
    gate = _gate(data)
    if gate is None:
        return ""
    failed, uncertain = len(gate["failed_on"]), len(gate["uncertain"])
    waived = len(gate.get("waived", []))
    tail = f", {uncertain} uncertain (they never fail the gate)" if uncertain else ""
    tail += f", {waived} waived (listed, they no longer fail it)" if waived else ""
    issues = [
        f"{len(gate['waivers'][key])} {key}"
        for key in ("expired", "unused", "exceeded")
        if gate.get("waivers", {}).get(key)
    ]
    tail += f"; waivers: {', '.join(issues)}" if issues else ""
    if gate["verdict"] == "fail":
        return f"Gate (policy {gate['policy']}): FAILED on {failed} finding(s){tail}"
    return f"Gate (policy {gate['policy']}): passed{tail}"


def _waiver_text(waiver: dict[str, Any]) -> str:
    return f"#{waiver['number']} {waiver['scope']} {waiver['target']}"


def baseline_gate_rows(
    data: ReportData, limit: int = GATE_ROWS
) -> tuple[list[tuple[str, ...]], int]:
    """What the gate failed on, what a waiver covers, the uncertain findings and the
    waivers that did not apply (result, class, what, rule or reason), at most `limit`,
    and how many there are."""
    gate = _gate(data)
    if gate is None:
        return [], 0
    rows: list[tuple[str, ...]] = []
    for item in gate["failed_on"]:
        rows.append(
            (
                "failed",
                item["class"],
                str(item["label"]),
                f"{item['rule']} ({item['state']})",
            )
        )
    for item in gate.get("waived", []):
        waiver = item["waiver"]
        rows.append(
            (
                "waived",
                item["class"],
                str(item["label"]),
                (
                    f"{_waiver_text(waiver)}; {waiver['owner']}, until "
                    f"{waiver['expires']}: {waiver['reason']}"
                ),
            )
        )
    for item in gate["uncertain"]:
        rows.append(
            ("uncertain", item["class"], str(item["label"]), str(item["reason"]))
        )
    notes: dict[str, Callable[[dict[str, Any]], str]] = {
        "expired": lambda w: f"expired {w['expires']}; would cover {w['matches']}",
        "unused": lambda w: f"matched no failing finding (until {w['expires']})",
        "exceeded": lambda w: (
            f"matches {w['matches']} but declares {w['covers']}: applies to none"
        ),
    }
    for key, note in notes.items():
        for waiver in gate.get("waivers", {}).get(key, []):
            rows.append(
                (f"waiver {key}", "waivers", _waiver_text(waiver), note(waiver))
            )
    return rows[:limit], len(rows)
