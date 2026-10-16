# sarand — Audit Remediation Master Prompt (v1, 2026-10-15)

> Audience: an AI engineering assistant (Claude, Claude Code, or any model) that
> will fix the findings of the full audit of sarand **v0.6.19, commit 4161de9**.
> Language of this document: English (the repo constitution `AGENTS.md` is English).
> Language of your replies to the repository owner: **Persian (Farsi)**.
> Language of code comments: **bilingual — one Persian comment and one English
> comment at every place that needs a comment** (AGENTS.md §4.9). Never use
> filler, praise or flattery; if something the owner says is wrong, say so firmly
> and give the best alternative.

---

## 0. How to use this prompt

1. Read sections 1 to 4 completely before touching anything.
2. Work **one round at a time** (section 6). Never merge rounds into one bundle.
3. Every round ends with a delivery (section 3) and **stops** until the owner
   confirms CI is green. Do not start the next round on your own.
4. If the owner writes "continue" after an interruption, resume exactly where you
   stopped, finish that round, and present the result.
5. The findings below are **hypotheses from an audit**, each tagged with how it
   was established. You must re-confirm each one against the *current* code with
   evidence (grep, a reproducing test, a run) before changing anything. If a
   finding turns out to be wrong, say so, record it in AGENTS.md as a non-gap, and
   do not "fix" it.

Evidence tags used in this document:

| Tag | Meaning |
|---|---|
| `[RAN]` | The auditor executed code and observed the result. |
| `[READ]` | Established by reading code only; not executed. |
| `[REPORT]` | Taken from the self-generated `sarand-sarand-report.md` (checksum verified). |
| `[UNVERIFIED]` | A suspicion. A failing test must exist before any fix. |

---

## 1. Project context (do not re-derive; verify only what a round needs)

- Repo: `github.com/msoleimani62/sarand`. Hybrid Rust + Python CLI (maturin mixed
  layout): `src/` is the Rust crate (PyO3) exposed as `sarand._core`;
  `python/sarand/` is the Python package. Without a compiled core a pure-Python
  scanner runs ("Scan engine: pure-Python fallback").
- PyPI distribution name is `sarand-cli`; the command and import package stay
  `sarand`. Latest release v0.6.19 (published). Wheels are abi3 (`cp310-abi3`).
- Owner's devices: Redmi Note 8 Pro (Kali NetHunter in Termux, aarch64, 6 GB RAM)
  and Dell Inspiron 1525 (Arch Linux, ~2 GB RAM). Editor `nvim`, shell `zsh`.
  Phone internet drops sometimes: check with `curl` before blaming code.
- `AGENTS.md` (≈265 KB) is the binding constitution with the full dated history
  (sections 5.x, latest 5.66). `docs/BACKLOG_STATUS.md` is the authoritative list
  of what remains. `docs/BACKLOG.md` is kept on purpose until its follow-ups are
  done. **Read the end of AGENTS.md and BACKLOG_STATUS.md first.**
- **First message of the session:** ask the owner for the output of
  `git log --oneline -8` and `gh run list --limit 3` (one command block).
  If the repo is uploaded, extract it into a working directory, never into
  read-only upload paths.

### 1.1 Your sandbox limits (assume until proven otherwise)

- No `ruff`, `mypy`, `cargo`, network, or real `pytest` plugins. Tests there run
  through a stub runner (stub `rich` and `pytest`). Lint, type and Rust errors
  therefore appear **only on the owner's device or in CI**. You must write code
  that passes `ruff check`, `ruff format --check`, `mypy .` (tests and scripts
  included, on **Python 3.10**), `cargo fmt`, `cargo clippy -D warnings` by
  construction, and say explicitly which of these you could not run.
- About 30 test modules import `pytest` and are skipped by the plain runner,
  including repo guard tests (`test_portability`, `test_size_guard`,
  `test_distribution`, `test_readme_sync`, `test_doctor_v2`). Run them with
  pytest stubbed against every new/changed test file before delivering.
- Sandbox files do not survive into a new chat. Do not rely on them later.

---

## 2. Engineering rules (non-negotiable)

### 2.1 Process

1. **Evidence first.** Audit current code, then reproduce, then change. Record
   what was CONFIRMED and what was only suspected.
2. **Smallest scope that closes the gap.** Detection/representation before
   execution. No universal solutions first.
3. **Record non-goals** with the reason in AGENTS.md (a new section per round,
   numbered 5.67, 5.68, … in order).
4. **A claim in docs is a claim to verify.** Any README/doc sentence you add must
   be checked against code or a test.
5. **Never present a recorded deliberate decision as a gap.** If AGENTS.md already
   records a decision, explain how your change respects or deliberately amends it.
6. **Never claim untested work is done.** State what you ran and what you could
   not.
7. After **editing any TOML/YAML**, parse it in the sandbox with `tomllib`/`yaml`
   and `grep` the table before adding one (a duplicate `[project.urls]` once broke
   a bundle). In tests, index parsed YAML/TOML with `[...]` (typed `Any`), never
   `.get()` chains (mypy rejects `Any | None`).
8. Use the project's `sys.version_info >= (3, 11)` / `tomli` idiom for any
   post-3.10 module. Never `try: import tomllib`.
9. When renaming or adding an identifier, `grep` every spelling
   (`sarand-`, `sarand_`) across `scripts/`, `.github/`, `tests/`.
10. In renderers build nested payloads in a typed local `dict[str, Any]`.
11. Do not raise after `if not isinstance(...)` (ruff TRY004); restructure.
12. Tests must not hardcode `"/tmp"` strings (guard test); use `tmp_path` or
    `tempfile`.
