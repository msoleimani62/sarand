# sarand report — advisories-project

**Generated:** 2026-01-01 12:00:00  
**Host:** (unknown)  
**Project:** `<PROJECT_ROOT>`  

This report is generated for AI analysis and contains project metadata, test results and source files.

---

## Quick Context

- **Project:** `advisories-project` -- Unknown (unknown); type unknown; build unknown
- **Structure:** 0 files, 0 LOC
- **Tests:** pytest: passed
- **Quality:** cargo clippy: skipped, ruff check: unavailable
- **Security:** cargo audit: failed, cargo deny check: failed
- **Health:** 64.0/100.0 (grade D), execution coverage 60% (3 of 5 requested checks ran to a verdict)
- **Critical findings:**
  - Security finding reported by cargo audit, cargo deny check (a tool result; exploitability is not assessed).
  - Dependency policy violation reported by cargo deny check (licenses, bans or sources); not a vulnerability.
- **Risks:**
  - 2 check(s) failed: cargo audit, cargo deny check
  - 1 check(s) could not run (the runner could not execute the tool), no verdict and no score points: ruff check
  - 1 check(s) skipped, so the score does not reflect them: cargo clippy
  - tools reported 2 error(s) and 3 warning(s)
  - 18 dependency advisory(ies) reported by the tools (tool results; applicability unknown)

## Architecture and Risks

- **Risks (rule-based):**
  - HEALTH-CRITICAL (high): 2 critical failure(s) in the health score; 2 of them restate the failed security check(s) reported by SEC-CHECK-FAILED [health.critical_failures]
  - SEC-CHECK-FAILED (high): 2 of 2 security check(s) failed [security_results[kind=cargo audit]; security_results[kind=cargo deny check]]
  - HEALTH-LOW-CONFIDENCE (warning): execution coverage is 60% (3 of 5 requested checks ran; threshold 80%) [health.execution_coverage]
- **Limitations:**
  - HEALTH-CRITICAL: Covers only the checks that ran.
  - SEC-CHECK-FAILED: A tool result, not a proven vulnerability.
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

**Score:** 64.0 / 100.0  **Grade:** D

**Execution coverage:** 60% (3 of 5 requested checks ran to a verdict)

Not run: cargo clippy (skipped: cargo not installed), ruff check (unavailable: tool_not_found)

Execution coverage counts which requested checks ran to a verdict. It does not measure how complete or correct the analysis is.

| Category | Points |
|----------|--------|
| tests | 25.0 |
| quality | 0.0 |
| security | 5.0 |
| git | 10.0 |
| code | 15.0 |
| tooling | 9.0 |

### Critical failures

- Security finding reported by cargo audit, cargo deny check (a tool result; exploitability is not assessed).
- Dependency policy violation reported by cargo deny check (licenses, bans or sources); not a vulnerability.

### Recommendations

- Quality check could not run (ruff check: tool not found); it gave no verdict and earns no points, so re-run it.
- Review the reported security advisories: whether this project reaches the affected code is not assessed.
- Review the dependency policy violations (licenses, bans, sources).
- 1 check(s) were skipped because their tool is not installed (cargo clippy); the score does not reflect them. See `sarand --doctor` for how to install them.

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

## Quality checks

### cargo clippy [SKIP]

*Skipped:* cargo not installed

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


## Security checks

### cargo audit [FAIL]

