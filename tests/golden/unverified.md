# sarand report — unverified-project

**Generated:** 2026-01-01 12:00:00  
**Host:** (unknown)  
**Project:** `<PROJECT_ROOT>`  

This report is generated for AI analysis and contains project metadata, test results and source files.

---

## Quick Context

- **Project:** `unverified-project` -- Unknown (unknown); type unknown; build unknown
- **Structure:** 0 files, 0 LOC
- **Tests:** pytest: passed, cargo test: unavailable
- **Quality:** ruff check: unavailable, mypy: passed
- **Security:** pip-audit: passed, cargo audit: unavailable
- **Health:** 63.0/100.0 (grade D), execution coverage 50% (3 of 6 requested checks ran to a verdict)
- **Critical findings:**
  - Test check could not run (cargo test); it gave no verdict and earns no points.
- **Risks:**
  - 3 check(s) could not run (the runner could not execute the tool), no verdict and no score points: cargo test, ruff check, cargo audit

## Architecture and Risks

- **Risks (rule-based):**
  - HEALTH-CRITICAL (high): 1 critical failure(s) in the health score [health.critical_failures]
  - CHECKS-SKIPPED (warning): 3 of 6 checks gave no verdict (3 unavailable; threshold 3) [test_results[kind=cargo test]; quality_results[kind=ruff check]; security_results[kind=cargo audit]]
  - HEALTH-LOW-CONFIDENCE (warning): execution coverage is 50% (3 of 6 requested checks ran; threshold 80%) [health.execution_coverage]
- **Limitations:**
  - HEALTH-CRITICAL: Covers only the checks that ran.
  - CHECKS-SKIPPED: Skipped means not run, not failed.
  - HEALTH-LOW-CONFIDENCE: Coverage says which requested checks ran, not how correct the analysis is. The rule id keeps its legacy name; it evaluates execution coverage.
- **Rules not evaluated (5 of 9, data absent):** DUPLICATE-FILES, GIT-STATE, LARGE-FILE, SECRET-PATTERNS, TODO-CLUSTER

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

**Score:** 63.0 / 100.0  **Grade:** D

**Execution coverage:** 50% (3 of 6 requested checks ran to a verdict)

Not run: cargo test (unavailable: timeout), ruff check (unavailable: tool_not_found), cargo audit (unavailable: timeout)

Execution coverage counts which requested checks ran to a verdict. It does not measure how complete or correct the analysis is.

| Category | Points |
|----------|--------|
| tests | 12.5 |
| quality | 10.0 |
| security | 8.0 |
| git | 10.0 |
| code | 15.0 |
| tooling | 7.5 |

### Critical failures

- Test check could not run (cargo test); it gave no verdict and earns no points.

### Recommendations

- Test check could not run (cargo test: timed out); it gave no verdict and earns no points, so re-run it.
- Quality check could not run (ruff check: tool not found); it gave no verdict and earns no points, so re-run it.
- Security check could not run (cargo audit: timed out); it gave no verdict and earns no points, so re-run it.

## Project statistics

- Total files: **0**
- By extension: n/a
- LOC: **0** (code 0 / comment 0 / blank 0)
- Binary files: 0 · Hidden files: 0
- Empty files: 0 · Broken symlinks: 0
- Temporary files: 0 · Cache-like: 0

## Test results

### pytest [PASS]

```text
3 passed
```

### cargo test [UNAVAILABLE]

*Unavailable:* the runner could not run this tool (timeout); it gave no verdict.

```text
Command timed out.
```

<details>
<summary>Full output</summary>

```text
Command timed out.
```

</details>


## Quality checks

### ruff check [UNAVAILABLE]

*Unavailable:* the runner could not run this tool (tool_not_found); it gave no verdict.

```text
Command not found: ruff
```

<details>
<summary>Full output</summary>

```text
Command not found: ruff
```

</details>


### mypy [PASS]

```text
Success
```

## Security checks

### pip-audit [PASS]

```text
No known vulnerabilities
```

### cargo audit [UNAVAILABLE]

*Unavailable:* the runner could not run this tool (timeout); it gave no verdict.

```text
Command timed out.
```

<details>
<summary>Full output</summary>

```text
Command timed out.
```

</details>


## Warnings detected

None detected.

## Errors detected

None detected.

## Project tree

```text
unverified-project/
(empty)
```

## Included files (0 included / 0 skipped / 0 excluded for secret safety)
