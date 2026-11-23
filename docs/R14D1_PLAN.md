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
| 11 | Integrated: performance of both paths recorded | the `compare` benchmark; the findings path shown not to load the structure package |
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
| S2 snapshot file, command line, report key | Pending: delivered, awaiting the owner's chain | `docs/STRUCTURE_BASELINE.md` (Command line), `tests/test_structure_baseline_cli.py` |
| F1 to F4, P, C | Pending | |
