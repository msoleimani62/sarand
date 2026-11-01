# The JSON report schema

`sarand --format json` writes one JSON object. This page lists every top-level key, the fields of its nested objects, and what a script may rely on. The current version is below; a test keeps this page and the code in step, so a key that exists but is not listed here fails the build.

Current version: **1.0**

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
| `todos` | array | always | TODO-style markers, each with `path`, `line_number`, `kind` and `content`. |
| `test_results` | array | always | Results of test runs (result objects, fields below). Empty when tests were skipped. |
| `quality_results` | array | always | Results of linters and type checkers (result objects). |
| `security_results` | array | always | Results of security tools (result objects). |
| `health` | object or null | always | The health score (fields below); `null` with `--no-health`. |
| `known_issues` | array of strings | always | Problems the scan itself noticed. |
| `ai_summary` | string | always | A plain-language summary meant for an AI reader. |
| `suggested_reading_order` | array of strings | always | Every included file, most important first. Quick Context shows the first ten. |
| `included_files` | array of strings | always | Project-relative paths whose content may be shown. |
| `skipped_files` | array of pairs | always | `[path, reason]` for files that were left out. |
| `excluded_secret_files` | array of strings | always | Paths left out because they look like, or contain, credentials. Only paths, never content. |
| `secret_findings` | array | always | Secret-pattern matches: `path`, `line_number`, `pattern_name`, `is_test_fixture`. Never the matched value. |
| `todos_suppressed` | integer | only when some markers were suppressed | How many markers an exception removed. |
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

- **`quick_context`**: `project`, `primary_language`, `languages`, `project_type`, `build_system`, `components`, `frameworks_declared`, `frameworks_declared_total`, `structure`, `total_files`, `total_loc`, `tests`, `quality`, `security`, `health`, `critical_findings`, `risks`, `reading_order`. `frameworks_declared` holds at most 8 entries of `{name, label, scope, manifest}`; `frameworks_declared_total` is the real count.
- **`architecture`**: `components`, `workspaces`, `entry_points`, `compose`, `kubernetes`. Five lists of short plain-text lines.
- **`risks`**: `risks`, `rules_not_evaluated`. `risks` is a list of `{rule_id, category, severity, evidence_refs, reason, limitations}`, `severity` is `high`, `warning` or `info`; `rules_not_evaluated` lists the rule ids whose data was absent.
- **`relevant_source`**: `budget`, `text`, `files`, `omitted_files`, `omitted_snippets`, `withheld_lines`, `unreadable_files`. `budget` is `{tokens, bytes_cap, bytes_used, bytes_per_token, wrapper_bytes}`; `files` is an index of `{path, why, score, same_as, snippets}`, not a second copy of the code.
- **`detection`**: `languages`, `primary_language`, `project_type`, `build_system`, `markers_found`, `entry_points`, `details`.
- **`environment`**: `python`, `rust_core`, `os_name`, `architecture`, `cpu_summary`, `memory_summary`, `disk_free`, `hostname`, `tool_versions`.
- **`git`**: `branch`, `commit`, `status`, `log`, `diff`, `dirty`, `ahead`, `behind`, `tags`, `stashes`, `untracked`.
- **`stats`**: `total_files`, `total_loc`, `code_lines`, `comment_lines`, `blank_lines`, `files_by_extension`, `largest_directories`, `largest_files`, `duplicate_files`, `broken_symlinks`, `temporary_files`, `unused_cache_files`, `empty_files`, `executable_scripts`, `hidden_files`, `binary_files`. `largest_files` is a list of `[path, bytes]`; `duplicate_files` is a list of `[hash, [paths]]`.
- **`health`**: `score`, `max_score`, `grade`, `breakdown`, `recommendations`, `critical_failures`, `checks_run`, `checks_skipped`, `confidence`, `checks_inconclusive`. `confidence` is between 0 and 1 and says how many checks ran, not how good the code is.
- **`result`**: `kind`, `returncode`, `summary`, `raw_output`, `warnings`, `errors`, `duration_seconds`, `skipped`, `skip_reason`, `inconclusive_reason`. The object inside `test_results`, `quality_results` and `security_results`. `inconclusive_reason` appears only when set.
- **`kubernetes`**: `helm_charts`, `kustomize_overlays`, and, only when raw manifests were found, `manifests` and `total_manifest_files`.
