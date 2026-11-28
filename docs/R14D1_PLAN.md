# R14-D1: plan for the findings baseline and the structural baseline

Status: plan, written 2026-11-21 after the owner's decision on the scope of D1. Nothing
described here is implemented yet. Each part is marked with the slice that builds it.

## 1. Scope

D1 delivers two **independent** comparisons. They share neither model nor code path, and
the cost of one is never paid by the other.

| | Findings baseline | Structural baseline |
|---|---|---|
| Compares | the findings of two analyses (failures, advisories, secrets, known issues) | two `--structure` snapshots |
| Rules | Amendment 1 (`docs/R14A_PLAN.md` section 7 and the R13 finding ids of `docs/FINDINGS.md`) | the identity design of `docs/R14A_ADR_STRUCTURAL_IDENTITY.md` |
| Question | what is new, fixed, unchanged, changed | which files, symbols, relations, cycles and entry points were added, removed or changed |
| Gate | yes (CI policy, exit code) | no: information only |
| Link between them | only by ids and origins; a structural change is never a finding and a finding change is not a structural change | the same |

Out of D1: incremental analysis and caches (D2), the architecture and impact analysis
(B), the local type inference and the `__getattr__` rule (decided after D1).

## 2. Structural baseline

### 2.1 What is compared

Two snapshots of one project, an older (the reference) and a newer (the current). Each
part has its own identity:

| Part | Identity | Reported as |
|---|---|---|
| File | repository-relative path | added, removed, changed (size, completeness, language) |
| Module | name and root | added, removed, changed |
| Symbol | the match classes of `structure/identity.py` (`exact`, `probable`, `ambiguous`, `unmatched`) | added, removed, unchanged, content changed, moved, ambiguous |
| Relation | kind, matched source symbol, matched target symbol or external name | added, removed, changed (confidence, method, flags, count) |
| Import edge | importer module, target, kind | added, removed, changed (class, confidence, flags) |
| Cycle | the set of module names | added, removed, eager changed |
| Entry point | type, name, target | added, removed, changed |

Content change and identity change stay apart: a symbol with the same id and another
fingerprint is `content_changed`, never removed plus added. A moved symbol (`probable`)
and an ambiguous one are reported as such and are never turned into a definite match. A
renamed symbol is an unmatched pair, as in the ADR.

### 2.2 When two snapshots can be compared

The result starts with a verdict, and the verdict decides what the rest may claim:

| Verdict | Condition | Effect |
|---|---|---|
| `comparable` | same structure schema, same fingerprint basis, every file `full` in both | everything is reported as found |
| `ids_only` | the fingerprint basis differs (another Python minor) | symbols match by id only; no `content_changed` is claimed |
| `partial` | some files are not `full` in one or both snapshots, or a path moved into or out of the secret exclusion | the parts that depend on those files are reported `uncertain`, with the paths and the reason; they are never counted as removed |
| `incompatible` | the structure schema is not one the comparison knows | no comparison; the reason names both schemas |
| `invalid` | the file is not a snapshot, the integrity digest does not match, or a required part is missing | no comparison; the reason says what is wrong |

Absence is not removal: a path, symbol or relation missing from the newer snapshot is
reported as removed only when the newer snapshot covers that file completely.

### 2.3 The snapshot file (slice S2)

An envelope around the existing `structure` object of the report: a snapshot format
number, the structure and report schema versions, the fingerprint basis, the effective
settings that change the content (size limit, the paths excluded as secrets), and a
SHA-256 digest of the canonical structure. It carries no time, so the same project and
the same code always write the same bytes. A JSON report that has a `structure` key is
also accepted as a reference (its settings are then read from the report).

Writing never destroys the reference. A snapshot is written to a temporary file in the
same directory and renamed into place; an existing file is replaced only with an explicit
option, and then its previous generation is kept next to it.

### 2.4 Surface (slice S2)

Opt-in, like `--structure`: a comparison against a reference gives the JSON key
`structure_comparison` (a new minor schema), a short Markdown section and a text line.
The report that has no reference stays byte-identical. A reference that cannot be used
(`invalid`, `incompatible`) is an error that names the file and the reason, never an
empty comparison.

## 3. Findings baseline

### 3.1 What is compared

