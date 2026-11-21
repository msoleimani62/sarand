# Repository structure (`--structure`)

Status: **R14-A1, R14-A2 and R14-A3 are implemented**: modules, imports, import
classification, cycles, symbols, relations between symbols, entry points, versioned
content fingerprints and the match classes between two states, evaluated on two real
repositories (`docs/R14A_GATE_REPORT.md`). Using identity to compare two runs (a
baseline) is R14-D and is **not implemented yet**; other languages are not started.

`sarand --structure` reads the project's Python source with the standard `ast`
module and adds a structure to the report. It never executes repository code and
reads only files the report may read (nothing flagged as a secret, nothing above the
size limit; such a file is listed as `skipped_size`, never dropped). It is off by
default, and a default report is unchanged.

## Four things that stay apart

| Thing | Where it comes from | What sarand does with it |
|---|---|---|
| A dependency **declared** | `pyproject.toml` (every section listed under "Declared dependencies"), `requirements.txt` | recorded as evidence, with the section, on an external package; never an import by itself |
| A package **installed** | the environment | never read |
| An import **found in source** | `import` statements and `importlib`/`__import__` calls | an edge |
| A **resolved** repository relationship | an edge whose target is a repository module | the import graph and the cycles |

## What an import resolves to (`target_class`)

| Class | Meaning |
|---|---|
| `internal` | a module of this repository (or an implicit namespace package) |
| `stdlib` | a standard-library name; the list is `sys.stdlib_module_names` of the interpreter that ran sarand and is recorded in `meta` |
| `external_declared` | not a repository module and not standard library, and a manifest declares a distribution that provides the import: one with the same normalised name (`definite`) or one that the table of `sarand/structure/distributions.py` says ships the import name (`probable`). `declared_in` lists every declaration with its section |
| `external_unmatched` | not a repository module, not standard library, and no declaration that sarand reads provides it. This is the "unresolved external" list: it means *no readable declaration matched*, which is not the same as *undeclared* (see "Declared dependencies" for what is not read) |
| `internal_unresolved` | the name starts in a repository package but no target was found: a missing submodule, an ambiguous name (several modules match), a relative import beyond the top package |
| `dynamic` | the module name is computed at run time (`importlib.import_module(name)`) |

## Declared dependencies

An external import is matched against what the project's manifests **declare**. Five
terms are kept apart:

| Term | Meaning |
|---|---|
| **import name** | the top-level name written in the source: `yaml`, `PIL`, `pytest` |
| **distribution name** | the name a manifest uses for a package: `PyYAML`, `Pillow`, `pytest`; compared after PEP 503 normalisation (case folded, runs of `-`, `_` and `.` become one `-`) |
| **dependency declaration** | one distribution name listed in one section of one manifest |
| **section** | where the manifest lists it; the dependency group (`tests`, `docs`, ...) or extra is part of the name |
| `external_declared` / `external_unmatched` | at least one readable declaration provides the import / none does |

**What is read** (Python, in every directory that has the manifest). The `declared_in` label
is `<directory>/pyproject.toml#<section>` or `<directory>/requirements.txt`:

| Section label | Source |
|---|---|
| `project.dependencies` | PEP 621 runtime dependencies |
| `project.optional-dependencies.<extra>` | PEP 621 extras |
| `dependency-groups.<group>` | PEP 735 groups (`{include-group = ...}` entries are not packages and are skipped) |
| `build-system.requires` | build requirements |
| `tool.poetry.dependencies`, `tool.poetry.dev-dependencies`, `tool.poetry.group.<group>.dependencies` | Poetry (`python` is the interpreter constraint, not a package) |
| `requirements.txt` | one requirement per line; options and comments are skipped |

**Matching.** The distribution with the same normalised name as the import is tried
first (`definite`). The import name can differ from the distribution name, so a short
**explicit table** (`sarand/structure/distributions.py`) lists, for a few well-established
import names, every distribution known to ship them (`yaml` is shipped by `pyyaml`,
`PIL` by `pillow` and `pillow-simd`, `cv2` by four `opencv-*` distributions). If any of
those is declared, the import is `external_declared` with confidence `probable` (the
pair comes from the table, not from the text of the project), resolution method
`declared-distribution`, and `declared_in` lists every declaration found. A name that
is not in the table is not guessed from similarity and stays `external_unmatched`; the
table is not complete.

