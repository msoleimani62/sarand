# The JSON report schema

`sarand --format json` writes one JSON object. This page lists every top-level key, the fields of its nested objects, and what a script may rely on. The current version is below; a test keeps this page and the code in step, so a key that exists but is not listed here fails the build.

Current version: **1.7**

## Compatibility policy

- `schema_version` is `MAJOR.MINOR` and is the first key. It is versioned on its own, apart from the program's version.
- **Adding** a key or a field bumps MINOR (1.0 to 1.1). Readers must ignore keys they do not know.
- **Removing or renaming** a key or field, changing its type, or changing what it means bumps MAJOR, and the CHANGELOG says so.
- An optional key is **absent**, never `null`, when its feature does not apply. The one `null` is `health` with `--no-health`.
- Free-form text is not covered: `raw_output`, `content`, `details`, `tool_versions`, and the wording of `reason`, `summary` and `ai_summary` can change without a bump. Rule ids (`rule_id`), reasons-as-data such as `severity`, and the keys on this page are covered.
- This page is about the JSON report. SARIF follows its own standard, and Markdown, HTML and text have no stability promise.

## Top-level keys

| Key | Type | Present | Meaning |
|---|---|---|---|
| `schema_version` | string | always | Version of this JSON schema, `MAJOR.MINOR` (see the policy below). Always the first key. |
| `project_root` | string | always | Absolute path of the scanned project. |
| `quick_context` | object | always | The short, bounded summary that opens the report (fields below). |
| `architecture` | object | always | Components, workspaces, entry points, Compose and Kubernetes items read from this report (fields below). |
| `risks` | object | always | Rule-based risks, each with its evidence and limitation, and the rules that could not be evaluated (fields below). |
| `generated_at` | string | always | ISO 8601 time the report was made. |
| `used_rust_core` | boolean | always | Whether the Rust scan engine was used. |
| `detection` | object | always | Detected languages, build system and entry points (fields below). |
| `environment` | object | always | The machine and tool versions the scan ran on (fields below). |
| `git` | object | always | Repository state; `branch` is `(unavailable)` outside a repository (fields below). |
| `stats` | object | always | File, line and size statistics (fields below). |
| `todos` | array | always | Every marker occurrence found, each with `path`, `line_number`, `kind`, `content` and `category` (`actionable`, `historical`, `safety`, `development` or `mention`; see `docs/MARKERS.md`). |
| `test_results` | array | always | Results of test runs (result objects, fields below). Empty when tests were skipped. |
| `quality_results` | array | always | Results of linters and type checkers (result objects). |
| `security_results` | array | always | Results of security tools (result objects). |
| `health` | object or null | always | The health score (fields below); `null` with `--no-health`. |
| `known_issues` | array of strings | always | Problems the scan itself noticed. |
| `known_issue_ids` | array of strings | only when `known_issues` was built from classified failures | The stable finding id of each known issue, in the same order (R13-F). See `docs/FINDINGS.md`. |
| `structure` | object | only with `--structure` | The repository structure (R14-A): files with their provenance, modules, imports with target class, confidence and evidence, external packages, and import cycles. Described in `docs/STRUCTURE.md`. |
| `ai_summary` | string | always | A plain-language summary meant for an AI reader. |
| `suggested_reading_order` | array of strings | always | Every included file, most important first. Quick Context shows the first ten. |
| `included_files` | array of strings | always | Project-relative paths whose content may be shown. |
| `skipped_files` | array of pairs | always | `[path, reason]` for files that were left out. |
| `excluded_secret_files` | array of strings | always | Paths left out because they look like, or contain, credentials. Only paths, never content. |
| `secret_findings` | array | always | Secret-pattern matches: `path`, `line_number`, `pattern_name`, `is_test_fixture`. Never the matched value. |
| `todos_suppressed` | integer | only when some markers were suppressed | How many markers an exception removed. |
| `todo_categories` | object | only when a marker was found | How many markers are in each category (all five keys, in a fixed order). Only `actionable` markers are scored. |
| `failures` | array | only when a check failed | Every failed check, classified: tool, group, category, cause, subject, exit code, a neutral summary and the evidence labels (fields below). A category says what kind of failure it is, not that the project is vulnerable. |
| `advisories` | array | only when a security tool reported an advisory | One entry per dependency advisory (id, package, version, kind, title, severity, fixed versions, url, the checks that reported it, database, applicability; fields below). A tool result, not proof that the project is exploitable. |
| `relevant_source` | object | only with `--relevant-source` | The relevant source subset: `budget`, `text`, a `files` index and counters (fields below). |
| `scan_skipped` | integer | only when the scan could not read some paths | How many paths the scan could not read. |
| `scan_skipped_samples` | array of strings | with `scan_skipped` | A few of those paths. |
| `workspace` | object | only when a workspace was detected | The detected workspace: its kind and members. |
| `workspaces` | array | only when there is more than one workspace | All workspaces; the first equals `workspace`. |
| `package_results` | array | only when packages ran their own checks | Per-package check summaries. |
| `kubernetes` | object | only when Helm or Kustomize was detected | Helm charts, Kustomize overlays and, when found, raw manifests. |
| `compose` | object | only when a Compose file was detected | `files`: Compose files with their services. |
| `makefile` | object | only when a Makefile was detected | `files` and `total_files` of the Makefiles and their targets. |
| `monorepo_tools` | array | only when Turborepo or Nx config was found | Declared Turborepo and Nx tasks, read statically. |
| `components` | object | only for a hybrid project | `components`, `links`, `total_components`, `total_links`. |
| `source_files` | array | unless `--no-source` | `{path, size, content}` for every included file. |

