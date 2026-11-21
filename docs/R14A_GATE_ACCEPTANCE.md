# R14-A3: acceptance of the gate and of the ADR

Date of the decision: 2026-11-21. Decided by the owner after reviewing
`docs/R14A_FINAL_CHECK.md`. This file records the decision. It adds to
`docs/R14A_GATE_REPORT.md`, `docs/R14A_IMPORT_REVIEW.md`, `docs/R14A_IMPORT_REREVIEW.md`
and `docs/R14A_FINAL_CHECK.md`, none of which is changed. Where
`docs/R14A_FINAL_CHECK.md` says "proposed" or "not accepted", this file replaces that
status; the evidence in that file stays valid.

## Scope of the acceptance

The decision covers R14-A3 only. It does not approve the later stages of R14
automatically, and a pass does not mean that every architectural aspect is flawless or
that topics outside this stage are closed. The basis is the evidence of the
implementation, the tests, the review of the outputs, the performance analysis and CI.

## Decision

| Subject | Decision |
|---|---|
| The 11 acceptance criteria | Pass, all 11 |
| Gate of R14-A3 | **Accepted** |
| ADR of the structural identity (`docs/R14A_ADR_STRUCTURAL_IDENTITY.md`) | Proposed to **Accepted** |
| Performance cost of the current state | Accepted, with a duty to monitor it |
| Local type inference | Open, examined after D1 |
| The `__getattr__` rule | Open, examined after D1 |
| Performance comparison of the CLI between A2 and A3 | Not done, to be measured in D1 |
| Start of the later stages of R14 | After D1 is complete |

## Reasons for the gate

- Every criterion of the stage is accepted.
- The test suite ran with 1,819 passed and 10 skipped.
- Ruff, mypy, bandit and markdownlint passed.
- CI of the final A3 commit `dda226f` (run 44890290097) succeeded.
- `git diff --check` found nothing.
- The change in time and memory was measured and documented.

## Reasons for the ADR

- Structural identity is implemented and tested.
- Its behaviour under formatting changes, comments, docstrings and quote style was
  checked.
- Its effect on performance was measured.
- Its cost was judged acceptable against the value of the capability.

Accepting the ADR fixes the current architectural decision. It does not forbid a
review later if new evidence shows that a change is needed.

## Performance

Measured on the phone (see `docs/R14A_FINAL_CHECK.md`): the structure build takes
6.716 s (A2) and 7.325 s (A3) in round 1 (+9.1%), 6.586 s and 7.276 s in round 2
(+10.5%), a mean of about +9.8%; the tracemalloc peak is 45,493 KiB (A2) and
45,819 KiB (A3), about +0.72%.

The increase of about 9.8% is accepted because the capability adds a defined analytical
and architectural value, the memory increase is small, the time increase appears in
both rounds and is not a single outlier, and the evidence is not enough to reject the
capability for its cost. The cost is not unimportant, and the budget is not unlimited:
later changes measure it again.

### Duties for D1

1. Build a repeatable benchmark with a fixed input and the same environment.
2. Use the same Python minor version, the same settings, the same cache state and the
   same conditions in every comparison.
3. Record the spread, the minimum and the maximum, and the P95 where possible, beside
   the median.
4. Time the structure phases and the fingerprint computation separately, so that the
   source of an increase is known.
5. Run the benchmark on small, medium and large inputs. One input does not describe the
   whole project.
6. Optimize only after profiling has found the real bottleneck. No speculative change
   and no extra architecture for a few percent of time.
7. There is no direct A2 against A3 comparison for the CLI yet. A change in the CLI must
   not be attributed to A3 before D1 measures it.

## Open items outside the acceptance

Neither item blocks R14-A3, because both are outside its scope. Neither enters the code
without evidence.

### Local type inference

- Document the current behaviour first.
- Separate what is detected from what is not.
- Do not credit type inference to cases without enough evidence.
- Every extension comes with positive and negative tests.

### The `__getattr__` rule

- Separate the module behaviour from the class behaviour.
- Do not mix dynamic access with static access.
- Without enough evidence, report a limit or an uncertainty, not a firm finding.
- Define an independent test for every supported behaviour.

## Rules kept for the next stages

- The fingerprint stays versioned, so that a change of algorithm never causes a silent
  incompatibility.
- Structural identity, content identity and file-path identity stay distinct in the
  data model.
- No result is reported as a definite negative only because information is missing.
- The limits of the static analysis stay traceable in the provenance and in the output.
- The regression tests of the structural identity are kept.

## What remains to complete the record

This file and the status change of the ADR are a documentation change. The technical
acceptance is the owner's decision above; the record in Git is complete only when this
change is committed and its CI run succeeds. Until then the two are not the same thing.

## Next steps, in order

1. Commit this record and check CI.
2. D1: a valid, repeatable baseline on one Python minor version.
3. Complete the performance comparison of A2 and A3, the CLI and the internal phases
   included.
4. Examine local type inference and the `__getattr__` rule on the results of D1.
5. Continue the stages of R14 with the scope and acceptance criteria of each.
6. Keep all evidence, benchmark results and architectural decisions, so that no earlier
   audit is repeated.
