# R14-A implementation plan: repository intelligence core

Status: **plan, not implemented.** Nothing here is shipped until its stage and
acceptance gate pass (see section 15). The source of authority is the R14 master
plan (R14-A, sections 4.1 to 4.9 and 18). This document extends what sarand has
today; it adds no capability beyond R14-A.

## 0. What exists today and what R14-A reuses

Read from the v0.8.0 source (138 Python modules, about 26,900 lines):

| Existing component | What it does today | Use in R14-A |
|---|---|---|
| `core/frameworks.py`, `declared_dependencies` in `core/components.py` | Reads dependencies **declared** in `pyproject.toml`, `requirements.txt` and `package.json`; says in its own docstring that actual use in code is "never claimed here" | Reused as the only source of declarations. R14-A adds the missing third item: actual imports in source |
| `discovery/project_detector.py` and the entry-point names in `constants.py` | Guesses entry points from file names (`main.py`, `cli.py`, `__main__.py`, `app.py`) | Kept unchanged. Structural entry points are an additional, evidence-carrying list; no report changes by default |
| `core/architecture.py` | Quick Context architecture block from components, entry points and file counts; states "No import graph" | Unchanged in R14-A. Consumed later by R14-B and R14-C |
| `core/relevant_source.py` (L4) | Picks source snippets by fixed weights | Unchanged. R14-C may replace weights with graph evidence |
| `ReportData.included_files`, `skipped_files`, `excluded_secret_files` | The file universe and its exclusions | The structure builder reads only paths that the report may read: nothing flagged as a secret, nothing above the size limit (such a file is listed as `skipped_size`, never dropped silently) |
| `core/finding_identity.py` (R13-F) | Versioned-style ids built from structured fields | Same style for structural identity (section 8); no second scheme |
| `core/coverage.py` | Uses `ast` only to classify analyzers | Unrelated; no reuse |

There is no import graph, no symbol model and no AST-based extraction of the scanned
project in sarand today (verified by search: no `ast` use outside `core/coverage.py`).

## 1. Required structural entities

All entities are frozen dataclasses in a new package `python/sarand/structure/`
(`model.py`). Every one carries `provenance` and, where it has a place in a file, a
`location`.

| Entity | Meaning |
|---|---|
| `SourceLocation` | repo-relative POSIX path, line, column, end line, end column |
| `Provenance` | parser, parser version, language rules, completeness (`full`, `partial`, `failed`, `skipped_size`), limitations (a tuple of codes) |
| `FileEntity` | path, language, size, content SHA-256, module name (empty if none), provenance |
| `ModuleEntity` | dotted name, file, `is_package`, `is_namespace`, source root |
| `Symbol` | id, kind (`class`, `function`, `method`, `variable`, `constant`, `property`), qualified name, module, location, decorators, bases, flags (`nested`, `conditional`, `dynamic`), `fingerprint` |
| `Edge` | kind, source id, target id, confidence, resolution method, evidence, location, original relationship type, flags |
| `EntryPoint` | type, location, detection method, confidence, evidence |
| `ExternalRef` | an external target: top-level name, class (`stdlib`, `external_declared`, `external_unmatched`), declaration evidence |

## 2. Import graph schema

Nodes are `ModuleEntity` (internal) and `ExternalRef`. An import statement produces
one `Edge` per imported target, kind `imports`, with these fields:

- `target_class`: `internal`, `stdlib`, `external_declared`, `external_unmatched`,
  `internal_unresolved`, `dynamic`.
- `flags`: `conditional` (inside `if`, `try`, `with` or a function body), `type_only`
  (under `if TYPE_CHECKING:`), `relative`, `star`, `lazy` (inside a function).
- `evidence`: the statement text span and location.

Rules: an installed or declared third-party package never creates an internal edge;
a declaration in project metadata never creates an edge at all (it is recorded on the
`ExternalRef` as evidence). `external_unmatched` (the name is not internal, not
stdlib and matches no declaration) is the report's "unresolved" list, because an
import name and a distribution name can differ (`yaml` and `pyyaml`) and sarand does
not read installed metadata. Cycles are found with an iterative Tarjan over internal
edges and reported with the cycle's edges and locations; edges flagged `type_only` or
`lazy` are listed in the cycle evidence so a reader can tell harmless cycles.