The reference is a previous JSON report. Identity is the R13 finding id
(`core/finding_identity.py`), computed from structured fields, never from text:

| Class | Id | In the reference since | Changed means |
|---|---|---|---|
| Classified failure | `failure_id` | schema 1.1 (id stored from 1.5; older ones are recomputed from the fields) | the same id with other evidence (return code, summary) |
| Advisory | `advisory_finding_id` (advisory id, package, version), recomputed from the fields | 1.3 | the same id with another severity, fixed versions or applicability |
| Secret finding | kind, path and pattern name, with the count per pair | always | the same pair with another count |
| Health critical failure | `critical_ids` | 1.5 | same id, other tools |

States: `new`, `fixed`, `unchanged`, `changed` and `not_checked`. The master plan's
`regressed` is the direction of a `changed` entry (`worse`, `better`, `neutral`) where an
order exists (advisory severity, secret count), and its `uncertain` is `not_checked` or
an ambiguous match. Nothing is dropped.

**The key rule.** A reference finding is `fixed` only if the source of that finding ran
to a verdict in the current run. If the check did not run, was inconclusive or is
unavailable, the finding is `not_checked`. A class that the schema of the reference
predates (for example advisories in a 1.2 report) is `not_checked` as a class, never
`new`. This uses the check states the report already has.

### 3.2 Gate, waivers, SARIF (slices F2 to F4)

- **Gate (F2):** policies `never` (default; a baseline never changes the exit code),
  `new` and `new-critical` and `critical` (a new finding of that level fails). A distinct
  exit code for a failed gate and for an unusable reference; the report says why a gate
  passed or failed. The default must not block an existing project for findings it
  already had.
- **Waivers (F3):** scope (finding id or rule), reason, owner, creation date, expiry,
  optional reference, and a matching policy. An expired waiver suppresses nothing; a
  broad waiver cannot silently cover a later, different finding; every applied waiver is
  visible in the report. The file format follows the existing configuration-file
  convention of the project (`core/secrets_config.py`), designed in F3.
- **SARIF (F4):** the finding id as `partialFingerprints` and stable rule ids, without
  changing level or severity.

### 3.3 No cost for the other path

The findings comparison reads only the reference report and the current findings. It does
not import the structure package and does not build a structure. A test enforces that
the findings path does not load `sarand.structure`.

## 4. Slices and order

| Slice | Content | Output |
|---|---|---|
| S1 | structural comparison as a library: the comparison function, verdicts, the result model, canonical serialization | tests with fixtures, no CLI |
| S2 | snapshot file, safe write, CLI option, `structure_comparison` key, Markdown and text, docs | schema minor, goldens, real runs |
| F1 | findings comparison as a library and the options that read the reference | tests, states, key rule |
| F2 | gate policy and exit codes | tests, report text |
| F3 | waivers | tests |
| F4 | SARIF fingerprints | SARIF validity test |
| P | performance of both paths, measured separately with the method of `docs/R14D1_BENCHMARK.md` (a `compare` mode is added to the benchmark script) | numbers in `docs/` |
| C | real runs on the phone and the sandbox; documentation of the contracts; the closing report | acceptance table |

Order: S1, S2, F1, F2, F3, F4, P, C. Each slice is delivered with its tests and its
chain, and nothing later is started on a red result.

## 5. Acceptance criteria

The criteria are those of the owner's decision, made checkable:

| # | Criterion | Evidence |
|---|---|---|
| 1 | Findings: Amendment 1 behaviour kept | tests for new, fixed, unchanged, changed, not_checked; the key rule; goldens of default reports unchanged |
| 2 | Findings: identity stable | the same findings with other text, order or line numbers give `unchanged` |
| 3 | Structural: two identical snapshots are `unchanged` | test on a real snapshot against itself |
| 4 | Structural: add, remove, change of file, symbol, relation | fixture pairs |
| 5 | Structural: a fingerprint change is not an identity change | `content_changed` against removed plus added |
| 6 | Structural: incomplete, invalid, incompatible snapshots | one test per verdict; absence never reported as removal |
| 7 | Structural: deterministic | the same pair twice and with shuffled input order gives the same bytes |
| 8 | Structural: versioning and reference preservation | schema and fingerprint-basis tests; a snapshot is never overwritten without the option; the previous generation is kept |
| 9 | Integrated: tests, quality tools | `ruff`, `mypy`, `bandit`, `markdownlint`, `pytest`, `git diff --check`, CI |
| 10 | Integrated: real outputs against the schema | real `sarand` runs on sarand and click; JSON checked against `docs/JSON_SCHEMA.md` |
| 11 | Integrated: performance of both paths recorded | the `compare` benchmark; the findings path shown not to load the structure package (sandbox numbers in `docs/R14D1_COMPARE_RESULT.md`; the phone run belongs to C) |
| 12 | Integrated: documentation | architecture, contracts and usage updated (en and fa where the project does so) |

