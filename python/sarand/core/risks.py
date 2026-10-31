"""Quick Context layer L3, part 2: rule-based risks (docs/QUICK_CONTEXT_DESIGN.md,
section 6.2 and 6.3, decisions D-QC3 and D-QC5).

A fixed table of NINE rules, no tenth. Every risk is a record with a stable
`rule_id`, a `category`, a `severity` from a fixed per-rule mapping, references
to the report fields it was read from, one sentence of `reason` with the
numbers, and a fixed `limitations` sentence saying what the evidence does NOT
show. Evidence, inference and limitation are never merged under one word.

Properties (they bind this module):

- A pure function of `ReportData`: no clock, no environment, stable order
  (severity high first, then `rule_id`), nothing mutated.
- A rule whose data is absent does not fire and is listed in
  `rules_not_evaluated`; missing data is never read as "all good".
- `SECRET-PATTERNS` counts findings that are not test fixtures and never shows
  a path or content.

Thresholds are named constants fixed from a real report (sarand on itself,
2026-10-31): `largest_files` holds BYTES (the three history documents are
81-100 KB), the report had 18 checks run, none skipped, confidence 1.0, five
secret-pattern matches that are all test fixtures, no duplicates, and 132
markers of which the busiest file had 16. Two of them, `CHECKS_SKIPPED_MIN` and
`CONFIDENCE_MIN`, are PROVISIONAL: that report skipped nothing, so it shows only
that they do not fire on a complete run. Calibrate them on a report from a
machine with missing tools.

لایه‌ی L3، بخش دوم: ریسک‌های قاعده‌محور. جدول ثابت نُه‌قاعده‌ای؛ هر ریسک
rule_id، category، severity، evidence_refs، reason و limitations دارد. داده‌ی
غایب هرگز «همه‌چیز خوب است» خوانده نمی‌شود و در `rules_not_evaluated` می‌آید.
دو آستانه‌ی `CHECKS_SKIPPED_MIN` و `CONFIDENCE_MIN` موقتی‌اند.
"""

from __future__ import annotations

import collections
from collections.abc import Callable
from dataclasses import dataclass, field

from sarand.models.results import CommandResult, ReportData

# Thresholds (see the module docstring for where each value comes from).
# آستانه‌ها (منبع هر مقدار در docstring ماژول).
TODO_CLUSTER_MIN = 10
LARGE_FILE_BYTES = 64 * 1024
CHECKS_SKIPPED_MIN = 3  # provisional / موقتی
CONFIDENCE_MIN = 0.8  # provisional / موقتی

DISPLAY_CAP = 8
_MAX_REFS = 5
_GIT_UNAVAILABLE = "(unavailable)"
_SEVERITY_ORDER = {"high": 0, "warning": 1, "info": 2}


@dataclass
class Risk:
    """One fired rule. Plain data, JSON-serialisable via `asdict`."""

    rule_id: str
    category: str
    severity: str
    evidence_refs: list[str] = field(default_factory=list)
    reason: str = ""
    limitations: str = ""


@dataclass
class RiskReport:
    """All fired risks (sorted) and the rules that could not be evaluated."""

    risks: list[Risk] = field(default_factory=list)
    rules_not_evaluated: list[str] = field(default_factory=list)


# What a rule's check returns when it fires: (reason, evidence_refs).
_Fired = tuple[str, list[str]]


@dataclass(frozen=True)
class _Rule:
    rule_id: str
    category: str
    severity: str
    limitations: str
    available: Callable[[ReportData], bool]
    check: Callable[[ReportData], _Fired | None]


def _status(result: CommandResult) -> str:
    if result.skipped:
        return "skipped"
    if result.inconclusive:
        return "inconclusive"
    return "passed" if result.passed else "failed"


def _all_results(data: ReportData) -> list[CommandResult]:
    return [*data.test_results, *data.quality_results, *data.security_results]


def _scanned(data: ReportData) -> bool:
    return data.stats.total_files > 0


def _kind_refs(field_name: str, kinds: list[str]) -> list[str]:
    refs = [f"{field_name}[kind={k}]" for k in kinds[:_MAX_REFS]]
    if len(kinds) > _MAX_REFS:
        refs.append(f"(+{len(kinds) - _MAX_REFS} more)")
    return refs


def _clip(text: str, limit: int = 60) -> str:
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


# --- the nine rules -------------------------------------------------------


def _sec_failed(data: ReportData) -> _Fired | None:
    failed = [_clip(r.kind) for r in data.security_results if _status(r) == "failed"]
    if not failed:
        return None
    reason = f"{len(failed)} of {len(data.security_results)} security check(s) failed"
    return reason, _kind_refs("security_results", failed)


def _health_critical(data: ReportData) -> _Fired | None:
    if data.health is None:
        return None
    count = len(data.health.critical_failures)
    if not count:
        return None
    return f"{count} critical failure(s) in the health score", [
        "health.critical_failures"
    ]


def _secret_patterns(data: ReportData) -> _Fired | None:
    count = sum(1 for f in data.secret_findings if not f.is_test_fixture)
    if not count:
        return None
    return (
        f"{count} secret-pattern match(es) outside test fixtures",
        ["secret_findings[is_test_fixture=false]"],
    )


