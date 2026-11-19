# R14-A3: review of the import classification

Scope: gate criteria 2 (import relationships correctly classified) and 4 (internal and
external dependencies distinguished) of `docs/R14A_PLAN.md` section 15, on two real
repositories. This file adds evidence; it does not replace `docs/R14A_GATE_REPORT.md`,
whose gate table is updated in the final check of all 11 criteria.

The reviewer is the engineer who built the tool, which is a limitation; every row carries
its location and evidence so the owner can check any of them. Rates from 50 rows are
**estimates, not accuracy**.

## Method

1. The import edges of `--structure` (one per imported module or name of a statement)
   are sorted by path, line, column and requested name. A simple random sample of 50 is
   drawn with `random.Random(14)`: the same for both repositories, no selection by
   difficulty, so rare classes are as rare in the sample as in the project.
2. For every sampled row `scripts/structure_eval_imports.py` **recomputes the answer
   without the structure code**: the flags from the syntax tree (`lazy`, `conditional`,
   `type_only`, `relative`, `star`, by the rules of `docs/STRUCTURE.md`), the
   standard-library test from `sys.stdlib_module_names`, the repository test from the
   file system, and the sections of `pyproject.toml` that declare the package. A row
   whose boundary class (internal, standard library, external) or flags differ is marked
   `DISAGREE`.
3. The reviewer then reads each row (the import line, its scope, the target) and records
   a verdict: `correct`, `wrong`, `ambiguous` or `undecidable`, with a note when it is not
   `correct`.
4. The tree of the sarand sample is the archive of `main` as uploaded by the owner
   (commit `3fe6f32`). Running the script again on a changed tree draws a different
   sample, because the sample is a function of the tree and the seed; the reviewed rows
   are the TSV files below. The click sample is the uploaded `click-main`.

Verdict rules. An **internal** or **standard library** row is `correct` when the import
statement exists at the location, the target is the module the written name binds to, and
the flags match the position of the statement. An **external** row is `correct` when the
package is not in the repository and not in the standard library and its
declared/unmatched label agrees with the declarations in `pyproject.toml`, `wrong` when
it does not, and `ambiguous` when the label follows the documented rule but is
misleading in substance.

## Results

| | sarand | click |
|---|---|---|
| Edges in the project | 2,498 | 708 |
| Sample | 50 | 50 |
| Sample classes | 30 standard library, 19 internal, 1 `external_unmatched` | 24 standard library, 24 internal, 2 `external_unmatched` |
| Flags in the sample | 3 `lazy` | 10 `relative`, 3 `lazy`, 1 `lazy` and `relative`, 3 `conditional`, `relative` and `type_only` |
| Independent recomputation agrees | 50 of 50 | 50 of 50 |
| Verdicts | 49 correct, 1 ambiguous, 0 wrong | 48 correct, 2 wrong, 0 ambiguous |

Internal, standard-library and flag results: **100 of 100 correct** on both repositories,
and the independent recomputation agrees on all 100 rows. The internal rows include
absolute imports through a package root (`python/`, `src/`), relative imports, a
re-exporting package (`from click import Option`), submodules imported by name
(`from sarand.renderers import json_renderer`) and sibling test modules (`from _helpers
import write`), and the `lazy`, `relative`, `conditional` and `type_only` flags.

The three external rows (all `external_unmatched`) are where the classification is
weak. The boundary (external, not in the repository, not standard library) is right in
all three. The declared/unmatched label is not:

| Row | Package | What `pyproject.toml` says | Verdict |
|---|---|---|---|
| sarand 21 | `yaml` | `PyYAML` is a declared runtime dependency; the import name differs from the distribution name | `ambiguous`: documented (`docs/STRUCTURE.md`: "`yaml` and `pyyaml`", no installed metadata is read) but misleading |
| click 37 | `pytest` | declared in `[dependency-groups]` (`tests`, `tests-random`, `typing`) | `wrong`: declared in `pyproject.toml`, which the documentation names as a source, and reported unmatched |
| click 47 | `pytest` | the same | `wrong` |

## Population audit of `external_unmatched`

Three rows say little about the whole list, so the audit looks at **every**
`external_unmatched` edge of both projects (`--audit-unmatched`; not a sample):

| Project | `external_unmatched` edges | Declared somewhere in `pyproject.toml` | Not declared |
|---|---|---|---|
| sarand | 53 | 53 (`pytest` 37 in `optional-dependencies.dev`, `yaml` 16 as runtime `PyYAML`) | 0 |
| click | 42 | 35 (`pytest` 33 in `[dependency-groups]`, `pallets_sphinx_themes` 2 in the `docs` group) | 7 (`typing_extensions` 3, `PIL` 3, `_typeshed` 1) |

The cause is in the reader of declarations (`python/sarand/core/components.py`): for
Python it reads `[project].dependencies`, the Poetry dependency tables and
`requirements.txt`, and **not** `[project.optional-dependencies]` or PEP 735
`[dependency-groups]`; and it matches by import name against distribution name. So
`external_unmatched` is, in these two projects, mostly "declared in a section that is not
read, or under a different distribution name", not "not declared". The list is the
"unresolved external" list of the documentation, but a reader would take it as
undeclared imports.

## Verdict for the criteria (proposed; the owner decides in the final check)

| # | Criterion | Proposed status | Why |
|---|---|---|---|
| 2 | Import relationships correctly classified | **Pass** | fixtures (A1); 100 of 100 reviewed rows correct, flags included; independent recomputation agrees on all 100; the cycles and the dynamic import of click were inspected (`docs/R14A_GATE_REPORT.md`) |
| 4 | Internal and external dependencies distinguished | **Fail** on the declared-versus-imported part; the internal/external/standard-library boundary passes | the plan row asks for a declared-versus-imported report at level 4; that report is wrong for declarations outside the runtime section (53 of 53 and 35 of 42 `external_unmatched` edges are declared) |

Limits of this evidence: one reviewer; 50 rows per project; the standard-library test used
Python 3.12.3 in the sandbox (the sets of later interpreters differ slightly); only
`pyproject.toml` was read for declarations, not Cargo manifests or `requirements.txt`
(neither project's Python imports depend on them); click has no `external_declared` edge,
so that class was reviewed only through sarand's population count (10 edges, not
sampled).

## Decision requested

The two gaps are **not fixed** here, because A3 code must not change without the owner's
permission. The options:

1. Fix inside A3: read `optional-dependencies` and `dependency-groups` into
   `declared_in` with the section name (for example `group:tests`), and keep the
   documented import-name rule (or add a small, documented alias table); add fixtures;
   re-run this review.
2. Keep the behaviour, document the limit in `docs/STRUCTURE.md` (which sections are read
   and that `external_unmatched` is not "undeclared"), and record criterion 4 as met
   with a documented limitation after the owner accepts that.
3. Defer the declared/unmatched label to a later stage and mark criterion 4 as failed
   for A3.

The recommendation is option 1 or 2 before the gate is accepted, because the current
label misleads in exactly the two projects that were evaluated.

## Files

- `scripts/structure_eval_imports.py` and `tests/test_structure_eval_imports.py`: the
  sampler, the independent recomputation and the audit, with tests.
- `docs/eval/r14a-imports-sarand.tsv`, `docs/eval/r14a-imports-click.tsv`: the reviewed
  rows (verdict and note in columns 3 and 4, the evidence last).
- `docs/eval/r14a-imports-sarand-summary.json`, `docs/eval/r14a-imports-click-summary.json`:
  class counts, agreement, verdict tally and the population audit.
