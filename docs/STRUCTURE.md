# Repository structure (`--structure`)

Status: **R14-A1 is implemented**: modules, imports, import classification, cycles.
Symbols and calls, entry points and stable structural identity are **not
implemented yet** (R14-A2 and R14-A3, see `docs/R14A_PLAN.md`).

`sarand --structure` reads the project's Python source with the standard `ast`
module and adds a structure to the report. It never executes repository code and
reads only files the report may read (nothing flagged as a secret, nothing above the
size limit; such a file is listed as `skipped_size`, never dropped). It is off by
default, and a default report is unchanged.

## Four things that stay apart

| Thing | Where it comes from | What sarand does with it |
|---|---|---|
| A dependency **declared** | `pyproject.toml`, `requirements.txt` | recorded as evidence on an external package; never an import by itself |
| A package **installed** | the environment | never read |
| An import **found in source** | `import` statements and `importlib`/`__import__` calls | an edge |
| A **resolved** repository relationship | an edge whose target is a repository module | the import graph and the cycles |

## What an import resolves to (`target_class`)

| Class | Meaning |
|---|---|
| `internal` | a module of this repository (or an implicit namespace package) |
| `stdlib` | a standard-library name; the list is `sys.stdlib_module_names` of the interpreter that ran sarand and is recorded in `meta` |
| `external_declared` | not a repository module and its normalised name equals a declared dependency |
| `external_unmatched` | not a repository module, not standard library, no matching declaration. An import name can differ from its distribution name (`yaml` and `pyyaml`) and sarand reads no installed metadata, so it does not guess; this is the "unresolved external" list |
| `internal_unresolved` | the name starts in a repository package but no target was found: a missing submodule, an ambiguous name (several modules match), a relative import beyond the top package |
| `dynamic` | the module name is computed at run time (`importlib.import_module(name)`) |

## Confidence

Assigned by these rules only. Whether an import is conditional is a **flag**, not a
confidence level.

| Level | Rule | Examples |
|---|---|---|
| `definite` | The name binds to exactly one repository module (or standard-library or declared name) by Python's own rules | `import a.b` where `a/b.py` exists; a relative import that lands on a file; a standard-library name; a name equal to a declaration |
| `probable` | One candidate, but an assumption was needed | the same module name exists in two source roots and the importer's own root is preferred; a repository module shadows a standard-library name; `importlib.import_module("literal")`; an external package matched only by elimination |
| `unknown` | The evidence cannot name a target | a computed module name; an ambiguous name; a missing submodule; a relative import with no parent package |

An `unknown` edge is never a dependency: it never makes a cycle.

## Flags on an import

`conditional` (inside an `if`, or a `try` that catches `ImportError`), `type_only`
(under `if TYPE_CHECKING:`), `lazy` (inside a function body), `relative`, `star`.
Decorators and default values run when a function is defined, so they are not lazy.

## Source roots and module names

A module name starts at a source root: a root declared in `pyproject.toml` (maturin
`python-source`, setuptools `package-dir` and `packages.find.where`) that contains the
file, otherwise the nearest ancestor directory without an `__init__.py`. A name found
in two roots is resolved only when the importer's own root has exactly one of them
(probable); otherwise it is `internal_unresolved`. A directory with no
`__init__.py` between a root and a module is an implicit namespace package.

Parent-package initialisation (`import a.b.c` runs `a/__init__.py` first) is **not**
modelled as an edge: it would turn every package and its submodules into a cycle.
`from pkg import name` depends on `pkg` only when `name` is not a repository
submodule.

## Cycles

Strongly connected components of the repository import graph, found without
recursion, plus a module that imports itself. A cycle is **eager** when it survives
after removing `type_only` and `lazy` imports, that is when it can fail at import
time; otherwise it is listed as lazy or type-only.

## Provenance and limits

Every file has a provenance: parser (`python-ast`), the interpreter version, the
completeness (`full`, `partial`, `failed`, `skipped_size`) and limitation codes:
`syntax_error`, `unsupported_syntax_for_interpreter`, `encoding_error`,
`recursion_limit`, `node_cap`, `too_large`, `unreadable`, `dynamic_construct_seen`.
A file that cannot be read stays in the output with its reason and the error
location, so a broken file is never a silent zero.

**Not detected does not mean nonexistent.** Dynamic imports, `getattr`/`setattr`,
monkey-patching, plugin loading by entry-point group and generated code can create
relationships that static reading cannot see. A listed `dynamic_construct_seen`
means the file contains such a construct.

Two environment inputs are named in `meta`, never hidden: the interpreter version
(the `ast` grammar and the standard-library name list depend on it, so a file with
newer syntax is `failed` on an older interpreter) and the standard-library source.

## Where it appears

- **JSON** (`structure`, schema 1.7): everything, including each edge with its
  evidence and location. See `docs/JSON_SCHEMA.md`.
- **Markdown and HTML**: counts, import cycles (first 10), imports that could not be
  resolved (first 20) and the external packages imported (first 30); the totals are
  always shown, and what is cut says how many are not shown.
- **Text**: one line.
- **SARIF**: not included.

All counts come from one place (`structure/serialize.py` and
`core/report_views.py`), so the formats agree.

## Not implemented yet

Symbols, calls, inheritance, references and entry points (R14-A2); stable structural
identity and fingerprints, the real-repository evaluation and the stage gate
(R14-A3). Other languages are not started.