13. Adding an analyzer ripples into guard tests (doctor `_CATEGORY_ORDER`, README
    rows in BOTH tables, `DOCTOR_CATEGORIES`, regenerated `docs/COVERAGE.md`,
    analyzer count). This audit adds **no** analyzers; if you think you need one,
    stop and ask.

### 2.2 Code quality and performance bar

- Professional, minimal, readable code. No dead code, no speculative generality,
  no new dependency unless a round says so (and then justify it in AGENTS.md).
- Layering: no import cycles (AGENTS.md §4.1). `rust_bridge.py` stays the only
  Rust import boundary (§4.5). One capability, one file (§4.4).
- Hot paths (secret scan runs over every included file; the issue scanner runs on
  every command output) must be **linear time**:
  - compile regexes once at import; no nested quantifiers; no
    catastrophic-backtracking constructs;
  - cheap literal pre-filters before regex (e.g. `"sk-" in line`) where it pays;
  - cap the line length examined (e.g. 4,000 chars) so a minified file cannot
    stall the scan, and record the cap as a constant;
  - add one adversarial test per new regex family (100,000-char input finishing
    under a generous wall-clock bound).
- Memory: the owner runs 2 GB and 6 GB machines. Never read unbounded data into
  memory when a bounded one will do.
- Determinism: reports must not depend on the machine (locale, global git
  config, hostname order, dict/set iteration order). Sort where order matters.
- Windows/macOS/Linux parity: use `Path.as_posix()` for stored relative paths,
  `os.name`/`sys.platform` guards that mypy understands.

### 2.3 Bilingual comments

Every comment you add in code gets a Persian line and an English line (as in the
existing files). Markdown docs follow the README rule: English in `README.md`,
Persian in `README.fa.md`, two separate linked files, high standard, visually
rich. `AGENTS.md` sections are English.

### 2.4 Security of fixtures

- Never write a realistic live-looking token as a literal anywhere except
  `tests/test_secrets.py` (the only file allow-listed in `.gitleaks.toml`).
  **Build fixtures at runtime by string concatenation** (`"sk-ant-" + "x" * 40`)
  so GitHub push protection and gitleaks do not reject the commit.
- Never print or log a matched secret value. Location and pattern name only.

---

## 3. Delivery protocol (every round)

1. **Audit** the relevant current code; list CONFIRMED / REFUTED / UNCERTAIN per
   finding, with evidence.
2. Deliver **one uniquely named, versioned zip** (e.g. `sarand-r1-secrets-v1.zip`;
   never reuse a filename across messages — the phone caches same-name downloads)
   containing:
   - an **idempotent** `apply_<round>.py` that edits shared files by **anchored
     replacement** and **aborts without writing anything** if any anchor is
     missing; it refuses to run twice destructively;
   - new/changed files, tests, an AGENTS.md section (5.67+), a CHANGELOG entry
     (Unreleased), and an update to `docs/BACKLOG_STATUS.md`.
3. Build the zip from **absolute paths inside its own directory**, list it with
   `unzip -l`, then **test by extracting the delivered zip itself** and running
   the apply script on a fresh copy of the repo. A zip packed from the wrong
   directory has already happened once.
4. Present the zip with `present_files`, then give the commands, **each step as
   one block, with no comments inside the commands** (explanations go before or
   after the block):
   1. phone: copy from `/sdcard/Download/<zip>` into `/tmp`, remove any stale
      extracted dir, unzip, `cd ~/sarand`, run the apply script, **then delete the
      zip from `/tmp` and from `/sdcard/Download` and remove the extracted dir**;
   2. check chain: `ruff check --fix . && ruff format . && ruff format --check . && ruff check . && mypy . && pytest -q`, **followed in the same block by the
      commit and push** (`git add -A && git commit -m "..." && git push`);
   3. `gh run watch; gh run list --limit 3`.
   The type check is `mypy .`, **not** `mypy python`.
5. Never tag a red or unfinished commit. Releases use
   `python3 scripts/release.py tag`, which refuses until every CI run for HEAD
   succeeded.
6. Reply format after delivery (Persian): what was confirmed/refuted, what
   changed, what you could not run, what is deliberately not done, and the exact
   next command block. No praise, no filler.

---

## 4. Findings catalogue

### A — serious

