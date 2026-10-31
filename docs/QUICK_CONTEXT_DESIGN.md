# Quick Context layers L2, L3 and L4: design record

Status: **accepted by the owner on 2026-10-25. R11a (declared frameworks and
the HTML and text sections) is implemented, 2026-10-31; R11b and R11c are not
implemented yet.**
This file is the single record of the design and of every decision taken about
it. Code is written in three rounds (R11a, R11b, R11c) that follow it; when a
round changes something here, it changes this file in the same commit.

The layer model comes from `docs/BACKLOG.md` section 12:

| Layer | Name | State |
|---|---|---|
| L0 | Full report | built |
| L1 | Project summary (the "AI Summary" section) | built |
| L2 | Quick Context (`core/quick_context.py`) | built; completed by R11a |
| L3 | Architecture and risks | designed here; R11b |
| L4 | Relevant source subset | designed here; R11c |

## 1. Principles

These bind every round. A change that breaks one needs a decision recorded here.

1. **Deterministic.** Every layer is a pure function of `ReportData` (and, for
   L4, of the bytes of the selected files). No clock, no environment, no
   randomness, stable ordering everywhere, ties broken by path.
2. **Nothing invented.** Every statement points at a real `ReportData` field or
   at a fixed rule table. If the data is not in the report, the layer does not
   say it ("exact fields must be based on current report data").
3. **Evidence, inference and limitation are kept apart.** A tool result, a
   pattern match and a repository state are different kinds of fact and are never
   merged under one word such as "security risk" (section 6.2).
4. **Bounded, with a budget that is documented honestly.** Every list is capped,
   every string is clipped, dropped items are counted, and the worst case of each
   layer is pinned by a test. A token budget is a documented conservative
   estimate, not a tokenizer guarantee (section 5.2).
5. **Analysis is untouched.** A layer only reads. It adds no finding, changes no
   score and no other section; a test compares the analysis output with and
   without the layer.
6. **Model-agnostic.** No per-model presets and no model-specific tokenizer
   until evidence shows a concrete need.

## 2. Evidence base (what exists, what does not)

Read from the code on 2026-10-25, not assumed.

Exists in `ReportData` and may be used:

- `detection` (languages, primary language, project type, build system,
  entry points), `stats` (files, lines, `largest_files`, `duplicate_files`),
  `components`, `workspace` and `extra_workspaces`, `compose`, `kubernetes`,
  `makefile`, `package_paths`;
- `test_results`, `quality_results`, `security_results` (each `CommandResult`
  with `kind`, `skipped`, `inconclusive`, `passed`, warnings and errors);
- `health` (`score`, `critical_failures`, `checks_skipped`,
  `checks_inconclusive`, `confidence`), `known_issues`;
- `secret_findings` (path, line, pattern name, `is_test_fixture`),
  `excluded_secret_files`, `todos` (path, line, kind, content);
- `git` (`dirty`, `ahead`, `behind`, `status`, `diff`, `untracked`);
- `included_files`: the paths that already passed every exclusion (binary,
  ignored, secret-flagged, size).

Does **not** exist, so no layer may state it:

- an import or dependency graph between source files;
- a structured file/line location on `Issue` (only `source`, `message`,
  `severity`);
- per-file line counts in `ReportData` (the scan record has them, the report
  does not keep them; `stats.largest_files` is the only per-file size data);
- which declared dependency the code actually uses.

Reusable: `core/secrets.py` has `scan_line(line)` (pattern names matching one
line) and `looks_like_secret_path(path)`, so L4 needs no new scanner.

## 3. Decisions

| Id | Decision | Date |
|---|---|---|
| D-QC1 | L4 is the optional flag `--relevant-source[=TOKENS]`, off by default, default budget 6000 tokens. | 2026-10-25 |
| D-QC2 | Frameworks come only from declared dependencies in manifests, never from folder layout or file names. | 2026-10-25 |
| D-QC3 | L3 risks are a fixed table of nine rules (section 6); no tenth rule in the first version. | 2026-10-25 |
| D-QC4 | The import graph is out of scope for the first versions; later it is a ranking signal only (section 8). | 2026-10-25 |
| D-QC5 | Every risk carries rule id, category, severity, evidence references, reason and limitation (section 6.2). | 2026-10-25 |
| D-QC6 | The L4 budget is enforced as a hard byte cap derived from the token budget, documented as an estimate (section 5.2). | 2026-10-25 |
| D-QC7 | L4 re-checks every snippet for secrets before it is written, even for files already in `included_files` (section 5.4). | 2026-10-25 |
| D-QC8 | R11a reads Node (`package.json`) and Python (`pyproject.toml`, `requirements.txt`) manifests only, because those are the only ones whose dependency names are already parsed (`core/components.py`). Cargo and Go dependency names are parsed nowhere, so those ecosystems give no entries until a separate, owner-approved step adds a reader (section 4, result). | 2026-10-31 |

