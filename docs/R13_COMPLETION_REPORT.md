# R13 completion report

Evidence-calibrated reporting, confidence semantics and risk integrity: stages A to
H. Stages A to G are verified by the owner's own terminal and CI (table below);
stage H (this report, the real-fixture comparison, `tests/test_ramz_real_fixture.py`
and the documentation) is verified when the same chain passes on it.

## A. Executive summary

sarand's reports could say things the evidence did not support. R13 fixed each one
at its source, in order, and pinned it with tests.

| Problem (confirmed) | What the report said | What it says now |
|---|---|---|
| A generic known issue | "Compilation or lint errors were detected." when only workflow, YAML and Markdown linters had failed | The failing tool and its category (`lint_failure`, `security_finding_detected`, `dependency_policy_failure`, ...) with the cause and a stable id |
| Confidence | "confidence 100%", also with nothing requested | Execution coverage `executed / requested`, "not available" when nothing was requested, with the note that it does not measure how complete or correct the analysis is |
| A security tool failing | "Security tool reported issues." for a timeout, a licence violation and an advisory alike | Security finding, dependency policy violation and tool failure are three things; an advisory is a tool result, applicability `unknown` |
| Skipped, inconclusive, unavailable | Read differently by health, risks and the renderers | One reading (`core/check_states.py`) used everywhere, with a formal table |
| Markers | Every `BUG` comment was a marker, the first marker per line only | Every marker is found and classified; only a TODO or FIXME written as a task is scored |
| One problem in many places | The same condition as a health critical failure, a known issue and a Quick Context line | One stable finding id; Quick Context shows it once |
| Formats disagreeing | Different error and warning counts, no failures or advisories in HTML, states only in Markdown | One set of lists (`core/report_views.py`), the same facts in Markdown, HTML, JSON, SARIF and text |

Hypotheses that did not hold: that the lock layout of the Ramz fixture differed
(withdrawn: it is a rendering ratio, and the working diff is 5 lines), and that a
timeout in the test group should leave the score ratio (rejected by the owner: it
raised the score; the check stays in the denominator and earns no points).

## B. Architecture changes

| Module | Stage | Role |
|---|---|---|
| `core/failures.py`, tables in `constants.py` | A | classify a check result by tool and evidence; known issues |
| `core/check_states.py` | B, D | the single reading of a check's state |
| `core/execution_coverage.py` | B | execution coverage, gaps and groups |
| `core/advisories.py` | C | advisories parsed from cargo audit and cargo deny |
| `core/markers.py` | E | marker categories and the one definition of actionable |
| `core/finding_identity.py` | F | stable finding ids (`<kind>:<12 hex>`) |
| `core/report_views.py` | G | the lists every renderer shares |

Models: `Failure`, `CoverageGap`, `Advisory`; `HealthScore` gained the coverage
fields and `critical_ids`; `ReportData` gained `failures`, `advisories`,
`known_issue_ids`; `TodoItem` gained `category`. JSON schema `1.0` to `1.6`
(additive only; the version history is in `docs/JSON_SCHEMA.md`).

## C. Confidence and coverage specification

See `docs/EXECUTION_COVERAGE.md`. In short: `execution_coverage = executed /
requested`, where executed means the state is `passed` or `failed`; skipped,
inconclusive, unavailable and unknown are not executed; nothing requested gives
`null` and "not available", never 100%. **Field-name decision:** option 1 of the
brief (additive). The new field is `execution_coverage`. The old `confidence` is
kept with its exact old arithmetic, because source inspection proved it is not
equivalent (it deduplicated kinds only in the denominator and counted a timeout
as run); it is deprecated, no longer shown in any report, and will not be removed
before schema 2.0.

## D. Security classification specification

See `docs/SECURITY_EVIDENCE.md`. A tool that could not run (timeout, not found)
gave no verdict and is not a finding. A recognised advisory is kept with its id,
package, version, kind, fixed versions, severity only when the tool printed one,
and sources. A dependency policy violation (cargo deny licences, bans, sources)
is not a vulnerability. Applicability is `unknown` for every advisory: sarand does
no reachability analysis, and no label of "exploitable" or "irrelevant" exists.
A confirmed vulnerability needs concrete evidence that sarand does not collect.

## E. Finding integrity

See `docs/FINDINGS.md` (identity and duplicates) and `docs/MARKERS.md`. Identity
comes from structured fields, never from the sentence; a condition that is a
health critical failure and a known issue has one id and counts once in Quick
Context; findings that read alike but differ keep separate ids.

## F. Test evidence

Run on the owner's terminal and in CI, one stage at a time:

| Stage | Commit | pytest (passed, skipped) | CI run |
|---|---|---|---|
| A | `3eee120` | 1436, 10 | 41802738433 |
| B | `cde9271` | 1466, 10 | green (all jobs) |
| C | `66a66a7` | 1501, 10 | 42521818749 |
| D | see `git log` | 1529, 10 | 42572508443 |
| E | `83f9f3e` | 1559, 10 | 42585275296 |
| F | `1c198b5` | 1578, 10 | 42694571943 |
| G | `01bd0c6` | 1602, 10 | 42746997234 |

Every one ran ruff lint and format, mypy, bandit, markdownlint, the full suite on
Ubuntu (Python 3.11, 3.12, 3.14, 3.15), macOS and Windows, Clippy, the Rust tests,
cargo deny, gitleaks and the real-tool jobs. No failure was left in any stage.

- **Passed:** the numbers above.
- **Skipped:** 10 tests, by their own skip conditions; not investigated in R13.
- **Not run:** validation of SARIF against the official schema (no validator in the
  repository, no network in the sandbox: SARIF is checked structurally); a live
  refresh of the advisory database.
- **Blocked:** nothing.

## G. Renderer comparison

The matrix of what each format carries is in `docs/RENDERERS.md`.

## H. Git status

Stages A to G are commits on `main` (table above). The changes of stage H are in
the working tree until the owner commits them; this report does not claim a clean
tree.

## I. Residual risks

| Risk | Evidence | Next action |
|---|---|---|
| The exact command of the historical Ramz run is unknown | the owner's shell history has no such command; the flags are inferred from the report (tests, quality, security, source included) | none needed: both reports include the same 12 checks, 39 files and 36 included files |
| The advisory database may differ between the two runs | its commit was not recorded for the historical run | none: both runs give 5 vulnerabilities and 13 warnings |
| 8 suppressed markers became 11 | the new scanner reports every marker on a line (R13-E); the three extra were not itemised | confirm by running the scanner on Ramz with the old and new code |
| Advisory reachability is not assessed | see section J, last part | a dedicated reachability feature, if wanted |
| SARIF is validated structurally only | no schema validator available | add one in CI when a pinned validator is chosen |
| `core/relevant_source.py` still weights every marker kind | recorded in R13-E, not changed | decide separately |
| `report_generation_failure` exists in the vocabulary and nothing produces it | R13-A | produce it from a real failure, or drop it |
| The same tool failing in two components under one label has one id | `docs/FINDINGS.md` | include the component in the id if it becomes a problem |

## J. Real-fixture before and after (Ramz)

**Inputs, verified.** Historical report: `sarand-ramz-report-historical.md`,
SHA-256 `4c6a0622147205b481ad4b3844d332036b75c5e1ccfe0456995d10926583c32d`
(matches the recorded digest), generated 2026-11-01 by sarand `160c589`.
Repository: Ramz `7252b1ca8fea9dc59ebfa082998d0da307cb4eb1` (tag `v0.3.2`) with
the `Cargo.lock` modification; the committed `Cargo.lock` plus the recorded patch
gives SHA-256 `906a1bd8198f58f2bcab13db40f3cfde647fb2ec1510a2f58e243d56ad920b87`,
which the working copy had before and after the new run. New reports: sarand
`01bd0c6`, `sarand --full`, on 2026-11-10 (cargo 1.97.1, rustc 1.97.1, cargo-audit
0.22.2, cargo-deny 0.20.2, Python 3.14.6), SHA-256 of the Markdown
`1ae1a238bd6d1714c75facdd93e07363d06c9fa8d4cf732a855462306a4c4792`, of the JSON
`2967fabf14ceb3055a692cd2a0d2b0c76a2e9d1bc1104e566fcfe0cf4d210b07`, of the SARIF
`81b49d25e968cd5312de20636b7284053e3050bfd1e4d5f3e643b7e5fa81d98e`. The
comparison uses the exact historical repository state; it is a same-repository,
same-checks comparison, not a byte-for-byte reproduction (different sarand code
is the point of it).