## Nested objects

The fields of the objects named above, in the order they are written.

- **`quick_context`**: `project`, `primary_language`, `languages`, `project_type`, `build_system`, `components`, `frameworks_declared`, `frameworks_declared_total`, `structure`, `total_files`, `total_loc`, `tests`, `quality`, `security`, `health`, `critical_findings`, `critical_finding_ids`, `risks`, `reading_order`. `frameworks_declared` holds at most 8 entries of `{name, label, scope, manifest}`; `frameworks_declared_total` is the real count.
- **`architecture`**: `components`, `workspaces`, `entry_points`, `compose`, `kubernetes`. Five lists of short plain-text lines.
- **`risks`**: `risks`, `rules_not_evaluated`. `risks` is a list of `{rule_id, category, severity, evidence_refs, reason, limitations}`, `severity` is `high`, `warning` or `info`; `rules_not_evaluated` lists the rule ids whose data was absent.
- **`relevant_source`**: `budget`, `text`, `files`, `omitted_files`, `omitted_snippets`, `withheld_lines`, `unreadable_files`. `budget` is `{tokens, bytes_cap, bytes_used, bytes_per_token, wrapper_bytes}`; `files` is an index of `{path, why, score, same_as, snippets}`, not a second copy of the code.
- **`detection`**: `languages`, `primary_language`, `project_type`, `build_system`, `markers_found`, `entry_points`, `details`.
- **`environment`**: `python`, `rust_core`, `os_name`, `architecture`, `cpu_summary`, `memory_summary`, `disk_free`, `hostname`, `tool_versions`.
- **`git`**: `branch`, `commit`, `status`, `log`, `diff`, `dirty`, `ahead`, `behind`, `tags`, `stashes`, `untracked`.
- **`stats`**: `total_files`, `total_loc`, `code_lines`, `comment_lines`, `blank_lines`, `files_by_extension`, `largest_directories`, `largest_files`, `duplicate_files`, `broken_symlinks`, `temporary_files`, `unused_cache_files`, `empty_files`, `executable_scripts`, `hidden_files`, `binary_files`. `largest_files` is a list of `[path, bytes]`; `duplicate_files` is a list of `[hash, [paths]]`.
- **`health`**: `score`, `max_score`, `grade`, `breakdown`, `recommendations`, `critical_failures`, `critical_ids`, `checks_run`, `checks_skipped`, `confidence`, `checks_inconclusive` (always present since 1.6; an empty list means none), `execution_coverage`, `checks_requested`, `checks_executed`, `coverage_by_group`, `coverage_gaps`. `execution_coverage` is `executed / requested` between 0 and 1, or `null` when no check was requested (never 100% for nothing); it says which requested checks ran to a verdict, not how complete or correct the analysis is. `coverage_by_group` has `tests`, `quality` and `security`, each with `requested` and `executed`; `coverage_gaps` lists `{kind, state, reason}` for every requested check that did not run (`state` is `skipped`, `inconclusive`, `unavailable` or `unknown`). `confidence` is **deprecated**: it keeps its old arithmetic (`ran / (ran + distinct skipped or inconclusive kinds)`, 1.0 when nothing was requested) and is not shown in the reports; read `execution_coverage` instead. It stays through all 1.x versions and is removed no earlier than schema 2.0.
- **`result`**: `kind`, `returncode`, `summary`, `raw_output`, `warnings`, `errors`, `duration_seconds`, `skipped`, `skip_reason`, `inconclusive_reason`, `state`. The object inside `test_results`, `quality_results` and `security_results`. `inconclusive_reason` appears only when set. `state` (1.6) is the check's state as sarand reads it everywhere: `passed`, `failed`, `skipped`, `inconclusive`, `unavailable` or `unknown` (see `docs/CHECK_STATES.md`).
- **`kubernetes`**: `helm_charts`, `kustomize_overlays`, and, only when raw manifests were found, `manifests` and `total_manifest_files`.
- **`failures`**: `tool`, `group`, `category`, `cause`, `subject`, `returncode`, `summary`, `signals`, `id`. `group` is `test`, `quality` or `security`. `category` is one of `compilation_failure`, `test_failure`, `lint_failure`, `security_tool_failure`, `security_finding_detected`, `configuration_failure`, `dependency_policy_failure`, `report_generation_failure` (reserved, not produced yet) or `unknown_tool_failure`. `cause` is `exit_code`, `timeout`, `tool_not_found` or `os_error`; only `exit_code` means the tool itself ran and exited non-zero. `signals` are labels of the evidence that decided the category, never raw output. One failed check can give several entries (cargo deny can report advisories and policy violations in one run).
- **`advisories`**: `id`, `package`, `version`, `kind`, `title`, `severity`, `fixed_versions`, `url`, `sources`, `database`, `applicability`. `kind` is the advisory database's word: `vulnerability`, `unsound`, `unmaintained`, `yanked` or `notice`. `severity` is the upstream value when the tool printed one and `null` when it did not (the RustSec text output prints a severity only for advisories with a CVSS score; none is guessed). `fixed_versions` lists the versions the tool names (empty when it says no safe upgrade exists). `sources` names every check that reported the advisory (cargo audit and cargo deny report one advisory once). `database` names the advisory database and how many advisories the tool loaded; it does not claim the database was refreshed. `applicability` is `unknown` for every entry: no reachability analysis (affected API, enabled features, target platform) is done, and a dependency in `Cargo.lock` is not evidence of exploitability. Entries are sorted by kind (vulnerability, unsound, unmaintained, yanked, notice), then id, package and version.