## 6. Stop rule

Findings are classified Blocker (must be fixed), Major (must be fixed in this scope),
Minor (fixed when cheap) and Deferred (recorded with the reason). When every Blocker and
Major is fixed and the acceptance and regression tests pass, D1 is accepted and closed. It
reopens only for a reproducible defect, a failed criterion or a valid regression; an audit
without a hypothesis, new evidence or a new criterion is not run.

## 7. Defaults taken without an answer

These are decided here so that work can start; each can be changed at the start of its
slice.

1. The reference of the findings baseline is a previous JSON report (no new file format);
   the reference of the structural baseline is a snapshot file, or a JSON report with a
   `structure` key.
2. The structural comparison has no gate and no exit-code effect; only an unusable
   reference is an error.
3. `regressed` is a direction on a changed finding, not a separate state.
4. Secret findings are identified by kind, path and pattern name, with the count per
   pair; a line number is never an identity.
5. A snapshot carries no timestamp.
6. D1 does not change `scripts/structure_bench.py` except to add the `compare` mode in
   slice P.

## 8. Progress

| Slice | Result | Evidence |
|---|---|---|
| S1 structural comparison (library) | Pass, closed | commit `cd2f807`, CI run `44968799181` green, 1,858 passed and 10 skipped, `docs/STRUCTURE_BASELINE.md` |
| S2 snapshot file, command line, report key | Pass, closed | commit `5830064`, CI run `45119095300` green, 1,898 passed and 10 skipped, report schema 1.11 |
| F1 findings comparison, `--baseline` | Pass, closed (after one CI fix) | commit `eb2bb33`: local chain green (1,936 passed, 10 skipped); CI run `45497163018` failed only in gitleaks, which flagged two secret-looking literals in `tests/test_findings_baseline_cli.py`; the fix `e5692d0` builds the literals at run time and `.gitleaksignore` holds the two fingerprints; the docs commit `88a6fe8` followed; CI run `45759439044` green on every job |
| F2 gate policies, exit codes | Pass, closed (after two chain fixes) | commit `a806f7c` (`--baseline-gate`, exit codes 3 and 4, 60 new tests); the owner's chain first stopped on mypy (two dicts unpacked into typed parameters in the tests) and on bandit B105 (constant names containing `pass` and `secret`), both fixed on the owner's machine before the commit; chain green (1,996 passed, 10 skipped); CI run `45911758761` green on every job; the decisions taken while building are under "Decisions taken in F2" below |
| F3 waivers | Pass, closed (after three chain fixes) | commit `d31cdc4` (`[[waivers]]`, 57 new tests); CI run `45971453963` failed only in gitleaks (an id-shaped test literal `ID_B`), the fix commit built it at run time through a helper (ruff FLY002 refuses a join of constants) and ignored the `d31cdc4` fingerprint; before that the chain stopped on ruff ISC004 (a two-line f-string in a tuple); chain green (2,053 passed, 10 skipped); CI run `45992391386` green on every job; the decisions are under "Decisions taken in F3" below |
| F4 SARIF fingerprints | Pass, closed | commit `4fa459d` (secrets carry `partialFingerprints`, 13 new tests, the `hybrid` SARIF golden gained two keys); the owner's chain green (2,066 passed, 10 skipped); CI run `46001284295` green on every job; the decisions are under "Decisions taken in F4" below |
| P performance of both paths | Pending: built and measured in the sandbox, not yet run on the owner's chain or CI, and not yet on the phone | `compare` mode in `scripts/structure_bench.py`; numbers in `docs/R14D1_COMPARE_RESULT.md`: the findings comparison and the gate add nothing measurable and never load the structure package; `--structure-baseline` adds 0.68 s (14.5 %) on the 603-file input; no optimization was made; the commit and the green CI run are recorded here when they exist |
| C | Pending | |