```text
Warning:   unsound
Title:     Use-after-free through `init_using_cdict` and `init_using_ddict`
Date:      2026-10-16
ID:        RUSTSEC-2026-0399
URL:       https://rustsec.org/advisories/RUSTSEC-2026-0399

Crate:     zstd-safe
Version:   7.2.4
Warning:   unsound
Title:     Use-after-free when changing a multithreaded context with an unfinished frame
Date:      2026-10-16
ID:        RUSTSEC-2026-0406
URL:       https://rustsec.org/advisories/RUSTSEC-2026-0406

Crate:     zstd-safe
Version:   7.2.4
Warning:   unsound
Title:     Double free in `DCtx::try_clone`
Date:      2026-10-16
ID:        RUSTSEC-2026-0404
URL:       https://rustsec.org/advisories/RUSTSEC-2026-0404

Crate:     zstd-safe
Version:   7.2.4
Warning:   unsound
Title:     `Seekable` reads a NULL or out-of-bounds seek table
Date:      2026-10-16
ID:        RUSTSEC-2026-0396
URL:       https://rustsec.org/advisories/RUSTSEC-2026-0396

Crate:     zstd-safe
Version:   7.2.4
Warning:   unsound
Title:     `OutBuffer::around_pos` exposes uninitialized memory
Date:      2026-10-16
ID:        RUSTSEC-2026-0397
URL:       https://rustsec.org/advisories/RUSTSEC-2026-0397

Crate:     zstd-safe
Version:   7.2.4
Warning:   unsound
Title:     Use-after-free with `CParameter::StableInBuffer`
Date:      2026-10-16
ID:        RUSTSEC-2026-0395
URL:       https://rustsec.org/advisories/RUSTSEC-2026-0395

Crate:     zstd-safe
Version:   7.2.4
Warning:   unsound
Title:     Out-of-bounds read in `train_from_buffer` when sample sizes overflow
Date:      2026-10-16
ID:        RUSTSEC-2026-0401
URL:       https://rustsec.org/advisories/RUSTSEC-2026-0401

Crate:     zstd-safe
Version:   7.2.4
Warning:   unsound
Title:     Heap buffer overflow in `CCtx::try_clone` on a multithreaded context
Date:      2026-10-16
ID:        RUSTSEC-2026-0402
URL:       https://rustsec.org/advisories/RUSTSEC-2026-0402

Crate:     zstd-safe
Version:   7.2.4
Warning:   unsound
Title:     Out-of-bounds read with an out-of-range `InBuffer::pos`
Date:      2026-10-16
ID:        RUSTSEC-2026-0405
URL:       https://rustsec.org/advisories/RUSTSEC-2026-0405

Crate:     zstd-safe
Version:   7.2.4
Warning:   unsound
Title:     Use-after-free of a dictionary after a one-shot call on a context with an open stream
Date:      2026-10-16
ID:        RUSTSEC-2026-0400
URL:       https://rustsec.org/advisories/RUSTSEC-2026-0400

error: 5 vulnerabilities found!
warning: 13 allowed warnings found
```

<details>
<summary>Full output</summary>

```text
    Fetching advisory database from `https://github.com/RustSec/advisory-db.git`
      Loaded 1395 security advisories (from /home/kali/.cargo/advisory-db)
    Updating crates.io index
    Scanning Cargo.lock for vulnerabilities (254 crate dependencies)
Crate:     ctutils
Version:   0.4.2
Title:     Non-constant-time mask generation and `u128` comparisons
Date:      2026-10-23
ID:        RUSTSEC-2026-0385
URL:       https://github.com/RustCrypto/utils/pull/1569
Solution:  Upgrade to >=0.4.4

Crate:     zstd
Version:   0.13.3
Title:     Data from an abandoned stream leaks into the next stream on a reused context
Date:      2026-10-16
ID:        RUSTSEC-2026-0391
URL:       https://rustsec.org/advisories/RUSTSEC-2026-0391
Solution:  Upgrade to >=0.14.3

Crate:     zstd-safe
Version:   7.2.4
Title:     Uninitialized memory exposed when streaming decompression of a legacy frame fails
Date:      2026-10-16
ID:        RUSTSEC-2026-0403
URL:       https://rustsec.org/advisories/RUSTSEC-2026-0403
Solution:  Upgrade to >=8.2.0

Crate:     zstd-safe
Version:   7.2.4
Title:     `Seekable::decompress` sets a `Vec` length beyond its capacity for offsets past the end
Date:      2026-10-16
ID:        RUSTSEC-2026-0398
URL:       https://rustsec.org/advisories/RUSTSEC-2026-0398
Solution:  Upgrade to >=8.2.0

Crate:     zstd-sys
Version:   2.0.16+zstd.1.5.7
Title:     WebAssembly allocator shim corrupts memory on allocation failure
Date:      2026-10-16
ID:        RUSTSEC-2026-0410
URL:       https://rustsec.org/advisories/RUSTSEC-2026-0410
Solution:  Upgrade to >=2.1.2

