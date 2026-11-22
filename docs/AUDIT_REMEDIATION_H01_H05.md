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

The Rust walker uses the `ignore` crate with `.ignore`, `.gitignore`,
`.git/info/exclude`, parent ignore files, and global Git excludes disabled.
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

## Verification boundary

Python unit and integration tests can be run independently of the Rust
extension. Rust source changes require `cargo test` and
`maturin develop --release` on a maintainer environment, followed by a
compiled-core parity run. If those commands have not been run, Rust changes
must be reported as **Not verified locally** rather than treated as accepted.
