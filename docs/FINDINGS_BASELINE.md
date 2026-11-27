# Findings baseline: what changed since a previous report

Status: the library, the `--baseline` option (slice F1 of R14-D1, `docs/R14D1_PLAN.md`)
the gate policies with their exit codes (slice F2) and the waivers (slice F3). SARIF
fingerprints (F4) are not built yet. Without `--baseline-gate` the comparison is
information only and never changes the exit code.

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
written (exit code 4). The comparison changes the exit code only when `--baseline-gate`
asks for it (below).

- **JSON:** the `baseline` object (report schema 1.12, `docs/JSON_SCHEMA.md`).
- **Markdown and HTML:** a "Findings since the baseline" section (the counts per class,
  the findings that are not unchanged, up to 40 rows).
- **Text:** one line. **SARIF:** nothing.

```text
sarand --full -f json -o before                      # the reference
sarand --full --baseline reports/before.json         # later: what changed?
```

## Gate and exit codes

`--baseline-gate POLICY` (only with `--baseline`; the default is `never`) lets the
comparison decide the exit code. The design is in `docs/R14D1_PLAN.md`, section 9.

| Policy | The gate fails when |
|---|---|
| `never` (default) | never: a baseline changes no exit code |
| `new` | a valid finding is `new` (a failure, an advisory of any severity, a secret that is not a fixture) |
| `new-critical` | a Critical finding is `new` |
| `critical` | any Critical finding is present, new or old |

**What is Critical** (the same for `new-critical` and `critical`; explicit, never guessed
from a summary, a message or a tool name):

- **Secret findings:** every valid one. Valid means not a test fixture: `is_test_fixture`
  comes from the project's explicit `[secrets] fixture_paths` list. A fixture secret is
  never Critical and never counted by any policy.
- **Advisories:** only severity `critical`. `high`, `moderate` and lower are not Critical.
  An advisory with no severity, or one this version does not know, is *uncertain*.
- **Failures:** only through a health critical condition (`health.critical_ids`). An
  ordinary tool failure is not Critical. The kinds `hardcoded_secrets` and
  `security_finding_detected` restate secrets and advisories and are left to those rules
  (otherwise a `high` advisory would be Critical through its health condition). A
  condition of kind `test_check_unavailable` means a check gave no verdict: it is
  *uncertain*, not a failure.

**A new Critical failure.** A condition id is built from a *set* of tools, so it changes
when that set changes: fixing one of two failing suites yields another id and is not a new
problem. For the kinds that come from failures (`test_suite_failed`,
`dependency_policy_failure`, `security_tool_failure`) a condition therefore counts as new
only when a failure of that kind is `new` in the comparison (which already requires that
the reference ran the check). Other kinds (`broken_symlinks`) are new when their id is not
in the reference's `health.critical_ids`.

**What the gate never does.** `fixed`, `unchanged`, `changed` and `not_checked` are never
counted as new. When what is needed to decide is missing, Critical is not assumed: the
finding is listed under `uncertain` with the reason, it does not fail the gate (no false
failure) and it is shown in every report and in the closing summary (no silent pass).
The reasons: `severity_unknown`, `health_not_computed` (`--no-health`),
`reference_has_no_critical_ids` (a reference older than schema 1.5 or without health),
`check_unavailable_no_verdict`, and the `not_checked` reasons of the comparison
(`reference_check_not_run`, `reference_file_skipped`, `class_not_recorded_in_reference`).

**The result** is `baseline.gate` in the JSON report (schema 1.12, no new version):
`policy`, `verdict` (`not_gated`, `pass` or `fail`), `failed_on` (each with `class`, `id`,
`state` `new` or `existing`, `rule`, `label` and `family`), `waived` (the failed items a
waiver covers, each with its `waiver`), `uncertain` (`class`, `id`, `reason`, `label`) and
`waivers` (`as_of`, and the lists `expired`, `unused` and `exceeded`). Markdown and HTML show a "Gate" part, text one line, and the closing summary of
the command prints `Gate    : FAILED ...` or `Gate    : passed ...`. A gate failure still
writes the report.

**Exit codes.**