### Decisions taken in F1 (they refine section 3.1)

- **Evidence of a changed failure** is the return code and the evidence signals. The
  summary text is left out: it carries counts and durations that change every run and
  would make every failure `changed`.
- **Health critical ids** are not a class of their own: they restate failures and
  known issues. The gate slice (F2) decides how a finding counts as critical.
- **Where the reference's check coverage comes from:** the report's own `state` of each
  check (schema 1.6); older reports are read with the same function from the raw fields.
- **A secret whose file no longer exists** is `not_checked` (`file_not_scanned`): the run
  cannot tell a deleted file from an ignored one.
- **The findings path does not load `sarand.structure`**: the two module-level imports in
  `cli.py` and `json_renderer.py` became local, and a test runs the real command.

### Decisions taken in P

- **The cost is measured on the whole command**, one configuration per option, each against
  the configuration it extends (`plain` for `--baseline`, `--baseline` for the gate,
  `--structure` for `--structure-baseline`). The reference report and the snapshot are made
  once per input, outside the measurement. A function-level timing would miss the reading
  of the reference and the report, which are part of what a user pays.
- **Isolation is evidence, not an assumption:** a probe in a fresh interpreter records
  whether `sarand.structure` was imported; the command fails when a findings configuration
  imported it or a structure configuration did not.
- **One code version per run.** Comparing two commits stays the job of `run`.
- **No optimization:** the numbers show no cost on the findings path and one seventh on the
  structure baseline; the plan's rule (profile first) leaves them as they are.
- **Sandbox numbers are labelled as such;** the phone run is part of C.

### Decisions taken in F4 (they refine section 3.2)

- **What carries a fingerprint:** the results that have an identity in the findings
  comparison: secrets (new) and advisories (already). The same key,
  `sarandFindingId/v1`, holds the same id the comparison, the gate and the waivers print,
  so one finding has one name everywhere. Todo notes and the unlocated tool-output
  results have no identity and get none; failures are not SARIF results (they stay in the
  `sarand` property bag).
- **The id has no line number**, so a moved finding is the same finding. Several secrets
  of one pattern in one file share an id; a second key, `sarandOccurrence/v1`
  (1-based, in line order), makes the pair unique without touching the id. Results keep
  the order of the report, so only the two keys were added to the `hybrid` golden.
- **Rule ids were already stable** (derived from the name, advisory results use the
  advisory id); F4 pins them with tests and does not change them. No `level` or severity
  change, and no SARIF `suppressions` for waived findings (not part of this slice).
- **Validity test:** `tests/test_sarif_fingerprints.py` checks every fixture's log for the
  SARIF 2.1.0 structure code-scanning tools rely on (version, schema, unique and declared
  rules, levels, locations, fingerprint keys of the form `name/vN`, and that a rule with
  its fingerprints names one result). It is structural, not a run against the official
  JSON schema (no network in the tests).

### Decisions taken in F3 (they refine section 3.2)

- **File format:** `[[waivers]]`, an array of tables in `.sarand.toml`, next to `[licenses]`
  and `[secrets]` (the other loaders read only their own table, so the file is shared).
  Code in `core/waivers.py`; the gate (`core/gate.py`) applies the waivers.
- **Scope:** exactly one of `id` (a finding or condition id) and `rule`
  (`<class>:<family>`; the family is the pattern name of a secret, the advisory id, the
  category of a failure or the kind of a condition). The gate puts the `family` on every
  failed item so that a rule has something stable to name.
- **A broad waiver cannot silently grow:** a `rule` waiver must declare `covers`; with
  more matches than that it applies to none and is reported as `exceeded`. This is the
  "matching policy" of the owner's decision: exact for `id`, capped for `rule`.
- **A waiver is a loan:** `created` and `expires` are required real dates, `created` is
  not in the future and `expires` is at most 366 days after it. The expiry day itself
  is still valid. An expired waiver suppresses nothing and is reported with how many
  failing findings it would have covered.
