# Check states

Every check sarand runs (a test suite, a quality tool, a security tool) ends in
exactly one **state**. `python/sarand/core/check_states.py` is the only place that
decides which one; the health score, the risk rules, Quick Context, the package
summary and the status badges all ask it, and a test fails if one of them reads
the raw record flags itself.

## The states

| State | Meaning | How a check gets there | Reached a verdict? |
|---|---|---|---|
| `passed` | The tool ran and exited 0 | exit code 0, not skipped, not inconclusive | yes |
| `failed` | The tool ran and exited non-zero | exit code other than 0 (what kind of failure is in `failures`) | yes |
| `skipped` | The check did not run | tool not installed, option such as `--skip-audit`, nothing to check | no |
| `inconclusive` | The tool exited 0 but could not finish its job | for example an audit with the network unreachable | no |
| `unavailable` | The runner could not run the tool at all | timeout, tool not found, operating-system error (recognised by the runner's own sentinel line together with its exit code) | no |
| `unknown` | A contradictory record (skipped **and** inconclusive) | never produced by sarand's own runners; kept visible instead of guessed | no |

`not_applicable` is a reserved name and no check can be in it, on purpose. An
analyzer runs only when its project marker exists, so a check that does not apply
to a project is never requested and is not part of the expected workload. A tool
that was requested but could not run is `skipped` or `unavailable`.

## How each state is counted

| State | Execution coverage | Test / quality score | Security score | Tooling points |
|---|---|---|---|---|
| `passed` | executed | counts as passed | counts as passed (15 when all that ran passed) | counts as ran |
| `failed` | executed | counts as failed | counts as failed (5) | counts as ran |
| `skipped` | gap | left out of the ratio | left out; all left out gives 8 | not ran |
| `inconclusive` | gap | left out of the ratio | left out; all left out gives 8 | not ran |
| `unavailable` | gap | stays in the ratio and earns no points; not called a failure | no clean score while one exists: 8 (5 if another check failed) | not ran |
| `unknown` | gap | left out of the ratio | left out; all left out gives 8 | not ran |

An `unavailable` check proves nothing, so it is never rewarded: in tests and
quality it stays in the denominator (a suite that passes beside one that timed out
scores like a suite that passes beside one that failed), and in security it keeps
the category at 8, never at the clean 15. It is also never punished as a finding:
no "test suite failed" critical failure, no lint recommendation, no security
finding or policy violation; the critical message and the recommendation say that
the check could not run and earned no points.

The deprecated fields `health.confidence`, `checks_run`, `checks_skipped`,
`checks_inconclusive` and `missing_tools` keep their original arithmetic, in which
an `unavailable` check still counts as ran (see `docs/EXECUTION_COVERAGE.md`).

## Where each state shows up

| State | Risk `CHECKS-SKIPPED` | Risk `SEC-CHECK-FAILED` | Quick Context | Markdown / HTML badge | JSON | SARIF |
|---|---|---|---|---|---|---|
| `passed` | no | no | listed as passed | `PASS` | result as before | none |
| `failed` | no | yes (security group) | "N check(s) failed" | `FAIL` | `failures[]` | the tool's own warning / error lines |
| `skipped` | counts | no | "N check(s) skipped" | `SKIP` | `coverage_gaps[]` (`skipped`) | none |
| `inconclusive` | counts | no | "N check(s) could not finish" | `INCONCLUSIVE` | `coverage_gaps[]` (`inconclusive`) | none |
| `unavailable` | counts | no | "N check(s) could not run" | `UNAVAILABLE` | `coverage_gaps[]` (`unavailable`) and `failures[]` with the cause | the tool's own lines, if any |
| `unknown` | counts | no | "N check(s) with a contradictory record" | `UNKNOWN` | `coverage_gaps[]` (`unknown`) | none |

A check with no verdict is **never** a security finding, a dependency policy
violation, a failed test suite or a lint failure. It stays visible instead: as a
coverage gap, in the risk `CHECKS-SKIPPED`, in Quick Context and in a
recommendation that says why it gave no verdict.

## The risk `CHECKS-SKIPPED`

The rule id keeps its legacy name. It counts every check with no verdict
(`skipped`, `inconclusive`, `unavailable` and `unknown` together) across tests,
quality and security, and fires when the count reaches **3**
(`CHECKS_SKIPPED_MIN`, unchanged and still provisional). With 2 such checks it
does not fire; with 3 it does, whatever mix of states they are in. The reason
names the mix, for example `3 of 11 checks gave no verdict (2 skipped, 1
unavailable; threshold 3)`.

## What changed in R13-D

Before, health and the risk rules each read a check's state in their own way, and
the two disagreed: an `inconclusive` check lowered the score but never counted
toward `CHECKS-SKIPPED`, and an `unavailable` check (a timeout) was scored as a
failed test suite and reported as one. Now there is one reading, and an
`unavailable` check is neither rewarded nor misreported:

| One suite passes, one other... | tests | tooling | critical failure |
|---|---|---|---|
| passes (full evaluation) | 25.0 | 15.0 | none |
| fails | 12.5 | 15.0 | "One or more test suites failed." |
| times out, before R13-D | 12.5 | 15.0 | "One or more test suites failed." |
| times out, now | 12.5 | 7.5 | "Test check could not run (cargo test); it gave no verdict and earns no points." |

The timed-out suite no longer claims a failure it did not report, and it scores
no better than the same suite failing; its tooling points drop because the tool
did not run (before, the legacy reading counted it as ran). Execution coverage
(50% here), `CHECKS-SKIPPED`, Quick Context and a recommendation keep the gap
visible. The weights and `CHECKS_SKIPPED_MIN = 3` are unchanged.