Source roots (where a dotted name starts): from `pyproject.toml`
(`tool.maturin.python-source`, setuptools `package-dir` and `where`), the `src/`
convention, and the nearest directory above a package that has no `__init__.py`. A
module name that maps to two roots is `Unknown`, not resolved by guess.

## 3. Symbol graph schema

Nodes are `Symbol` and `ExternalRef`. Edge kinds: `defines`, `imports`, `calls`,
`inherits`, `references`, `depends_on` (a derived module-level edge). `implements`
and `overrides` are out of R14-A: Python has no declaration of them and a guess would
be fabricated.

R14-A resolves a **syntactically observed** reference to a candidate only by name
binding inside the repository's own sources (scope, import binding, class bodies). It
does no type inference. A reference whose binding cannot be settled is recorded with
confidence `Unknown` and the reason; it is never dropped and never promoted.

## 4. Common structural model

The language-independent layer is the entity set of section 1 plus an
`extensions: dict[str, str | int | bool]` field on every entity for language-specific
facts (for Python: `decorator_names`, `is_async`, `is_generator`, `has_star_args`,
`dunder_all`). Generic fields never carry a concept a language lacks. A second
language only enters after this model survives R14-A's gate (master plan 4.6).

## 5. Confidence semantics

Three levels, assigned only by the rules below, never by a score or by intuition.
Conditionality is a separate flag; it does not lower confidence.

| Level | Operational definition | Examples |
|---|---|---|
| **Definite** | The name binds to exactly one repository entity by the language's own rules, using only syntax and repository files, and nothing in the repository can rebind it | `import a.b` where `a/b.py` exists; a relative import that lands on a file; `from m import f` where `m` defines `f` once at top level by `def` or `class`; `class C(Base)` where `Base` is bound by such an import or by a top-level class in the same module |
| **Probable** | One candidate, but the binding depends on an assumption | `self.method()` resolved in the class and its repository bases (a subclass may override); a call on a name bound by `from m import *` when `m` has a static `__all__`; a decorated function whose decorator is not in the table of transparent decorators; `mod.func` when some assignment `mod.func = ...` or `setattr(mod, "func", ...)` exists in the repository |
| **Unknown** | The evidence cannot establish a target | `getattr(x, name)` with a non-constant name; `importlib.import_module(expr)`; `from m import *` without static `__all__`; a name resolved only through a module-level `__getattr__`; two candidates; an attribute on a value of unknown type |

Promotion: `Probable` becomes `Definite` only by a documented rule that removes the
assumption (for example the class has no repository subclass that redefines the
method). Demotion to `Unknown` happens whenever a rule above fires on the path.
Downstream stages treat `Unknown` as no dependency: an `Unknown` edge never counts as
a definite dependency, and its absence from a result is never proof (R14-B and
R14-E rely on this).

## 6. Parser provenance model

Each file records `Provenance`: `parser = "python-ast"`, `parser_version` (the
interpreter's version), `rules` (the grammar version the file needs, when
detectable), `completeness`, and limitation codes from a closed list
(`syntax_error`, `recursion_limit`, `too_large`, `unsupported_syntax_for_interpreter`,
`encoding_error`, `dynamic_construct_seen`). A file that does not parse is kept as a
`FileEntity` with `completeness = failed` and the error location; it contributes no
edges and is counted in every summary, so a failed parse is never a silent zero. An
entity inherits its file's completeness. The interpreter version is part of the
output because `ast` and the stdlib module list differ between Python versions; it is
the one named, unavoidable environment input (section 9).

## 7. Internal and external dependency distinction

Four things stay separate in the data and in the report (master plan 4.3):
declarations (`ExternalRef.declared_in`), installed packages (never read), actual
imports (`imports` edges), resolved internal relationships (`target_class =
internal`). Stdlib is decided by `sys.stdlib_module_names` of the running interpreter,
recorded in the output metadata; tests inject a fixed set so results do not depend on
the CI interpreter.

## 8. Stable identity and fingerprint design

Reuse the R13-F pattern: ids are `<kind>:<12 hex>` over structured fields, never over
text.

- **Exact id** of a symbol: language, kind, repo-relative path, qualified name inside
  the file, and a disambiguator `#n` for duplicate qualified names (conditional
  redefinition). Line numbers, formatting and unrelated edits do not change it.