## Version history

- **1.7** (R14-A1): added the `structure` object, present only with `--structure`: `schema`, `language`, `meta` (interpreter, standard-library source, source roots), `summary` (counts), `files` (each with provenance and completeness), `modules`, `externals`, `edges` (an import with `target_class`, `confidence`, `resolution_method`, `flags`, `evidence`, `location`) and `cycles`. A default report is unchanged apart from the version number. See `docs/STRUCTURE.md`.
- **1.6** (R13-G): each entry of `test_results`, `quality_results` and `security_results` gained `state`, and `health.checks_inconclusive` is now always present (it used to be left out when empty, although this page listed it). Tool lines that restate a dependency advisory are no longer counted twice in the Quick Context error and warning counts. See `docs/RENDERERS.md`.
- **1.5** (R13-F): added `known_issue_ids`, `health.critical_ids`, `quick_context.critical_finding_ids` and `id` in each entry of `failures`: a stable finding id (`<kind>:<12 hex>`) built from structured fields, never from the sentence. The same condition told by a health critical failure and by a known issue has one id, and Quick Context shows it once (the known issue stays in `known_issues`). `health.critical_failures` no longer repeats one condition twice. See `docs/FINDINGS.md`.
- **1.4** (R13-E): each entry of `todos` gained `category`, and the optional key `todo_categories` was added. The scanner now reports every marker on a line (it used to report the first only), so counts can rise. Only `actionable` markers (TODO or FIXME written as a task) count toward the health score and the `TODO-CLUSTER` risk; BUG, SAFETY, HACK, XXX and a mere mention are discovered and shown but not scored. SARIF marker results carry the category in `properties.category`. See `docs/MARKERS.md`.
- **1.3** (R13-C): added the optional key `advisories`. The wording of `health.critical_failures` for security checks changed: "Security tool reported issues." is replaced by messages that say what the tool reported (a security finding, a dependency policy violation, or a failure without a recognised finding). A check the runner could not execute (timeout, tool not found, operating-system error) is no longer a critical failure and no longer lowers the security category; it appears as an execution-coverage gap. The SARIF `informationUri` is the real repository, and SARIF has one result per advisory with the advisory id as `ruleId`. See `docs/SECURITY_EVIDENCE.md`.
- **1.2** (R13-B): added `health.execution_coverage`, `checks_requested`, `checks_executed`, `coverage_by_group` and `coverage_gaps`; `health.confidence` is deprecated (value unchanged). The Markdown, HTML and text reports, the CLI summary, Quick Context and the risk rule `HEALTH-LOW-CONFIDENCE` now use execution coverage; the rule id keeps its legacy name.
- **1.1** (R13-A): added the optional key `failures`. The wording of `known_issues` changed: the catch-all sentence "Compilation or lint errors were detected." no longer exists, because on a real report it came from `cargo audit` and `cargo deny`, not from a compiler or linter. Scripts that matched that sentence should read `failures[].category` instead. The two older sentences ("One or more source files contain syntax errors." and "A required Python dependency is missing.") are unchanged.
- **1.0**: first documented version.
