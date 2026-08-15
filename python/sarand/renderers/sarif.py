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

from sarand.models.results import Issue, ReportData
from sarand.progress import status

_SCHEMA_URI = "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"
_SARAND_INFO_URI = (
    "https://github.com/example/sarand"  # update once the repo has a real remote
)


def _rule_id(prefix: str, name: str) -> str:
    slug = name.strip().lower().replace(" ", "-")
    return f"{prefix}/{slug}"


def render(data: ReportData, *, include_source: bool = True) -> str:
    """Render `data` as a SARIF 2.1.0 log. `include_source` is accepted
    for interface consistency with the other renderers but has no
    effect -- SARIF is a findings format, not a source-embedding one."""
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

    def add_unlocated_issues(issues: list[Issue]) -> None:
        for issue in issues:
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