- **Fingerprint** (`fp1:` plus 12 hex, versioned): SHA-256 of
  `ast.dump(node, include_attributes=False)` with docstrings removed. It is stable
  under formatting and line shifts and changes when the definition's content changes.
- **Matching between two states** returns one of `exact` (same exact id),
  `probable` (same language, kind, qualified name and fingerprint at a different
  path: a move), `ambiguous` (two or more candidates) or `unmatched`. `ambiguous`
  and `probable` never become `exact` silently. A rename of a symbol is `unmatched`
  plus an `unmatched` counterpart; R14-A does not try to guess renames.
- The fingerprint version is stored in the output; a change of the algorithm bumps it.

## 9. Python AST extraction strategy

One pass per file with `ast.parse` (never executes repository code; bandit and the
master plan's data-handling rule). The visitor keeps a scope stack to bind names
(module, class, function, comprehension; `global` and `nonlocal` handled). It records
definitions, imports with flags, calls, base classes, decorators, `__all__` when a
static list or tuple, `if __name__ == "__main__":` blocks, and module-level
`__getattr__`. Resource limits: the existing `--max-file-size`, a recursion guard that
turns `RecursionError` into `partial`, and a cap on nodes per file.
Determinism: files in sorted POSIX-path order; all collections sorted before output;
no set iteration in output paths; no timestamps inside the structure.

Entry points (master plan 4.7), each with type, location, method, confidence and
evidence: `__main__` blocks (Definite); `[project.scripts]` and
`[project.entry-points]` in `pyproject.toml` resolved to a function when the target
module is internal (Definite if it resolves, else Unknown); `if __name__` guards in
`__main__.py`; `[tool.pytest.ini_options]` test roots as `test` entry points;
`argparse`/`click`/`typer` application objects only as Probable, and only when a
declared framework matches. Plain executable functions are not entry points.

## 10. Dynamic Python limitations (documented, not hidden)

Recorded as limitation codes on the file and as `Unknown` edges: `getattr`/`setattr`
with non-constant names, `__getattr__` and `__getattribute__`, monkey-patching,
runtime-generated attributes and classes, `importlib` and `__import__` with
expressions, `exec` and `eval`, metaclasses, decorator-generated behaviour,
conditional definitions, dependency injection by registry or entry-point group (sarand
itself loads analyzer plugins this way). The report states: **not detected does not
mean nonexistent.**

## 11. Test strategy

Synthetic trees written into `tmp_path`, one focused test group per fixture class in
master plan 4.9: import resolution; relative imports; cycles; external and stdlib
classification; dynamic imports; symbol definitions; cross-module references;
inheritance; decorators; monkey-patching; dynamic attributes; ambiguous resolution;
entry points; parser limitations (syntax error, huge file, deep nesting); identity under
line shifts and reformatting; serialization determinism (shuffled file order and
repeated runs give byte-identical JSON). Interpreter-specific syntax (`match`,
PEP 695, PEP 701) is guarded by `sys.version_info` because CI runs 3.11, 3.12, 3.14
and 3.15. Paths are POSIX-normalised for the Windows job. The default report and every
golden stay byte-identical (the feature is opt-in).

## 12. Real-repository validation strategy

The R14-A gate needs at least one real, medium repository chosen for structural
diversity.

1. **sarand itself** (138 modules, about 26,900 lines): `__main__`, argparse CLI,
   asyncio, entry-point plugin loading, a registry, `TYPE_CHECKING` imports (2
   modules), dynamic attribute use (`getattr`/`setattr`, 5 modules), mixed Python and
   Rust. It uses almost only absolute imports (3 relative-import lines), so it
   cannot test relative resolution on its own. It is the owner's project, so every
   sampled result can be traced to a known author's intent.
2. **A second, structurally different pure-Python project** that uses relative
   imports heavily and is decorator-heavy or dynamic. Candidates readable offline in
   the sandbox: `click` and the Python layer of `cryptography`; the owner may add one
   repository.

Method (all recorded in the evaluation report): enumerate modules and compare with the
filesystem; list unresolved and cyclic imports and inspect each; take a **seeded
random sample** of 50 `Definite` edges, 50 `Probable` and 50 call sites that came out
`Unknown`, trace each by reading the source, and record correct, wrong or
undecidable; estimate false negatives from the 50 sampled call sites by tracing the
true target. Rates from samples this small are labelled estimates, not accuracy. The
reviewer is the engineer who built the tool, which is a limitation the report states;
the owner can spot-check any sampled row because each carries its source location.
Repeat run: two runs, same state, byte-identical output.

## 13. Performance measurement strategy

Measured, not assumed: wall time and peak memory (`tracemalloc` and `resource`) for
cold parse of every file, graph construction, resolution, serialisation, on the two
repositories, five runs each, reporting median and range, on the sandbox machine and
on the owner's phone (the real constraint: Termux, 6 GB). No budget is invented in
advance; the first measurement sets the baseline. Rust is considered only if a
profile shows Python is the bottleneck on the larger repository.

## 14. Compatibility and regression risks

| Risk | Mitigation |
|---|---|
| Default output changes | The feature is opt-in (`--structure`); a test asserts every existing golden is byte-identical with it off |
| JSON schema drift | Additive key `structure`, schema 1.7, documented in both languages, version history entry |
| Interpreter differences (`ast`, stdlib names) | Interpreter version recorded; tests inject a fixed stdlib set; version-guarded syntax tests |
| Windows and macOS paths | POSIX-normalised repo-relative paths; case-collision test |
| Memory and time on large repositories | Size and node caps, `partial` instead of failure, measured in section 13 |
| Reading a secret file | The universe excludes files flagged as secrets; the structure stores no source text, only locations and names |
| Two sources of "entry point" | Old list unchanged; the new one is additive and labelled |

## 15. Acceptance gates

R14-A passes only when every row has evidence at the stated level (verification levels
of the master plan, section 12).

| # | Criterion (master plan 4.9) | Evidence | Levels |
|---|---|---|---|
| 1 | Structural model stable and documented | `docs/STRUCTURE.md` (en, fa), schema tests | 0, 1 |
| 2 | Import relationships correctly classified | import fixtures; reviewed sample | 1, 4 |
| 3 | Symbol relationships preserve uncertainty | confidence rule tests; reviewed sample | 1, 4 |
| 4 | Internal and external dependencies distinguished | fixtures; declared-versus-imported report | 1, 4 |
| 5 | Parser provenance preserved | provenance tests; failed-parse fixture | 1 |
| 6 | Stable identity design established | identity fixtures; match-class tests | 1 |
| 7 | Dynamic limitations explicit | limitation fixtures; docs | 1 |
| 8 | Output deterministic | shuffled-order and repeat-run tests; two-run comparison on both repositories | 1, 4 |
| 9 | Tests cover supported and unsupported constructs | the fixture list of section 11 | 1, 2 |
| 10 | At least one real repository passes | the evaluation report of section 12 | 4 |
| 11 | No critical regression | the full existing suite and goldens unchanged; owner's chain and CI | 3, 5 |

Pass thresholds for criterion 10, fixed now so they cannot move later: no crash on
either repository; no file silently missing from the summary; byte-identical repeat
runs; **zero wrong results in the reviewed `Definite` sample** (a `Definite` label
is a claim); the observed error rate of the `Probable` sample and the false-negative
estimate are reported, without a pass threshold, as estimates.

## 16. Delivery plan inside R14-A

1. **A1**: model, file discovery, import extraction and classification, cycles,
   `--structure` in JSON and a short Markdown section, tests, docs draft.
2. **A2**: symbols and edges with confidence, entry points, decorators and dynamic
   limitations.
3. **A3**: identity and fingerprints, determinism tests, real-repository evaluation
   report, `docs/STRUCTURE.md` (en, fa), gate report, ADR.

Each delivery is a zip with an apply script, run through the owner's full chain. No
R14-B work starts before the gate and the owner's approval.

## 17. Decisions needed from the owner

1. Is `--structure` (opt-in; JSON key `structure` plus a Markdown section) the right
   surface for R14-A, with no default report change?
2. May R14-D be split into D1 (baseline, diff, waivers, gate, SARIF fingerprints on
   the existing R13 finding ids; no dependency on the graph) and D2 (incremental
   analysis and cache; depends on R14-A), with D1 allowed to run before R14-B?
3. Which second repository besides sarand for the gate? (The sandbox can read
   `click` offline; the owner may upload another.)