D-QC8 was taken in R11a from the audit the design asked for. D-QC5 to D-QC7 come from an outside review of the first design, adopted after the
owner's approval; the disposition of every point of that review is in section 9.

## 4. Round R11a: finish L2

Scope: frameworks as **declared dependencies**, and the HTML and text sections.

- Three different things must not be conflated, and the output names only the
  first two: (1) a dependency declared in a manifest, (2) a framework recognised
  from a fixed table, (3) actual use in code. Only (1) and (2) are available, so
  the Markdown line reads "Declared frameworks (from manifests, not verified in
  code)" and the JSON key is `frameworks_declared`.
- Each entry: `name` (the declared dependency), `label` (from the table), `scope`
  (`runtime` or `dev`, only where the manifest makes it unambiguous) and
  `manifest` (the file it was read from).
- The table (about 60 names such as `fastapi`, `django`, `react`, `tokio`) is a
  constant with `FRAMEWORK_TABLE_VERSION`; a snapshot test pins its content, so
  a change is a deliberate edit with a changed snapshot.
- First step of the round: audit which manifests the analyzers already parse
  (Node, Python, Cargo, Go) and reuse that; no new parser per ecosystem. An
  ecosystem with no parsed manifest simply yields no entries.
- HTML and text renderers use **one** shared function that returns the lines, so
  the renderers cannot drift apart (Markdown and JSON already carry L2).

Acceptance criteria:

- [ ] no framework is ever reported from the directory layout (test);
- [ ] output order is stable (test: same input, same bytes, twice);
- [ ] the table snapshot test exists;
- [ ] the worst-case size of L2 is still pinned and still documented;
- [ ] the golden reports change only by the new lines, reviewed one by one
      (regenerate with `SARAND_UPDATE_GOLDEN=1`, read the diff, classify each
      change as intended or not);
- [ ] the full suite passes, and analysis output is unchanged.

### Result of R11a (2026-10-31)

Audit finding (first step of the round): the dependency names of **Node and
Python manifests** were already read in `core/components.py` (for the
`frontend` / `backend` hint), but merged into one set with the scope thrown
away. **No Cargo or Go dependency name is read anywhere** (the workspace code
reads Cargo members, not dependencies). Decision D-QC8: reuse, do not add a
parser. The reader was extracted into one public function,
`declared_dependencies`, which now feeds both the `kind` hint (behaviour
unchanged, every `test_components.py` test passes) and the framework line, so
the two cannot disagree.

What was built:

- `core/frameworks.py`: `FRAMEWORK_TABLE` (64 names, Node and Python),
  `FRAMEWORK_TABLE_VERSION = 1`, `detect_declared_frameworks(root)`. It reads the
  project root and the application components found by `core/components.py`
  (same bounded search, `examples/`, `tests/`, `vendor/` and `node_modules/`
  pruned), and nothing else. Output is sorted by (manifest, label, name) and
  capped at 100 entries.
- `scope`: `runtime` for `dependencies`, `[project].dependencies` and Poetry
  dependencies; `dev` for `devDependencies`; empty for `peerDependencies` and
  `requirements.txt`, whose meaning is not unambiguous (a `requirements.txt` may
  hold development tools). Poetry groups and `optional-dependencies` are not
  read, as before.
- `ReportData.frameworks_declared: list[FrameworkEntry]` (empty by default),
  filled in `cli.py`, so Quick Context stays a pure function of `ReportData`.
- Quick Context JSON: `frameworks_declared` (at most 8 entries) and
  `frameworks_declared_total` (the real count). Markdown line: "Declared
  frameworks (from manifests, not verified in code)", only when non-empty, with
  "(+N more)".
