# Audit remediation: deterministic scanning and safe report delivery

This document records the implementation contract for H-01 through H-05.
It describes the supported behavior, not a claim that every platform-specific
edge case has been proven by the local environment.

## H-01 — deterministic hash selection

Both scan engines select hash candidates by normalized project-relative POSIX
path order. A candidate must be a regular, non-symlink, non-binary file with a
non-zero size no greater than `hash_max_bytes`. The first `max_hash_files`
eligible paths are selected before hashing. Rust hashes the selected set in
parallel; the Python fallback hashes the same selected set in its deterministic
ordered pass. A failed hash attempt still consumes one slot in the cap.

The contract is about the selected path set, not the order in which hashing
finishes. File records remain ordered by the same normalized path order.

## H-02 — output-name and destination validation

`output_name` is one portable filename component. Empty names, `.` / `..`,
separators, drive-qualified or absolute paths, control characters, Windows
alternate-stream syntax, and non-portable trailing dot/space names are rejected.

Before writing, both the report destination and its `.sha256` companion are
resolved relative to the configured output directory. A destination symlink
is rejected, as is any resolved path outside that directory. The configured
output directory itself may be a symlink; its resolved directory is the
effective destination.

This is path validation, not a sandbox against a hostile process concurrently
renaming writable parent directories. The output directory remains part of
the caller's trusted filesystem boundary.

## H-03 — staged report replacement

A report is rendered to a temporary file in the destination directory. The
completed file is fsynced and hashed incrementally; its checksum is staged
before the live report is replaced. `os.replace` commits the report and then
the checksum. If checksum replacement fails in-process, the previous report
is restored from a same-directory backup (or the newly created report is
removed when no previous report existed). If rollback itself fails, the
backup is preserved and its path is included in the raised error so that
manual recovery remains possible. Renderer and staging failures leave the
previous report and checksum untouched. Temporary files are cleaned up,
except for a backup deliberately retained after failed rollback.

New report and checksum files take the permission bits of the report they
replace; when there is none they get the process default (`0666` minus the
umask). `tempfile.mkstemp` alone would make them private (`0600`), which would
silently change who can read a report that used to be written with `write_text`.

The report and checksum are two filesystem entries. Their two renames cannot
be made a single portable atomic operation. A sudden process or machine crash
between the report rename and checksum rename can leave a detectable checksum
mismatch; this implementation does not claim crash-atomic pair replacement.
The checksum is a consistency signal, not a transactional manifest.

Only an explicit PDF rendering failure (`RenderOutcome(ok=False)`) triggers
the Markdown fallback. Failures during report commit or rollback propagate
instead of being misclassified as recoverable PDF rendering failures. If
rollback fails, the previous PDF backup is retained for manual recovery.

## H-04 — one release-gate definition

The required pre-release workflow set is explicit in
`scripts/release.py::REQUIRED_CI_WORKFLOWS`; it currently contains only `CI`.
Optional workflows do not silently become release blockers. For each required
workflow, only the newest run (ordered by GitHub `databaseId` and then `attempt`) for the exact target
SHA decides. It must be completed with conclusion `success`. A missing run,
pending run, malformed response, API error, or any other conclusion fails
closed.

The local release helper and `.github/workflows/release.yml` use the same
newest-run rule. A previous successful run cannot mask a newer failed,
cancelled, or in-progress run.

## H-05 — scanner ignore behavior

The Rust walker uses the `ignore` crate with `.ignore` files, `.gitignore`
files, `.git/info/exclude` and parent ignore files enabled, and the user's
global Git excludes disabled (`git_global(false)`).
The Python fallback uses `pathspec.GitIgnoreSpec` to apply the same local
sources: ancestor and nested `.gitignore` files, ancestor and nested `.ignore`
files, and the repository's `info/exclude`. `.ignore` rules take precedence
over `.gitignore`; deeper rules take precedence within each source class.
Global user ignore files remain disabled. `IGNORE_DIRS` remains an independent
directory-name pruning rule.

The Python and Rust test suites cover direct patterns, wildcards, negation, directory pruning,
nested and parent rules, repository excludes, no-repository operation, and
the absence of global-ignore leakage. They are representative contract
fixtures, not a proof of equivalence for every possible ignore-file edge case.
The Rust tests must still be run with the project's pinned Rust toolchain.

## Known differences, deferred

- A hash read that fails is reported as a scan problem by the Python fallback
  (`<path>: <reason>`); the Rust core returns no hash and records no problem. The
  selected set and the quota rule are the same in both. Not a correctness issue
  for selection; recorded so that nobody expects identical `problems` lists.
- `release.py` raises `TypeError` for a non-dictionary row from `gh run list`
  and `RuntimeError` for every other malformed row; `require_green_ci` catches
  only `RuntimeError`, so the first case ends with a traceback instead of
  "Cannot verify CI". Both fail closed. The test that pins the `TypeError`
  would change with it.
- The release gate rule exists twice (`scripts/release.py` and an embedded
  script in `release.yml`); tests pin both to the same cases. One shared
  implementation would remove the duplication.
- A report name close to the filesystem limit (255 bytes) can overflow once the
  staging prefix and suffix are added; it fails with an `OSError`.

## Verification

Recorded for commit `1e9e59a` (the maintainer's validation on 2026-11-22):

| Check | Result |
|---|---|
| Full Python suite | 1,882 passed, 10 skipped |
| `mypy` | no issues in 307 source files |
| `ruff check`, `ruff format` | passed, 364 files formatted |
| `cargo test` | 32 passed (includes the walker tests for deterministic hash selection and for global-ignore isolation) |
| `cargo clippy` | passed |
| Markdown lint, `git diff --check` | passed |
| Exact-commit CI | run `44991819799`: success |

The review that followed (report-file permissions, install notes, comments) was
validated at commit `2ce40a4`: 1,884 passed and 10 skipped, `mypy` clean, `ruff`
clean, `cargo fmt --check`, `cargo test` (32 passed) and `cargo clippy` clean, and
CI run `45024003488` green.

CI builds the release wheel, installs it and runs the full Python suite against
the compiled core, so the Rust/Python parity tests (skipped without a compiled
core) run there. A separate local `maturin develop --release` run is not part of
this record.

## Traceability

| Finding | Code | Tests | Acceptance criterion |
|---|---|---|---|
| H-01 | `src/walker.rs`, `rust_bridge._pure_python_scan` | `tests/test_scan_parity.py`, `src/walker_tests.rs` | the hashed set does not depend on thread timing or listing order: met |
| H-02 | `config.validate_output_name`, `config.resolve_report_path`, `cli._output_name_argument` | `tests/test_config.py` | no name or resolved path can write outside the output directory: met |
| H-03 | `cli.atomic_write_report` | `tests/test_report_replacement.py`, `tests/test_pdf_pipeline.py` | a failed new report keeps the previous one; the pair is consistent after in-process failures: met (permissions added in review) |
| H-04 | `scripts/release.py`, `.github/workflows/release.yml` | `tests/test_release_ci_gate.py`, `tests/test_release_workflow.py` | script and workflow give the same verdict for the same runs: met |
| H-05 | `rust_bridge` ignore helpers, `src/walker.rs` | `tests/test_scan_parity.py` (including cases checked against `git`), `src/walker_tests.rs` | the two engines agree within the documented ignore contract: met |