| ID | Finding | Tag |
|---|---|---|
| A1 | Credential **filename** denylist (`SECRET_FILENAME_PATTERNS`, `constants.py`) misses: `.pypirc`, `.git-credentials`, `credentials` (AWS), `*.tfstate`, `*.tfvars`, `.htpasswd`, `kubeconfig`, `secrets.yaml/json`, `*.p8`, `*.ppk`, `id_ecdsa_sk`, `firebase-adminsdk*.json`. Measured later (AGENTS.md 5.67): only the ones with an essential extension were embedded (`secrets.yaml/json/toml`, `*-adminsdk-*.json`, `kubeconfig.yaml`, `*.tfvars.json`, `wp-config.php`, `.docker/config.json`); the rest are silently skipped and not listed as excluded. | `[RAN]` |
| A2 | Credential **content** patterns (`_CONTENT_PATTERNS`, `core/secrets.py`) cover only AWS `AKIA`, `ghp_`-style, Slack, RSA/EC/OPENSSH/DSA private keys and an `api_key=` assignment. Missed: `github_pat_`, `sk-ant-`, `sk-proj-`, `AIza…`, `sk_live_`, `pypi-…`, `npm_…`, `ASIA…`, JWT, URL-embedded passwords, `password = '…'`, PGP and `ENCRYPTED PRIVATE KEY` blocks. gitleaks results are reported but **never used to exclude a file from embedding**. | `[RAN]` + `[READ]` |
| A3 | `is_fixture = rel.startswith("tests/")` in `scan_for_secrets` is a path guess. A real secret inside `tests/` escapes the −10 health penalty while the report says "explicitly identified as test fixtures". | `[READ]` |
| A4 | README never warns that a scan **executes the target project's code** (`pytest`/`conftest.py`, `npm test`, `cargo test`/`build.rs`, …). Only `--skip-tests` mitigates it and it is not presented as the safe mode. No `SECURITY.md`. | `[READ]` (README grep) |
| A5 | Rust `walker.rs` applies `ignore_dirs` to **every component of the absolute path** (`entry.path().components().any(...)`). A project located under a directory named `build`, `dist`, `target`, `.cache`, `venv`, … loses **all** files. The Python fallback prunes relative `dirnames` and is correct. | `[READ]`, `[UNVERIFIED]` at runtime (no cargo) — failing test first |
| A6 | `scan_for_issues` (`utils/command.py`) matches bare substrings (`failed`, `exception`, `panic`, `error:`) on the output of **every** tool, passing ones included. Seen in the report: syft's healthy line "License policy: 0 violation(s), 0 exception(s) applied" is listed under *Errors detected*; `KNOWN_ISSUE_PATTERNS["error:"]` makes Quick Context claim "Compilation or lint errors were detected" while ruff, mypy and clippy all PASSED. | `[REPORT]` + `[READ]` |
| A7 | `cargo audit` printed "couldn't check if the package is yanked: request could not be completed in the allotted timeframe" three times and was still `PASS`. A security tool that did not finish must not be green. | `[REPORT]` |
| A8 | **Python fallback drops `.github/`**: `_pure_python_scan` prunes `d.startswith(".git")`, so `.github/workflows/ci.yml` is missing from scan records while the Python tree view shows it. The Rust core keeps it. Engines disagree. | `[RAN]` |

### B — medium

| ID | Finding | Tag |
|---|---|---|
| B1 | CI runs none of: `bandit`, `pip-audit`, `cargo audit`/`cargo deny` (although `deny.toml` exists), `gitleaks`, `actionlint`, `markdownlint`. No `dependabot.yml`, no `permissions:` in `ci.yml`, no coverage, no concurrency cancel. | `[READ]` |
| B2 | bandit is FAIL in the report: 1 Medium (B314 at `core/jvm_workspace.py:76`, already mitigated by the `DOCTYPE/ENTITY` rejection and a 1 MiB cap, but without a reasoned `# nosec`), 8 Low (`subprocess` in `scripts/`), ~20 warnings "nosec B108 … no failed test" in `device_report/environment.py` (stale/misplaced markers). | `[REPORT]` |
| B3 | `asyncio.gather` in `analyzers/registry.py` (`run_tests/quality/security_concurrently`) and in per-component/workspace planning is **uncapped**; no `--jobs`. `run_cmd_async` buffers all output in memory with no cap. | `[READ]` |
| B4 | Rust walker swallows walk errors (`filter_map(\|e\| e.ok())`) → silent incomplete scans. Directories are filtered *after* traversal (`.filter`, not `filter_entry`) so `node_modules` of non-git trees is fully walked. `git_global(true)` makes output depend on the machine's global gitignore. | `[READ]` |
| B5 | `release.yml`: aarch64 and macOS-x86_64 wheels are never smoke-tested; the workflow does not check that CI was green for the tagged commit; no GitHub Release with wheels + `SHA256SUMS`; third-party actions pinned to tags/branches, not SHAs. | `[READ]` |
| B6 | Python 3.10 reaches end of life around Oct 2026 (verify the date from python.org before writing it anywhere) yet it is the floor in `requires-python`, classifiers and CI. Python 3.15 is absent from the CI matrix. | `[READ]` + external date to verify |
| B7 | The Rust core is ~900 lines (walk, line count, hash, tree) while the dominant cost is subprocesses; no benchmark in AGENTS.md shows its benefit, yet it costs maturin, five wheels and failed no-Rust installs. | `[READ]` |

### C — minor

| ID | Finding |
|---|---|
| C1 | `AGENTS.md` ≈265 KB (~65k tokens) is auto-loaded by agent tools every session and is the biggest file in the self-report; 40 markdownlint errors are mostly there and in `README.fa.md` (MD012, MD022, MD032, MD038, MD004, MD036, MD040). |
| C2 | TODO/FIXME scanner yields ~540 rows of noise (golden fixtures, `test_health.py`, prose in `AGENTS.md`/docs). |
| C3 | `license = { text = "MIT" }` is the legacy form (PEP 639 prefers an SPDX string + `license-files`); no `rust-version` (MSRV) in `Cargo.toml`. |
| C4 | `install.sh` manipulates pipx's internal `venvs/` layout; with the PyPI wheel `pipx install sarand-cli` is enough. |
| C5 | `.benchmarks/` is not in `.gitignore`. |
| C6 | Missing `SECURITY.md`, `CONTRIBUTING.md`. |

### Decisions that belong to the owner (ask, do not assume)

- **D1** What to do about Python 3.10 (keep, or raise the floor in a later release).
- **D2** `git_global` default in the Rust walker (recommended: `false`, for
  reproducible reports).
- **D3** Whether the Rust core stays after the benchmark of B7.
- **D4** musllinux wheels / a pure-Python wheel (feasibility unknown).
- **D5** Whether a failing/INCONCLUSIVE security tool should lower the health
  score or only the confidence (recommended: confidence only).

