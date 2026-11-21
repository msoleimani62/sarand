# R14-A3: declared dependencies fixed and the import review repeated

This file follows `docs/R14A_IMPORT_REVIEW.md`, which found that the declared/unmatched
label of external imports was wrong for dependencies declared outside the runtime section
of `pyproject.toml`. The owner decided to fix it inside R14-A3 (option 1). The earlier
review, its rows and its verdicts are **kept unchanged**; this file adds the fix, the
repeated review and the evidence. Where this file corrects a statement of the earlier one,
it says so.

The reviewer is the engineer who built the tool, which is a limitation. Every row keeps
its location and evidence, and the old and the new verdict sit side by side.

## What was wrong, in one paragraph

`external_declared` required the import name to equal a distribution name declared in
`[project].dependencies`, a Poetry dependency table or `requirements.txt`. Dependencies in
`[project.optional-dependencies]`, in PEP 735 `[dependency-groups]` or in
`build-system.requires` were never read, and an import name that differs from its
distribution name (`yaml` and `PyYAML`) never matched. So `external_unmatched` mostly
meant "declared in a section that is not read, or under another name", not "undeclared".

## The change

| Part | What it does now |
|---|---|
| `core/components.py`, `python_declarations()` | one reader for every Python declaration, each with its section: `project.dependencies`, `project.optional-dependencies.<extra>`, `dependency-groups.<group>`, `build-system.requires`, `tool.poetry.dependencies`, `tool.poetry.dev-dependencies`, `tool.poetry.group.<group>.dependencies`, `requirements.txt`. `{include-group = ...}` entries and the Poetry `python` pin are not packages and are skipped. The older `declared_dependencies()` is derived from it and still reports only its three sections, so Quick Context does not change (apart from the Poetry `python` pin, which was never a package) |
| `structure/distributions.py` | a short **explicit table** of import names and every distribution known to ship them (`yaml`: `pyyaml`; `PIL`: `pillow`, `pillow-simd`; `cv2`: four `opencv-*`; ...), written as data, with an invariant test. Nothing is guessed: a name that is not in the table stays unmatched, installed packages are never read |
| `structure/imports.py`, `declared_match()` | the one rule used everywhere: the distribution of the same name first (`definite`); then every table provider that is declared (`probable`, method `declared-distribution`, with a note); `declared_in` lists every declaration found |
| `structure/build.py` | labels are `<dir>/pyproject.toml#<section>` or `<dir>/requirements.txt`; a manifest in a subdirectory keeps its directory |
| `structure/resolve.py` | usage sites use the same `declared_match` rule. The first version of this change left the old name-only test here, so import edges said `external_declared` and usage sites said `external_unmatched` for `yaml`; the comparison below caught it and a regression test now covers it |
| schema | structure `schema` 4, report `schema_version` 1.10 (`docs/JSON_SCHEMA.md`); documented in `docs/STRUCTURE.md` and `docs/STRUCTURE.fa.md` ("Declared dependencies": import name, distribution name, declaration, section, group, `external_declared`, `external_unmatched`, what is read, what is not) |

## Tests

| File | Tests | Covers |
|---|---|---|
| `tests/test_structure_declarations.py` (new) | 18 | the reader (every section, the interpreter pin, odd or broken manifests, the older reader unchanged); labels for runtime, optional, group, build, Poetry and `requirements.txt` declarations; one package declared in several places; a nested manifest; `yaml` and `PIL` through the table; a table pair with nothing declared; a pair not in the table (`fitz` and `pymupdf`) not guessed; several providers (`cv2`); the same-named distribution winning; a literal dynamic import; internal and standard-library names not taken over; the JSON labels; the table's own invariants; usage sites following the same rule |
| `tests/test_structure_eval_imports.py` (rewritten for the new script) | 8 | independent recomputation of every kind of import, a missed declaration reported as a disagreement, determinism, no trailing whitespace, verdicts, the re-review mode (the earlier file is only read), the audit, a manifest outside the importer's tree |
| `tests/test_structure_diff.py` (new) | 3 | the comparison of two outputs recognises a change of external classification alone and does not hide any other change |
| `tests/test_structure.py` (one test updated) | 1 | the test that said `yaml` is not `pyyaml` now states the new rule and the new label |

In the sandbox the whole suite equals the baseline (no failure) and the five JSON goldens
differ only in `schema_version`. The owner's chain (ruff, mypy, bandit, markdownlint,
pytest) and CI of the commit are run by the owner and are reported separately.

## Nothing else changed (old and new code on identical input)

`scripts/structure_diff.py` dumps the structure with each version of the code on the same
project and compares the two. For both projects the symbols, relations, entry points,
cycles, files, modules and language are identical, and **only edges with external targets
changed** (and only their class, confidence, resolution method and note):

| | sarand (the sampled tree) | click |
|---|---|---|
| Edges | 2,498; 53 changed | 708; 38 changed |
| Edge fields changed | `target_class` 53, `resolution_method` 53, `note` 53, `confidence` 37 | `target_class` 38, `resolution_method` 38, `note` 38, `confidence` 35 |
| Symbols, relations, entry points, cycles, files, modules | identical | identical |
| Usage sites `external_declared` / `external_unmatched` | 28 / 218 to 246 / 0 | 0 / 689 to 684 / 5 |
| `declared_in` labels | `pyproject.toml` becomes `pyproject.toml#project.dependencies` for `rich` and `filelock` | none declared before |

The totals of usage sites do not change (246 and 689); they only move between the two
classes. Files: `docs/eval/r14a-imports-sarand-regression.json`,
`docs/eval/r14a-imports-click-regression.json`.

## The 100 earlier rows, reviewed again with the new code

