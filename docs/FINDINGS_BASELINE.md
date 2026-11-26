# Findings baseline: what changed since a previous report

Status: the library and the `--baseline` option (slice F1 of R14-D1,
`docs/R14D1_PLAN.md`). The gate policies (slice F2), waivers (F3) and SARIF fingerprints
(F4) are not built yet; today the comparison is information only and never changes the
exit code.

The findings baseline is **independent of the structural baseline**
(`docs/STRUCTURE_BASELINE.md`). It compares the findings of two analyses; it does not
look at the structure of the project, and no structural change is ever a finding.

## The reference and the identity

`--baseline PATH` takes a previous **JSON report**. A finding is told apart by its R13
identity (`docs/FINDINGS.md`, `core/finding_identity.py`): built from structured fields,
never from text. The same problem stays the same finding when its wording, its order or
its line number changes.

| Class | Identity | Recorded by the report schema from |
|---|---|---|
| Classified failure | `failure_id`: tool, group, category, cause, subject | 1.5 |
| Advisory | the advisory id, the package and the version | 1.3 |
| Secret finding | the path and the pattern name (a line number is never identity; the number of matches in that file is the evidence) | always |

The health critical ids and the known-issue texts restate failures; they are not compared
as classes of their own.

## The five states

Every finding is in exactly one:

| State | Meaning |
|---|---|
| `new` | in this run, not in the reference, **and the reference could have seen it** |
| `fixed` | in the reference, not in this run, **and this run checked** |
| `unchanged` | in both, with the same evidence (counted, not listed) |
| `changed` | in both, with other evidence; `direction` is `worse`, `better` or `neutral` where an order exists |
| `not_checked` | no verdict is possible; the `reason` says why |

### The key rule

A finding is **never `fixed` because a check did not run**, and never `new` because the
reference did not run it. A check that was skipped, inconclusive, unavailable, unknown or
simply absent gave no verdict; what depends on it is `not_checked`.

| Class | `fixed` needs | `new` needs |
|---|---|---|
| Failure | the check `<group>/<tool>` passed or failed in this run | the same check passed or failed in the reference |
| Advisory | **every** check that reported it ran (passed or failed) in this run; an advisory with no recorded source is never fixed | every reporting check ran in the reference |
| Secret | its file was scanned again in this run (it is in the included files, or flagged and excluded) | its file was not skipped (too large) in the reference |

Reasons of a `not_checked` finding: `check_skipped`, `check_inconclusive`,
`check_unavailable`, `check_unknown`, `check_not_run`, `no_source_recorded`,
`file_skipped`, `file_not_scanned`, and the same with the prefix `reference_` when it is
the reference that could not have seen the finding. A secret whose file no longer exists
is `file_not_scanned`, not `fixed`: the run cannot tell a deleted file from an ignored
one.

A class that the reference schema did not record (advisories in a 1.2 report, failures
in a 1.4 report) is `not_checked` as a class (`class_not_recorded_in_reference`); the
list is in `reference.classes_not_recorded`.

### What `changed` means

| Class | Compared | Direction |
|---|---|---|
| Failure | the return code and the evidence signals; **not** the summary text (it carries counts and durations that move every run) | `neutral` |
| Advisory | the severity (compared by rank: `medium` and `moderate` are the same level) and the fixed versions | `worse` or `better` by severity; `neutral` otherwise or when a severity is unknown |
| Secret | the number of matches in the file | `worse` if more, `better` if fewer |

## Command line

`--baseline PATH` compares the findings of this run with the report in `PATH` and adds the
result to the report. An unusable file (missing, not a regular file, too large, not JSON,
not a report, a schema other than 1.x, or a malformed finding) is an error that names the
file and the reason; it is checked before any work, so no scan runs and no report is
written (exit code 1). The comparison never changes the exit code.

- **JSON:** the `baseline` object (report schema 1.12, `docs/JSON_SCHEMA.md`).
- **Markdown and HTML:** a "Findings since the baseline" section (the counts per class,
  the findings that are not unchanged, up to 40 rows).
- **Text:** one line. **SARIF:** nothing.

```text
sarand --full -f json -o before                      # the reference
sarand --full --baseline reports/before.json         # later: what changed?
```

## Gate and exit codes (slice F2: decided, not built yet)

The owner decided the following on 2026-11-24; `docs/R14D1_PLAN.md`, section 9, has the
design. Until F2 is built the comparison is information only.

| Policy | The gate fails when |
|---|---|
| `never` (default) | never: a baseline changes no exit code |
| `new` | a valid finding is `new` |
| `new-critical` | a Critical finding is `new` |
| `critical` | any Critical finding is present, new or old |

What is Critical (the same for `new-critical` and `critical`): every valid secret finding
(valid means not a test fixture), an advisory whose severity is `critical` (`high` and lower
are not), and a health condition id that the project classification marks critical
(`health.critical_ids`; an ordinary tool failure is not). Nothing is guessed from a summary,
a message or a tool name. When criticality cannot be decided it is not assumed, and the
uncertainty is reported in the gate result instead of failing the gate or passing silently.
`fixed`, `unchanged` and `not_checked` are never counted as new by the gate.

Exit codes: `0` success, `1` general run error, `3` the gate failed, `4` the baseline
reference is unusable (today an unusable reference exits `1`; F2 changes it to `4`).

## Independence

The comparison reads two reports and the results of the run; it never imports
`sarand.structure`. The structure package is imported only when `--structure` builds one,
so a findings-only run does not pay for the structural comparison. A test runs the real
command and asserts it.

## Limits

- A reference made by a different project, or with other settings, is compared as is; the
  comparison does not check that the two runs are comparable beyond the rules above.
- Only the failures, advisories and secret findings are compared. Todos, tool versions
  and the health score are not findings.
- `unchanged` findings are counted, not listed; the JSON `old` and `new` of a listed
  finding hold the evidence of both sides.

## Tests

`tests/test_findings_baseline.py` covers every state, the key rule for each class, the
direction of a change, identity that survives wording, order and line numbers, a class
the schema did not record, every way a reference can be unusable, determinism, a real
rendered report read back, and the independence from the structure package.
`tests/test_findings_baseline_cli.py` covers the command: the JSON key, the other
formats, the refusals, a run without the option, and the import check.