- **Visible, never hidden:** a covered finding moves to `baseline.gate.waived` with its
  waiver; the closing summary, Markdown, HTML and text show it; `waivers` lists the
  expired, unused and exceeded waivers. `waived` and `waivers` are additive inside
  `baseline.gate` (schema 1.12, no new version).
- **Only a gate reads them:** with `never` or without `--baseline` the file is not read,
  so an invalid waiver cannot break a run that does not use it. With a gate on, an
  invalid file stops the command before any work (exit code `1`, no report): an ignored
  waiver would silently change the gate.
- **The date is an input:** `evaluate_gate` takes `today`; the command passes the local
  date and the report stores it as `waivers.as_of`.
- **Not waivable:** an `uncertain` finding never fails, so a waiver aimed at it is
  `unused`.

### Decisions taken in F2 (they refine section 9)

- **A new Critical failure is backed by a new failure.** A health condition id hashes a
  set of tools, so it changes when that set changes (fixing one of two failing suites
  gives another id). Comparing the id sets alone would fail the gate on a fix. For the
  kinds that come from failures (`test_suite_failed`, `dependency_policy_failure`,
  `security_tool_failure`) a condition counts as new only when a failure of the matching
  group or category is `new` in the findings comparison, which already requires that the
  reference ran the check. Kinds with no failure behind them (`broken_symlinks`) are new
  when their id is not in the reference's `health.critical_ids`; with no reference ids
  they are uncertain. This also makes the reference health optional for the failure kinds.
- **`test_check_unavailable` is uncertain, not a failure.** It is a health critical id, but
  it says a check gave no verdict; counting it would turn a missing tool into a gate
  failure, which the owner's rule on `not_checked` excludes. It is listed under
  `uncertain` (always for `critical`, only when new for `new-critical`).
- **`changed` is never new.** A secret whose count grew, an advisory whose severity rose
  or a failure whose evidence changed is an old finding; `critical` still fails on a
  Critical one that is present, whatever its state.
- **Uncertain does not change the verdict** (`pass` with a list), and is shown in the JSON,
  Markdown, HTML, text and the closing summary, so a pass is never silent about it.
- **The comparison moved after the health score** in `cli.run` (the gate reads
  `health.critical_ids`); `--no-health` leaves conditions unknown, which is uncertain.
- **Exit codes** `4` replaces `1` for an unusable findings or structural baseline (their
  documents and tests changed); a snapshot target that cannot be used stays `1`; the gate
  failure `3` wins over a report or snapshot error `1`.
- **`--baseline-gate`** given without `--baseline` is a general error (`1`, no report);
  another value is refused by the argument parser (`2`).

## 9. Decisions of 2026-11-24 for F2, and how to continue

### The owner's decisions

1. **What is Critical** (one definition for `new-critical` and `critical`; explicit, never
   guessed from a summary, a message or a tool name):
   - **Secret findings:** every valid finding is Critical. Valid means not a test fixture:
     `is_test_fixture` is set from the project's explicit `[secrets] fixture_paths` list,
     and health and the risks already exclude those findings the same way.
   - **Advisories:** only severity `critical`. `high`, `moderate` and lower are not Critical.
   - **Failures:** only the health failure ids that the project classification explicitly
     marks Critical (`health.critical_ids`). An ordinary tool or check failure is not
     Critical by itself.
   - If what is needed to decide Critical is missing, it is **not** assumed Critical; the
     uncertainty is kept and reported, and it never lets the gate pass by mistake.
2. **Exit codes:** `0` success, `1` general run error, `3` the gate failed, `4` the baseline
   reference is invalid, incompatible or unusable. A baseline error is never confused with a
   gate failure. Other exit paths are not changed without need.
3. **Gate policies** (exactly four): `never` (default; a baseline changes no exit code),
   `new` (a new valid finding fails the gate), `new-critical` (a new Critical finding fails
   it), `critical` (any Critical finding, new or old, fails it). `fixed`, `unchanged` and
   `not_checked` are never counted as new or as fixed by the gate; in particular
   `not_checked` must not give a false failure.
