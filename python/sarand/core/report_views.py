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

from dataclasses import dataclass, field

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