Crate:     basic-toml
Version:   0.1.10
Warning:   unmaintained
Title:     `basic-toml` is unmaintained
Date:      2026-09-26
ID:        RUSTSEC-2026-0374
URL:       https://rustsec.org/advisories/RUSTSEC-2026-0374

Crate:     number_prefix
Version:   0.4.0
Warning:   unmaintained
Title:     number_prefix crate is unmaintained
Date:      2025-11-17
ID:        RUSTSEC-2025-0119
URL:       https://rustsec.org/advisories/RUSTSEC-2025-0119

Crate:     proc-macro-error
Version:   1.0.4
Warning:   unmaintained
Title:     proc-macro-error is unmaintained
Date:      2024-09-01
ID:        RUSTSEC-2024-0370
URL:       https://rustsec.org/advisories/RUSTSEC-2024-0370

Crate:     zstd-safe
Version:   7.2.4
Warning:   unsound
Title:     Use-after-free through `init_using_cdict` and `init_using_ddict`
Date:      2026-10-16
ID:        RUSTSEC-2026-0399
URL:       https://rustsec.org/advisories/RUSTSEC-2026-0399

Crate:     zstd-safe
Version:   7.2.4
Warning:   unsound
Title:     Use-after-free when changing a multithreaded context with an unfinished frame
Date:      2026-10-16
ID:        RUSTSEC-2026-0406
URL:       https://rustsec.org/advisories/RUSTSEC-2026-0406

Crate:     zstd-safe
Version:   7.2.4
Warning:   unsound
Title:     Double free in `DCtx::try_clone`
Date:      2026-10-16
ID:        RUSTSEC-2026-0404
URL:       https://rustsec.org/advisories/RUSTSEC-2026-0404

Crate:     zstd-safe
Version:   7.2.4
Warning:   unsound
Title:     `Seekable` reads a NULL or out-of-bounds seek table
Date:      2026-10-16
ID:        RUSTSEC-2026-0396
URL:       https://rustsec.org/advisories/RUSTSEC-2026-0396

Crate:     zstd-safe
Version:   7.2.4
Warning:   unsound
Title:     `OutBuffer::around_pos` exposes uninitialized memory
Date:      2026-10-16
ID:        RUSTSEC-2026-0397
URL:       https://rustsec.org/advisories/RUSTSEC-2026-0397

Crate:     zstd-safe
Version:   7.2.4
Warning:   unsound
Title:     Use-after-free with `CParameter::StableInBuffer`
Date:      2026-10-16
ID:        RUSTSEC-2026-0395
URL:       https://rustsec.org/advisories/RUSTSEC-2026-0395

Crate:     zstd-safe
Version:   7.2.4
Warning:   unsound
Title:     Out-of-bounds read in `train_from_buffer` when sample sizes overflow
Date:      2026-10-16
ID:        RUSTSEC-2026-0401
URL:       https://rustsec.org/advisories/RUSTSEC-2026-0401

Crate:     zstd-safe
Version:   7.2.4
Warning:   unsound
Title:     Heap buffer overflow in `CCtx::try_clone` on a multithreaded context
Date:      2026-10-16
ID:        RUSTSEC-2026-0402
URL:       https://rustsec.org/advisories/RUSTSEC-2026-0402

Crate:     zstd-safe
Version:   7.2.4
Warning:   unsound
Title:     Out-of-bounds read with an out-of-range `InBuffer::pos`
Date:      2026-10-16
ID:        RUSTSEC-2026-0405
URL:       https://rustsec.org/advisories/RUSTSEC-2026-0405

Crate:     zstd-safe
Version:   7.2.4
Warning:   unsound
Title:     Use-after-free of a dictionary after a one-shot call on a context with an open stream
Date:      2026-10-16
ID:        RUSTSEC-2026-0400
URL:       https://rustsec.org/advisories/RUSTSEC-2026-0400

error: 5 vulnerabilities found!
warning: 13 allowed warnings found

