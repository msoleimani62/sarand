# Renderer consistency

Markdown, HTML, JSON, SARIF and text are different views of **one** model. They
may draw it differently; they must not say different things. The lists they all
need (the errors and warnings, the failure rows, the advisory rows, the state of
every check) are decided once, in `core/report_views.py`, and a renderer only
chooses how to show them. No renderer recalculates a fact.

## What each format carries

| Field | Markdown | HTML | JSON | SARIF | Text |
|---|---|---|---|---|---|
| Health score and grade | yes | yes | yes | `runs[0].properties.sarand.health` | yes |
| Execution coverage (and its basis) | yes | yes | yes | `...health.executionCoverage`, `checksRequested`, `checksExecuted`, `coverageByGroup` | one line |
| Coverage gaps (what did not run, and why) | yes | yes | yes | `...health.coverageGaps` | one line |
| State of every check | `[PASS]` `[FAIL]` `[SKIP]` ... | badge | `state` in each result | `...checkStates` | no |
| Classified failures with ids | table | table | `failures[].id` | `...failures` | count |
| Critical failures | yes | yes | `health.critical_failures`, `critical_ids` | `...health.criticalFindingIds` | no |
| Known issues | list | list | `known_issues`, `known_issue_ids` | `...knownIssueIds` | no |
| Advisory id, package, version, kind | table | table | `advisories` | one result per advisory, `ruleId` is the advisory id | count |
| Advisory severity (only if the tool printed one) | column | column | `severity` | `properties.severity` | no |
| Advisory applicability (always `unknown`) | column | column | `applicability` | `properties.applicability` | in the count line |
| Source of an advisory (which tools reported it) | column | column | `sources` | `properties.reportedBy` | no |
| Finding identity of an advisory | its id | its id | its id, package, version | `partialFingerprints.sarandFindingId/v1` | no |
| Errors and warnings of the tools | lists | tables | inside each result | `tool-output/...` results | no |

SARIF has no native field for check states or coverage, so they are kept in a
property bag under the `sarand` key; the standard allows it and nothing there
changes the meaning of a result. Levels follow the standard (`note`, `warning`,
`error`): a tool-reported vulnerability or unsound advisory is a `warning`, a
maintenance notice a `note`, and neither is raised or lowered to look cleaner.

## One fact, one count

- **Advisory lines are not listed twice.** The anonymous `Warning:   unsound`
  lines of `cargo audit` and the `error[vulnerability]` / `warning[unmaintained]`
  heads of `cargo deny` are represented by the advisory itself. They are not
  repeated under "Errors detected", "Warnings detected" or as SARIF
  `tool-output` results, and one sentence says how many were folded in. The
  check's own output still shows them in full. A line is folded only when the same
  check produced at least one advisory; the other lines of those tools (a
  license violation, `error: 5 vulnerabilities found!`, a duplicate crate) stay.
- **Quick Context counts the same.** "tools reported N error(s) and M warning(s)"
  uses the same lists, and a separate line gives the advisory count.
- **A check that could not run is not a known issue.** A timeout or a missing
  tool gave no verdict (`unavailable`, see `docs/CHECK_STATES.md`), so it is not
  "a tool that failed" and no longer appears in `known_issues` or among the Quick
  Context critical findings. It stays in `failures` with its cause (for example
  `tool_not_found`), in the coverage gaps and in the risks.
- **JSON** keeps every check output in full (it is the evidence) and gains
  `state` in each result; `health.checks_inconclusive` is always present.

## Not covered

HTML does not draw the per-component tables of a workspace report differently
from Markdown, and the text format is a summary by design (it points to the full
report for the lists). The Ramz before/after comparison belongs to the R13
completion report.
