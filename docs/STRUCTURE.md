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

`conditional`, `type_only`, `lazy`, `relative`, `star`.

- **`conditional`**: the import may not run when its scope runs. It is set for the
  branches of `if`/`elif`/`else`; a `try` body that an `ImportError` handler guards; every
  `except` handler; the `else` of a `try`; the body and `else` of `for` and `while`;
  `match` cases; the right side of `and`/`or`; the branches of a conditional expression;
  comprehension bodies. It is **not** set for `finally` or `with` (a context manager can
  swallow an exception, but that is not decided by sarand). A `try` without an
  `ImportError` handler does not make its body conditional.
- **`type_only`**: under `if TYPE_CHECKING:` (and the `else` of `if not TYPE_CHECKING:`);
  always also `conditional`.
- **`lazy`**: inside a function or lambda body, that is the import runs when the function
  is called. Decorators, default values and annotations run when the function is defined,
  so they are not lazy.
- **`relative`**: a `from . import x` form. **`star`**: `from m import *`.

A handler **guards** an import when it names `ImportError`, `ModuleNotFoundError`,
`Exception` or `BaseException` (or has no type at all), as a name bound to the builtin, as
`builtins.<name>`, as an alias assigned from the builtin (`IE = ImportError`), or inside a
tuple of these. `foo.ImportError` and a rebound `ImportError` do not count.

## Recognised forms and their limits

Names are resolved **by scope**, not by spelling. The table of bindings only knows
`TYPE_CHECKING`, the modules `typing`/`typing_extensions`, `importlib` and `builtins`
(under any alias), `importlib.import_module`, `importlib.__import__`, `__import__`, and the
`ImportError` family. A name rebound to anything else, or bound in two different ways in one
scope, is ambiguous and is not recognised. Supported:

- the `TYPE_CHECKING` sentinel as `from typing import TYPE_CHECKING [as T]`, `typing.TYPE_CHECKING`
  (also through `import typing as t`), and the idiom `TYPE_CHECKING = False`. A name of
  that spelling that comes from anywhere else (`from .compat import TYPE_CHECKING`,
  `custom.TYPE_CHECKING`, a parameter, a variable) is only `conditional`.
- `importlib.import_module(name, package=None)` and the builtin
  `__import__(name, globals, locals, fromlist, level)`, called by their names or through
  aliases (`import importlib as il`, `from importlib import import_module as im`,
  `from builtins import __import__ as ci`). A literal name resolves like an import but is
  at most `probable`. A relative `import_module` name is resolved against its `package=`
  argument (as `importlib.util.resolve_name` does); a `__import__` level is resolved against
  the importing module only when `globals` is the plain `globals()` call. `fromlist` is
  not followed.
- A computed name, a `*args` or `**kwargs` call, or a computed `package=` is `dynamic`
  (unknown).
- `exec` and `eval` (only when they are the builtins) mark the file with
  `dynamic_construct_seen`; their location is **not** recorded (no edge exists for them).

Not supported (the construct is simply not seen): assignment expressions (`:=`) and the
names a `from m import *` brings in as bindings; aliases of aliases; `getattr(importlib,
"import_module")`; `__import__` reached through `globals()["__import__"]`; `eval`ed code.
The scope-aware table follows Python's lookup order (a class scope is skipped inside a nested
function), and a name declared `global` anywhere is ambiguous at module level.

## Source roots and module names

A module name starts at a source root. The root of a file is, in order:

1. a root declared in `pyproject.toml` that contains the file: maturin `python-source`;
   setuptools `package-dir` (the empty key `{"" = "src"}` means no prefix; a named key
   `{"mypkg" = "lib/other"}` says the directory `lib/other` **is** the package `mypkg`, so
   `lib/other/a.py` is `mypkg.a`); setuptools `packages.find.where`. The longest declared
   directory wins;
2. otherwise the nearest ancestor directory without an `__init__.py`.

A declared root must be a repository-relative path: an absolute path, a backslash, a
Windows drive, or a `..` that leaves the repository is **rejected** and listed in
`meta.rejected_roots` (never silently used or dropped); `./src/` and `a/../b` are
normalised.

A module name is derived only for a path inside its root. A root-level `__init__.py` has no
importable name (it is listed with an empty module and its imports are reported by file
path). A directory with no `__init__.py` is an implicit **namespace package**; a namespace
package can have portions in several roots (PEP 420) and one `ModuleEntity` is kept per
(name, root); a name that is a regular package in any root is not also a namespace package.
A name found in two roots resolves only when the importer's own root has exactly one of them
(`probable`); otherwise it is `internal_unresolved`.

Parent-package initialisation (`import a.b.c` runs `a/__init__.py` first) is **not**
modelled as an edge: it would turn every package and its submodules into a cycle.
`from pkg import name` depends on `pkg` only when `name` is not a repository submodule.

**Paths given to the builder** (`included`, `skipped`) are relative, inside the project,
without `..`; an absolute path or a parent traversal raises `ValueError`.