- One shared function, `quick_context_lines(qc)`, produces the plain lines for
  the **HTML and text** renderers, which had no Quick Context before; Markdown
  keeps its own markup over the same fields.

Acceptance criteria, as checked:

- [x] no framework from the directory layout (`test_no_framework_is_ever_reported_from_the_directory_layout`);
- [x] stable order, same bytes twice (`test_output_is_deterministic_sorted_and_not_a_mutation_of_anything`);
- [x] table snapshot test (version and SHA-256 of the sorted table; changing the
      table is a deliberate edit that changes both);
- [x] worst case still pinned and documented: the Markdown block went from 6438
      to 7362 bytes in the worst case (8 declared frameworks at their longest),
      so the documented figure is now about 7 KiB, and the test still requires
      under 9000;
- [x] goldens reviewed one by one (below);
- [x] the full suite passes and analysis output is unchanged (a test compares
      the report before and after rendering).

Golden changes, each classified **intended**: `hybrid.md` gains one line (the
frameworks line, from two entries added to the hand-built fixture); `hybrid.json`
and `minimal.json` gain `frameworks_declared` and `frameworks_declared_total`
inside `quick_context` (a stable schema, empty list when none); `hybrid.txt`,
`minimal.txt`, `hybrid.html` and `minimal.html` gain the whole Quick Context
block (new, from the shared function), and `minimal.txt` shows one
trailing-newline artefact on the line above it. SARIF snapshots are unchanged.

Open for the owner: a reader for Cargo (`[dependencies]`, `[dev-dependencies]`,
`[workspace.dependencies]`) and Go (`go.mod` `require`) would let `tokio`,
`axum`, `gin` and similar names into the table. It is small, but it is a new
parser, which this design said not to add inside R11a.

## 5. Round R11c: L4, the relevant source subset

### 5.1 Interface and universe

- `--relevant-source[=TOKENS]`; off by default; `--relevant-source` alone means
  6000 tokens; `--relevant-source=3000` lowers the cap to that value.
- Optional `--focus "text"` adds a signal (a match of the words against the path).
- **Candidate universe: `included_files` only.** So every existing exclusion rule
  applies to L4 with no extra code, and a test states the property: the files L4
  can show are a subset of the files `--source` could show.

### 5.2 Budget semantics (D-QC6)

- The token count of a text depends on the model, and no tokenizer is bundled
  (model-agnostic). So the guarantee is on **bytes**: L4 output, including
  headers, labels and formatting, never exceeds `TOKENS x 3` UTF-8 bytes. Three
  bytes per token is deliberately more conservative than the four characters
  per token used for estimates elsewhere, and counting bytes penalises
  non-ASCII text (for example Persian) as it should.
- This is documented as a conservative estimate. It is not a promise that a given
  model counts at most `TOKENS` tokens; adversarial text (long random strings)
  can tokenize worse. The JSON `relevant_source.budget` block states `tokens`,
  `bytes_cap`, `bytes_used` and the ratio used.
- The budget covers file selection, snippet text and formatting overhead
  together, not only source characters.
- A file bigger than the budget is clipped to snippets; it never breaks the cap.
- When space is short, the order of what is kept is fixed: file path and "why this
  file" label first, then snippets in score order; a snippet is dropped before a
  header is, and dropped items are counted as "(+N more)".

### 5.3 Selection

- Signals read from `ReportData`: files with TODOs, paths of secret-pattern
  matches (the path only), files changed or untracked in git, entry points, files
  named by `--focus`. Weights are fixed constants set in R11c from real reports.
- Score = sum of signal weights; ties broken by path, ascending. Deterministic.
- Greedy selection until the byte cap is reached.
- **No redundant files:** candidates that share a content hash
  (`stats.duplicate_files`) count as one; only the first path is shown, with the
  others named. The tests include two near-identical files plus one unique file,
  to check that the unique file is not crowded out by the duplicates. The
  algorithm stays this simple until such a test fails; no diversity algorithm
  is added in advance.
- Snippets: lines around the signal (TODO line, finding line, diff hunk) with a
  fixed number of context lines; the file head when the signal is the whole file
  (entry point). Each snippet states file, line range and reason.

### 5.4 Secret handling (D-QC7)

