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
import re

from sarand.constants import SARAND_INFO_URI
from sarand.models.results import Advisory, Issue, ReportData
from sarand.progress import status

_SCHEMA_URI = "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"
_SARAND_INFO_URI = SARAND_INFO_URI
# The generic lines `cargo audit` prints per advisory ("Warning:   unsound"): with
# parsed advisories they are represented by one result each, with the advisory id.
# خطوط عمومی cargo audit برای هر advisory؛ با advisory پارس‌شده یک نتیجه‌ی دارای id می‌گیرند.
_AUDIT_KIND_LINE = re.compile(r"^Warning:\s+\w+$")


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

    def add_unlocated_issues(issues: list[Issue]) -> None:
        for issue in issues:
            if (
                data.advisories
                and issue.source == "cargo audit"
                and _AUDIT_KIND_LINE.match(issue.message)
            ):
                continue
            rule_id = _rule_id("tool-output", issue.source)
            register_rule(rule_id, f"Output from {issue.source}")
            results.append(
                {
                    "ruleId": rule_id,
                    "level": "error" if issue.severity == "error" else "warning",
                    "message": {"text": issue.message},
                }
            )

    for r in data.test_results + data.quality_results + data.security_results:
        add_unlocated_issues(r.warnings)
        add_unlocated_issues(r.errors)

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
                "originalUriBaseIds": {
                    "PROJECTROOT": {"uri": data.project_root.as_uri() + "/"}
                },
            }
        ],
    }

    return json.dumps(sarif_log, indent=2, ensure_ascii=False)
