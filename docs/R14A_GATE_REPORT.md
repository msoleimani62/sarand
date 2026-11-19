# R14-A gate report

Scope: the repository intelligence core (`--structure`, R14-A1 to R14-A3), judged against
the acceptance gates of `docs/R14A_PLAN.md` section 15 and the validation method of
section 12. Everything below says what was measured, how, by whom and at which
verification level. Rates from samples this small are **estimates, not accuracy**.

The reviewer of every sampled row is the engineer who built the tool, which is a
limitation. Each row carries its source location and context, so the owner can check
any of them (`docs/eval/`).

## Gate table

| # | Criterion | Evidence | Status |
|---|---|---|---|
| 1 | Structural model stable and documented | `docs/STRUCTURE.md` and `.fa.md`, schema tests (structure schema 3, report schema 1.9) | Met (levels 0, 1) |
| 2 | Import relationships correctly classified | A1 fixtures; on both repositories every Python file is in the output, the 2 cycles and the 1 dynamic import of click were inspected (below). **No 50-row sample of imports was reviewed in A3.** | Partly met: fixtures and inspection, no reviewed import sample |
| 3 | Symbol relationships preserve uncertainty | confidence rule tests; reviewed samples (below) | Met (levels 1, 4) |
| 4 | Internal and external dependencies distinguished | fixtures; the real runs split externals into declared and unmatched (sarand 10 and 53, click 0 and 42, the 42 of click inspected by package name) | Partly met: no reviewed sample |
| 5 | Parser provenance preserved | provenance tests; `files_by_completeness` on both repositories: every file `full`, none failed | Met (level 1) |
| 6 | Stable identity design established | `docs/R14A_ADR_STRUCTURAL_IDENTITY.md`; 31 identity and match-class tests | Met (level 1) |
| 7 | Dynamic limitations explicit | limitation fixtures; `docs/STRUCTURE.md`; two more limits found by this evaluation are written there | Met (level 1) |
| 8 | Output deterministic | shuffled-order and repeat-run tests; 5 runs per repository byte-identical on both | Met (levels 1, 4) |
| 9 | Tests cover supported and unsupported constructs | the A1 and A2 suites plus `tests/test_structure_identity.py` and `tests/test_structure_eval.py` | Met (levels 1, 2) |
| 10 | At least one real repository passes | thresholds below | **Met on both repositories** (level 4) |
| 11 | No critical regression | in the sandbox the whole existing suite is unchanged and the five JSON goldens differ only in `schema_version`; the owner's chain and CI have **not** run on this change | **Open** until the owner's chain and CI pass (levels 3, 5) |

## Criterion 10: thresholds and result

The thresholds were fixed in the plan before the measurement.

| Threshold | sarand | click |
|---|---|---|
| no crash | met | met |
| no file silently missing | every Python file is in the output, all `full`: 295 of 295 on the reviewed tree, 296 of 296 on the final tree | 91 of 91, 0 failed, 0 skipped |
| byte-identical repeat runs | 5 of 5 | 5 of 5 |
| zero wrong results in the reviewed `Definite` sample | 0 wrong of 50 | 0 wrong of 50 |

Reported without a threshold: the `Probable` error rate (0 of 50 on both) and the
false-negative estimate (below).

## Repositories

- **sarand** itself (the owner's project, Rust and Python, almost only absolute
  imports): on the reviewed tree 295 Python files, 4,964 symbols, 9,298 relations
  (8,949 definite, 323 probable, 26 unknown), 0 import cycles. The sample was drawn on
  the sandbox tree during review, which already contained the A3 code except the later
  rewrite of `fingerprint.py` and the test file of the evaluation script (the final
  tree has 296 files and 4,971 symbols). The reviewed rows are kept as they were drawn.
- **click** (uploaded by the owner; pure Python, relative imports, heavy use of
  decorators and classes, a large test suite): 91 Python files, 2,546 symbols, 4,347
  relations (3,177 definite, 1,076 probable, 94 unknown), 2 import cycles, 1 dynamic
  import.

## Method

1. A seeded random draw (seed 14) of 50 stored relations per confidence class, taken
   from a list sorted by location, and of 50 usage sites that were counted but not
   stored (the false-negative sample). sarand has only 26 `Unknown` relations, so that
   sample is the whole class.
2. Each row was judged by reading the source: the binding of the written name in its
   scope (imports, definitions, rebindings, `global`), then the target.
3. Verdict rules. **Definite or Probable relation**: `correct` when the named target is
   what the written name refers to (for `Probable`, under the assumption the method
   name states: `self-member`, `decorated`, `patched`, `alias`, `inherited-member`,
   `super-call`); `wrong` when it is not; `undecidable` when only runtime decides.
   **Unknown relation**: `correct` when the label follows the documented rule for
   `unknown` (`docs/STRUCTURE.md`), `wrong` when a unique target was determinable.
   **Uncounted site**: `missed` when the site really points at a repository symbol,
   `outside` when it points at the standard library, a third-party package, a builtin or
   a value that is not a repository symbol, `undecidable` otherwise.
