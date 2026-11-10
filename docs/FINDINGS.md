# Finding identity and duplicates

One underlying problem can be told in several places of a report: a failed
check, a health critical failure, a known issue, a risk and a Quick Context line.
sarand gives such a problem **one stable id**, built from structured fields and
never from the rendered sentence, so the places can be tied together without
guessing from similar words.

## The id

An id looks like `security_finding_detected:b48a5277b74b`: a readable kind, a
colon and the first 12 hex digits of a SHA-256 over the kind and the identifying
parts. The parts are stripped and a set of tools is sorted, so the id does not
depend on the order the checks ran in.

| Finding | Kind | Identifying parts |
|---|---|---|
| A classified failure (`failures[].id`) | its category, such as `lint_failure` | tool, group, category, cause, subject |
| A security finding, a policy violation or a failed security tool | `security_finding_detected`, `dependency_policy_failure`, `security_tool_failure` | the sorted set of tools |
| Failed test suites, or a test check that could not run | `test_suite_failed`, `test_check_unavailable` | the sorted set of checks |
| Broken symlinks, hard-coded secrets | `broken_symlinks`, `hardcoded_secrets` | none (one condition per report) |
| A Python syntax error or a missing module | `python_syntax_error`, `python_missing_module` | the sorted set of tools |

The return code and the summary are **evidence** of a finding, not part of what
makes it that finding, so they are not in the id.

## Distinct stays distinct

- `cargo audit` and `cargo deny` reporting advisories are two conditions (the tool
  sets differ), and so are a security finding and a policy violation of the same
  tool (the kinds differ).
- Two sentences that read alike but have different ids are never merged.
- Without ids (a hand-built `HealthScore` or `ReportData`) nothing is merged,
  even when two texts are identical.

## Roles in the report

| Role | Meaning | Where |
|---|---|---|
| primary | Owns the finding and shows all its evidence | `failures`, `health.critical_failures` |
| summary | Counts or restates it | risks, Quick Context |
| related | Tells the same condition in other words | `known_issues` beside the health critical failure of the same id |

Nothing is dropped from the report:

- `health.critical_failures` adds a condition once; a second finding with the same
  id is not a second critical failure.
- **Quick Context** shows a known issue only when its id is not already a health
  critical failure. The known issue stays in `known_issues` and in the Known
  issues section. The `(+N more known issue(s))` counter counts unique ones.
- The `HEALTH-CRITICAL` risk counts distinct ids. When `SEC-CHECK-FAILED` also
  fires, its reason says how many of the critical failures restate the failed
  security checks, so two risks read as one cause told twice.

## In the JSON report (schema 1.5)

`known_issue_ids`, `health.critical_ids`, `quick_context.critical_finding_ids`
and `failures[].id`. Ids are identical on every run for the same input, and they
survive serialization. See `docs/JSON_SCHEMA.md`.

## Not covered

An id identifies a condition, not a location: the same tool failing in two
components under the same label has the same id, and the `failures` list is not
collapsed. SARIF advisory results carry the advisory's own identity as
`partialFingerprints.sarandFindingId/v1`; the failures and critical ids are in the
`sarand` property bag (see `docs/RENDERERS.md`).