## Cycles

Strongly connected components of the repository import graph, found without
recursion, plus a module that imports itself. Only edges that resolved to a repository
module with confidence `definite` or `probable` count.

`Cycle.edges` is **every** such edge whose two ends are both in the cycle, lazy and
type-only ones included, each with its own flags. It is not a minimal set of edges that
closes one loop. A cycle is **eager** when it survives after removing `type_only` and
`lazy` edges, that is when it can fail at import time; `conditional` edges still count as
eager (they run on some path). Otherwise it is listed as "lazy or type-only".

## Model contract

- **Two schema versions.** The outer **report** schema (`schema_version`, `"1.7"`) is
  versioned with the JSON report (`docs/JSON_SCHEMA.md`). The **structure model** schema is
  `structure.schema`, an integer, `1` today. They change independently.
- **Coordinates.** `line` is 1-based (0 = unknown). `col` and `end_col` are 0-based
  **UTF-8 byte offsets** in the line, exactly as `ast` reports them (`end_col` 0 =
  unknown). A `SyntaxError` reports characters; sarand converts them to bytes so the whole
  model uses one unit. A form feed does not shift line numbers (lines end at `\n`, `\r\n`
  or `\r`, as in Python's tokenizer).
- **Validation.** Every entity validates its fields when it is built: a value outside
  the closed vocabularies, a malformed path (absolute, backslash, `..`) or a negative
  coordinate raises `ModelError` naming the field and the allowed values. Invalid data
  therefore cannot reach a summary or a renderer.
- **Immutability.** Deep: nested mappings are read-only and sequences are tuples; building an
  entity copies what it is given.
- **Unknown stays unknown.** A file that could not be read has `size: null`, an empty
  `sha256` and the limitation `unreadable`; it is never shown as an empty file.
- **Evidence** is the statement's own text, from its start column to its end column (a
  trailing comment is not part of it), its lines joined by single spaces and cut at 240
  characters (a cut ends with `...`). `note` is sarand's own text explaining an unresolved or
  dynamic edge; it is never source text.
- **Canonical output.** The serializer sorts every collection by an explicit key (files by
  path; modules by name, root, path; externals by name; edges by source, location,
  requested name and the rest; cycles by their modules; the edges of a cycle like edges),
  key-sorts mappings recursively, and sorts the sequences in `meta`. Sequences inside file
  `extensions` keep their order. Two equal models therefore serialize to the same bytes
  whatever order their producers used, and serializing never changes the model.

## Provenance and limits

Every file has a provenance: parser (`python-ast`), the interpreter version, the
completeness (`full`, `partial`, `failed`, `skipped_size`) and limitation codes:
`syntax_error`, `encoding_error`, `recursion_limit`, `resource_limit`, `node_cap`,
`too_large`, `unreadable`, `dynamic_construct_seen`; `unsupported_syntax_for_interpreter`
is defined but **not produced**: a syntax error cannot be reliably attributed to newer
grammar, so it is reported only as `syntax_error`. A file that cannot be read stays in the
output with its reason and the error location, so a broken file is never a silent zero.

Guards: a recursion failure while walking loses only the statement it happened in (the
file is `partial` and every other import is kept); the node cap (1,000,000) and a
memory failure stop the walk (`partial`, with what was found before); a recursion or
memory failure while parsing makes the file `failed`. Only these failures are handled;
anything else is a bug and is not swallowed.

**Not detected does not mean nonexistent.** Dynamic imports, `getattr`/`setattr`,
monkey-patching, plugin loading by entry-point group and generated code can create
relationships that static reading cannot see. A listed `dynamic_construct_seen`
means the file contains such a construct.

Two environment inputs are named in `meta`, never hidden: the interpreter version
(the `ast` grammar and the standard-library name list depend on it, so a file with
newer syntax is `failed` on an older interpreter) and the standard-library source.

## Where it appears

- **JSON** (`structure`, outer schema 1.7): everything, including each edge with its
  evidence, note and location. See `docs/JSON_SCHEMA.md`.
- **Markdown and HTML**: counts; import cycles (first 10); **unresolved and dynamic imports**
  (first 20): the imports whose target class is `internal_unresolved` or `dynamic`, with the
  reason; and the **external packages imported** (first 30, the `external_declared` and
  `external_unmatched` ones, with how many modules import each). The totals are always shown,
  and a cut list says how many are not shown. An empty section is not drawn. Every cell is
  escaped (HTML entities in HTML; pipes and line breaks in Markdown tables).
- **Text**: one line.
- **SARIF**: not included.

All counts come from one place (`structure/serialize.py` and
`core/report_views.py`), so the formats agree.

## Not implemented yet

Symbols, calls, inheritance, references and entry points (R14-A2); stable structural
identity and fingerprints, the real-repository evaluation and the stage gate
(R14-A3). Other languages are not started. Python import constructs that remain unsupported
are listed under "Recognised forms and their limits".