def _checks_skipped(data: ReportData) -> _Fired | None:
    skipped = [_clip(r.kind) for r in _all_results(data) if _status(r) == "skipped"]
    if len(skipped) < CHECKS_SKIPPED_MIN:
        return None
    total = len(_all_results(data))
    reason = (
        f"{len(skipped)} of {total} checks were skipped "
        f"(threshold {CHECKS_SKIPPED_MIN})"
    )
    refs = [
        f"{name}[kind={k}]"
        for name, group in (
            ("test_results", data.test_results),
            ("quality_results", data.quality_results),
            ("security_results", data.security_results),
        )
        for k in (_clip(r.kind) for r in group if _status(r) == "skipped")
    ]
    return reason, refs[:_MAX_REFS]


def _git_state(data: ReportData) -> _Fired | None:
    parts: list[str] = []
    refs: list[str] = []
    if data.git.dirty:
        parts.append("uncommitted changes")
        refs.append("git.dirty")
    if data.git.ahead > 0:
        parts.append(f"{data.git.ahead} commit(s) ahead of upstream")
        refs.append("git.ahead")
    if data.git.behind > 0:
        parts.append(f"{data.git.behind} commit(s) behind upstream")
        refs.append("git.behind")
    if not parts:
        return None
    return "working copy has " + ", ".join(parts), refs


def _low_confidence(data: ReportData) -> _Fired | None:
    if data.health is None or data.health.confidence >= CONFIDENCE_MIN:
        return None
    pct = round(data.health.confidence * 100)
    return (
        f"health confidence is {pct}% (threshold {round(CONFIDENCE_MIN * 100)}%)",
        ["health.confidence"],
    )


def _todo_cluster(data: ReportData) -> _Fired | None:
    counts = collections.Counter(t.path for t in data.todos)
    busy = sorted(
        ((path, n) for path, n in counts.items() if n >= TODO_CLUSTER_MIN),
        key=lambda item: (-item[1], item[0]),
    )
    if not busy:
        return None
    path, n = busy[0]
    reason = (
        f"{len(busy)} file(s) with at least {TODO_CLUSTER_MIN} markers; "
        f"most: {_clip(path, 50)} ({n})"
    )
    return reason, ["todos[path]"]


def _large_file(data: ReportData) -> _Fired | None:
    large = sorted(
        ((p, size) for p, size in data.stats.largest_files if size >= LARGE_FILE_BYTES),
        key=lambda item: (-item[1], item[0]),
    )
    if not large:
        return None
    path, size = large[0]
    reason = (
        f"{len(large)} file(s) of at least {LARGE_FILE_BYTES // 1024} KiB; "
        f"largest: {_clip(path, 50)} ({size // 1024} KiB)"
    )
    return reason, ["stats.largest_files"]


def _duplicates(data: ReportData) -> _Fired | None:
    groups = data.stats.duplicate_files
    if not groups:
        return None
    return f"{len(groups)} group(s) of files with identical content", [
        "stats.duplicate_files"
    ]


RULES: tuple[_Rule, ...] = (
    _Rule(
        "SEC-CHECK-FAILED",
        "security",
        "high",
        "A tool result, not a proven vulnerability.",
        lambda d: bool(d.security_results),
        _sec_failed,
    ),
    _Rule(
        "HEALTH-CRITICAL",
        "quality",
        "high",
        "Covers only the checks that ran.",
        lambda d: d.health is not None,
        _health_critical,
    ),
    _Rule(
        "SECRET-PATTERNS",
        "security",
        "warning",
        "Pattern matches, not confirmed leaked secrets; only a count is shown.",
        _scanned,
        _secret_patterns,
    ),
    _Rule(
        "CHECKS-SKIPPED",
        "coverage",
        "warning",
        "Skipped means not run, not failed.",
        lambda d: bool(_all_results(d)),
        _checks_skipped,
    ),
    _Rule(
        "GIT-STATE",
        "repository-state",
        "info",
        "Says nothing about security or quality.",
        lambda d: d.git.branch != _GIT_UNAVAILABLE,
        _git_state,
    ),
    _Rule(
        "HEALTH-LOW-CONFIDENCE",
        "coverage",
        "warning",
        "Confidence is about how many checks ran, not about the code.",
        lambda d: d.health is not None,
        _low_confidence,
    ),
    _Rule(
        "TODO-CLUSTER",
        "maintainability",
        "info",
        "A count, not a density: per-file line counts are not in the report; "
        "comment tags that explain a fix are counted too.",
        _scanned,
        _todo_cluster,
    ),
    _Rule(
        "LARGE-FILE",
        "maintainability",
        "info",
        "Size in bytes alone is not a defect; documents and data files count.",
        _scanned,
        _large_file,
    ),
    _Rule(
        "DUPLICATE-FILES",
        "maintainability",
        "info",
        "Identical content among the files the scan hashed (its size cap applies).",
        _scanned,
        _duplicates,
    ),
)


def evaluate_risks(data: ReportData) -> RiskReport:
    """Evaluate the nine rules. Pure and deterministic; never mutates `data`."""
    risks: list[Risk] = []
    not_evaluated: list[str] = []
    for rule in RULES:
        if not rule.available(data):
            not_evaluated.append(rule.rule_id)
            continue
        fired = rule.check(data)
        if fired is None:
            continue
        reason, refs = fired
        risks.append(
            Risk(
                rule_id=rule.rule_id,
                category=rule.category,
                severity=rule.severity,
                evidence_refs=refs,
                reason=reason,
                limitations=rule.limitations,
            )
        )
    risks.sort(key=lambda r: (_SEVERITY_ORDER[r.severity], r.rule_id))
    return RiskReport(risks=risks, rules_not_evaluated=sorted(not_evaluated))
