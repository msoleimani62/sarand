# Execution coverage

`execution_coverage` says **which of the checks you asked for ran to a verdict**.
It is not analytical confidence, not a statement about how complete or correct the
analysis is, and not a statement about the project.

## The formula

```text
execution_coverage = executed / requested
```

- **requested** is the number of records in the test, quality and security results.
  A check that was never requested (for example you did not pass `--quality`) has
  no record, so it is not in the denominator. The per-group counts in the report
  (`coverage_by_group`) show which groups had nothing requested, so a high
  percentage cannot be read as "everything was checked".
- **executed** is the number of those records that reached a verdict: the check
  `passed` or `failed`. A failed check executed; it did not succeed.
- Records are counted one by one. Two results of the same tool are two checks.
- The value is rounded to four decimal places in JSON and shown as a whole
  percent, rounded half up (0.725 is 73%).
- **Nothing requested**: there is no denominator, so the value is `null` in JSON
  and the reports say "not available (no check was requested)". It is never 100%.

## What happened to a check

One interpretation of a check's state is used by every consumer
(`python/sarand/core/check_states.py`):

| State | Meaning | Counts as executed |
|---|---|---|
| `passed` | the tool ran and exited 0 | yes |
| `failed` | the tool ran and exited non-zero (see `failures[]` for the kind of failure) | yes |
| `skipped` | the check did not run (tool missing, option, not applicable) | no |
| `inconclusive` | the tool exited 0 but could not finish its job (for example the network was unreachable) | no |
| `unavailable` | the runner could not run the tool: a timeout, the tool was not found, an operating-system error | no |
| `unknown` | a contradictory record (skipped and inconclusive at once) | no |

`not_applicable` is reserved: no result records it yet, so it cannot be told apart
from `skipped`. Every check that did not run is listed in `coverage_gaps` with its
state and the reason the check gave.

## Where it appears

- JSON, in `health`: `execution_coverage`, `checks_requested`, `checks_executed`,
  `coverage_by_group`, `coverage_gaps`.
- The Markdown and HTML Health Score section, the plain-text report, the CLI
  summary and Quick Context all use the same wording
  (`python/sarand/core/execution_coverage.py`).
- The risk rule `HEALTH-LOW-CONFIDENCE` fires when the coverage is below 80%. The
  rule id keeps its legacy name for compatibility; it evaluates execution
  coverage, and it is "not evaluated" when nothing was requested.

## The old `confidence` field

`health.confidence` is **deprecated**. It is still written, with its exact old
arithmetic, and the reports no longer show it:

```text
confidence = ran / (ran + distinct skipped kinds + distinct inconclusive kinds)
```

It differs from execution coverage in three ways: skipped and inconclusive checks
are counted once per distinct kind while ran checks are counted per record, a
timed-out or not-found tool counts as "ran", and an empty request gives `1.0`.
Because its meaning is not the same, it is not rewritten to mirror the new field.
It stays through all 1.x versions of the JSON schema and is removed no earlier than
schema 2.0; read `execution_coverage` instead.
