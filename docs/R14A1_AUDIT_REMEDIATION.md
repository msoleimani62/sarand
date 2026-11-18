# R14-A1 audit remediation

Scope: only the existing R14-A1 subsystem (`python/sarand/structure/`, its report
surface and `docs/STRUCTURE.md`). Nothing of R14-A2 or R14-A3 was started. Each finding
of the external audit was re-checked against the code at `55dc8aa` (R14-A1 as committed,
with the owner's type-annotation fixes) before it was acted on.

Statuses are the audit's own: **Confirmed** (demonstrated by reading the code or by a
reproduction run before any change), **Potential**, **Needs test**, **Design clarification**.
"Fixed" means the code changed; "Decided" means a contract was written down and tested;
"Left" means intentionally unchanged.

## Review of the owner's two changes after the first delivery

The owner fixed 5 mypy errors and the HTML-side type errors himself. Compared with the
delivered code, the differences are formatting (`ruff format`) and type annotations
only: `SourceLocation` now gets `int(...)` coercions, the row-returning helpers return
`list[tuple[str, str, str, str]]` and the HTML table helper accepts `Sequence`, a variable
was renamed to remove a duplicate definition. None of them changes behaviour or leaves the
purpose of the subsystem; they are kept.

## Findings

| ID | Audit status | Re-check | Outcome |
|---|---|---|---|
| A1 | Confirmed, P2 | `meta` and `extensions` were plain dicts and lists | **Fixed.** `model.freeze` stores read-only mappings and tuples; entities copy their input. Tests: `test_model_objects_cannot_be_changed_after_construction`, `test_nested_inputs_are_copied_not_shared` |
| A2 | Confirmed, P1 | Reproduced: AST column 10 (bytes), `SyntaxError` column 9 (characters) for the same line | **Fixed and decided.** One unit: UTF-8 byte offsets, 0-based; syntax errors are converted (`byte_column`). Tests: `test_columns_are_utf8_byte_offsets_for_ast_and_for_syntax_errors`, `test_a_form_feed_does_not_shift_line_numbers` (a second defect found here: `str.splitlines` splits on form feeds and shifted line numbers) |
| A3 | Confirmed, P1 | No validation anywhere in the model | **Fixed.** Every entity validates in `__post_init__` and raises `ModelError` naming the field and the allowed values. Tests: `test_invalid_values_are_rejected_at_construction_with_a_clear_message` and the related ones |
| A4 | Confirmed, P2 | The serializer docstring called the model schema "1.7" | **Fixed.** Docstrings and `docs/STRUCTURE.md` separate the structure model schema (`1`) from the outer report schema (`1.7`). Test: `test_the_inner_and_outer_schema_versions_are_independent` |
| A5 | Potential, P2 | Confirmed: an unreadable file got `size=0` | **Fixed.** `size` is `None` (JSON `null`) when unknown; test `test_an_unreadable_file_has_an_unknown_size_not_zero` |
| B1 | Confirmed, P1 | Reproduced: `custom.TYPE_CHECKING` and a shadowed `TYPE_CHECKING = True` were `type_only` | **Fixed.** Binding-aware: only the `typing`/`typing_extensions` sentinel, `typing.TYPE_CHECKING` through aliases, and the `TYPE_CHECKING = False` idiom; `if not X` handled. Test: `test_type_checking_is_recognised_only_from_the_typing_sentinel` |
| B2 | Confirmed, P1 | Reproduced: the level was read from `args[3]` | **Fixed.** Level is argument 4 or `level=`; a level above 0 is resolved only when `globals` is the plain `globals()` call. Tests: `test_builtin_dunder_import_reads_its_level...`, `test_a_relative_dunder_import_without_a_plain_globals_is_unresolved` |
| B3 | Confirmed, P1 | Reproduced: `ci('os')` was not seen | **Fixed.** Aliases through `from builtins import` and `import builtins as`; a user-defined `__import__` is not the builtin. Test: `test_an_aliased_builtin_dunder_import...` |
| B4 | Confirmed, P1 | Reproduced: `il.import_module('sys')` was not seen | **Fixed.** Test: `test_importlib_module_and_member_aliases_are_recognised` |
| B5 | Confirmed, P1 | Reproduced: a name bound in `f()` was recognised in `g()` after `import_module = print` | **Fixed.** Per-scope binding tables (module, class, function, comprehension) with Python's lookup order; a name bound two ways is ambiguous. Tests: `test_an_alias_does_not_leak...`, `test_a_name_bound_two_different_ways_is_ambiguous...` |
| B6 | Confirmed, P1 | Reproduced: `else` and `finally` imports were marked conditional | **Fixed.** Only a guarded `try` body, the handlers and the `else` are conditional; `finally` is not. Test: `test_try_sections_have_their_own_control_flow` |
| B7 | Potential, P2 | Both directions reproduced: `foo.ImportError` accepted, alias `IE` missed | **Fixed.** Recognition by binding: builtin names, `builtins.X`, `IE = ImportError`, tuples, bare `except`, `Exception`, `BaseException`. Test: `test_import_error_handlers_are_recognised_by_binding_not_by_spelling` |
| B8 | Needs test / design | Definition missing | **Decided and tested.** `conditional` = a control-flow decision in the same scope (`if`, guarded `try`, handlers, `try ... else`, loops, `match`, `and`/`or` right side, conditional expressions, comprehensions); not `finally`, not `with`. Documented in `docs/STRUCTURE.md`. Test: `test_conditional_means_a_control_flow_decision_in_the_same_scope` |
| B9 | Needs test | Code reading: `returns` was not visited | **Fixed.** Return annotations and `type_params` are traversed. Test: `test_return_annotations_are_traversed` |
| B10 | Potential, P1 | Reproduced: `import_module(".mod", package="pkg")` was treated as absolute | **Fixed.** `package=` is modelled; relative names resolve as `importlib.util.resolve_name` does; missing, computed and too-high cases are unresolved or dynamic. Test: `test_import_module_resolves_a_relative_name_against_its_package_argument` |
| B11 | Potential, P2 | No location kept for `exec`/`eval` | **Decided, left.** A1 only needs the limitation `dynamic_construct_seen`; no edge exists for them. Documented; no new feature added. Test: `test_exec_and_eval_mark_the_file_only_when_they_are_the_builtins` |
| B12 | Potential, P2 | The docstring promised "never raises" | **Fixed.** `MemoryError` while walking becomes `resource_limit`; docstring names exactly the handled failures; nothing else is swallowed. Test: `test_a_memory_failure_while_walking_is_a_resource_limit` |
| B13 | Confirmed heuristic, P2 | The message-keyword heuristic could call an ordinary f-string error "newer syntax" | **Fixed by removal.** A syntax error cannot be attributed reliably; it is reported as `syntax_error` only. `unsupported_syntax_for_interpreter` stays defined, not produced (documented). Test: `test_syntax_error_files_are_failed_without_guessing_the_grammar` |
| B14 | Confirmed, P2 | Only the first line of a statement | **Fixed and decided.** Evidence is the statement's own text (start to end column, trailing comment excluded), lines joined by single spaces, cut at 240 characters with `...`. Test: `test_evidence_is_the_statement_text_bounded...` |
| B15 | Potential, P2 | Recursion before the node cap | **Fixed.** A recursion failure loses only its top-level statement; later statements are read; earlier imports are kept; the cap and memory failures stop the walk with `partial`. Tests: `test_a_walk_failure_loses_only_its_statement`, `test_the_node_cap_keeps_the_imports_found_before_it`, `test_a_deep_expression_never_crashes...` |
| B16 | Needs test | Traversal order reviewed | **Tested, one change.** Decorators, defaults, annotations, class bases and the first comprehension iterable are evaluated in the enclosing scope; bodies in their own. Test: `test_decorators_and_defaults_are_not_lazy_but_the_body_is` and the context tests |
| C1 | Confirmed, P1 | Reproduced: only the empty key was read | **Fixed.** Named mappings carry a package prefix (`{"mypkg" = "lib/other"}` makes `lib/other/a.py` the module `mypkg.a`). Tests: `test_a_named_package_dir_mapping_renames_the_package` and related |
| C2 | Potential, P1 | No validation | **Fixed.** `normalise_root`: relative, inside the project, normalised; the rest is rejected and listed in `meta.rejected_roots`. Tests: `test_root_paths_are_normalised_inside_the_project`, `test_root_declarations_that_leave_the_project_are_rejected_and_reported` |
| C3 | Potential, P1 | Reproduced: `module_name("other/x.py", "lib")` gave a garbage name | **Fixed.** Containment is checked; outside paths give no name. Test: `test_a_module_name_needs_the_path_to_be_inside_its_root` |
| C4 | Needs test | Root-level `__init__.py` | **Decided and tested.** It has no importable name; it is listed with an empty module and its imports are reported by path. Test: `test_a_root_level_init_has_no_importable_name` |
| C5 | Needs test | Namespace semantics | **Tested** (regular, namespace, mixed, nested, several roots). No defect found. Test: `test_regular_namespace_and_mixed_packages_resolve_like_python` |
| C6 | Potential, P1 | Confirmed: one root kept per namespace prefix | **Fixed.** One `ModuleEntity` per (name, root). Test: `test_a_namespace_package_keeps_every_root_it_has_a_portion_in` |
| C7 | Needs test | No path contract | **Decided and tested.** Relative, inside the project, no `..`; an absolute or parent path raises `ValueError`. The CLI's secret-exclusion seam is tested with the real functions. Tests: `test_the_path_contract_rejects_absolute_and_parent_paths`, `test_files_the_secret_steps_exclude_never_reach_the_structure` |
| D1 | Needs test | Iterative Tarjan | **Tested; no defect found** (disconnected components, several SCCs, a node joining two cycles, parallel edges, self cycles, a 3000-node chain with a back edge, edge-order independence) |
| D2 | Design | `Cycle.edges` meaning | **Decided.** Every definite or probable edge whose two ends are in the cycle, lazy and type-only included, each with its flags; not a minimal loop. Documented; test `test_cycle_edges_are_every_internal_edge_with_its_own_flags` |
| D3 | Needs test | Eager semantics | **Tested; no defect found.** `conditional` edges still count as eager (documented) |
| E1, E2 | see C6, A5 | | Fixed there |
| E3 | no defect | | **Left.** Declarations still come from `core.components.declared_dependencies` (one source of truth) |
| E4 | Needs test | Metadata determinism | **Tested** (`test_metadata_is_deterministic_and_names_its_environment`): the only environment values are the interpreter and the standard-library source, both named |
| E5 | no defect | CLI order | **Preserved and tested at the seam** (see C7); the end-to-end check is in the verification list below |
| F1 | see A4 | | Fixed there |
| F2 | Confirmed, P1 | The serializer did not sort | **Fixed and decided.** The serializer sorts every collection by an explicit key (the shared `edge_sort_key` for edges and cycle edges); producers stay sorted too. Test: `test_the_serializer_orders_every_collection_itself` |
| F3, F5 | Potential/Confirmed, P2 | Shallow canonicalisation | **Fixed.** `canonical` is recursive; `meta` sequences are sorted, extension sequences keep their order; the model is not mutated. Tests: `test_nested_metadata_and_extensions_are_canonical...`, `test_canonical_is_plain_json...` |
| F4 | see A3 | | Fixed there (the summary cannot meet an unknown value) |
| F6 | Confirmed gap, P1 | Only the outer version was asserted | **Fixed** (see A4) |
| G1 | Confirmed, P2 | The heading said "could not be resolved" but listed dynamic edges too | **Fixed.** Renamed "Unresolved and dynamic imports", column "Reason". Test: `test_the_unresolved_section_is_named_for_what_it_lists` |
| G2 | Confirmed gap, P2 | One row tested | **Fixed.** Boundary tests at 9/10/11/25 cycles, 19/20/21/30 unresolved, 29/30/31/45 externals in Markdown and HTML |
| G3 | Needs test, P1 | **A real defect found:** the Markdown "reason" and "location" cells were not escaped (a pipe character in a file name broke the table) | **Fixed** with the shared `_cell`; hostile-input tests for Markdown and HTML |
| G4 | Needs test | Malformed external references | **Fixed through A3:** they cannot be constructed |
| G5 | Needs test | Attention semantics | **Decided and tested.** Attention rows are exactly the `internal_unresolved` and `dynamic` edges; an unmatched external is listed in the external table instead. Test: `test_attention_rows_are_exactly_the_unresolved_and_dynamic_edges` |

## Two further defects found while re-checking

1. The edge `evidence` carried sarand's own note appended after two spaces and a `#`, so a source comment
   and a note were indistinguishable. `Edge.note` is now a separate field, and evidence
   excludes a trailing comment.
2. `SyntaxError` end columns were always 0; they are now converted like the start column.

## Compatibility

- The outer report schema stays `1.7`; the structure model schema stays `1`. The structure
  model was added in the unreleased R14-A1; no released version contains it, so the changes
  to it (`Edge.note`, nullable `FileEntity.size`, tuple/mapping `meta`) break no consumer.
- A default report is unchanged: all goldens are byte-identical (checked by running every
  fixture and format).
- SARIF has no structure output. Secret exclusion is unchanged and tested at the seam.

## Remaining risks and limits

- Assignment expressions (`:=`) and the names a `from m import *` binds are not tracked
  in the scope tables; names such as `getattr(importlib, "import_module")` are not followed.
- The scope-aware walk costs about 1.5x the previous run time on the same files (median
  0.69 s to 1.07 s for 279 files in the sandbox; the owner's phone was not measured).
- `ruff`, `mypy` and `bandit` do not run in the sandbox; they are verified by the owner's chain.
- The end-to-end CLI check of secret exclusion is not an automated test.
