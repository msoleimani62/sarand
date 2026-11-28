# R14-D1 closing report

Baselines for sarand: the structural comparison and the findings comparison (with the
gate, the waivers and the SARIF fingerprints). The plan is `docs/R14D1_PLAN.md`; this page
closes it against its twelve acceptance criteria (section 5 of the plan).

Status words: **Pass** (the evidence exists and is green), **Pending** (the evidence is
built but a run that only the owner can make is missing), **Fail** (none).

## Slices

| Slice | Commit | CI run | Tests after it |
|---|---|---|---|
| S1 structural comparison | `cd2f807` | `44968799181` | 1,858 passed, 10 skipped |
| S2 snapshot, command line | `5830064` | `45119095300` | 1,898 passed, 10 skipped |
| F1 findings comparison | `eb2bb33`, fix `e5692d0`, docs `88a6fe8` | `45759439044` | 1,936 passed, 10 skipped |
| F2 gate, exit codes | `a806f7c` | `45911758761` | 1,996 passed, 10 skipped |
| F3 waivers | `d31cdc4`, fix commit | `45992391386` | 2,053 passed, 10 skipped |
| F4 SARIF fingerprints | `4fa459d` | `46001284295` | 2,066 passed, 10 skipped |
| P benchmark `compare` | `0368816` | `46087877493` | 2,072 passed, 10 skipped |

## The twelve criteria

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Findings: Amendment 1 behaviour kept | Pass | `tests/test_findings_baseline.py` (23) and `tests/test_findings_baseline_cli.py` (5): new, fixed, unchanged, changed, not checked; the goldens of default reports carry no baseline content and did not change (the golden tests show no mismatch) |
| 2 | Findings: identity stable | Pass | `tests/test_finding_identity.py` (19) and the identity cases of `tests/test_findings_baseline.py`: other text, order or line numbers give `unchanged`; the SARIF fingerprint has no line number (`tests/test_sarif_fingerprints.py`) |
| 3 | Structural: two identical snapshots are `unchanged` | Pass | `tests/test_structure_compare.py` (28); also check A5 of the real-run acceptance on sarand, click and requests |
| 4 | Structural: add, remove, change of file, symbol, relation | Pass | `tests/test_structure_compare.py`, `tests/test_structure_identity.py` (34), `tests/test_structure_symbols.py` (32); check A8 of the real-run acceptance |
| 5 | Structural: a fingerprint change is not an identity change | Pass | `content_changed` against removed plus added in `tests/test_structure_compare.py` |
| 6 | Structural: incomplete, invalid, incompatible snapshots | Pass | one test per verdict in `tests/test_structure_compare.py` and `tests/test_structure_baseline_cli.py` (14); an unusable reference is exit code 4 |
| 7 | Structural: deterministic | Pass | the same pair twice and with shuffled input order gives the same bytes (`tests/test_structure_compare.py`) |
| 8 | Structural: versioning and reference preservation | Pass | schema and fingerprint-basis tests; a snapshot is never overwritten without `--replace-structure-snapshot` and the previous generation is kept (`tests/test_structure_baseline_cli.py`) |
| 9 | Integrated: tests, quality tools | Pass | for every slice the owner's chain (`ruff`, `mypy`, `bandit`, `markdownlint`, `pytest`, `git diff --check`, gitleaks of the changed files) and a CI run green on every job (table above) |
| 10 | Integrated: real outputs against the schema | Pending | the real-run acceptance (`scripts/d1_acceptance.py`) passed all eleven checks in the sandbox on sarand (439 files), on the installed packages `click` 8.5.0 (17 files) and `requests` 2.34.2 (19 files) and on a small tree; the same run on the phone, on the sarand checkout and on the click repository, is the missing piece (below) |
| 11 | Integrated: performance of both paths recorded | Pass | `docs/R14D1_COMPARE_RESULT.md`: the sandbox run and the phone run; the findings comparison and the gate add nothing measurable and never load the structure package; the structural baseline is below a second; no optimization was needed |
| 12 | Integrated: documentation | Pass | `docs/STRUCTURE_BASELINE.md`, `docs/FINDINGS_BASELINE.md` (en and fa), `docs/JSON_SCHEMA.md` (en and fa), `docs/RENDERERS.md` (en and fa), the README option tables (en and fa), `docs/R14D1_BENCHMARK.md`, `docs/R14D1_COMPARE_RESULT.md`, the changelog; `tests/test_json_schema.py` and `tests/test_readme_sync.py` keep the pages and the code in step |

## Criterion 10: what the real-run acceptance checks

`scripts/d1_acceptance.py` runs the real `sarand` command on a copy of a project (the
original is never touched) and checks the outputs, not the code:

| Check | What it shows |
|---|---|
| A1, A2 | the reference run exits 0 and every key of its JSON is documented in both schema pages, with the schema version stated |
| A3, A4, A5 | against its own reference, an unchanged project exits 0, the gate passes, nothing is new, fixed or changed, and the structure is `comparable` with no change |
| A6, A7 | after a planted secret, a new file and a removed file, `--baseline-gate new` exits with code 3 and the gate names the new secret |
| A8 | the structural comparison reports the added and the removed file |
| A9 | the keys of that report, including `baseline`, its `gate` and `structure_comparison`, are documented |
| A10 | a waiver for the planted secret gives exit 0 with one waived item |
| A11 | the SARIF result of the planted secret carries the id the gate printed |

The sandbox run (2026-11-28, Python 3.12.3, the code of the commit after F4): sarand,
`click` 8.5.0 and `requests` 2.34.2, **all 33 checks passed**. The two packages are the
installed releases, not their repositories (the sandbox has no network), so the run on the
click repository stays with the owner. The planted secret is built at run time and exists
only in the copy.

To finish criterion 10, on the phone, from the sarand checkout with the environment
active (the click repository cloned once):

```text
git clone --depth 1 https://github.com/pallets/click /tmp/click-src
python scripts/d1_acceptance.py --out /tmp/acc --project sarand=$PWD --project click=/tmp/click-src
cat /tmp/acc/acceptance.md
```

`acceptance.md` is the record and `acceptance.json` the full one. When every check passes
for both projects, criterion 10 is Pass and D1 is closed under its stop rule (section 6 of
the plan); a failed check is a reproducible defect and reopens D1 for that defect only.

## Findings of the closing audit

None open. Blockers: none. Majors: none. The records that were corrected on the way are in
the plan (the chain fixes of F1 to F3, the pitfalls list of section 7 of the continuation
guide).

## Deferred

- SARIF `suppressions` for waived findings: not part of this slice and not needed by a
  criterion; a waived finding is visible in the JSON, the reports and the closing summary.
- Profiling `compare_structures` and the snapshot read: only if a later measurement shows a
  cost that matters (none of the two runs did).
