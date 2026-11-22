# R14-A3: final check of the 11 gate criteria

This file records the evidence of the final check. It adds to `docs/R14A_GATE_REPORT.md`,
`docs/R14A_IMPORT_REVIEW.md` and `docs/R14A_IMPORT_REREVIEW.md`, none of which is changed.
**The statuses below are proposals: the gate and the ADR are not accepted.** The ADR
(`docs/R14A_ADR_STRUCTURAL_IDENTITY.md`) stays `Proposed` until the owner formally accepts
the gate after reviewing this file.

> Update, 2026-11-21: the owner accepted the gate and the ADR; the decision is in
> `docs/R14A_GATE_ACCEPTANCE.md` (commit `2118c89`, CI run `44914439029`). The
> statuses in this file are the proposals as they were reviewed; they stay as
> evidence and are not rewritten.

The reviewer of every sampled row is the engineer who built the tool; rates from samples
of 50 rows are estimates, not accuracy.

## Ledger

| Commit | What | CI run |
|---|---|---|
| `31a038d` | R14-A2: symbols, relations, entry points | 44305577315, success |
| `3fe6f32` | R14-A3: stable identity, fingerprints, evaluation | 44480908868, success |
| `030663b` | review of 100 sampled imports | 44621798223, success |
| `dda226f` | **final A3 code**: every dependency section read, import names matched to distributions | 44890290097, success |

At `dda226f` the owner's chain passed: ruff (one error fixed, six files reformatted),
mypy (302 source files), bandit, markdownlint, `git diff --check` and pytest (1,819 passed,
10 skipped). The CI run covered Python 3.11, 3.12, 3.14 and 3.15, Windows, macOS, Rust,
bandit, markdownlint, actionlint, gitleaks, cargo-deny and the Docker Compose, Turborepo,
PDF and Kubernetes jobs.

## Decisions of the owner recorded here

- The declared/unmatched defect of the import classification is fixed inside A3 (option 1),
  with tests and a repeated review.
- The two findings of the relation evaluation stay out of A3 and unchanged, to be decided
  after D1: no local type inference for `x = Class(...)` and annotated parameters
  (16 percent of the sampled uncounted sites of sarand and 38 percent of click's really
  point at repository symbols), and the class `__getattr__` rule (17 of 50 sampled
  `Unknown` relations of click are attributes the class assigns itself).
- Fingerprints are compared only between outputs of the same Python minor version
  (`meta.fingerprint_basis`); D1 builds and compares on one interpreter and records the
  environment.

## Phone benchmark

Device: Redmi Note 8 Pro, MediaTek MT6785V/CC, 8 cores, `MemTotal` 5,771,204 kB, Linux
4.14.186 aarch64 in a Kali NetHunter proot, Python 3.14.6. `uptime` is not readable in the
proot, so the load was checked only before the runs (`free`, `pgrep`).

Design: the code of A2 (`31a038d`) and of A3 (`dda226f`) in two `git worktree`s, both run
with the `scripts/structure_eval.py` of A3 on **the same input** (the A3 worktree), two
rounds of five runs, `sarand.__file__` printed for every round to show which code ran.
The CLI numbers of A2 measured earlier were on another input and are not compared.

Final run (input 437 files, 5,078 symbols, 9,496 relations; every run identical, exit code
0, no stderr; the sha256 of each version is the same in both rounds):

| Round | A2 median (min to max) | A3 median (min to max) | A3 time | RSS A2 / A3 (KiB) |
|---|---|---|---|---|
| 1 | 6.716 s (5.937 to 7.134) | 7.325 s (7.079 to 7.761) | +9.1% | 159,336 / 160,776 |
| 2 | 6.586 s (6.225 to 6.855) | 7.276 s (6.728 to 7.987) | +10.5% | 159,236 / 159,476 |

Mean of the two medians: about +9.8% time; tracemalloc peak 45,493 KB (A2) and 45,819 KB
(A3). The whole `sarand --structure` command on the same input (A3 only): 16.66 s and
16.41 s, peak RSS 132,536 KB and 137,304 KB.

Earlier sessions on commit `3fe6f32`, kept for the record: phone busy, A3 +19% and +17%;
phone idle, +11.4% and +8.8% (mean +10.1%). In the sandbox (x86, Python 3.12) the cost was
about +8% to +17%; timing the fingerprint function alone gave about 15 percent of the
structure build.

Limits: two rounds are not a statistical result; the load was not logged during the runs;
the same script (A3) measured both versions.

## The 11 criteria

| # | Criterion | Proposed status | Evidence | Limits and open points |
|---|---|---|---|---|
| 1 | Structural model stable and documented | Pass | `docs/STRUCTURE.md` and `.fa.md`, `docs/JSON_SCHEMA.md` and `.fa.md`, schema tests (structure schema 4, report 1.10) | the schema was raised twice in A3 (3, then 4) |
| 2 | Import relationships correctly classified | Pass | 100 of 100 reviewed imports correct, the independent recomputation (flags, standard library, repository, manifests) agrees on all 100; the two cycles and the dynamic import of click inspected | 50 rows per project, one reviewer |
| 3 | Symbol relationships preserve uncertainty | Pass | seed-14 samples: 50 of 50 `Definite` and 50 of 50 `Probable` correct on sarand and on click; `Unknown` consistent with the documented rule | the `__getattr__` rule is over-conservative (open finding) |
| 4 | Internal and external dependencies distinguished | Pass after the fix | the declared-versus-imported report matches the manifests on every external edge of both projects (63 of 63, 42 of 42); the 100 rows re-reviewed are correct; the old-versus-new comparison shows only external edges changed | the explicit table is short; `setup.py`, `setup.cfg`, `Pipfile`, `requirements-*.txt`, `uv`, `pdm`, `hatch` are not read; a declaration counts for the whole project |
| 5 | Parser provenance preserved | Pass | every file `full` on both projects, none failed or skipped | |
| 6 | Stable identity design established | Pass | ADR, identity and match-class tests, the same-path correction by the owner | the ADR is `Proposed` |
| 7 | Dynamic limitations explicit | Pass | limitation fixtures, `docs/STRUCTURE.md`, the two findings of the evaluation documented | |
| 8 | Output deterministic | Pass | repeat runs byte-identical on both projects in the sandbox and on the phone (two rounds, stable sha256 per version) | |
| 9 | Tests cover supported and unsupported constructs | Pass | the suites of A1 to A3 and the new declaration, review and comparison tests; 1,819 passed at `dda226f` | |
| 10 | At least one real repository passes | Pass on two | sarand and click: no crash, no file lost, identical repeats, zero wrong results in the 50 `Definite` relations and the 50 reviewed imports of each | |
| 11 | No critical regression | Pass proposed; the owner decides | CI green at `dda226f`; the owner's full chain passed; the old-versus-new comparison shows nothing but external classification changed | fingerprints add about 10 percent to the structure build on the phone; whether that cost is acceptable is the owner's decision |

## Open items

- Formal acceptance of the gate and of the ADR (status change `Proposed` to `Accepted`), by
  the owner, after reviewing this file.
- D1 (baseline and comparison of two runs), then the stages B to F of R14. The two findings
  above are examined after D1.
- The stages A to H of R13 that await the owner's authorization are not started.
