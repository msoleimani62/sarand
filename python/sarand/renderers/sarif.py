"""SARIF 2.1.0 renderer (Static Analysis Results Interchange Format).

Standard JSON schema consumable by GitHub code scanning and similar
tooling. Unlike the other renderers this one is naturally structured --
it maps cleanly onto sarand's existing findings without inventing new
concepts:

- SecretFinding  -> a located, "error"-level result (security first, §7)
- TodoItem       -> a located, "note"-level result
- Issue (from test/quality/security CommandResults) -> an unlocated
  result, since Issue only carries a source+message, no file/line
"""

from __future__ import annotations

import json

from sarand.constants import SARAND_INFO_URI
from sarand.core.finding_identity import (
    advisory_finding_id,
    failure_id,
    unique_ids,
)
from sarand.core.markers import marker_category
from sarand.core.report_views import check_state_rows, collect_issues
from sarand.models.results import Advisory, ReportData
from sarand.progress import status

_SCHEMA_URI = "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"
_SARAND_INFO_URI = SARAND_INFO_URI
# The key under which sarand's own metadata is kept (SARIF property bags are free
# form; the standard defines no field for check states or coverage).
# کلیدی که فراداده‌ی خود sarand زیر آن می‌آید (property bag در SARIF آزاد است).
_PROPERTY_KEY = "sarand"


def _rule_id(prefix: str, name: str) -> str:
    slug = name.strip().lower().replace(" ", "-")
    return f"{prefix}/{slug}"


def _advisory_level(adv: Advisory) -> str:
    """SARIF level of an advisory: a tool-reported vulnerability or unsound code
    is a warning, a maintenance notice is a note. The upstream severity and the
    applicability stay in `properties`; neither is folded into the level.
    """
    return "note" if adv.kind in ("unmaintained", "notice", "yanked") else "warning"


def _advisory_message(adv: Advisory) -> str:
    fixed = f"; fixed in {', '.join(adv.fixed_versions)}" if adv.fixed_versions else ""
    return (
        f"{adv.kind} advisory {adv.id} in {adv.package} {adv.version}{fixed}: "
        f"{adv.title or 'no title'} (reported by {', '.join(adv.sources)}; "
        f"applicability to this project: {adv.applicability})."
    )


def _sarand_properties(data: ReportData) -> dict[str, object]:
    """What SARIF has no native field for, kept as metadata (R13-G): the state of
    every check, the execution coverage, the classified failures and the finding
    ids. Nothing here is recalculated: it is the model the other formats read."""
    props: dict[str, object] = {
        "checkStates": [
            {"group": group, "check": kind, "state": state}
            for group, kind, state in check_state_rows(data)
        ],
        "failures": [
            {
                "id": failure_id(f),
                "tool": f.tool,
                "group": f.group,
                "category": f.category,
                "cause": f.cause,
                "subject": f.subject,
            }
            for f in data.failures
        ],
        "knownIssueIds": unique_ids(data.known_issue_ids),
    }
    health = data.health
    if health is not None:
        props["health"] = {
            "score": health.score,
            "maxScore": health.max_score,
            "grade": health.grade,
            "executionCoverage": health.execution_coverage,
            "checksRequested": health.checks_requested,
            "checksExecuted": health.checks_executed,
            "coverageByGroup": health.coverage_by_group,
            "coverageGaps": [
                {"check": g.kind, "state": g.state, "reason": g.reason}
                for g in health.coverage_gaps
            ],
            "criticalFindingIds": unique_ids(health.critical_ids),
        }
    return props


def render(
    data: ReportData, *, include_source: bool = True, full_output: bool = False
) -> str:
    """Render `data` as a SARIF 2.1.0 log. `include_source` and
    `full_output` are accepted for interface consistency with the other
    renderers but have no effect -- SARIF is a findings format (not a
    source-embedding one), and it already lists every finding with no
    truncation regardless of --full."""
    status("Rendering SARIF report...")

    rules: dict[str, dict] = {}
    results: list[dict] = []

    def register_rule(rule_id: str, description: str) -> None:
        if rule_id not in rules:
            rules[rule_id] = {
                "id": rule_id,
                "shortDescription": {"text": description},
            }

    for finding in data.secret_findings:
        rule_id = _rule_id("secret-detection", finding.pattern_name)
        register_rule(rule_id, f"Potential hardcoded secret: {finding.pattern_name}")
        results.append(
            {
                "ruleId": rule_id,
                "level": "error",
                "message": {
                    "text": f"Potential hardcoded secret ({finding.pattern_name})."
                },
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": finding.path},
                            "region": {"startLine": finding.line_number},
                        }
                    }
                ],
            }
        )

    for todo in data.todos:
        rule_id = _rule_id("todo", todo.kind)
        register_rule(rule_id, f"{todo.kind} marker found in source")
        results.append(
            {
                "ruleId": rule_id,
                "level": "note",
                "message": {"text": todo.content},
                "properties": {"category": marker_category(todo)},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": todo.path},
                            "region": {"startLine": todo.line_number},
                        }
                    }
                ],
            }
        )

    def add_advisories() -> None:
        for adv in data.advisories:
            rule_id = adv.id
            register_rule(rule_id, adv.title or f"Dependency advisory {adv.id}")
            if adv.url:
                rules[rule_id]["helpUri"] = adv.url
            results.append(
                {
                    "ruleId": rule_id,
                    "level": _advisory_level(adv),
                    "message": {"text": _advisory_message(adv)},
                    "partialFingerprints": {
                        "sarandFindingId/v1": advisory_finding_id(adv)
                    },
                    "properties": {
                        "package": adv.package,
                        "version": adv.version,
                        "kind": adv.kind,
                        "fixedVersions": list(adv.fixed_versions),
                        "severity": adv.severity,
                        "applicability": adv.applicability,
                        "reportedBy": list(adv.sources),
                        "database": adv.database,
                    },
                }
            )

    add_advisories()

    # The same errors and warnings every renderer shows (core/report_views.py): a
    # tool line that an advisory already represents is not a second result.
    # همان errorها و warningهای همه‌ی رندرها؛ خطِ بازگوکننده‌ی advisory نتیجه‌ی دوم نیست.
    for issue in collect_issues(data).ordered:
        rule_id = _rule_id("tool-output", issue.source)
        register_rule(rule_id, f"Output from {issue.source}")
        results.append(
            {
                "ruleId": rule_id,
                "level": "error" if issue.severity == "error" else "warning",
                "message": {"text": issue.message},
            }
        )

    sarif_log = {
        "$schema": _SCHEMA_URI,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "sarand",
                        "informationUri": _SARAND_INFO_URI,
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
                "properties": {_PROPERTY_KEY: _sarand_properties(data)},
                "originalUriBaseIds": {
                    "PROJECTROOT": {"uri": data.project_root.as_uri() + "/"}
                },
            }
        ],
    }

    return json.dumps(sarif_log, indent=2, ensure_ascii=False)
