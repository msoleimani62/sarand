# Frozen Ramz v0.3.2 tool outputs (R13 test fixtures)

These files are real tool output, copied unchanged from a Sarand report of the
Ramz project (tag v0.3.2, commit 7252b1ca8fea9dc59ebfa082998d0da307cb4eb1, with
a local Cargo.lock modification), produced on 2026-11-01 by Sarand 160c589. They
are fixtures for `tests/test_failures.py`; they are not scanned for meaning.

- `cargo_audit.txt` -- whole output of `cargo audit` (exit code 1, 5 advisories)
- `cargo_deny_excerpt.txt` -- the first diagnostic of each kind from `cargo deny
  check` (exit code 5); the full output is 70 KB
- `actionlint.txt`, `yamllint.txt` -- whole output (exit code 1)
- `markdownlint_excerpt.txt` -- the first 12 lines of `markdownlint` (exit code 1)

The full evidence bundle (hashes, provenance) is described in the R13 completion
report.