**What is not read:** installed packages (never; no `top_level.txt`), `setup.py`,
`setup.cfg`, `Pipfile`, `requirements-*.txt` variants, `uv`, `pdm` and `hatch` tables,
Cargo and npm manifests for Python imports. A package declared only there is
`external_unmatched`.

**Scope.** A declaration anywhere in the scanned project counts for the whole project;
it is not limited to the directory of its manifest. The evaluation script reports how
many declared edges have no declaring manifest above the importing file
(`scripts/structure_eval_imports.py --audit-external`).

## Confidence

Assigned by these rules only. Whether an import is conditional is a **flag**, not a
confidence level.

| Level | Rule | Examples |
|---|---|---|
| `definite` | The name binds to exactly one repository module (or standard-library or declared name) by Python's own rules | `import a.b` where `a/b.py` exists; a relative import that lands on a file; a standard-library name; a name equal to a declaration |
| `probable` | One candidate, but an assumption was needed | the same module name exists in two source roots and the importer's own root is preferred; a repository module shadows a standard-library name; `importlib.import_module("literal")`; an external package matched only by elimination; an external package declared only through a distribution that ships the import name (`import yaml` with `PyYAML` declared) |
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

- **Two schema versions.** The outer **report** schema (`schema_version`, `"1.10"`) is
  versioned with the JSON report (`docs/JSON_SCHEMA.md`). The **structure model** schema is
  `structure.schema`, an integer, `4` today (`1` was imports only, `2` added symbols,
  relations and entry points, `3` added the symbol `fingerprint` and
  `meta.fingerprint_basis`, `4` makes `declared_in` name the manifest section and adds the
  `declared-distribution` resolution method). They change independently.
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

## Symbols, relations and entry points (R14-A2)

`--structure` also lists the **symbols** the source defines and the **relations** between
them. Everything is read from `ast`; nothing is executed and **no types are inferred**: a
usage is resolved only by name binding inside the repository (lexical scopes, import
bindings, class bodies, base classes).

### Symbols

Kinds: `class`, `function`, `method`, `property`, `variable`, `constant` (an assignment
at module or class level whose name is `UPPER_CASE`). Instance attributes
(`self.x = ...`) and local variables are not symbols. Each symbol has an `id`
(`sym:` plus 12 hex digits over language, kind, path, qualified name and a `#n` for a
duplicate), its `qualname` (`Outer.method`, `outer.<locals>.inner`), `module`, `path`,
`parent` (the enclosing class or function, empty at module level: this is the plan's
`defines` relationship, stored once), `location`, the written `decorators` and `bases`
in source order, `flags` (`nested`, `conditional`, `dynamic`) and `extensions`
(`is_async`, `is_generator`, `has_star_args`, `has_metaclass`, `alias_of`,
`declared_only`, `overload`) and a `fingerprint` (see "Identity and fingerprints"). A property is recognised by the written decorator
(`property`, `cached_property`, `x.setter`/`getter`/`deleter`); the accessor defs of one
property are one binding. `@overload` stubs are symbols but do not bind the name. The id
contains no line number, so it survives formatting and unrelated edits.

### Relations

Kinds: `calls`, `inherits`, `references` (a name or attribute used but not called, a
decorator, an annotation). `original_type` says which: `call`, `name`, `attribute`,
`decorator`, `base`, `dynamic_attribute`. Each relation has a source (a symbol, or the
module for module-level code), a target (a symbol, a module, `unresolved` or `dynamic`),
`confidence`, `resolution_method`, `evidence`, `location`, `flags` (`conditional`,
`type_only`, `lazy`, `annotation`) and `note`. Equal relations are **merged**: `count` says
how many sites, `location` and `evidence` are the first one. `depends_on` is not stored: it
is derived from relations and imports in R14-B.

### Confidence rules

The lowest level on the way wins. Conditionality is a flag, never a level.