The rows are the 50 + 50 of the earlier review, matched by location and evidence on the
same trees. For every row the class, target, flags and method of the new code were
compared with the earlier ones, and the independent recomputation (which now also reads
the declaration sections and the manifests of every directory) was run again.

| | sarand | click |
|---|---|---|
| Independent recomputation agrees | 50 of 50 | 50 of 50 |
| Rows whose class, target, flags or method changed | 1 (row 21) | 2 (rows 37 and 47) |
| Earlier verdicts | 49 correct, 1 ambiguous | 48 correct, 2 wrong |
| New verdicts | 50 correct | 50 correct |
| Verdicts changed | row 21 | rows 37 and 47 |

The changed rows and why their verdict changed:

| Row | Earlier | Now | Reason |
|---|---|---|---|
| sarand 21, `import yaml as _yaml` | `external_unmatched`, `ambiguous` | `external_declared`, `probable`, method `declared-distribution`, `declared_in` `pyproject.toml#project.dependencies`, `correct` | PyYAML is a declared runtime dependency and the explicit table maps `yaml` to `pyyaml`; the confidence is `probable` on purpose (the pair comes from the table) |
| click 37, `import pytest` | `external_unmatched`, `wrong` | `external_declared`, `definite`, three labels (`dependency-groups.tests`, `.tests-random`, `.typing`), `correct` | declared in three PEP 735 groups |
| click 47, `import pytest` | `external_unmatched`, `wrong` | the same, `correct` | the same |

The other 97 rows are unchanged in every compared field and keep `correct`; the note of
each says so. Files: `docs/eval/r14a-imports-sarand-rereview.tsv` and
`docs/eval/r14a-imports-click-rereview.tsv` (old verdict, new verdict, reason, old and new
class and declarations, evidence), next to the untouched earlier files.

## Every external import, recounted

The audit (`--audit-external`) takes **every** external edge of the project, not a sample,
and compares the structure with the manifests read independently.

| Project | External edges | Before (`external_declared` / `external_unmatched`) | After |
|---|---|---|---|
| sarand | 63 | 10 / 53 | **63 / 0**: `pytest` 37 (`project.optional-dependencies.dev`), `yaml` 16 (`project.dependencies`, through the table), `rich` 9 and `filelock` 1 (`project.dependencies`) |
| click | 42 | 0 / 42 | **38 / 4**: `pytest` 33 (three groups), `PIL` 3, `pallets_sphinx_themes` 2 (`dependency-groups.docs`); unmatched `typing_extensions` 3 and `_typeshed` 1 |

Packages where the structure and the independently read manifests differ: none in either
project. Declared edges with no declaring manifest above the importing file: 0 in both.

**Correction to the earlier review.** It said that 35 of click's 42 unmatched edges were
declared and that `PIL` (3 edges) was not. That audit read only the root `pyproject.toml`.
`PIL` is imported by `examples/imagepipe/imagepipe.py`, whose own
`examples/imagepipe/pyproject.toml` declares `pillow`, so the declared count was 38. The
four that remain unmatched are really not declared: click declares no `typing_extensions`,
and `_typeshed` is a type-checker-only module.

## What is still limited (documented in `docs/STRUCTURE.md`)

- The table is short and not complete. An import name that differs from its distribution
  name and is not in the table stays `external_unmatched` although it may be declared. It
  is never guessed; installed packages are never read.
- A match through the table is `probable`, not `definite`.
- `setup.py`, `setup.cfg`, `Pipfile`, `requirements-*.txt`, `uv`, `pdm` and `hatch` tables
  are not read.
- A declaration anywhere in the scanned project counts for the whole project, not only for
  the directory of its manifest. In these two projects the audit found no declared edge
  without a declaring manifest above the importing file, so no harm was observed here.
- The review is one reviewer, 50 rows per project, on two repositories; the
  standard-library test used Python 3.12.3.

## Proposed gate status (the owner decides in the final check of all 11 criteria)

| # | Criterion | Proposed status | Why |
|---|---|---|---|
| 2 | Import relationships correctly classified | **Pass** | unchanged: 100 of 100 reviewed rows correct, independent recomputation agrees, nothing but external classification changed |
| 4 | Internal and external dependencies distinguished | **Pass**, pending the CI of the commit | the declared-versus-imported report matches the manifests on every external edge of both projects (63 of 63 and 42 of 42 edges agree), the 100 rows are correct, the limits above are documented and not hidden |
| 11 | No critical regression | **Pending** | the sandbox suite equals the baseline and the old-versus-new comparison shows nothing else changed; the owner's chain and the CI of this commit have not run |

## Files

- Changed: `python/sarand/core/components.py`, `python/sarand/structure/build.py`,
  `imports.py`, `resolve.py`, `model.py`, `serialize.py`,
  `python/sarand/renderers/json_renderer.py`, `scripts/structure_eval_imports.py`, the
  tests listed above, the schema-version assertions of eight existing tests, the five JSON
  goldens,
  `docs/STRUCTURE.md`, `docs/STRUCTURE.fa.md`, `docs/JSON_SCHEMA.md`,
  `docs/JSON_SCHEMA.fa.md`, `CHANGELOG.md`.
- New: `python/sarand/structure/distributions.py`, `scripts/structure_diff.py`,
  `tests/test_structure_declarations.py`, `tests/test_structure_diff.py`, this file and
  the `docs/eval/r14a-imports-*-rereview*`, `*-regression.json` files.
- Not touched: `docs/R14A_IMPORT_REVIEW.md` and `docs/eval/r14a-imports-sarand.tsv`,
  `r14a-imports-click.tsv` and their summaries, which stay as the record of the first
  review.
