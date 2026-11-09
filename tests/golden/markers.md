# sarand report — markers-project

**Generated:** 2026-01-01 12:00:00  
**Host:** (unknown)  
**Project:** `<PROJECT_ROOT>`  

This report is generated for AI analysis and contains project metadata, test results and source files.

---

## Quick Context

- **Project:** `markers-project` -- Unknown (unknown); type unknown; build unknown
- **Structure:** 3 files, 0 LOC
- **Tests:** none run
- **Quality:** none run
- **Security:** none run
- **Health:** 43.0/100.0 (grade F), execution coverage not available (no check was requested)
- **Critical findings:** none recorded
- **Risks:** none identified

## Architecture and Risks

- **Risks (rule-based):** none identified
- **Rules not evaluated (4 of 9, data absent):** CHECKS-SKIPPED, GIT-STATE, HEALTH-LOW-CONFIDENCE, SEC-CHECK-FAILED

## Detected Project

No recognized project marker was found in this directory.

---

## Environment

| Fact | Value |
|------|-------|
| Python | (unavailable) |
| Rust core | (unavailable) |
| OS | (unknown) |
| Architecture | (unknown) |
| CPU | (unknown) |
| Memory | (unknown) |
| Disk | (unknown) |
| Hostname | (unknown) |

## Git

- **Branch:** (unavailable)
- **Commit:** (unavailable)
- **Dirty:** False
- **Ahead / Behind:** 0 / 0

### Status
```text
(clean)
```

### Recent commits
```text
(none)
```

## Health Score

**Score:** 43.0 / 100.0  **Grade:** F

**Execution coverage:** not available (no check was requested)

Execution coverage counts which requested checks ran to a verdict. It does not measure how complete or correct the analysis is.

| Category | Points |
|----------|--------|
| tests | 5.0 |
| quality | 5.0 |
| security | 8.0 |
| git | 10.0 |
| code | 15.0 |
| tooling | 0.0 |

### Recommendations

- Add automated tests, or make sure your test runner is installed.
- Run quality checks with --quality.
- Consider enabling --security for dependency audits.

## Project statistics

- Total files: **3**
- By extension: n/a
- LOC: **0** (code 0 / comment 0 / blank 0)
- Binary files: 0 · Hidden files: 0
- Empty files: 0 · Broken symlinks: 0
- Temporary files: 0 · Cache-like: 0

## TODO / FIXME markers

Found 2 actionable, 1 historical, 1 safety, 1 development, 1 mention. Only `actionable` markers (TODO / FIXME written as a task) count toward the health score and the `TODO-CLUSTER` risk; the others are shown for review, not scored.

| File | Line | Kind | Category | Content |
|------|------|------|----------|---------|
| `app/core.py` | 12 | TODO | actionable | `x = load()  # TODO(ana): cache this  # BUG: see #12` |
| `app/core.py` | 12 | BUG | historical | `x = load()  # TODO(ana): cache this  # BUG: see #12` |
| `app/core.py` | 40 | FIXME | actionable | `# FIXME - handle the empty file` |
| `app/unsafe.rs` | 7 | SAFETY | safety | `// SAFETY: the pointer comes from a live Box` |
| `app/util.py` | 3 | HACK | development | `# HACK: sleep until the socket is ready` |
| `README_helper.py` | 1 | TODO | mention | `"""The TODO scanner reads TODO-style markers."""` |

*2 marker(s) suppressed by the TODO exclusions (golden/fixture directories, Markdown prose, `[todo] exclude_globs`).*

## Test results

No tests executed.

## Warnings detected

None detected.

## Errors detected

None detected.

## Project tree

```text
markers-project/
(empty)
```

## Included files (0 included / 0 skipped / 0 excluded for secret safety)