```

</details>


### cargo deny check [FAIL]

```text
   ├ Announcement: https://github.com/dtolnay/basic-toml/commit/dd2ea1df197f255a402b8990cb852ade3e37ea34
   ├ Solution: No safe upgrade is available!
   ├ basic-toml v0.1.10
     └── i18n-config v0.4.8
         ├── i18n-embed-fl v0.7.0
         │   └── age v0.10.1
         │       └── ramz-backends-age v0.3.2
         │           ├── ramz-cli v0.3.2
         │           └── (dev) ramz-integration-tests v0.3.2
         └── i18n-embed-impl v0.8.4
             └── i18n-embed v0.14.1
                 ├── age v0.10.1 (*)
                 └── i18n-embed-fl v0.7.0 (*)

error[vulnerability]: Non-constant-time mask generation and `u128` comparisons
   ┌─ /home/kali/ramz/Cargo.lock:43:1
   │
43 │ ctutils 0.4.2 registry+https://github.com/rust-lang/crates.io-index
   │ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ security vulnerability detected
   │
   ├ ID: RUSTSEC-2026-0385
   ├ Advisory: https://rustsec.org/advisories/RUSTSEC-2026-0385
   ├ ## Summary
     
     The `ctutils::Choice` type has mask generation functions for each unsigned
     integer size (`u8`, `u16`, `u32`, `u64`, `u128`). These are `const fn` and
     therefore can't reuse the `asm!`-backed mask generation in the `cmov` crate
     that's otherwise used to ensure constant-time.
     
     In releases prior to v0.4.4, the generated code from these functions could
     include a branch on commonly used platforms. This has been corrected in this
     release and now verified on several platforms using BINSEC.
     
     Additionally, `u128` comparison operations provided via `ctutils::Choice` and
     intended to work in constant-time were generating branches on 32-bit targets.
     This has been resolved via a special case implementation of these functions
     for such targets.
     
     ## Impact
     
     Branch instructions on secret values can potentially leak such values via
     covert channels. This can enable attackers to potentially recover such secrets.
     
     ## Resolution
     
     This has been resolved by calling `Choice::to_u8()` when generating the mask,
     which in turn uses `black_box` as an optimization barrier. Verification that
     this resulted in the desired change in the generated assembly across a variety
     of target CPU architectures was performed by BINSEC, which now runs
     automatically in CI using `cargo checkct`.
   ├ Announcement: https://github.com/RustCrypto/utils/pull/1569
   ├ Solution: Upgrade to >=0.4.4 (try `cargo update -p ctutils`)
   ├ ctutils v0.4.2
     ├── hybrid-array v0.4.13
     │   ├── block-buffer v0.12.1
     │   │   └── digest v0.11.3
     │   │       ├── sha2 v0.11.0
     │   │       │   └── rust-embed-utils v8.12.0
     │   │       │       ├── rust-embed v8.12.0
     │   │       │       │   ├── age v0.10.1
     │   │       │       │   │   └── ramz-backends-age v0.3.2
     │   │       │       │   │       ├── ramz-cli v0.3.2
     │   │       │       │   │       └── (dev) ramz-integration-tests v0.3.2
     │   │       │       │   └── i18n-embed v0.14.1
     │   │       │       │       ├── age v0.10.1 (*)
     │   │       │       │       └── i18n-embed-fl v0.7.0
     │   │       │       │           └── age v0.10.1 (*)
     │   │       │       └── rust-embed-impl v8.12.0
     │   │       │           └── rust-embed v8.12.0 (*)
     │   │       └── sha3 v0.11.0
     │   │           └── ml-kem v0.3.2
     │   │               └── ramz-backends-age v0.3.2 (*)
     │   ├── crypto-common v0.2.2
     │   │   ├── digest v0.11.3 (*)
     │   │   └── kem v0.3.0
     │   │       └── ml-kem v0.3.2 (*)
     │   ├── ml-kem v0.3.2 (*)
     │   └── module-lattice v0.2.3
     │       └── ml-kem v0.3.2 (*)
     └── module-lattice v0.2.3 (*)
```

<details>
<summary>Full output</summary>

```text
warning[duplicate]: found 2 duplicate entries for crate 'block-buffer'
   ┌─ /home/kali/ramz/Cargo.lock:22:1
   │  