Excluding secret-flagged files is not enough: a file never flagged may still
contain something the scanner did not recognise. L4 therefore:

1. never copies the content of a file in `excluded_secret_files`, and never shows
   a path from `looks_like_secret_path`;
2. runs `scan_line` on **every line of every snippet** just before it is written;
   a matching line is replaced by a marker that says a line was withheld and why
   (pattern name only, never the value);
3. has a test that plants a fake secret in a file that is in `included_files` and
   selected, and asserts that the secret text is absent from the final output in
   every renderer.

Limit, stated in the user documentation: a secret no pattern recognises is not
withheld. This is the same limit `--source` already has, so L4 is never weaker
than the existing output, and it adds no new scanner.

### 5.5 Performance

All inputs are already in memory; there is no new walk of the repository.
Candidates are bounded by the number of signals; sorting costs O(C log C) over
that set. Only the selected files, about 10 to 20, are read from disk, each with a
size cap and the existing path-safety checks. Memory is bounded by the byte cap.
For scale: the 410K-token report of sarand on itself against a 6000-token budget
is about 1.5 percent of its size.

Acceptance criteria:

- [ ] optional flag, off by default, the default run is byte-identical;
- [ ] `bytes_used <= bytes_cap` for every fixture, including a file larger than
      the whole budget and a budget too small for one header (test);
- [ ] L4 files are a subset of `included_files` (property test);
- [ ] planted secret absent from the output (test, all renderers);
- [ ] deterministic: same input, same bytes, twice;
- [ ] the duplicate-versus-unique selection test passes;
- [ ] a timing test or documented measurement on a large fixture shows that
      only selected files are read.

## 6. Round R11b: L3, architecture and risks

### 6.1 Architecture block (about 1 to 2 KiB)

Built only from fields that exist: components and workspace members, entry
points, Compose services, Kubernetes and Helm items, with file counts and lines
per component. No graph, no layers inferred from names.

### 6.2 Risk entries (D-QC5)

Each risk is a record with:

| Field | Meaning |
|---|---|
| `rule_id` | stable identifier of the rule (below), safe to test and to reference |
| `category` | `security`, `quality`, `coverage`, `repository-state` or `maintainability` |
| `severity` | `info`, `warning` or `high`, from a fixed per-rule mapping, never from a guess |
| `evidence_refs` | references to real report fields, by kind name, for example `security_results[kind=cargo-audit]`, not by list index (indices change with ordering) |
| `reason` | one sentence on why the rule fired, with the numbers |
| `limitations` | a fixed sentence per rule saying what the evidence does **not** show |

Markdown and text render one short line per risk (id, severity, reason, evidence
reference); `limitations` and the full records are in JSON, and the Markdown
legend carries each rule's limitation once. Display cap: 8 risks, ordered by
severity (high first) then `rule_id`; the rest are counted as "(+N more)". JSON
lists all of them.

The block also lists `rules_not_evaluated`: rules whose data was absent (for
example `health` is `None`). Missing data is never read as "all good".

### 6.3 The nine rules

| `rule_id` | Category | Fires when (source field) | What it does not show |
|---|---|---|---|
| `SEC-CHECK-FAILED` | security | a `security_results` entry is failed (not skipped, not inconclusive) | a tool result, not a proven vulnerability |
| `HEALTH-CRITICAL` | quality | `health.critical_failures` is not empty | covers only the checks that ran |
| `SECRET-PATTERNS` | security | `secret_findings` with `is_test_fixture` false; **count only**, never path or content | pattern matches, not confirmed leaked secrets |
| `CHECKS-SKIPPED` | coverage | skipped checks reach the threshold | skipped means not run, not failed |
| `GIT-STATE` | repository-state | `git.dirty`, or `git.ahead` or `git.behind` above zero | says nothing about security or quality |
| `HEALTH-LOW-CONFIDENCE` | coverage | `health` exists and `health.confidence` is below the threshold | confidence is about coverage of checks |
| `TODO-CLUSTER` | maintainability | one path has at least N entries in `todos` | a count, not a density: per-file line counts are not in the report |
| `LARGE-FILE` | maintainability | an entry of `stats.largest_files` is at or above the threshold | size alone is not a defect |
| `DUPLICATE-FILES` | maintainability | `stats.duplicate_files` is not empty | identical content among files the scan hashed (its size cap applies) |