4. Counts and timings come from `scripts/structure_eval.py`; the reviewed rows are in
   `docs/eval/r14a-<repository>-<sample>.tsv` with the verdict and a note per row.

Reproducing: the TSV files are the reviewed rows. Running the script again on a changed
tree draws a new sample, because the sample is a function of the tree and the seed.

## Reviewed samples

| Sample | sarand | click |
|---|---|---|
| `Definite` (50) | 50 correct, 0 wrong | 50 correct, 0 wrong |
| `Probable` (50) | 50 correct, 0 wrong (47 `self-member`, 3 `patched`) | 50 correct, 0 wrong (27 `self-member`, 15 `decorated`, 6 `inherited-member`, 1 `super-call`, 1 `alias`) |
| `Unknown` | 26 of 26 follow the rule (19 ambiguous binding, 7 dynamic attribute) | 50 of 50 follow the rule, 17 of them over-conservative (finding F2) |
| Uncounted sites (50) | 8 missed, 41 outside, 1 undecidable | 19 missed, 25 outside, 6 undecidable |

With 0 wrong in 50, the 95 percent upper bound of the true error rate is about 6 percent
(rule of three). It is not evidence that the rate is zero. The `Definite` sample covers
imported names, module-level and nested definitions, annotations, decorators,
`click.x` attribute chains through a re-exporting package, enum members and type
variables.

Inspected on click: the eager cycle `click._compat` and `click._winconsole` is real (a
platform-conditional import at module level that is eager on Windows); the 11-module
group around `click.core` is correctly not eager, because its back edges are
type-only or lazy; the one dynamic import is `__import__(f"complex.commands.cmd_{name}")`
in an example; the 42 unmatched externals are `pytest` (33), `typing_extensions`,
`PIL`, `pallets_sphinx_themes` and `_typeshed`.

## Findings

**F1: no local type inference (the main false-negative source).** A method called on a
local variable or parameter whose class is known from a constructor call or an
annotation is counted but not stored: `runner = CliRunner()` then `runner.invoke(...)`,
`report: Report` then `report.write(...)`, `analyzer = JsonAnalyzer()` then
`analyzer.matches(...)`. Estimated share of uncounted sites that really point at a
repository symbol: **8 of 50 (16 percent) on sarand, 19 of 50 (38 percent) on click**,
the larger share because click's tests call `CliRunner.invoke` constantly. This lowers
recall of the relation graph, not its precision: nothing wrong is claimed. A small
inference for `x = Class(...)` and for annotated parameters is the natural next
improvement. It is **not** done in A3; it changes resolver behaviour and needs the
owner's decision.

**F2: the class `__getattr__` rule is over-conservative.** In click, 17 of the 50 sampled
`Unknown` relations are attributes such as `self._stream` that the class itself assigns
in `__init__`, in classes that define `__getattr__`. The documented rule makes every
attribute that is not a class member `unknown` there. The label is honest (no wrong
target) but noisy: the precise answer is an instance attribute that is not a symbol.
Not changed in A3.

**F3: fingerprints are tied to the interpreter's minor version.** A baseline built with
Python 3.14 and compared with one built with 3.12 matches by id only (no `probable`
moves). R14-D should build and compare on the same interpreter or report the limit.

**F4: the fingerprint is not free.** In the sandbox it takes about 0.18 s of 1.25 s of
the structure build on click (about 15 percent); measured by timing the function inside
a build.

## Performance

Sandbox (Python 3.12.3, 5 runs, median and range of the structure build only):

| Repository | Wall time | Peak allocation (`tracemalloc`) | Process peak RSS | Structure JSON |
|---|---|---|---|---|
| sarand | 2.99 s (2.79 to 3.21) | 42.2 MB | 150 MB | 7.6 MB |
| click | 1.37 s (1.34 to 1.56) | 23.3 MB | 94 MB | 3.5 MB |

The owner's phone (Redmi Note 8 Pro, Kali NetHunter, Python 3.14), measured by the
owner on the A2 commit, before fingerprints: `sarand --structure` on sarand twice, 16.12 s
and 14.85 s wall time for the whole command (not only the structure), peak RSS 126.9 and
130.9 MB, report JSON 14 MB, structure output byte-identical between the two runs, 4,782
symbols, 8,928 relations (8,585 definite, 318 probable, 25 unknown), 14 entry points.
A3 was not measured on the phone.

## What this does not show

- No claim of accuracy: three samples of 50 rows on two repositories.
- The import classification was not sampled in A3 (criteria 2 and 4).
- Cross-version behaviour of fingerprints was tested by unit tests, not on a second
  interpreter.
- Other languages, relation matching and the use of identity in a baseline are not built.