22 │ ╭ block-buffer 0.10.4 registry+https://github.com/rust-lang/crates.io-index
23 │ │ block-buffer 0.12.1 registry+https://github.com/rust-lang/crates.io-index
   │ ╰─────────────────────────────────────────────────────────────────────────┘ lock entries
   │  
   ├ block-buffer v0.10.4
     └── digest v0.10.7
         ├── blake2 v0.10.6
         │   └── argon2 v0.5.3
         │       └── ramz-backends-age v0.3.2
         │           ├── ramz-cli v0.3.2
         │           └── (dev) ramz-integration-tests v0.3.2
         ├── hmac v0.12.1
         │   ├── age v0.10.1
         │   │   └── ramz-backends-age v0.3.2 (*)
         │   ├── hkdf v0.12.4
         │   │   └── age-core v0.10.0
         │   │       └── age v0.10.1 (*)
         │   └── pbkdf2 v0.12.2
         │       └── scrypt v0.11.0
         │           └── age v0.10.1 (*)
         ├── pbkdf2 v0.12.2 (*)
         └── sha2 v0.10.9
             ├── age v0.10.1 (*)
             ├── age-core v0.10.0 (*)
             ├── ramz-backends-age v0.3.2 (*)
             ├── ramz-core v0.3.2
             │   ├── ramz-backend-7z v0.3.2
             │   │   ├── ramz-cli v0.3.2 (*)
             │   │   └── (dev) ramz-integration-tests v0.3.2 (*)
             │   ├── ramz-backends-age v0.3.2 (*)
             │   ├── ramz-cli v0.3.2 (*)
             │   └── (dev) ramz-integration-tests v0.3.2 (*)
             └── scrypt v0.11.0 (*)
   ├ block-buffer v0.12.1
     └── digest v0.11.3
         ├── sha2 v0.11.0
         │   └── rust-embed-utils v8.12.0
         │       ├── rust-embed v8.12.0
         │       │   ├── age v0.10.1
         │       │   │   └── ramz-backends-age v0.3.2
         │       │   │       ├── ramz-cli v0.3.2
         │       │   │       └── (dev) ramz-integration-tests v0.3.2
         │       │   └── i18n-embed v0.14.1
         │       │       ├── age v0.10.1 (*)
         │       │       └── i18n-embed-fl v0.7.0
         │       │           └── age v0.10.1 (*)
         │       └── rust-embed-impl v8.12.0
         │           └── rust-embed v8.12.0 (*)
         └── sha3 v0.11.0
             └── ml-kem v0.3.2
                 └── ramz-backends-age v0.3.2 (*)

error[rejected]: failed to satisfy license requirements
   ┌─ /home/kali/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f/option-ext-0.2.0/Cargo.toml:21:12
   │
21 │ license = "MPL-2.0"
   │            ━━━━━━━
   │            │
   │            rejected: license is not explicitly allowed
   │
   ├ MPL-2.0 - Mozilla Public License 2.0:
   ├   - OSI approved
   ├   - FSF Free/Libre
   ├   - Copyleft
   ├ option-ext v0.2.0
     └── dirs-sys v0.4.1
         └── dirs v5.0.1
             └── ramz-cli v0.3.2

warning[license-not-encountered]: license was not encountered
  ┌─ /home/kali/ramz/deny.toml:2:48
  │
2 │ allow = ["MIT", "Apache-2.0", "BSD-3-Clause", "ISC", "Unicode-DFS-2016"]
  │                                                ━━━ unmatched license allowance

error[unmaintained]: `basic-toml` is unmaintained
   ┌─ /home/kali/ramz/Cargo.lock:16:1
   │