| Criterion (brief 11.5) | Before (`160c589`) | After (`01bd0c6`) |
|---|---|---|
| The generic phrase when no compiler failed | appears 3 times, as a known issue and a Quick Context critical finding | 0 times, in Markdown, JSON and SARIF |
| Failure of the non-compiler tools | not classified | `actionlint`, `yamllint`, `markdownlint`: `lint_failure`, each with an id |
| Confidence or coverage | "confidence 100%" | "execution coverage 100% (12 of 12 requested checks ran to a verdict)" with the note that it is not analytical certainty |
| Historical BUG markers | 8 `BUG` rows, no category | the same 8 rows, category `historical`: "0 actionable, 8 historical"; the health code points are unchanged (15.0) |
| Security tool failure, licence policy, vulnerability | one line: "Security tool reported issues." | two lines: a security finding reported by cargo audit and cargo deny ("a tool result; exploitability is not assessed") and a dependency policy violation ("not a vulnerability") |
| Advisories | not listed (only 13 `Warning:` lines and `error[...]` heads) | 18 listed by id: 5 vulnerability, 10 unsound, 3 unmaintained; severity none printed; applicability `unknown` |
| Errors and warnings | 12 errors and 37 warnings | 4 and 24, with 21 tool lines folded into the advisories (12 + 37 = 4 + 24 + 21) |
| Health critical failures vs risks | 1 critical failure; Quick Context showed 2 | 2 critical failures, each once in Quick Context; the risk says both restate the failed security checks |
| Counts across formats | not comparable | Markdown, JSON and SARIF: 18 advisories, 28 tool-output items, 6 failures with the same ids, 12 check states, coverage 12 of 12 |
| Health score | 76.0 (C): tests 25, quality 10, security 5, git 6, code 15, tooling 15 | 76.0 (C): the same breakdown |

The score is unchanged because R13 changed no weight and no scored fact: the same
checks ran and the same checks failed. Quality is 10.0 because 3 of 6 quality
checks passed (20 x 3/6); security is 5.0 because a security check failed.

**Claims that could not be verified.** The exact flags of the historical run
(inferred); the advisory database commit of the historical run; the three extra
suppressed markers; any reachability of the advisories by sarand (by design).

**Manual reachability evidence (not part of sarand's output).** From the Ramz
source at `7252b1c` and its `Cargo.lock`; advisory text as printed by cargo audit
in the fixture, not refreshed from the network, and the dependency crates were not
read.

| Advisory | Evidence in the Ramz source | Conclusion |
|---|---|---|
| RUSTSEC-2026-0391 (zstd, reused context) | `zstd::stream::Decoder::new` and `Encoder::new` per call in `backends-age/src/lib.rs`; no context is kept between calls | no evidence of context reuse; not established |
| RUSTSEC-2026-0403 (zstd-safe, streaming decompression of a legacy frame) | streaming `Decoder` is used; the `legacy` feature of zstd was not inspected | unknown |
| RUSTSEC-2026-0398 (zstd-safe `Seekable::decompress`) | no use of a seekable API in the source | no direct use found |
| RUSTSEC-2026-0410 (zstd-sys, WebAssembly) | the release targets are Linux, macOS, Windows and Android; none is WebAssembly | not applicable to the released targets; not established for other builds |
| RUSTSEC-2026-0385 (ctutils) | reached through `hybrid-array` and `module-lattice` (the `ml-kem` dependency); the constant-time functions used were not inspected | unknown |

## K. Health-score weight decision

**Original weights retained**, because no disproportionate penalty was
demonstrated. On the Ramz fixture the score is 76.0 before and after; security is
5.0 of 15 for any failed security check, quality 10.0 of 20 for 3 of 6 passing.
That a policy-only failure costs the same security points as an advisory is a
design property that this fixture cannot isolate (both occur together), so no
measurement supports a change. A proposal would need a synthetic comparison of the
two cases first.

## Acceptance criteria

| # | Status | Evidence |
|---|---|---|
| 1 | VERIFIED | stage A; the real run shows no compilation claim |
| 2, 3 | VERIFIED | stages A and C |
| 4, 5 | VERIFIED | stage C: applicability `unknown`, no exploitability claim |
| 6, 7 | VERIFIED | stage B and `docs/EXECUTION_COVERAGE.md` |
| 8, 19 | VERIFIED | stage D and `docs/CHECK_STATES.md` |
| 9, 10 | VERIFIED | stage E |
| 11, 12 | VERIFIED | stage F |
| 13 | VERIFIED | stage G and the real run (J) |
| 14 | VERIFIED through G | the tests of every stage; stage H adds the real-fixture tests |
| 15 | VERIFIED through G | the full suite green at every stage; behaviour changes are listed in `CHANGELOG.md` |
| 16 | VERIFIED through G | section F; stage H after its own chain |
| 17 | VERIFIED | every delivery was hash-guarded and refused a changed tree |
| 18 | by review | claims are limited to what sections F and J show |
| 20 | VERIFIED with the limits in J | exact repository state; exact flags inferred |
| 21 | VERIFIED | section C |
| 22 | NOT APPLICABLE | no weight changed (section K) |
| 23 | VERIFIED | each stage began after the previous one was verified |