---

## 5. Out of scope for this whole effort

Nx/Turborepo; a plugin marketplace; Bazel; new analyzers; rewriting `cli.py` or
splitting large modules (a size guard already exists); the Beta classifier
(owner's call after more stable releases); `make` execution; rewriting
`install.sh`; changing the health-score weights (only the *inputs* that were
wrong are fixed).

---

## 6. Rounds

Round order is chosen by risk: output safety → report truthfulness → engine
correctness → trust model → CI → resource limits → Rust robustness → hygiene.
Suggested releases: **v0.6.20 = R1 + R2 + R3**, then **v0.6.21 = R4 + R5**, then
**v0.6.22 = R6 + R7**, R8 any time.

---

### R1 — Secrets: filenames, content, gitleaks wiring, fixture allowlist (A1, A2, A3)

**Read first:** `constants.py` (`SECRET_FILENAME_PATTERNS`), `core/secrets.py`,
`core/gitleaks.py`, `core/health.py` (the `secret_findings` block), `cli.py`
(around the `scan_for_secrets` / `exclude_flagged_files` calls), `userconfig.py`,
`tests/test_secrets.py`, `.gitleaks.toml`, `.sarand.toml`, AGENTS.md §4.10.

**A1 — filenames.** Extend the filename denylist (still matched against the
lower-cased bare name) with, at least:

```text
^\.pypirc$   ^\.git-credentials$   ^credentials$   ^\.dockercfg$
\.tfstate(\.backup)?$   \.tfvars(\.json)?$   ^\.htpasswd$
^kube[-_]?config$   ^secrets?\.(ya?ml|json|toml)$   \.p8$   \.ppk$
^id_(ecdsa|ed25519)_sk$   -adminsdk-.*\.json$   \.kdbx$   \.ovpn$
^wp-config\.php$
```

Because bare-name matching cannot express `.docker/config.json` or
`.aws/credentials`, add a **second tuple of path-suffix patterns** matched against
the POSIX relative path (e.g. `(^|/)\.docker/config\.json$`,
`(^|/)\.aws/credentials$`, `(^|/)\.kube/config$`). Keep both lists in
`constants.py` and expose one function that applies both.
Every pattern needs a positive **and** a negative test (e.g. `credentials.py`
and `secrets.py` and `server.crt` must NOT match). The current `.env*` pattern
(also catches `.env.example`) stays; record that over-exclusion is deliberate.

**A2 — content.** Add compiled, linear-time patterns (names are what the report
shows; never the value):

| Name | Regex (starting point; harden and test) |
|---|---|
| GitHub Fine-grained Token | `github_pat_[A-Za-z0-9_]{22,}` |
| Anthropic API Key | `sk-ant-[A-Za-z0-9_\-]{20,}` |
| OpenAI API Key | `sk-(?:proj-)?[A-Za-z0-9_\-]{32,}` |
| Google API Key | `AIza[0-9A-Za-z_\-]{35}` |
| Stripe Live Key | `[sr]k_live_[0-9A-Za-z]{16,}` |
| PyPI Token | `pypi-AgEI[A-Za-z0-9_\-]{50,}` |
| npm Token | `npm_[A-Za-z0-9]{36}` |
| AWS Temporary Key ID | `ASIA[0-9A-Z]{16}` |
| JSON Web Token | `eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}` |
| Private Key Block | widen to `-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----` (covers PGP and ENCRYPTED) |
| Credentials in URL | `[a-z][a-z0-9+.\-]*://[^\s:/@]+:[^\s@/]{3,}@[^\s/]+` **with a placeholder filter** (skip when the password is one of `pass`, `password`, `changeme`, `example`, `xxx`, `secret`, or looks like `<...>`, `${...}`, `{{...}}`, `%s`) |
| Hardcoded Password Assignment | `(?i)\b(?:password\|passwd\|pwd\|secret\|token)\b\s*[:=]\s*["'][^"'\s]{12,}["']` **gated by a Shannon-entropy threshold (≥ 3.0 bits/char) and the same placeholder filter** |

Rules: patterns are data (a tuple of `(name, compiled, optional validator)`);
`list_pattern_names()` keeps working (callers and tests use it); the Persian/English
docs of the pattern list are updated; cap the examined line length (constant);
measure the added cost on the repo itself (the secret pass over ~270 files must
stay in the same order of magnitude; report before/after wall-clock from
`scripts/benchmark_report.py` or a small timing snippet).
False-positive discipline: run every new pattern over the whole sarand repo and
over `tests/golden/`; any hit outside `tests/test_secrets.py` must be either a real
bug or justified in AGENTS.md. Do not weaken a pattern just to make the repo pass.

**A2b — gitleaks wiring.** Read `core/gitleaks.py`. If gitleaks is installed,
run it so that it yields **file paths only** (JSON report to a temp file outside
the project, `--redact`, deleted afterwards; never place matched values in memory
longer than needed or in logs) and merge those paths into the same exclusion step
as the built-in scanner. If gitleaks is absent or fails, behaviour is exactly as
today (graceful degradation, one SKIPPED result). The report must say which engine
flagged each excluded file. Do not change the existing PASS/FAIL semantics of the
gitleaks check itself.

**A3 — explicit fixture allowlist.** Remove the `startswith("tests/")` guess.
Introduce `[secrets] fixture_paths = ["tests/test_secrets.py"]` (globs, POSIX
relative paths) in `.sarand.toml`, loaded through the existing config layer
(`userconfig.py`, tomllib/tomli idiom). `SecretFinding.is_test_fixture` becomes
`True` only when the file matches the allowlist. Default for projects without the
table: **empty** (every finding counts). Update the health recommendation text to
say "matched `[secrets].fixture_paths`". Excluded-from-embedding behaviour does
**not** change: allow-listed files with findings are still not embedded.
Golden reports may change; regenerate them deliberately via the existing mechanism
(read `tests/golden/README.md`; the directory is excluded from ruff on purpose)
and explain every diff in AGENTS.md.

**Non-goals:** a plugin API for secret rules; scanning git history; entropy
scanning of arbitrary strings; changing health weights.

**Tests (minimum):** parametrised positive/negative filename tests; one positive
and one near-miss negative per content pattern; placeholder filter tests; entropy
gate tests; adversarial 100k-char inputs per regex family; allowlist behaviour
(default empty, glob match, no match); a test that a finding never contains the
value; gitleaks-merge test with a stubbed runner (no network, no binary); a test
that an old report fixture still renders. Fixtures are built by concatenation and
live only in `tests/test_secrets.py`.

**Acceptance:** every `[RAN]` miss in A1/A2 is now detected; no value ever appears
in any renderer output (grep the rendered markdown/json/sarif/html in a test);
`mypy .` clean on 3.10; all guard tests pass.

---

### R2 — Truthful issue extraction and inconclusive tools (A6, A7, C2)

**Read first:** `utils/command.py` (`scan_for_issues`, `make_command_result`),
`constants.py` (`WARNING_PATTERNS`, `ERROR_PATTERNS`, `KNOWN_ISSUE_PATTERNS`),
`core/issues.py`, `models/results.py` (`CommandResult`, `.passed`),
`core/health.py`, `core/quick_context.py`, `core/ai_summary.py`, renderers,
`analyzers/rust_analyzer.py` (cargo audit), the pip-audit call in
`analyzers/python_analyzer.py`, `scanners/todos.py`, existing tests for all of
these and `tests/golden/`.

**A6 — design.**
- A command that **exited 0** produces **no Errors**. Its warnings are limited to
  line-anchored tool warnings (`^\s*warning(\[|:)` and equivalents), not the bare
  substrings `deprecated`/`unused`.
- A command that **exited non-zero** extracts errors only from line-anchored
  signatures: `^\s*error(\[E\d+\])?:`, `^Traceback \(most recent call last\)`,
  `^thread '.*' panicked`, `^FAILED `, `^ERROR `, and tool-specific forms already
  handled elsewhere. Remove bare `failed`, `exception`, `panic` substring matching.
- `KNOWN_ISSUE_PATTERNS` is evaluated **only over results that failed**
  (non-zero exit, not skipped, not inconclusive), line-anchored, never over passing
  output. The sentence "Compilation or lint errors were detected." may appear only
  when a quality/test/security result actually failed with such a signature.
- Keep the bandit-context-line and tool-log-line filters (they are still correct)
  and the `0 failed` handling.
- Replace the substring tuples with a small, documented, compiled-regex table in
  `constants.py` (data, not logic) so adding a signature is a one-line change.
- Back-compat: `Issue`, `CommandResult` field names and JSON/SARIF shapes stay.

**A7 — inconclusive state.**
- Add a tri-state outcome without breaking the public model: a boolean
  `inconclusive: bool = False` on `CommandResult` (JSON key `inconclusive`, shown
  only when true), set by a **signature table** of "the tool did not finish its
  job" outputs: cargo-audit `couldn't check if the package is yanked`,
  `request could not be completed`, advisory-DB fetch failures; pip-audit
  network/connection errors; generic `Temporary failure in name resolution`,
  `timed out` for security kinds. Signatures live in `constants.py`.
- Renderers print `[INCONCLUSIVE]` instead of `[PASS]`; SARIF/JSON carry the flag.
- Health: an inconclusive security result counts as **not run** (it lowers
  `confidence`, it is excluded from the "passed" count, and a recommendation says
  to re-run with network access). It does **not** count as a failure and does not
  take the −10 / "Security tool reported issues" path (decision D5: ask the owner
  before changing this; default as written).
- `--doctor`/Quick Context mention it in one short line.

**C2 — TODO noise.** By default the TODO scanner skips: directories named
`golden`, `fixtures`, `snapshots`, `__snapshots__`; and Markdown/reStructuredText
files (prose, not task markers) — record this as a deliberate default. Add
`[todo] exclude_globs` in `.sarand.toml` for extra patterns and show
"N markers suppressed by exclusions" in the section so nothing is hidden silently.
Do not change what counts as a marker syntax-wise (the health test
"only explicit TODO/FIXME task syntax is actionable" must keep passing).

**Non-goals:** parsing every tool's structured output; changing exit codes of
sarand; making warnings configurable per tool.

**Tests:** table-driven cases for each signature (positive + negative) using the
real strings from the self-report (syft "0 exception(s) applied" must produce no
error; cargo-audit yanked-timeout must set `inconclusive`); a passing ruff/mypy/
clippy output with the word "error:" inside a docstring must not produce a Known
issue; a failing run with a real `error[E0308]:` must; golden regeneration with
explained diffs; health tests for inconclusive (confidence drops, no −10).

**Acceptance:** re-running sarand on its own repo no longer lists the syft line as
an error nor claims compilation/lint errors while those checks passed; the cargo
audit timeout case renders `[INCONCLUSIVE]`.

---

### R3 — Scan-engine correctness and parity (A5, A8)

**Read first:** `src/walker.rs`, `src/tree.rs`, `src/lib.rs`, `src/*_tests.rs`,
`python/sarand/rust_bridge.py` (`scan_project`, `_pure_python_scan`,
`_pure_python_tree`), `scanners/stats.py`, `scanners/tree.py`, AGENTS.md notes on
the walker and the cache.

1. **Reproduce before fixing (A8, runnable in the sandbox).** Write a Python test
   that builds `tmp_path/"build"/"proj"/".github"/"workflows"/"ci.yml"` plus
   `src/a.py`, runs `_pure_python_scan` on `proj`, and asserts both files are
   present. It currently fails for `.github/`. Fix: prune only names in
   `ignore_dirs` (exact match), drop the `startswith(".git")` rule. Check whether
   anything relied on pruning `.gitlab`/`.github` and record the decision.
2. **Reproduce A5 (not runnable without cargo).** Add a Rust test in
   `walker_tests.rs` that creates `<tmp>/build/proj/src/a.py` and scans `proj`; it
   must return the record. Also add a Python parity test (skipped when
   `RUST_CORE_AVAILABLE` is false) asserting the **same set of `rel_path` values**
   from `_core.scan_project` and `_pure_python_scan` on a tree that contains
   `.github/`, `node_modules/`, a file named `dist`, and a root under `build/`.
   State clearly in your reply that the Rust test could not be executed in the
   sandbox and give the owner the exact `cargo test` command to run first.
3. **Fix A5 conservatively:** compute names from the path **relative to `root`**
   (`strip_prefix`), prune with `WalkBuilder::filter_entry` on **directories only**
   (so pruned trees are not traversed at all, which also removes the B4
   traversal cost), keep files whose *name* merely equals an ignore name (parity
   with Python). `cargo fmt` and `cargo clippy -D warnings` must pass by
   construction (no unused imports/variables, no needless clones).
4. Document the final, single ignore semantics in AGENTS.md and in the
   `IGNORE_DIRS` comment (bilingual).

**Non-goals:** changing hashing, line counting, binary sniffing; the cache format.

**Acceptance:** both engines return identical relative-path sets on the parity
tree; the `build/proj` case passes in Python now and in Rust after the owner runs
`cargo test`.

---

### R4 — Trust model and security documentation (A4, C6 part)

**Read first:** README.md and README.fa.md (the "Quick start", "Security
checks" and "Troubleshooting" parts), `tests/test_readme_sync.py`, `cli.py`
(`--skip-tests`, `--skip-audit`, `--no-source`), AGENTS.md §4.3.

1. Add a **"Trust model / Running untrusted code"** section to `README.md` and the
   Persian equivalent to `README.fa.md` (two files, linked to each other, same
   facts): what sarand executes (list exactly which tools run per language, from
   `docs/COVERAGE.md`), that scanning is equivalent to executing the project's
   test code, the safe modes (`--skip-tests`, `--no-source`, running inside a
   disposable container/VM, a throwaway user), what sarand **never** runs
   (`make`, project scripts other than the documented test/lint/audit commands —
   verify this claim in code before writing it), and the fact that secret
   exclusion is best-effort and not a substitute for reviewing a report before
   sharing it.
2. Add `SECURITY.md` (supported versions, how to report a vulnerability privately
   — use GitHub private vulnerability reporting, do not invent an email address —
   scope, the trust-model summary). Add `CONTRIBUTING.md` (setup with
   `pip install -e ".[dev]"`, the check chain, the bilingual-comment rule,
   AGENTS.md as the constitution, how to add an analyzer pointing to the guard
   tests). Both short.
3. A one-line epilog in `sarand --help` pointing to the trust model. No new flags.
4. Keep `tests/test_readme_sync.py` green; PyPI renders `README.md`, so any link
   you add there must be **absolute** (`tests/test_pypi_readiness.py` enforces it).

**Non-goals:** sandboxing, containers built into sarand, an interactive consent
prompt.

**Acceptance:** every sentence about behaviour is traceable to code or a test
named in the AGENTS.md section; `twine check --strict` still passes.

---

### R5 — CI, release and static-analysis hygiene (B1, B2, B5, B6, C5)

**Read first:** `.github/workflows/ci.yml`, `release.yml`, `deny.toml`,
`.markdownlint.json`, `pyproject.toml` (`[project.optional-dependencies]`),
`scripts/release.py`, `scripts/smoke_install.py`, `docs/PUBLISHING.md`,
`tests/test_release_workflow.py`, `tests/test_distribution.py`.
**You have no network: never invent an action version, a commit SHA or a runner
label.** Verify against the existing workflow or official docs the owner pastes;
otherwise leave the item as a recorded open question.

1. **bandit (B2).** Add `[tool.bandit]` to `pyproject.toml` (exclude `tests`;
   `scripts/` handled with narrowly scoped, **reasoned** `# nosec B603 B607`
   markers placed on the exact line bandit reports, each with a short why).
   Put `# nosec B314` with the reason ("DOCTYPE/ENTITY rejected and size-capped
   above") on the `ET.fromstring` line. For `device_report/environment.py`
   remove or relocate the stale `# nosec B108` markers so bandit reports neither
   findings nor "nosec encountered but no failed test" warnings. Because you
   cannot run bandit, give the owner the exact verification command and ask for
   the output; iterate once if needed.
2. **New CI job `static` (ubuntu only).** Runs: `bandit -c pyproject.toml -r python scripts`,
   `pip-audit`, `cargo deny check` (uses the existing `deny.toml`), `actionlint`,
   `markdownlint` (see R8 for the lint fixes), and gitleaks. Reuse the project's
   own dev extras (`bandit`, `pip-audit` are already there). `cargo audit` is
   network-flaky: if added, treat "inconclusive" as a warning, not a red job, and
   say why in a comment. Every new step has a bilingual comment.
3. **ci.yml hardening:** `permissions: contents: read` at top level;
   `concurrency` with `cancel-in-progress: true` for pull requests only; keep
   `shell: bash`; keep the existing matrix; optionally a **non-blocking** job
   (`continue-on-error: true`) for Python 3.15 **only if** the owner confirms
   `setup-python` supports it (ask; decision D1 covers the 3.10 floor — do not
   change `requires-python` or classifiers in this round).
4. **`.github/dependabot.yml`:** `github-actions`, `cargo`, `pip`, weekly, grouped
   minor/patch, with a commit-message prefix `ci:`/`deps:`.
5. **release.yml (B5):**
   - a `ci-gate` job (needs `check`) that fails unless the CI workflow concluded
     `success` for `$GITHUB_SHA` (use `gh run list --commit … --workflow CI --json conclusion`
     with `GH_TOKEN`, `permissions: actions: read`); `publish-pypi` needs it;
   - a `github-release` job after `publish-pypi` (`permissions: contents: write`)
     creating the release for the tag with all wheels, the sdist and a generated
     `SHA256SUMS`;
   - smoke tests for the aarch64 and macOS-x86_64 wheels **only if** a native
     runner label for them is verified; otherwise record it in AGENTS.md as open
     with the reason (do not add emulation actions from memory);
   - action SHA pinning: do **not** fabricate SHAs. Add `scripts/pin_actions.py`
     (stdlib only, network required, run by the owner) that rewrites `uses:` tags
     to SHAs with a `# vX.Y.Z` comment, plus a guard test that, once pinned, every
     `uses:` is a 40-hex SHA. Ship the script and the test in "not enforced yet"
     mode; enforcement is a follow-up after the owner runs the script.
   - extend `tests/test_release_workflow.py` accordingly (parse with `yaml`,
     index with `[...]`, 3.10-safe).
6. `.gitignore`: add `.benchmarks/` (C5).

**Non-goals:** changing the publishing mechanism (trusted publishing stays), the
matrix of built wheels, or `requires-python`.

**Acceptance:** `actionlint` clean; the owner's `gh run list` shows green on all
jobs including `static`; a dry `workflow_dispatch` of Release still succeeds
(TestPyPI box unticked); the guard tests pass.

---

### R6 — Resource limits: `--jobs` and bounded command output (B3)

**Read first:** `analyzers/registry.py`, `analyzers/plugin_adapter.py` (it says
`run_*_concurrently` use `gather` without …; keep that guarantee), `core/per_component.py`,
`cli.py` (argument parsing and where the three concurrent helpers are called),
`utils/command.py` (`run_cmd_async`, `_terminate_process`), `core/estimate.py`
(memory warning), `constants.py`, existing tests for the registry and command
runner.

1. **`--jobs N` / `SARAND_JOBS`.** New small module `core/concurrency.py` with
   `gather_limited(coros, limit)` built on `asyncio.Semaphore`, **preserving result
   order** and the exact exception behaviour of the current `gather` (plugin
   exceptions are already isolated by the adapter; do not swallow others).
   Default: `max(1, min(4, os.cpu_count() or 1))`, reduced to `1`–`2` when the
   available memory read by the existing environment scanner is under 2 GiB
   (reuse it; do not duplicate probing). CLI value validated (`>=1`, sane upper
   bound), documented in `--help`, both READMEs, and docs. Apply the limiter to
   the three `run_*_concurrently` helpers and to per-component/workspace-member
   runs. The project-wide trio (gitleaks, syft, lockfile) is **not** limited
   below its current behaviour unless measurement shows a need (record it).
2. **Bounded output.** `run_cmd_async` must read the pipe incrementally, keep at
   most `MAX_COMMAND_OUTPUT_BYTES` (new constant, default 8 MiB) **as head + tail**
   with a clear truncation marker in the middle, and **keep draining the pipe**
   after the cap so the child never blocks. Record `truncated: bool` on
   `CommandResult` (shown only when true). Timeout, process-group termination,
   cancellation and Windows paths keep working exactly as today. Issue scanning
   (R2) operates on the retained text.
3. Peak-memory evidence: extend `scripts/benchmark_report.py` or add a tiny test
   helper that runs a child printing ~50 MB and asserts the retained output is
   ≤ cap + marker. Ask the owner to run the benchmark on the phone and paste the
   numbers; do not invent figures.

**Non-goals:** a scheduler with priorities; per-tool limits; changing timeouts;
the synchronous `run_cmd` (short environment probes only — record the
reasoning; do not touch).

**Tests:** order preservation; limit actually bounds concurrency (use a counter
inside fake coroutines); exception propagation; `--jobs 0`/negative rejected;
output cap with head+tail content check; draining (child writing beyond the cap
terminates normally); timeout still returns 124.

**Acceptance:** with `--jobs 1` no two analyzer subprocesses overlap (test);
default on a 2 GiB box is ≤ 2; golden reports unchanged unless truncation hits.

---

### R7 — Rust walker robustness (B4)

**Read first:** the state of `src/walker.rs` after R3, `src/lib.rs` (PyO3
signatures — keep the existing `scan_project` signature untouched for ABI/back-compat),
`rust_bridge.py`, `scanners/stats.py`.

1. Stop swallowing errors: collect walk and metadata errors (count + first N
   messages, N small and constant). Add a **new** PyO3 function
   (e.g. `scan_project_report`) returning records plus `{"skipped": int, "samples": [str]}`;
   keep the old function as a thin wrapper. Python fallback collects the same via
   `os.walk(onerror=...)` and `OSError` on stat.
2. Surface it: a "Scan warnings" line in Project statistics and a JSON field
   (only when non-zero), so a permission-denied directory is no longer invisible.
3. `git_global`: apply decision **D2** (ask the owner; recommended default
   `false`), expose a documented override, record it in AGENTS.md.
4. Keep `panic = "unwind"`; no `unwrap()`/`expect()` introduced.

**Non-goals:** changing the parallelism strategy; new hashing; async Rust.

**Tests:** Rust unit test for the error collector; Python parity test on an
unreadable directory (skip on Windows and when running as root); stats rendering
test; clippy-clean by construction (no `needless_return`, no unused).

**Acceptance:** an unreadable directory produces a visible warning in both
engines; reports for normal trees are byte-identical to before.

---

### R8 — Repository hygiene and measurement (B7, C1, C3, C4)

1. **B7 benchmark (data, not a decision).** Add `scripts/bench_scan.py`: builds a
   synthetic tree (10k small files, nested dirs, some ignored dirs) in a temp
   directory, times `_core.scan_project` vs `_pure_python_scan` (median of 5
   runs, after one warm-up), prints a small table and peak RSS where available.
   Run on the sarand repo itself too. The owner runs it on both devices and pastes
   the output; you then write the numbers into AGENTS.md and prepare decision
   **D3** with the facts. **Do not remove or alter the Rust core in this round.**
2. **C1 — AGENTS.md diet.** Keep `AGENTS.md` as the constitution (sections 1–4,
   priorities, definition of done, a short current-state pointer) targeting
   **under ~15 KB**, and move the dated history (§5.x) **verbatim** to
   `docs/history/AGENTS-HISTORY-5.x.md` (split by range if a file would exceed
   ~100 KB). Nothing is deleted or reworded. Update every reference: links,
   guard tests that read AGENTS sections, `docs/BACKLOG_STATUS.md`, README mentions,
   the `Read first` hints in `core/quick_context.py` if they name it, and the
   handoff text. A test asserts every `5.N` section id that existed before is still
   present exactly once in the new layout. Fix the markdownlint errors listed in
   the self-report (MD012, MD022, MD032, MD038, MD004, MD036, MD040 in
   `AGENTS.md`/history and MD022 in `README.fa.md`) with a **script that edits by
   anchored line rules**, not by hand-rewriting; verify no content change other
   than blank lines/markers (diff check in the script's own test). If
   `markdownlint` joins CI (R5), this round must land first or together.
3. **C3.** Switch to `license = "MIT"` + `license-files = ["LICENSE"]` **only if**
   the minimum `maturin` in `[build-system]` is verified to support PEP 639 and
   `twine check --strict` passes (ask the owner to run the build and paste the
   result; otherwise defer and record). Add `rust-version`: ask the owner to run
   `cargo metadata --format-version 1` and send the `rust_version` field of
   `pyo3`; set the MSRV from that **fact** and add an MSRV CI job only if cheap.
4. **C4.** Do not rewrite `install.sh`. Make both READMEs lead with
   `pipx install sarand-cli` for users and describe `install.sh` as the
   developer/source route (keep tests in `tests/test_distribution.py` green).

**Non-goals:** deleting `docs/BACKLOG.md` (its Definition of Done for items 8 and
11 still lives only there — the owner decides when).

**Acceptance:** AGENTS.md size drop verified with `wc -c`; section-id test green;
self-scan shows markdownlint PASS; no behaviour change in the package.

---

## 7. Cross-cutting Definition of Done (every round)

- [ ] Each finding in the round is marked CONFIRMED / REFUTED / UNCERTAIN with
      evidence; refuted ones are recorded as non-gaps.
- [ ] Tests added for every behaviour change, including negative and adversarial
      cases; no test hardcodes `/tmp`; fixtures with secrets are built at runtime.
- [ ] `ruff check`, `ruff format --check`, `mypy .` (3.10-safe), `pytest` pass by
      construction; Rust changes pass `cargo fmt`/`clippy -D warnings` by
      construction; anything not runnable is stated explicitly.
- [ ] Repo guard tests run (pytest stubbed) against the changed files:
      `test_portability`, `test_size_guard`, `test_distribution`,
      `test_readme_sync`, `test_doctor_v2`, `test_pypi_readiness`,
      `test_release_workflow`, `test_pyproject_valid`.
- [ ] Every TOML/YAML touched was parsed in the sandbox.
- [ ] `docs/COVERAGE.md` regeneration checked if analyzers/doctor data changed.
- [ ] Bilingual comments on every new comment; READMEs updated in both languages
      when user-visible behaviour changed.
- [ ] AGENTS.md section added (what was confirmed, what was built, non-goals,
      lessons), CHANGELOG (Unreleased) entry, `docs/BACKLOG_STATUS.md` updated.
- [ ] One uniquely named zip, tested by extracting the delivered file, presented
      with `present_files`; the command blocks contain no inline comments, include
      the cleanup of the zip and extracted copies, and end with commit + push.
- [ ] The reply is in Persian, names what was **not** verified, and ends with the
      exact next command block.

## 8. Final rule

If a requirement here conflicts with the current code, the current code, or with
a decision recorded in AGENTS.md: **stop, show the evidence, and ask the owner**.
Do not silently pick a side, and never make a claim in documentation that a test or
a command output has not backed.