| Code | Meaning |
|---|---|
| `0` | success |
| `1` | general run error (an invalid option, a report or snapshot that could not be written, a snapshot target that cannot be used) |
| `3` | the gate failed |
| `4` | the baseline reference is unusable (the findings baseline or the structural one): invalid, incompatible, missing |

A baseline error is never confused with a gate failure. If the gate fails and a report or
snapshot error happened too, the exit code is `3` (the other error is still printed): the
gate is the signal a pipeline acts on.

```text
sarand --full --baseline reports/before.json --baseline-gate new-critical
```

## Waivers

A waiver tells the gate not to fail on a finding the project accepts on purpose. It never
hides the finding: it moves from `failed_on` to `waived`, stays in every report and in the
closing summary, with its reason, owner and end date. Waivers count only when a gate
policy other than `never` is on; with `never` the file is not even read.

They are written in `.sarand.toml`, the file of the license policy and the secret
settings, as an array of tables:

```toml
[[waivers]]
id = "dependency_advisory:0123456789ab"
reason = "No fixed release; the vulnerable path is not reachable (ticket 123)"
owner = "m.soleimani"
created = 2026-11-27
expires = 2027-02-27
reference = "https://example.org/issues/123"

[[waivers]]
rule = "advisories:RUSTSEC-2024-0001"
covers = 2
reason = "Both affected crates are build-time only"
owner = "m.soleimani"
created = 2026-11-27
expires = 2027-01-31
```

| Key | Meaning |
|---|---|
| `id` | one exact finding or condition: the `id` the report and the gate print (`<kind>:<12 hex digits>`) |
| `rule` | a whole rule, `<class>:<family>`: the class is `secrets`, `advisories` or `failures`; the family is the pattern name of a secret, the advisory id, the category of a failure, or the kind of a health condition (the `family` of a failed item) |
| `covers` | only for a `rule`, and required: the most findings the rule may cover |
| `reason`, `owner` | required, not empty |
| `created`, `expires` | required, real dates (`2026-12-31`, not a string) |
| `reference` | optional: a ticket or a link |

Exactly one of `id` and `rule` is given.

**What the rules guarantee.**

- A waiver is a loan, not a permanent exception: `created` cannot be in the future,
  `expires` cannot be before it, and the two cannot be more than 366 days apart.
- An **expired** waiver (its `expires` date is before today; the day itself still counts)
  suppresses nothing. The gate fails again and the report lists the waiver under
  `waivers.expired` with how many failing findings it would have covered.
- A broad waiver cannot silently cover a later, different finding. A `rule` waiver
  declares `covers`; if more findings match it than that, it applies to **none** of them
  and is listed under `waivers.exceeded`. To accept the new finding too, the owner has to
  raise `covers` on purpose.
- A waiver that covers nothing (the finding was fixed, or never existed) is listed under
  `waivers.unused`, so stale waivers are visible and can be removed. It does not fail the
  run.
- Two waivers with the same scope are an error. When two different waivers match one
  finding, the first in the file covers it and the second is `unused`.
- Only what the gate would fail on is waivable: an `uncertain` finding never fails, so a
  waiver aimed at it is `unused`.
- Anything wrong in the file (an unknown key, a bad type, a missing field, a duplicate,
  invalid TOML) is an error, never ignored: the command stops before any work with exit
  code `1` and writes no report, because an ignored waiver would silently change the
  gate.

The closing summary shows the effect:

```text
Gate    : passed (policy new), 1 waived
          ~ secrets: conf.py (AWS Access Key ID) (waived by #1, m.soleimani, until 2027-02-27)
Waivers : 1 expired
          ! #2 expired 2026-11-20 (m.soleimani); it would cover 1 failing finding(s)
```

The date used is the local date of the run; it is stored as `waivers.as_of`, so a report
says which day its waivers were judged on.

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
`tests/test_baseline_gate.py` and `tests/test_baseline_gate_cli.py` cover the policies and
the exit codes. `tests/test_waivers.py` covers reading the file (every invalid case and
the date boundaries), the application rules and the waivers through the gate;
`tests/test_baseline_waivers_cli.py` covers them on the command.