4. **Authority:** F1 and F2 may be completed without asking again for small fixes: apply,
   validate, fix real defects, keep the English and Persian documentation in step with the
   behaviour, commit, push, check the CI of that commit. No scope growth, no repeated audits.
5. **Delivery:** the complete implementation, valid tests with the boundary cases, bilingual
   documentation, the result of the quality tools and tests, the commit SHA and the green CI
   run of that commit, and a short report (changes, decisions, results, what remains).

### The design that follows from them (taken within that authority)

- **Where criticality comes from.** Secrets and advisories are classified per finding as
  above. The failure criticality is the set of health critical condition ids
  (`health.critical_ids`), compared as a set between the reference and this run, because a
  condition id is built from a tool set and not from one failure. Two kinds of condition
  restate the other classes and are left to those classes' own rules: `hardcoded_secrets`
  and `security_finding_detected` (otherwise a `high` advisory would be Critical through its
  health condition, which contradicts decision 1). The kind is the prefix of the id before
  the colon.
- **Uncertainty is reported, not decided.** A new advisory whose severity is unknown, a
  finding that is `not_checked` and would count if it were new, and critical conditions that
  cannot be known (health was not computed, or the reference did not record `critical_ids`)
  are listed in the gate result as `uncertain` with the reason. They do not fail the gate
  (it must not give a false failure) and they are visible (it must not pass silently).
- **The result** is `baseline.gate`: `policy`, `verdict` (`not_gated`, `pass` or `fail`),
  `failed_on` (the findings that failed it) and `uncertain`.
- **Options:** `--baseline-gate {never,new,new-critical,critical}` (default `never`), valid
  only with `--baseline`.
- **Exit code order.** An unusable baseline (findings or structural) is `4` and is decided
  before any work. If the gate fails the run exits `3`, also when a report or snapshot error
  happened too (that error is still printed): the gate is the signal a pipeline acts on.
- **Where it changes existing behaviour:** the F1 and S2 refusals of an unusable reference
  exit `1` today and become `4`; the documents of F1 and S2 and their tests change with it.

### How to continue (for the next session)

1. Get a fresh zip of `main` after every delivery is committed; the files the owner's
   `ruff format` rewrote differ from any sandbox copy, so apply changes against that zip only.
2. F2 was built as in the design above (done; see "Decisions taken in F2"). The design was: `core/gate.py` (new), the `conditions` and secret
   `fixture` fields in `core/baseline.py` views, `--baseline-gate` in `config.py` and
   `cli.py` (health is computed after the report data exists, so the comparison and the gate
   move after `compute_health_score`), exit codes `3` and `4`, the gate lines in Markdown,
   HTML and text, tests for every policy and every boundary (unknown severity, `not_checked`,
   missing health, fixture secrets, a reference without `critical_ids`), documentation in
   English and Persian, the JSON schema note (the `gate` object is inside `baseline`,
   schema 1.12, no new version).
3. F3 (waivers) and F4 (SARIF `partialFingerprints` from the finding id) were built as in
   "Decisions taken in F3" and "Decisions taken in F4". P (the `compare` mode of
   `scripts/structure_bench.py` and its numbers) was built as in "Decisions taken in P".
   What is left: C (real runs on sarand and click, the closing report with Pass, Fail or Pending per
   criterion).
4. The recurring pitfalls: `ruff` has FURB and RUF015 on (use `min()` and `next()`); mypy
   rejects a name re-bound with another type inside one function; wrap multi-line f-string
   groups in list literals in parentheses; no shebang without the executable bit; no `assert`
   in production code; a constant whose NAME contains `pass`, `secret`, `token` or `pwd` and
   is assigned a string is flagged by bandit B105 (rename it, the value may stay); mypy
   rejects a `**dict` of mixed value types unpacked into typed parameters (annotate the dict
   as `dict[str, Any]`); a literal that looks like a secret in a test is flagged by gitleaks
   (build it at run time through a helper: ruff FLY002 folds a join of constants, and an id-shaped
   value named like a secret is flagged too); ruff ISC004 wants a multi-line f-string inside a
   tuple or list in parentheses; never run `gitleaks dir .` on the working tree (it reads
   `__pycache__` and `target/`), scan only the changed files; a new file in `python/sarand` needs its tests and both language
   documents; `markdownlint "**/*.md"` runs in CI.