Thresholds are **not chosen here**. They are fixed in R11b from real reports
(sarand on itself and the golden fixtures), recorded in the code as named
constants and in this file: the skipped-checks threshold, the confidence
threshold, N for `TODO-CLUSTER`, and the size for `LARGE-FILE` (first confirm
whether the number in `largest_files` is bytes or lines).

Tests, three per rule, no exception:

- positive: real failing or present data fires the rule;
- negative: healthy data does not;
- incomplete: absent or empty data does not fire the rule and the rule appears
  in `rules_not_evaluated`, so absence is not mistaken for success. For
  `SEC-CHECK-FAILED` that means: failed fires; passed does not; no
  `security_results` does not fire and is listed as not evaluated.

Other acceptance criteria:

- [ ] only reads `ReportData`; analysis output unchanged (test);
- [ ] the worst case size of L3 is pinned by a test and documented;
- [ ] ordering is stable (test);
- [ ] goldens reviewed one by one as in R11a.

## 7. Process rules for the three rounds

- One round, one commit series, one new test file per round, plus the regression
  suite after each round.
- If an earlier behaviour changes, the change is classified as intentional (and
  written here and in the CHANGELOG) or as a bug (and fixed).
- Golden reports are regenerated only with `SARAND_UPDATE_GOLDEN=1`, and the diff
  is read before it is committed.
- The user documentation (README en and fa, the report description) is updated in
  the round that adds the option, not after.

## 8. Later: the import graph (not in these rounds)

Possible only after L4 has run on real reports and its selection quality is
judged. It would be a **ranking signal for the candidates already chosen**, never
evidence of architectural dependency. Known difficulties, so nobody underestimates
them: relative and absolute imports, type-only imports in Python, aliases and
path mappings, dynamic imports, differences between Rust, JavaScript and Python,
and false links from regular expressions. Start with Python (`ast`) only if a
measured need appears.

## 9. Disposition of the outside review

An outside review of the first design was received on 2026-10-25. Each point and
what was done with it:

| Review point | Disposition |
|---|---|
| Separate evidence, inference and limitations in L3 | Adopted as D-QC5. Adjusted: `limitations` is a fixed sentence per rule (not per instance) and full records live in JSON, so the Markdown block keeps its size cap. |
| A secret-pattern match is not a confirmed leak | Adopted: wording in the rule table, count only, test fixtures excluded; the existing L2 rule "never paths or content" is kept. |
| References by field, never invented paths | Adopted; refined to references by kind name instead of list index. |
| The token budget must be guaranteed | Adopted in part as D-QC6. A true token guarantee needs a tokenizer per model, against the model-agnostic principle. The guarantee is a hard byte cap with a conservative documented ratio, stated as an estimate. |
| Budget covers selection, snippets and overhead; a huge file must not break it; fixed priority when space is short | Adopted (section 5.2). |
| Greedy selection may pick near-duplicates and drop a unique file | Adopted as a test, with duplicate hashes counted once; no diversity algorithm in advance. |
| Keep the nine rules, add no tenth; three tests per rule (positive, negative, incomplete data) | Adopted (section 6.3). Added `rules_not_evaluated`. |
| Density rule depends on line counts | Checked against the code: per-file line counts are not in `ReportData`, so the rule is a count (`TODO-CLUSTER`) and says so. |
| Import graph later, as a ranking signal only | Adopted (section 8). |
| Declared dependency is not use; three concepts; versioned table with tests | Adopted (section 4): `frameworks_declared`, table version, snapshot test, and scope (runtime or dev) where unambiguous. |
| L4 must re-check for secrets even for included files | Adopted as D-QC7 (section 5.4), reusing `scan_line`. |
| Acceptance criteria and regression tests per round; classify behaviour changes | Adopted (sections 4 to 7). |

## 10. Open parameters (to be fixed with evidence in the rounds)

- R11a: which manifests are already parsed; the final framework table.
- R11b: the four thresholds in section 6.3; the L3 worst-case size.
- R11c: the signal weights; context lines per snippet; per-file snippet cap;
  the confirmed bytes-per-token ratio (3 is the starting value); the behaviour of
  `--focus` with several words.