16 │ basic-toml 0.1.10 registry+https://github.com/rust-lang/crates.io-index
   │ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ unmaintained advisory detected
   │
   ├ ID: RUSTSEC-2026-0374
   ├ Advisory: https://rustsec.org/advisories/RUSTSEC-2026-0374
   ├ The last release was on March 3, 2025, the day after the repository was archived and marked as unmaintained.
     
     ## Possible alternatives
     
     - [toml](https://crates.io/crates/toml)
   ├ Announcement: https://github.com/dtolnay/basic-toml/commit/dd2ea1df197f255a402b8990cb852ade3e37ea34
   ├ Solution: No safe upgrade is available!
   ├ basic-toml v0.1.10
     └── i18n-config v0.4.8
         ├── i18n-embed-fl v0.7.0
         │   └── age v0.10.1
         │       └── ramz-backends-age v0.3.2
         │           ├── ramz-cli v0.3.2
         │           └── (dev) ramz-integration-tests v0.3.2
         └── i18n-embed-impl v0.8.4
             └── i18n-embed v0.14.1
                 ├── age v0.10.1 (*)
                 └── i18n-embed-fl v0.7.0 (*)

error[vulnerability]: Non-constant-time mask generation and `u128` comparisons
   ┌─ /home/kali/ramz/Cargo.lock:43:1
   │
43 │ ctutils 0.4.2 registry+https://github.com/rust-lang/crates.io-index
   │ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ security vulnerability detected
   │
   ├ ID: RUSTSEC-2026-0385
   ├ Advisory: https://rustsec.org/advisories/RUSTSEC-2026-0385
   ├ ## Summary
     
     The `ctutils::Choice` type has mask generation functions for each unsigned
     integer size (`u8`, `u16`, `u32`, `u64`, `u128`). These are `const fn` and
     therefore can't reuse the `asm!`-backed mask generation in the `cmov` crate
     that's otherwise used to ensure constant-time.
     
     In releases prior to v0.4.4, the generated code from these functions could
     include a branch on commonly used platforms. This has been corrected in this
     release and now verified on several platforms using BINSEC.
     
     Additionally, `u128` comparison operations provided via `ctutils::Choice` and
     intended to work in constant-time were generating branches on 32-bit targets.
     This has been resolved via a special case implementation of these functions
     for such targets.
     
     ## Impact
     
     Branch instructions on secret values can potentially leak such values via
     covert channels. This can enable attackers to potentially recover such secrets.
     
     ## Resolution
     
     This has been resolved by calling `Choice::to_u8()` when generating the mask,
     which in turn uses `black_box` as an optimization barrier. Verification that
     this resulted in the desired change in the generated assembly across a variety
     of target CPU architectures was performed by BINSEC, which now runs
     automatically in CI using `cargo checkct`.
   ├ Announcement: https://github.com/RustCrypto/utils/pull/1569
   ├ Solution: Upgrade to >=0.4.4 (try `cargo update -p ctutils`)
   ├ ctutils v0.4.2
     ├── hybrid-array v0.4.13
     │   ├── block-buffer v0.12.1
     │   │   └── digest v0.11.3
     │   │       ├── sha2 v0.11.0
     │   │       │   └── rust-embed-utils v8.12.0
     │   │       │       ├── rust-embed v8.12.0
     │   │       │       │   ├── age v0.10.1
     │   │       │       │   │   └── ramz-backends-age v0.3.2
     │   │       │       │   │       ├── ramz-cli v0.3.2
     │   │       │       │   │       └── (dev) ramz-integration-tests v0.3.2
     │   │       │       │   └── i18n-embed v0.14.1
     │   │       │       │       ├── age v0.10.1 (*)
     │   │       │       │       └── i18n-embed-fl v0.7.0
     │   │       │       │           └── age v0.10.1 (*)
     │   │       │       └── rust-embed-impl v8.12.0
     │   │       │           └── rust-embed v8.12.0 (*)
     │   │       └── sha3 v0.11.0
     │   │           └── ml-kem v0.3.2
     │   │               └── ramz-backends-age v0.3.2 (*)
     │   ├── crypto-common v0.2.2
     │   │   ├── digest v0.11.3 (*)
     │   │   └── kem v0.3.0
     │   │       └── ml-kem v0.3.2 (*)
     │   ├── ml-kem v0.3.2 (*)
     │   └── module-lattice v0.2.3
     │       └── ml-kem v0.3.2 (*)
     └── module-lattice v0.2.3 (*)

```

</details>


## Known issues

- Security findings were reported by: cargo audit, cargo deny check. These are tool results, not proof that the project is exploitable.
- Dependency policy checks failed in: cargo deny check (licenses, bans or sources). This is not a vulnerability.

## Failure classification

| Tool | Group | Category | Cause | Subject | Evidence | Id |
|---|---|---|---|---|---|---|
| ruff check | quality | `unknown_tool_failure` | tool_not_found | Python source | tool_not_found | `unknown_tool_failure:046173f351ac` |
| cargo audit | security | `security_finding_detected` | exit_code | Rust dependency advisories | advisory-reported | `security_finding_detected:24c9d7d1c316` |
| cargo deny check | security | `security_finding_detected` | exit_code | dependency advisories | cargo-deny:unmaintained, cargo-deny:vulnerability | `security_finding_detected:b950cb59ff4a` |
| cargo deny check | security | `dependency_policy_failure` | exit_code | dependency licenses, bans and sources | cargo-deny:rejected | `dependency_policy_failure:1ef0aa19fe5d` |

## Dependency advisories

18 advisory(ies) reported by the security tools. These are tool results, not proof that this project is exploitable: no reachability analysis was done, so applicability is unknown for every row. Severity is shown only when the tool printed one.

Database: https://github.com/RustSec/advisory-db.git (1395 advisories loaded)

| ID | Package | Version | Kind | Severity | Fixed in | Reported by | Applicability |
|---|---|---|---|---|---|---|---|
| RUSTSEC-2026-0385 | ctutils | 0.4.2 | vulnerability | - | >=0.4.4 | cargo audit, cargo deny check | unknown |
| RUSTSEC-2026-0391 | zstd | 0.13.3 | vulnerability | - | >=0.14.3 | cargo audit | unknown |
| RUSTSEC-2026-0398 | zstd-safe | 7.2.4 | vulnerability | - | >=8.2.0 | cargo audit | unknown |
| RUSTSEC-2026-0403 | zstd-safe | 7.2.4 | vulnerability | - | >=8.2.0 | cargo audit | unknown |
| RUSTSEC-2026-0410 | zstd-sys | 2.0.16+zstd.1.5.7 | vulnerability | - | >=2.1.2 | cargo audit | unknown |
| RUSTSEC-2026-0395 | zstd-safe | 7.2.4 | unsound | - | - | cargo audit | unknown |
| RUSTSEC-2026-0396 | zstd-safe | 7.2.4 | unsound | - | - | cargo audit | unknown |
| RUSTSEC-2026-0397 | zstd-safe | 7.2.4 | unsound | - | - | cargo audit | unknown |
| RUSTSEC-2026-0399 | zstd-safe | 7.2.4 | unsound | - | - | cargo audit | unknown |
| RUSTSEC-2026-0400 | zstd-safe | 7.2.4 | unsound | - | - | cargo audit | unknown |
| RUSTSEC-2026-0401 | zstd-safe | 7.2.4 | unsound | - | - | cargo audit | unknown |
| RUSTSEC-2026-0402 | zstd-safe | 7.2.4 | unsound | - | - | cargo audit | unknown |
| RUSTSEC-2026-0404 | zstd-safe | 7.2.4 | unsound | - | - | cargo audit | unknown |
| RUSTSEC-2026-0405 | zstd-safe | 7.2.4 | unsound | - | - | cargo audit | unknown |
| RUSTSEC-2026-0406 | zstd-safe | 7.2.4 | unsound | - | - | cargo audit | unknown |
| RUSTSEC-2024-0370 | proc-macro-error | 1.0.4 | unmaintained | - | - | cargo audit | unknown |
| RUSTSEC-2025-0119 | number_prefix | 0.4.0 | unmaintained | - | - | cargo audit | unknown |
| RUSTSEC-2026-0374 | basic-toml | 0.1.10 | unmaintained | - | - | cargo audit, cargo deny check | unknown |

## Warnings detected

- **cargo audit**: `warning: 13 allowed warnings found`
- **cargo deny check**: `warning[duplicate]: found 2 duplicate entries for crate 'block-buffer'`
- **cargo deny check**: `warning[license-not-encountered]: license was not encountered`

## Errors detected

- **cargo audit**: `error: 5 vulnerabilities found!`
- **cargo deny check**: `error[rejected]: failed to satisfy license requirements`

15 tool line(s) that restate a dependency advisory are listed under Dependency advisories, not here.

## Project tree

```text
advisories-project/
(empty)
```

## Included files (0 included / 0 skipped / 0 excluded for secret safety)