| Level | Rule |
|---|---|
| `definite` | a name defined once in its module by `def`/`class`; `from m import f` where `m` defines `f` once (also through a chain of re-exports, at most 8 deep); `mod.f` through `import mod`; `Cls.member` where that class defines the member once; a base class bound by one of these |
| `probable` | `self.m()` and `cls.m()` (a subclass may override); a member found in a base class (the walk is depth-first, not the exact MRO); `super().m()`; a name from `from m import *` where `m` has a static `__all__`; a definition whose decorator is not in the table of transparent decorators (`resolve.py`: `staticmethod`, `classmethod`, `property`, `functools.lru_cache`/`cache`/`wraps`/`cached_property`, `dataclasses.dataclass`, `abc.abstractmethod`, `typing.overload`/`final`/`override`, `contextlib.contextmanager`, ...); an alias (`Foo = Bar`); a module or class attribute that something assigns (`mod.f = g`, `setattr(mod, "f", g)`); a name that is both an attribute and a submodule; `cls()` |
| `unknown` | `getattr`/`setattr`/`delattr` with a name that is not a string constant; a star import whose source has no static `__all__` (or two sources list the name); a module-level `__getattr__`; two bindings of one name (including a `global` rebinding); an unresolved base class; a class `__getattr__`; a name the module does not define |

`self.m()` is deliberately never promoted to `definite`: an instance may belong to a
subclass outside the repository.

### What is stored and what is counted

A usage site is **stored** as a relation only when it resolves to the repository
(any confidence) or is one of the specific `unknown` forms above. Every other site is
**counted**, never dropped: `structure.sites` has `total` and how each site ended:
`internal`, `external_stdlib`, `external_declared`, `external_unmatched`, `builtin`,
`unresolved`, `dynamic`, `untracked` (with `untracked_by_reason`). The reasons are a
closed list: `local_binding` (a call of a parameter or local), `expression_without_a_name`
(`f().g()`), `instance_attribute` (not found in the class or its bases), `attribute_of_value`
(`logger.info`), `call_of_variable`, `call_of_module`, `base_not_a_class`, `unbound_name`,
`attribute_by_constant_name`, `self_reference`, `module_not_analysed`, `reexport_depth`,
`ambiguous_binding_without_repository_candidate`. Reading a local variable, a bare module
name or a bare `self` is not a usage site and is not counted. Uses of things outside the
repository are aggregated in `external_use` (name, class, calls, inherits, references).
`sites.total == internal + external_* + builtin + unresolved + dynamic + untracked`.

### Entry points

Each has `type`, `name`, `target`, `resolved`, `confidence`, `method`, `evidence`, `note`:
`main_block` (`if __name__ == "__main__":` at module level, definite), `package_main` (a
`__main__.py`, definite), `console_script` (`[project.scripts]`, `[project.gui-scripts]`,
`[tool.poetry.scripts]`) and `entry_point_group` (`[project.entry-points.<group>]`): the
target `module:attr` resolves to a symbol with that resolution's confidence, or stays
`unknown` with a note (a module outside the repository, in two roots, a missing name);
`test_root` (`[tool.pytest.ini_options] testpaths`, definite when an included file lies
under it); `framework_app` (probable only: `click.command`/`click.group` with `click`
declared, `typer.Typer()` with `typer` declared, `argparse.ArgumentParser()`). A plain
function is never an entry point. The list of Quick Context entry points is unchanged.

### Limits (not detected does not mean nonexistent)

String annotations and forward references are not read. `:=` binds when the walk reaches
it. Instance attributes, attributes of values of unknown type, descriptors, metaclass and
decorator-generated behaviour, dependency injection by registry or entry-point group
(sarand loads its own analyzer plugins that way), `exec`/`eval`, `globals()` mutation and
`__init_subclass__` are not followed; where the file shows such a construct it carries the
limitation `dynamic_construct_seen`. A symbol pass that hits the node, recursion or memory
guard keeps what it read and makes the file `partial`. `implements` and `overrides` do not
exist in Python and are not produced.

## Identity and fingerprints (R14-A3)

A later comparison of two runs (a baseline, R14-D) needs to know which symbol of the new
state *is* which symbol of the old one. R14-A defines the identity and tests it; it does
not compare runs yet.

- **The symbol `id`** is the identity: `sym:` plus 12 hex digits over language, kind,
  repository-relative path, qualified name and a `#n` ordinal for a duplicated name. It
  has no line number and no content, so it survives formatting, comments, docstrings
  and unrelated edits, and it changes when a symbol is renamed or its file is moved.
- **The `fingerprint`** (`fp1:` plus 12 hex digits) answers a different question: *did
  the content of this definition change?* It is a SHA-256 over a canonical walk of the
  definition's syntax tree. It ignores positions, whitespace, parentheses, quote style,
  trailing commas, comments and the docstring of a function or class; it includes every
  statement and expression, nested definitions, decorators, defaults and annotations.
  A class fingerprint therefore includes its methods. A variable is fingerprinted from
  its annotation and value only, so another target of the same statement does not
  change it. The algorithm is `structure/fingerprint.py`; a change of it bumps `fp1`.
- **The basis** (`meta.fingerprint_basis`, `fp1/python-3.12`) names the algorithm version
  and the interpreter's minor version, because the syntax tree differs between Python
  versions. Fingerprints are compared only between outputs with the same basis; across
  bases only ids can match.
- **Match classes** (`structure/identity.py`, `match_symbols`) between an old and a new
  list of symbols. Every symbol appears in exactly one row, and the result does not
  depend on input order.

| Class | Meaning |
|---|---|
| `exact` | the same id, with nothing doubtful about it; `content_changed` says whether the fingerprint differs (`null` when it cannot be compared) |
| `probable` | the same kind, qualified name and fingerprint at a different path (a move), exactly one candidate on each side |
| `ambiguous` | several candidates on at least one side: a duplicated qualified name whose duplicates cannot be paired by content, or several equally good move candidates; every candidate id is listed and none is chosen |
| `unmatched` | nothing on the other side (`removed` or `added`); a renamed symbol is an unmatched pair on purpose, because R14-A does not guess renames |

Limits: a fingerprint is not a security hash and never decides alone (it can only make a
match `probable`); a symbol that moved *and* changed has no counterpart; a method moved
with its class is matched per symbol; two outputs from different Python minor versions
match by id only. The match is defined on symbols; relations and entry points are not
matched yet.

## Evaluation on real repositories

`scripts/structure_eval.py` measures time and memory, checks that repeated runs
serialise to the same bytes and draws seeded samples (50 each of `Definite`,
`Probable` and `Unknown` relations, and of usage sites that were counted but not
stored) for manual review. The results for sarand and click, the rule used to judge a
row and the reviewed rows themselves are in `docs/R14A_GATE_REPORT.md` and
`docs/eval/`. The numbers are **estimates from small samples**, not accuracy.

## Where it appears

- **JSON** (`structure`, outer schema 1.10, structure schema 4): everything, including each edge,
  symbol, relation and entry point with its evidence, note and location. See `docs/JSON_SCHEMA.md`.
- **Markdown and HTML**: counts; import cycles (first 10); **unresolved and dynamic imports**
  (first 20): the imports whose target class is `internal_unresolved` or `dynamic`, with the
  reason; and the **external packages imported** (first 30, the `external_declared` and
  `external_unmatched` ones, with how many modules import each). The totals are always shown,
  and a cut list says how many are not shown. An empty section is not drawn. Every cell is
  escaped (HTML entities in HTML; pipes and line breaks in Markdown tables).
- **Markdown and HTML** also show the symbol, relation and entry-point counts; the symbols and
  relations themselves are in the JSON only.
- **Text**: one line.
- **SARIF**: not included.

All counts come from one place (`structure/serialize.py` and
`core/report_views.py`), so the formats agree.

## Not implemented yet

Comparing two runs (a baseline, R14-D), matching relations and entry points, and other
languages. Known precision limits found by the evaluation: a method called on a local
variable or parameter whose class is known only from a constructor call or an annotation
is not resolved (no local type inference), and a class that defines `__getattr__` makes
every attribute that is not found as a class member `unknown`, including instance
attributes the class assigns itself. Python import constructs that remain unsupported
are listed under "Recognised forms and their limits".
