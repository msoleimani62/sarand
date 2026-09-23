# AGENTS.md — sarand project constitution

> [!IMPORTANT]
> **⚠️ Binding directive**
>
> Before performing any action in this repository — writing code, modifying files, running commands, reviewing changes, or proposing architectural decisions — every AI agent (Claude Code, Aider, Cursor, Codex, or equivalent) and every human contributor **must** read this document in full. It is the single source of truth for this project. Where anything here conflicts with general "best practice" you might otherwise default to, this file wins, for this repository.
>
> Work done without following this document is not accepted.

---

## 1. What sarand is

sarand is a cross-platform CLI that scans any software project, detects its
language/architecture, runs its tests, and generates a single AI-ready
intelligence report (Markdown/JSON/text) containing: project tree, full
source, test results, health score, and a structured AI summary.

It is meant to be run **before** handing a codebase to an AI coding
assistant — the report *is* the context you paste in, or point the
assistant at.

Formerly a single-project tool named `bxt`, hardcoded to one directory
(`~/bimarz`). It was rebuilt from scratch under the name **sarand** as a
hybrid Rust + Python project. Nothing in this repository should ever again
assume a specific project name, path, or user — sarand analyses whatever
directory it is pointed at, full stop. This was the first bug ever fixed in
this project's history and must never regress (see the regression test in
`tests/test_project_detector.py::test_never_hardcodes_a_specific_project_name`).

---

## 2. Role & engineering mindset

You are not a code generator. Treat yourself as a Principal Software
Engineer, accountable for long-term stability, robust security, clean
architecture, a good user experience, and the project's ability to evolve
for years, not just to pass today's request.

Before writing or modifying any code:

- Fully understand the existing architecture — read the relevant modules,
  don't guess from the file name.
- Analyze dependency relationships (see the layering rule, §4.1).
- Preserve existing design principles unless you have an explicit,
  discussed reason to change them.

Evaluate every implementation against: scalability, edge-case handling,
error resilience, maintainability, and future extensibility. "It works for
the one case I tested" is not sufficient — see §4.8 on verification.

---

## 3. Architecture

```text
sarand/
├── Cargo.toml, src/*.rs        Rust core, compiles to `sarand._core`
│   ├── walker.rs                parallel, .gitignore-aware file walk
│   ├── linecount.rs              binary detection + LOC counting
│   ├── hasher.rs                 SHA-256 (duplicate-file detection)
│   ├── tree.rs                   ASCII project tree builder
│   └── lib.rs                    PyO3 bindings (thin translation layer only)
│
├── python/sarand/
│   ├── models/results.py         dependency-free dataclass layer (§4.1)
│   ├── constants.py               all tunables, project markers, ignore lists
│   ├── rust_bridge.py             THE ONLY file allowed to import sarand._core
│   ├── discovery/                 language/project-type detection (incl. discovery/android.py)
│   ├── scanners/                  git, environment, stats, tree, TODOs
│   ├── analyzers/                 one file per language, pluggable (§4.4, §4.9)
│   │   ├── base.py                 LanguageAnalyzer Protocol
│   │   ├── registry.py             built-in list + entry_points plugin loading
│   │   └── {python,rust,go,node,cpp,java,android}_analyzer.py
│   ├── core/                      health.py, ai_summary.py, issues.py, secrets.py, doctor.py
│   ├── renderers/                 one file per output format (§4.4)
│   ├── userconfig.py              persisted config (~/.config/sarand/config.json)
│   ├── config.py                  CLI-argument → runtime config resolution
│   ├── progress.py                Rich-based terminal output
│   └── cli.py                     argparse + async orchestration
│
└── tests/                        pytest suite, mirrors the module layout above
```

### Why Rust for some things and Python for others

Rust owns exactly four things: walking the filesystem, counting lines,
hashing files, and building the tree string. These are the O(n)-over-every-
file hot path that is genuinely slow in pure Python on a large repo, and
they change *rarely* — the algorithms are stable.

Everything else — which files count as "essential", how TODOs are
classified, health-score weighting, report formatting, which tools run for
which language — stays Python, because it changes *often* and should never
require a recompile to tweak.

If you're about to add something to the Rust core, ask: "will this need to
change every time we tweak a business rule?" If yes, it belongs in Python.

### Target platforms

sarand must work on Linux, macOS, Windows, and Android (Termux/Kali
NetHunter proot). Avoid fragile platform-specific assumptions (hardcoded
path separators, Linux-only `/proc` reads without a fallback, shell syntax
that isn't POSIX-portable). The primary day-to-day development and testing
environments for this project specifically are Android+Termux/Kali
NetHunter and Arch Linux on resource-constrained hardware — if a proposed
dependency or tool is heavy (large compile times, big binary, high RAM
during build), say so up front, explain the constraint, and propose a
lighter alternative before implementing it.

---

## 4. Coding rules (non-negotiable)

These are established project conventions, several of them written after a
real bug taught us the lesson the hard way. Follow them exactly; don't
"improve" them without discussing first.

### 4.1 Layering — no import cycles, ever

`models/results.py` must **never** import from any other sarand module. It
is the base layer everything else depends on. This project already hit a
real circular-import bug once (`models.results` → `discovery` → `utils`
package `__init__` → `utils.command` → `models.results`) during the `bxt`
days. The fix was moving `ProjectDetection` directly into `models/results.py`
instead of importing it from `discovery`. Do not reintroduce a reverse
dependency into the models layer for any reason.

`discovery/project_detector.py` uses stdlib `logging` directly, not
`sarand.utils.logging` — this avoids pulling in the `sarand.utils` package
`__init__` (which imports `command.py`, which imports `models.results`)
during early module load. If you add a new "early" module, follow the same
pattern: prefer stdlib over sarand.utils if it would otherwise be imported
before `models` is fully loaded.

### 4.2 Never hardcode a specific project

No file path, project name, or user-specific assumption is ever allowed in
core logic (constants.py, discovery/, scanners/, analyzers/, cli.py). Every
project sarand analyses is discovered at runtime from the target directory
alone. This is the #1 rule this project exists to enforce on itself — see
§1.

### 4.3 Gate every external tool call on a real project marker

Never run `pytest`, `ruff`, `npm test`, etc. just because the binary
happens to be on PATH. Each `LanguageAnalyzer.matches(root)` must check for
a real marker file (`pyproject.toml`, `Cargo.toml`, `go.mod`,
`package.json`, ...) before that analyzer's `run_tests`/`run_quality` are
ever called. `NodeAnalyzer` additionally requires a real `"test"` script in
`package.json` before running `npm test` — running it unconditionally just
produces a useless "no test specified" failure. This class of bug (bxt used
to run `pytest` on non-Python projects just because pytest was installed
globally) must never come back.

### 4.4 One capability, one file

One file per language analyzer (`analyzers/*.py`), one file per output
renderer (`renderers/*.py`), one file per scanning concern
(`scanners/*.py`). Never merge two languages or two output formats into one
file "for convenience" — the whole point of this architecture is that
adding a language or format means adding one file, not editing a
monolithic module. When any file, module, or function grows too complex to
hold in your head at once, split it — don't let a single file accumulate
multiple unrelated responsibilities.

### 4.5 `rust_bridge.py` is the only Rust import boundary

No file other than `rust_bridge.py` may `import sarand._core`. Every public
function in `rust_bridge.py` must have a pure-Python fallback that produces
the **exact same data shape** (same dict keys, same semantics) as the Rust
path. This is what makes the Rust core optional rather than required —
sarand must keep working on a platform where `maturin develop` fails to
compile (this has real precedent: exotic Termux/aarch64 toolchains).
Never let a downstream module (`scanners/`, `analyzers/`, `cli.py`) branch
on `RUST_CORE_AVAILABLE` itself — that decision belongs in `rust_bridge.py`
alone.

### 4.6 Pin dependencies deliberately, and expect drift

We were already bitten once: `Cargo.toml` pinned `pyo3 = "0.22"`, and the
API for creating a `PyDict` had changed between minor versions
(`PyDict::new` vs `PyDict::new_bound`) — code that looked correct by memory
failed to compile. Lesson: don't trust a remembered API signature for a
fast-moving dependency (PyO3 especially). When adding or bumping a Rust or
Python dependency, note the exact version pinned and re-check the relevant
API against that version's docs/changelog rather than assuming.
Compile/import errors caused by version drift are expected, not a sign
something is deeply wrong — fix forward, and log the fix as a comment in
`Cargo.toml`/`pyproject.toml` if the correct API differs from the "obvious"
one.

### 4.7 Async for independent work

Independent external command invocations (different languages' test/lint
runs) run concurrently via `asyncio.gather`, never chained sequentially
without a reason. See `analyzers/registry.py`
(`run_tests_concurrently`/`run_quality_concurrently`) and
`utils/command.py` (`run_cmd_async`). If you add a new kind of independent
work, make it async and fan it out the same way. More generally: prioritize
low memory use and minimal redundant work in anything that touches every
file in a project (that's precisely why the hot path is in Rust, §3) —
avoid needless repeated filesystem walks, redundant loops, and blocking
calls where concurrency is possible.

### 4.8 Verification requirements — never claim untested work is done

- Every Python change must be import-tested and, where practical, run
  end-to-end against a throwaway test project before being considered done.
- Any Rust change must be confirmed by actually running
  `maturin develop --release` and reporting the exact compiler output —
  an assistant without a local Rust toolchain cannot claim a Rust change
  "works" without that confirmation from the maintainer.
- Never fabricate test results or claim success without execution. If
  something was not verified locally, say so explicitly — literally write
  "Not verified locally" rather than staying silent about it or implying
  it was checked.
- The project must accumulate real automated coverage over time: unit
  tests, integration tests, and smoke tests, not just ad-hoc manual runs.
  Tests protect users (especially less experienced ones — sarand should be
  usable by someone without deep CLI experience) from silent regressions.
- A test's isolation technique must actually work on every platform CI
  covers, not just the one it was written on. `test_output_dir_uses_
  persisted_config_when_present` set `XDG_CONFIG_HOME` to redirect
  `get_config_dir()` -- correct on Linux, silently a no-op on macOS/
  Windows (which use their own OS conventions by design), so the test
  passed locally for months without actually testing anything on those
  platforms. If a test fakes an OS-specific mechanism (an env var, a
  well-known directory, a platform branch), monkeypatch the function
  that reads it directly instead -- that isolates correctly regardless
  of which OS the test happens to run on.
- Plain `pytest` (no flags) must always mean "the whole suite ran" — never
  configure `addopts` (or any other mechanism) to silently deselect tests
  by default, even slow/network-dependent ones. Without CI (not built yet
  — Phase G), there is no scheduled safety net to catch a test nobody
  remembers to run explicitly; a default that quietly skips real coverage
  is exactly the kind of silent regression risk this rule exists to
  prevent. Slow tests get a marker (see `slow_external` in
  `pyproject.toml`) so people can opt into a *faster* subset during quick
  local iteration (`pytest -m "not slow_external"`) — the fast path is
  the opt-in, not the default; the safe direction to fail in is "forgot a
  flag, ran more than intended," never the reverse.

### 4.9 Bilingual comments in code

Wherever a comment is genuinely needed to explain *why* — not what, and
not an architectural decision that isn't obvious from the code — write it
in Persian **and** English, back to back, no exceptions:

```python
# جلوگیری از اجرای دوباره عملیات سنگین هنگام استفاده از cache
# Prevent repeating expensive operations when using cache
```

Comments that just restate the code ("# increment counter") should not
exist in either language. Only comment where the reasoning isn't obvious
from the code itself.

### 4.10 Never embed secrets in a generated report

sarand's whole purpose is to dump a project's source into one file for an
AI to read — which means it is also very good at accidentally leaking
credentials if a secret-shaped file sits in the scanned directory, or if
one is hardcoded inside an otherwise ordinary source file. Beyond whatever
`.gitignore` already excludes, two independent, always-on layers apply
(`core/secrets.py` — never gated behind `--security`, since this is a
safety rule, not an optional check):

1. **Filename-based exclusion** — `essential_files`/renderers never embed
   the contents of files that look like credentials by name, regardless
   of extension: `.pem`, `.key`, `id_rsa`/`id_ed25519` (`.pub` is fine,
   the private half is not), `.env*`, anything named like a cloud
   service-account JSON, and similar
   (`constants.SECRET_FILENAME_PATTERNS`).
2. **Content-based scanning** — a lightweight regex scan
   (`scan_for_secrets`) over files that *were* included, looking for
   secret-shaped patterns (AWS keys, private-key headers, common token
   formats). Critically, a match doesn't just produce a warning next to
   an unredacted dump of the same file — `exclude_flagged_files` removes
   that file from source embedding entirely, the same way a
   filename-based exclusion would. A finding that still lets the flagged
   file's full content ship two sections later is not a fix; it's a
   demonstration of the bug. (This exact gap existed in the first version
   of this rule's implementation and was caught by the end-to-end
   regression test in `tests/test_secrets.py` before being called done —
   see §4.8.)

Security and data safety outrank every other concern in this project (§7).

### 4.11 Startup dependency checks should never fail silently

If a required tool, binary, or runtime dependency is missing, sarand must
not crash with a raw traceback — it should explain exactly what's missing
and give an actionable command to fix it. This already holds for
per-language toolchains (`LanguageAnalyzer.run_tests` returns a skipped
`CommandResult` with a human-readable reason, §4.3) — apply the same
standard to any new startup or dependency check you add. A `sarand doctor`
command that checks Rust-core availability, Python version, and known
per-language toolchains in one pass, printing clear pass/fail/fix-it output,
is a good future addition (see roadmap Phase C) precisely because this
rule already implies it.

### 4.12 Documentation standard

`README.md` must stay genuinely useful for a full range of users, not just
maintainers: project introduction, goals, requirements, installation for
Linux/Termux/Windows, basic usage, advanced configuration, real examples,
troubleshooting, and safe uninstall instructions — all present, all kept
in sync with the actual CLI flags (don't let README drift from `cli.py`'s
`build_parser()`). Prefer clear Markdown structure and tables over walls of
prose; use badges/emoji only where they add real scannability, not as
decoration on every heading.

**Structure (2026-09-20):** the README is two files, not one interleaved
bilingual file — `README.md` (English) and `README.fa.md` (Persian, wrapped
in `<div dir="rtl">`), each linking to the other, sharing `assets/banner.svg`
and a `LICENSE` file. Both are linted by `markdownlint` (`.markdownlint.json`)
and pinned to the real argparse definitions by `tests/test_readme_sync.py`:
every long option of `cli.py`, `rc/command.py` and `device_report/config.py`
must be documented in both files, and neither may mention an option that
no parser defines. When you add or change an option, update **both**
READMEs; the test names what you forgot. The rewrite found real drift the
old README had accumulated: it documented a `--max-file-size` flag that
never existed, `--output-dir`'s `--help` text contradicted
`resolve_output_dir()` (the code is the truth: `--output-dir` >
`SARAND_OUTPUT_DIR` > saved config > `~/Downloads`; the help text was
corrected), `--verify`, `--source` and `SARAND_RC_SOURCE` were
undocumented, and its "Current scope" paragraph still said Zig/Swift/C#
analyzers were missing. Do not put numbers that go stale (test counts,
versions) in the README; the version badge reads the git tag. Note: the
RTL rendering of the Persian file and the banner SVG were not viewed in a
browser by the assistant that wrote them — check them on GitHub, on a
phone and on a desktop, before treating them as final.

### 4.13 "Check, remove, announce, then create fresh" for anything that replaces a previous artifact

Any time sarand (or its install tooling) is about to produce something at
a path that may already hold a previous version of that same thing —
a generated report, an installed package — the sequence is: check
whether it already exists, remove it first, print what you're doing,
then create the new one. Never rely on a silent overwrite (`write_text`,
`pipx install` over a stale copy) even when that would produce the same
end state, because a silent overwrite gives no signal that a *previous*
version existed at all — the user has to infer it from a changed mtime.
Two concrete instances of this rule: `cli.py`'s `remove_previous_report`
(a report at the exact output path is removed and announced before the
new one is written) and `install.sh` (a previous pipx installation is
uninstalled and announced before installing the current source tree —
this also fixes a real staleness bug: pipx installs are not editable by
default, so re-running a plain `pipx install` after pulling new sarand
code does not actually pick up the changes without an uninstall first).

---

## 5. Working-session conventions (for Claude Code / assistant sessions)

- Respond to the maintainer in Persian; technical/computing terms may stay
  in English. Code and code comments follow §4.9 regardless of chat
  language.
- Avoid flattery, empty approval, or emotional statements. Focus on
  technical accuracy, engineering trade-offs, and practical next steps.
- If a requested approach introduces real risk — high coupling, a security
  problem, a performance regression, or an architecture that fights this
  document — say so plainly, explain *why* with concrete reasoning (cite
  the specific rule or a past incident if relevant), and propose a better
  alternative. Don't silently comply with something that violates §4.
- No comments inside standalone terminal/shell command blocks — put any
  needed explanation before or after the command block instead. Commands
  must work correctly in both Zsh and Bash (the maintainer's actual
  shells), with no assumptions specific to one.
- When generating a complete file via heredoc, use the plain, real
  delimiter:

  ```bash
  cat > target_file.py <<'EOF'
  # code here
  EOF
  ```

  (Inside *this* document specifically, some examples use `<EOF>` instead
  of a bare `EOF` purely to avoid the delimiter being misread as the end of
  this Markdown file's own code fence — never do that in an actual command
  you run.)
- When a deliverable spans multiple files, bundle them into a single zip
  rather than presenting file-by-file. When it's a single file or a small,
  precise patch, prefer giving the complete, production-ready content (or
  an exact `sed`/`str_replace`-style patch) over a partial diff or
  "...rest unchanged" placeholder. Never deliver partial snippets,
  incomplete patches, or truncated implementations as if they were done.
- When the maintainer says `continue`, resume exactly from the last known
  state — don't restart, ignore prior progress, or rebuild sections that
  were already finished.
- Proposed changes should include clean, descriptive, conventional commit
  messages.
- When code changes and the maintainer needs to re-test via pipx, tell
  them to run `./install.sh`, not a raw `pipx install ~/sarand` — see
  §4.13 for why the raw command silently fails to pick up changes.

---

## 6. Current state (as of this commit)

| Area | Status |
|---|---|
| Rust core (walker/linecount/hasher/tree + PyO3 bindings) | **Compiles and runs** (`maturin develop --release`, verified on aarch64/Termux; `PyDict::new_bound` fix applied for the pyo3 0.22 pin — see §4.6) |
| Pure-Python fallback | Implemented and tested; produces identical report structure |
| Language analyzers | Python, Rust, Go, Node.js — all gated on real markers (§4.3) |
| Async concurrent test/quality execution | Implemented (`asyncio.gather`) |
| Single shared filesystem scan | Implemented — tree/stats/essential-files/TODOs all read from one `scan_project()` call |
| Persisted output-dir config | Implemented (`sarand --set-output-dir`, OS-appropriate path) |
| Markdown / JSON / text renderers | Implemented |
| Health score engine | Implemented (tests/quality/security/git/code/tooling breakdown) |
| Automated test suite (pytest) | **Implemented and confirmed — 565 tests passing on-device** (`pytest -q`, 2026-09-20, after the §5.12 follow-up on top of v0.5.0; the §5.13 round adds 9 more, confirmed 574; the README round adds 4 more, confirmed 578; the memory-reporting round adds 12, confirmed 590; the hang-fix round adds 1, confirmed 591; the license-policy round adds 26, confirmed only up to the ruff step (its `ruff check` stopped the chain); the Windows-portability round adds 1 more, confirmed 618; the `/tmp` guard round adds 1, confirmed 619; the assembly round adds 34, confirmed 653 with all five CI jobs green; the §5.18 round adds 43, confirmed 696 with `ruff`/`mypy` clean; the doctor-visibility fix adds 2, confirmed 698; the `install.sh` fix adds 6, confirmed 707; the §5.20 round (report-size guard, health-check transparency, installation diagnostics, README rewrite) adds 47, expected 754 — re-confirm), covering every analyzer/renderer/core module added through §5. CI green on all five jobs (Ubuntu x3 on Python 3.10/3.12/3.14, macOS, Windows) at commit `79cfe3d`; re-confirm after each push before tagging (see the release rule in the 5.13 section). `pytest` runs everything by default (no `addopts` filtering, §4.8); use `pytest -m "not slow_external"` for a fast local-iteration subset. Two lasting lessons from this project's test-bug history: (1) don't hardcode a "tool not installed" assumption in a test — branch on `shutil.which(...)` (Phase B); (2) don't fake a platform-specific mechanism (env var, well-known dir) — monkeypatch the function that reads it directly, or the test only really runs on whichever OS wrote it (Phase G) |
| `--security` checks | **Implemented and tested** — per-language `run_security` (pip-audit + bandit / cargo-audit / govulncheck / npm audit), all gated on real markers + toolchain presence, run concurrently via `run_security_concurrently` |
| Secrets exclusion from reports (§4.10) | **Implemented and tested** — filename-based exclusion (`.pem`, `.env*`, `id_rsa`, service-account JSON, ...) always on; content-based regex scan (`core/secrets.py`) always on; any file with a content-level finding is moved out of the source-embed list entirely (`exclude_flagged_files`), not just flagged — regression-tested end-to-end (`tests/test_secrets.py::test_end_to_end_flagged_file_content_never_reaches_markdown_report`) |
| `sarand doctor` command (§4.11) | **Implemented, tested, and redesigned for readability** — `sarand --doctor` (flag, not a subcommand — see Phase C note below): checks Python version (critical), Rust core, persisted config, and 15 tool binaries, now grouped into two `rich.table.Table`s (Core, then per-language tools) inside `rich.panel.Panel`s instead of a flat list — a maintainer read the flat version as "many things sarand doesn't support" rather than "optional external tools you can install if you use that language"; each row now states explicitly what it's used for (e.g. "--security", "Gradle & Android projects"). Real `rich` isn't available in the build sandbox, so the visual result is unverified by the assistant — confirm it looks right on-device |
| HTML dashboard renderer | **Implemented and tested** — `renderers/html.py`, self-contained single file (inline CSS, no external assets), dark-mode, collapsible `<details>` sections, properly HTML-escaped |
| PDF / SARIF renderers | **Implemented and tested** — `renderers/sarif.py` (valid SARIF 2.1.0 JSON: secret findings as located errors, TODOs as located notes, tool warnings/errors unlocated). `renderers/pdf.py` shells out to an installed `wkhtmltopdf`/`weasyprint` on the HTML renderer's output rather than adding a heavy Python PDF dependency — gates cleanly with a fix-it message if neither is present. Verified end-to-end: real PDF produced (`%PDF-1.4` magic bytes, 42 KB) via `wkhtmltopdf` |
| Incremental scan cache | **Implemented and tested** — opt-in via `--cache` (deliberately NOT default; see the rationale in Phase E notes below and §4.8). Scoped to the Python side only: skips re-scanning TODOs/secrets in files whose content hash is unchanged since the last `--cache` run for the same project; does not change how `walker.rs` itself works. Cache lives under the *output* dir (`.sarand-cache/`), never inside the scanned project. Auto-invalidates if the detection rules themselves change (`rules_fingerprint`). `--clear-cache` wipes it. Verified end-to-end on a real 3-run sequence: cold run, warm run (byte-identical report, confirmed via matching SHA256), and a changed-file run that correctly found a newly added FIXME marker while still skipping the untouched file |
| Additional language analyzers (C/C++, Java/Kotlin, Android, Zig, Dart, Ruby, PHP, Lua, Swift, C#, TypeScript, CSS, SQL, Kotlin, Shell, YAML, JSON, TOML, XML, R, Perl, Julia, Objective-C, Groovy, PowerShell, Nix) | **All implemented and tested — 40 analyzers total (Markdown added in the P0 round, Assembly in §5.17, eight more in §5.18).** C/C++, Java/Kotlin, Android landed first (Phase C); Lua, Ruby, PHP, Dart/Flutter, TypeScript, CSS, Zig, Swift, SQL, Kotlin, C#, Shell, and the YAML/JSON/TOML/XML format analyzers (§5.4) landed in the first post-§4 round; R, Perl, Julia, Objective-C, Groovy, PowerShell, and Nix landed in a second round (§5.8) — see §5 for the conventions established along the way (bundler-wrapped-tool pattern, complementary-match analyzers, honest-empty precedent, format-analyzer category). Full roster in §5.6/§5.9 |
| Packaging (pipx, Docker, AUR, Homebrew, deb/rpm, standalone binary) | **pipx: implemented and confirmed** — `pipx install ~/sarand` builds the Rust extension inside pipx's isolated venv and installs cleanly; `sarand --doctor` confirmed "Rust core: compiled and loaded" post-install, no manual venv/PATH steps needed. `install.sh` added (§4.13) so upgrading an existing pipx install actually picks up new code — a raw `pipx install` over a stale copy silently doesn't, since pipx installs aren't editable by default. LICENSE (MIT) and full `pyproject.toml` metadata (classifiers, keywords) added. **AUR: `pkgs/aur/PKGBUILD` written**, not yet verified with a real `makepkg -si` in a clean chroot (see Phase F, still open). Docker/Homebrew/deb/rpm/binary: not started |
| Report replacement (§4.13) | **Implemented and tested** — `cli.py::remove_previous_report` explicitly checks for, removes, and announces a previous report (+ its `.sha256`) at the exact output path before writing a new one, for the same "check, remove, announce, create fresh" reason as `install.sh` |
| `--full` flag | **Implemented and tested — completeness gaps found and fixed 2026-09-18.** Forces `--quality`+`--security` on and removes the file-size/tree-depth/tree-entry truncation limits (raised to effectively-unlimited sentinel values), while still letting an explicit `--max-depth`/`--max-entries`/`--max-file-size` win over `--full`'s own defaults. An external audit of a real `--full` report found this description was not the whole truth: the **rendering layer** ignored `--full` entirely — a *passing* tool's output was always cut to an 80-line tail (raw output only shown on FAIL), issue lists capped at 500 rows and TODOs at 100 regardless of `--full`, and **`--format json` never embedded source code at all** (`include_source` was accepted in the signature and silently never read — the one format most likely to be piped straight into another AI's context had zero source, full stop). All four fixed: `config.full` is now stored on `SarandConfig` and threaded into every renderer as `full_output`; JSON gained a real `source_files: [{path, size, content}]` array; markdown/html now show a passing tool's full raw output and uncap issues/TODOs under `--full`. See §5.10 for what's still open (git history/contributor/hotspot depth) |
| `scripts/paste_chunks.py` | **Rewritten from a maintainer-supplied script and merged in** — chunked, resumable paste helper for chat UIs without file upload (e.g. pasting a `sarand --full` report into ChatGPT). Generalized from a hardcoded README.md/BiMarz-specific tool to work on any file, with per-source-file state namespacing (mirrors `core/cache.py`'s per-project namespacing). Fixed three real bugs found on review (dead `initialize` param, a shallow-copy rollback that only worked by accident, a UX trap where re-running with no flags mid-block silently repeated chunk 0 instead of continuing) — see the module's own docstring for details. Added OSC52 terminal-escape-sequence clipboard support as the primary copy mechanism, since it is the *only* clipboard method that works at all on the maintainer's actual hardware (non-rooted Android, Termux/Kali NetHunter proot, no X11/Wayland session) — `xclip`/`xsel`/`wl-copy` have no display server to talk to there. `OSC52_MAX_BYTES = 6000` applies to the raw text *before* base64 encoding (an empirically-tested ceiling on that hardware/terminal combination, not the final escape-sequence length) |
| CI | **Was green on all three OSes at run #3; NOT confirmed green since run #44 (see §5.13/§5.14) — re-confirm after the latest push** — public at `github.com/msoleimani62/sarand`. Two real issues found and fixed across the first three runs (see Phase G notes): a CI-infra bug (`maturin develop` needs a virtualenv CI runners don't have) and a genuine cross-platform test-isolation bug (two tests relied on `XDG_CONFIG_HOME`, which the product code only honors on Linux by design — the product code was correct, the tests weren't platform-independent). Run #3: `ubuntu-latest`, `macos-latest`, `windows-latest` all passed |

---
| pipx install robustness | **A real pipx bug hit and worked around** — pipx's own internal per-venv metadata can get corrupted independently of anything sarand does ("Unknown metadata version N. Perhaps it was installed with a later version of pipx" — a known upstream issue, <https://github.com/pypa/pipx/issues/1619>). When it happens, `pipx list` silently omits the corrupted entry AND `pipx uninstall` fails the same way trying to read it, so `install.sh` now falls back to removing `~/.local/share/pipx/venvs/sarand` directly if either the venv is present-but-untracked or `pipx uninstall` itself fails |
| Android/Kotlin priority | **Implemented ahead of the general "more languages" backlog**, per an explicit maintainer request (upcoming Android tooling work). `.kts`/`.xml`/`.gradle`/`.properties` added to essential extensions (Kotlin build scripts, manifests, layouts, config); `local.properties`/`*.jks`/`*.keystore`/`google-services.json` added to the secret-filename exclusion list (§4.10) — Android projects commonly put SDK paths and sometimes signing credentials in exactly those files. `discovery/android.py` holds the shared detection logic (`is_android_project`) so both `discovery/project_detector.py` (report's top-line language label) and `analyzers/android_analyzer.py` use the same signal, in the dependency direction the architecture diagram implies (analyzers depend on discovery, not the reverse) |

---

## 7. Priority hierarchy

When principles conflict, resolve the conflict in this order:

1. **Security & data safety** — highest priority, without exception
   (§4.10 exists because of this).
2. **Correctness & stability** — the system must behave reliably.
3. **Sound architecture** — modularity, clean boundaries, zero import
   cycles (§4.1).
4. **Performance & resource optimization** — optimize responsibly, not
   prematurely (§4.7).
5. **Maintainability & clean code** — readable, sustainable code.
6. **Development velocity** — speed matters only once everything above is
   satisfied.

---

## 8. Roadmap (in priority order)

### Phase A — Test suite ✅ done, confirmed with real `pytest`

`tests/` exists with pytest-compatible coverage of every module marked
"Implemented" in §6. Next concrete step: maintainer runs `pytest -v` for
real and reports the output back. **Confirmed** — 42/42 passed, including the Rust-vs-fallback cross-check (`test_rust_and_python_paths_agree_on_fixture_project`).

### Phase B — Security checks + secrets exclusion ✅ done

Implemented exactly as scoped: `LanguageAnalyzer.run_security` per
language (pip-audit/bandit, cargo-audit, govulncheck, npm audit), wired
behind `--security`, plus §4.10's filename- and content-based secret
exclusion (both always-on, not gated behind any flag). One design
refinement made during implementation, worth noting for future readers:
a content-level secret finding now removes that file from source
embedding entirely (`core/secrets.py::exclude_flagged_files`) rather than
just recording a warning next to an unredacted dump of the same file —
the first version of this phase had exactly that gap, caught by writing
the end-to-end regression test before declaring it done (§4.8 in
practice).

### Phase C — `sarand doctor` + more language analyzers ✅ done (Lua/Ruby/PHP/Dart added later; Zig/Swift/C# still deferred)

- `sarand doctor` implemented as a **flag** (`sarand --doctor`), not a
  subcommand — the CLI is argparse-flag-based throughout (see
  `--set-output-dir` for the same early-exit pattern), and introducing
  subcommands would be a separate, larger CLI restructuring not scoped
  into this phase. Checks Python version (the one critical check), Rust
  core availability, the persisted config location, and 13 per-language
  tool binaries — every failing check prints a fix-it command, nothing
  fails silently (§4.11).
- Added `analyzers/cpp_analyzer.py` (CMakeLists.txt → `ctest` if a
  configured build dir exists, `clang-format --dry-run` if configured,
  `cppcheck` for security) and `analyzers/java_analyzer.py` (pom.xml or
  build.gradle(.kts) → `mvn`/`gradle`, preferring a project's own
  `./gradlew` wrapper over a system Gradle). Both deliberately never
  invoke `cmake configure`/`cmake --build`/a full Gradle sync themselves
  — see the "heavy dependency" warning rule in §3; they only run
  against a build the user already configured.
- `analyzers/lua_analyzer.py` added later (rockspec/init.lua/main.lua,
  `busted` for tests, `luacheck` for quality, no standard security-audit
  tool for Lua so `run_security` returns `[]`).
- `analyzers/ruby_analyzer.py`, `analyzers/php_analyzer.py`,
  `analyzers/dart_analyzer.py` added later:
  - Ruby: `Gemfile`/`*.gemspec` → `bundle exec rspec` (or `bundle exec
    rake test` if no `spec/` but a `Rakefile` exists) for tests,
    `bundle exec rubocop` for quality, `bundle exec bundler-audit` for
    security. Everything goes through `bundle exec` deliberately, never
    a bare global binary, so the `Gemfile.lock`-pinned tool versions are
    what actually runs.
  - PHP: `composer.json` → PHPUnit for tests, PHPStan for quality,
    `composer audit` for security. Prefers a project-local
    `vendor/bin/<tool>` over a global binary of the same name — a
    globally-installed PHPUnit/PHPStan can easily be a different major
    version than what the project's own `composer.json` expects.
  - Dart/Flutter: `pubspec.yaml` → `dart test`/`dart analyze`, or
    `flutter test`/`flutter analyze` instead when the project actually
    declares a `flutter:` dependency (checked by content, not just
    whether the `flutter` binary happens to be installed on the
    machine). No `run_security`: no broadly standard vulnerability-audit
    tool exists yet for this ecosystem (as of this writing) — returning
    `[]` here is honest about that rather than reaching for something
    that doesn't fit, same precedent as Lua.
- Zig, Swift, C#, TypeScript, CSS, SQL, Kotlin, Shell, and the
  YAML/JSON/TOML/XML format analyzers were added in later rounds —
  see §5 for the conventions established along the way. Phase C is
  now fully closed.

### Phase D — Additional renderers ✅ done

- `renderers/html.py`: dashboard-style HTML report (dark mode, collapsible
  sections). Reuses `ReportData` as-is — no data-model changes needed.
- `renderers/sarif.py`: valid SARIF 2.1.0, following the `Renderer`
  protocol exactly like every other text-based renderer.
- `renderers/pdf.py`: **does not** implement the `Renderer` protocol —
  PDF is binary, not a string. It shells out to an installed
  `wkhtmltopdf`/`weasyprint` against the HTML renderer's own output
  (reuse, not reinvention) via `render_to_file(data, output_path)`, and
  `cli.py` special-cases `"pdf"` in its output-writing branch for exactly
  this reason. This was a deliberate deviation from "each renderer
  implements the same `render() -> str` signature" — forcing PDF into
  that shape would have meant either a heavy new Python PDF dependency
  (risky to compile on Termux, see §3) or awkwardly base64-encoding
  binary bytes through a string return. Document any future
  protocol-breaking renderer the same way: state why, right here.

### Phase E — Incremental scan cache ✅ done, scoped down from the original plan

Implemented as `core/cache.py`, opt-in via `--cache`. Deliberately
narrower than the original plan of "skip re-hashing/re-counting
unchanged files" at the `walker.rs` level: making the Rust walker itself
cache-aware means it has to accept and consult a cache map from Python,
which is a real Rust-code change that can't be compile-verified without
a local toolchain (§4.8) — too risky to ship unverified after the
`PyDict::new` lesson (§4.6). Instead this phase stays entirely on the
Python side of the `rust_bridge.py` boundary: it reuses the
`content_hash` Rust/the fallback already compute for free, and skips the
*Python-side* re-scan of file content for TODOs and secrets when a
file's hash is unchanged. `walker.rs` still processes every file on
every run — which is fine, since Rust's own pass was never the
bottleneck this phase was meant to address; the redundant *Python*
regex scanning over full file content (once for TODOs, once for
secrets, on every included file, every run) was.

Opt-in, not default, for the same reason `slow_external` pytest tests
are opt-in-to-skip rather than opt-in-to-run: a stale-cache bug's
failure mode is a silently wrong report (a real finding hidden because
the cache claimed "unchanged"), and the safe direction to fail is doing
more work than necessary, not less. A `rules_fingerprint` (hash of every
TODO/secret pattern) auto-invalidates the whole cache if detection logic
ever changes, so a future Phase-B-style pattern addition can't silently
miss findings in files a stale cache still thinks are "clean."

If a *deeper* cache (skipping Rust-side hash/linecount work too) is
ever wanted, that's a distinct, larger follow-up requiring an actual
Rust change and real compile verification — don't conflate the two.

### Phase F — Packaging

**pipx: done and confirmed on-device.** `pipx install ~/sarand` builds
the Rust extension inside pipx's own isolated environment and installs
cleanly — confirmed via `sarand --doctor` reporting "Rust core:
compiled and loaded" post-install, with no manual venv activation or
PATH editing needed. `LICENSE` (MIT) added, `pyproject.toml` gained
classifiers/keywords, README's install section now leads with pipx
specifically *because* this project's history includes several rounds
of manual venv-activation/PATH confusion that pipx sidesteps entirely.

**AUR: PKGBUILD written, not yet submitted/confirmed by a real
`makepkg` build.** `pkgs/aur/PKGBUILD` builds from the GitHub release
tarball (`v$pkgver`) via the standard Arch PEP517 pattern
(`python -m build --wheel --no-isolation` + `python -m installer`),
with `rust`/`python-maturin` as makedepends so the PyO3 extension
compiles the same way `pipx install` already does. `check()` runs the
real pytest suite (minus the Rust-vs-fallback parity test, which
needs the compiled `._core` module installed into the *same*
environment pytest runs in, not just built as a wheel) — everything
else already tolerates missing optional tools by design (Phase A/C),
so this is a meaningful check, not a rubber stamp. Still open before
this counts as done: run an actual `makepkg -si` in a clean chroot
(`extra-x86_64-build` or similar) to catch anything only a real build
surfaces, regenerate `.SRCINFO` from that build
(`makepkg --printsrcinfo > .SRCINFO`, never hand-edited), confirm the
`sarand` name is free on aur.archlinux.org, then `git push` to the AUR
git remote.

**Reordering the remaining targets from the original plan:** the
original order was Docker → AUR → Homebrew → deb/rpm → binary. Nothing
in this project's actual usage (Android/Termux/Kali NetHunter phone +
Arch Linux laptop) involves Docker — there's no described workflow that
needs it, and running a container inside a Termux proot is its own can
of worms. AUR is directly useful (the maintainer runs Arch daily).
Remaining order once AUR is confirmed: Docker/Homebrew/deb/rpm/binary
only if a real need for them shows up later — don't build packaging
for platforms nobody described using, mirroring the same "don't
pre-build analyzers for languages nobody asked to scan" principle from
Phase C.

One packaging target per phase, verified working, before starting the
next -- this is the rule that kept Phase F from becoming "try to do 6
packaging systems in one pass and verify none of them."

### Phase G — CI ✅ done, confirmed green on all three OSes

The repo is now public at `github.com/msoleimani62/sarand`.

**Run #1 (CI infra)**: `maturin develop --release` requires an active
virtualenv (`VIRTUAL_ENV`, `CONDA_PREFIX`, or a `.venv` folder) to know
where to install into -- the maintainer's own machine always has one
(the pipx/dev-venv setup), but a fresh GitHub Actions runner does not.
Fixed by switching the workflow from `maturin develop` to `maturin
build --release --out dist` + `pip install dist/*.whl` -- `build` has
no virtualenv requirement, and installing that wheel covers both "the
code works" and "a release wheel actually builds" in one step. Also
added `defaults: run: shell: bash` so wheel-glob installs behave
identically across the OS matrix.

**Run #2 (real product-vs-test bug, worth remembering)**:
`ubuntu-latest` passed clean. `macos-latest` and `windows-latest` both
failed on `test_output_dir_uses_persisted_config_when_present` (and
`..._falls_back_to_default_when_nothing_set` was quietly relying on the
same shaky isolation). Root cause: the tests set `XDG_CONFIG_HOME` to
redirect where `get_config_dir()` looks -- but `get_config_dir()` only
honors that variable on Linux, by design (§ its own docstring: macOS
uses `~/Library/Application Support`, Windows uses `%APPDATA%`). **The
product code was correct the whole time**; the test's isolation
technique just wasn't cross-platform. This is exactly the kind of bug
CI exists to catch -- it had been silently passing locally (Linux-only
development environment) since the test was written. Fixed by
monkeypatching `sarand.userconfig.get_config_dir` directly (save the
original, replace with a lambda returning a temp path, restore in
`finally`) instead of the env var -- this isolates the test from every
platform's real config location at once, correctly, rather than only
happening to work on whichever OS wrote the test.

**Confirmed**: run #3 passed on all three OSes (Linux, macOS, Windows).
Phase G is done -- CI is now the scheduled safety net §4.8 talks about,
not just an aspiration.

### Phase H — `--full` git-history depth ⏸️ DEFERRED (kept as a reminder, not a priority)

**2026-09-19 update**: maintainer decision — this is *not* worth
building right now. `sarand`'s own projects (this one, `ramz`, `odl`,
etc.) are all solo-developer repos, so `contributors`
(`git shortlog -sn`) would always render as one name at 100% — a field
with zero signal for a single-author project. `total_commits`/
`full_log`/`hotspots` were judged individually reasonable but the
maintainer chose to prioritize language/tool coverage (P0 below)
instead for now. Kept here, unimplemented, specifically so a future
session doesn't have to rediscover the git-stats gap from scratch --
re-read this whole section before starting it, don't just skim the
one-line summary. Re-evaluate `contributors` specifically if this ever
gets picked up in a context with multiple committers; it stays
low-value for every project this maintainer currently runs it on.

Flagged directly by the maintainer (2026-09-18): `--full` is supposed to
be sarand's single most-complete artifact — full tests, full source,
full git statistics, built specifically to hand to an AI model without
the maintainer having to assemble any of it by hand. The rendering-layer
half of that promise was broken and is now fixed (§6's `--full` row,
§5.10). The **git-statistics half is still genuinely shallow** and is
the next thing to fix, before any further language analyzers or
supply-chain tooling (§5.10's P0–P3 list stays lower priority than this).

Current state (`scanners/git.py::collect_git_snapshot`), confirmed by
reading the module directly, not assumed:

- `git log --oneline -20` — **hardcoded to the last 20 commits only**,
  regardless of `--full`. No total commit count, no full history.
- No `git shortlog -sn` (or equivalent) — zero contributor/authorship
  stats anywhere in the report.
- `git diff --stat` only covers the current uncommitted working-tree
  diff — no per-file change-frequency / "hotspot" analysis (which files
  churn most across history is exactly the kind of signal an AI
  reviewer benefits from and a human wouldn't compute by hand).
- No repo age / first-commit date, no branch count, no `.gitattributes`
  or submodule awareness.

Scoped plan for next session:

1. Extend `GitSnapshot` (`models/results.py`) with new fields: `total_commits`,
   `contributors: list[tuple[str, int]]` (name, commit count, via
   `git shortlog -sn --no-merges`), `full_log: str | None` (only populated
   under `--full` — normal runs keep the existing `-20` summary to stay
   fast and readable), `hotspots: list[tuple[str, int]]` (path, times
   changed, via `git log --format= --name-only | sort | uniq -c | sort -rn`,
   capped like everything else *except* under `--full`), `first_commit_date`.
2. Every new call joins the existing `asyncio.gather` in
   `collect_git_snapshot` (§4.7 — independent commands, run concurrently,
   not appended sequentially).
3. Thread `full: bool` into `collect_git_snapshot(root, *, full: bool = False)`
   the same way renderers now take `full_output` (§5.10) — `full_log`/
   uncapped `hotspots` only computed when true, so a normal run's git
   step doesn't get slower for data most runs don't need.
4. Render in markdown/html/json — a `## Git history` section (commit
   count, top contributors, hotspot files) alongside the existing
   branch/commit/dirty/tags/stash block, not replacing it.
5. Regression test mirroring `tests/scanners`'s existing git test
   pattern (real repo in a tmpdir, `git init` + a few commits, assert
   `total_commits`/`contributors`/`hotspots` come back correct) — not
   yet written, since this whole phase is not yet started.

---

## 9. Definition of done

A task in this repo is not done until:

1. Python changes are import-tested and run end-to-end against a real or
   throwaway project directory.
2. Any Rust change has been confirmed by the maintainer actually running
   `maturin develop --release` and reporting success (§4.6, §4.8).
3. The pure-Python fallback path (§4.5) still produces equivalent output —
   verify by running in an environment where `sarand._core` was never
   built.
4. This document is updated if the change affects architecture, adds a
   new rule, or changes the roadmap/status tables (§6, §8).
5. No project-specific hardcoding was introduced (§4.2), no external tool
   runs unconditionally (§4.3), and no secret-shaped file was embedded in
   a report (§4.10).

---

## Final rule

Every contribution to sarand must improve the project without sacrificing
security, stability, architecture, user experience, or long-term
maintainability. When in doubt, re-read §7.

## §5 — Analyzers added post-§4 (Ruby/PHP/Dart/Lua/TS/CSS/Zig/Swift/SQL/Kotlin/C#/Shell/YAML/JSON/TOML/XML)

This section documents conventions established after the original §4
analyzer set, in the order they came up. Treat it as additive to §4,
not a replacement.

### 5.1 — Bundler-wrapped-tool false-failure pattern (RubyAnalyzer)

`bundle exec X` can fail two structurally different ways that both
look like "command not found" at the exit-code level:

1. `bundle` itself isn't installed (`shutil.which("bundle") is None`)
   -- checked before ever invoking a command.
2. `bundle` **is** installed, but the gem providing `X` isn't
   (`bundle install` was never run) -- `bundle exec X` still exits
   127, but with `bundler: command not found: X` in its own output,
   not the shell's "command not found".

Only case 1 was originally checked. Case 2 was silently reported as a
real failure. Any analyzer that shells out through a wrapper binary
(`bundle exec`, `npx`, `poetry run`, etc.) must check for the
wrapper's own "the wrapped tool is missing" message, not just the
wrapper's own presence, before treating a nonzero exit as a genuine
failure. See `ruby_analyzer.py`'s `_bundle_exec_missing_gem()` for the
concrete pattern.

### 5.2 — Complementary-match analyzers (no exclusivity assumed)

Starting with TypeScriptAnalyzer/NodeAnalyzer, several analyzer pairs
are designed to **both** match the same project at once rather than
one excluding the other:

- `TypeScriptAnalyzer` + `NodeAnalyzer` on a TS project
- `KotlinAnalyzer` + `JavaAnalyzer` on a Kotlin Gradle project
- Any format analyzer (§5.4) alongside whatever language analyzer
  already claims that same file for a different purpose (e.g.
  `YamlAnalyzer` + `DartAnalyzer` both matching `pubspec.yaml`,
  `TomlAnalyzer` + `RustAnalyzer` both matching `Cargo.toml`,
  `XmlAnalyzer` + `JavaAnalyzer` both matching `pom.xml`)

The rule: when a "narrower" analyzer's whole contribution is a single
extra check (a type-check, a style-linter, a syntax-linter) that a
"broader" analyzer either can't do or deliberately doesn't attempt,
add it as a second analyzer that also matches, with
`run_tests`/`run_security` returning `None`/`[]` and a docstring note
explaining which other analyzer owns that responsibility -- never
make the narrower one exclude the broader one's matches() just to
avoid "double-counting" a project.

This is *not* the same thing as genuine mutual exclusivity
(`AndroidAnalyzer` vs `JavaAnalyzer`, `JavaAnalyzer` deferring on
Android detection): that stays exclusive because running Java's
Maven/Gradle test flow AND Android's Gradle test flow on the same
project would be genuinely redundant/conflicting, not complementary.

### 5.3 — Honest-empty precedent, formalized

`run_security` returning `[]` and/or `run_tests` returning `None` is
not a gap to be filled later -- it is the correct, deliberate answer
whenever no broadly standard tool exists for that concern in that
ecosystem. Established across `DartAnalyzer`, `LuaAnalyzer`,
`CssAnalyzer`, `SqlAnalyzer`, `ZigAnalyzer`, `SwiftAnalyzer`, and every
format analyzer in §5.4. Do not invent a check just to have something
in that slot; do not treat an empty result here as a TODO.

### 5.4 — Format analyzers: a distinct third category

Alongside "language analyzer" (build system + test/quality/security
tool trio) there is now a second shape: **format analyzer**
(`YamlAnalyzer`, `JsonAnalyzer`, `TomlAnalyzer`, `XmlAnalyzer`). These
lint a data/config format, not a programming language:

- `matches()` is a **shallow, top-level-only** file-extension or
  config-file check -- same discipline as `LuaAnalyzer`/`CssAnalyzer`
  (§4's precedent, now the standard for every format analyzer too). A
  file three directories deep inside `node_modules` or any vendored
  dependency must never trigger a project-level match.
- `run_tests` always returns `None` -- no format has an executable
  test-suite concept.
- `run_security` always returns `[]` -- see §5.3.
- `run_quality` runs exactly one linter, gated on that linter's
  binary via `shutil.which`, skipping cleanly (never crashing) if
  absent.
- These intentionally match **independently** of whatever
  language analyzer already claims the same file for a build-system
  purpose -- see §5.2. A format analyzer is never scoped down to
  "only the files no other analyzer already claimed."

**Exception -- JsonAnalyzer's stdlib fallback:** every other analyzer
in sarand skips cleanly when its tool binary is missing. `JsonAnalyzer`
is the one deliberate exception: JSON syntax validation needs no
external tool at all (Python's own `json` module already does it), so
when `jsonlint` isn't installed, `run_quality` validates syntax via
`json.loads()` directly instead of skipping. Skipping instead of
validating would be strictly worse for no reason. `jsonlint` is still
preferred when present since it also catches style issues, not just
parse errors. Do not generalize this exception to other analyzers
without the same "the check needs no external tool" justification.

### 5.5 — `--doctor` output: panels, not a table

The original `--doctor` table (5 columns: Category/Tool/Status/Used
for/Fix) truncated every cell to an unreadable sliver on a phone-width
terminal (Termux, SSH from a small screen). It was replaced with one
`rich.panel.Panel` per category, containing plain wrapped text lines
(`✓`/`○` icon, tool name, `used_for` on its own line, `fix` on its own
line only when missing). Plain wrapped text degrades gracefully at any
width -- narrower terminals just wrap onto more lines; nothing is ever
truncated or ellipsized. `collect_checks()` and `_CATEGORY_ORDER`
stayed the same shape specifically so this redesign didn't touch any
existing test; only `_print_core`/`_print_language_tools` changed.
Any future `--doctor` UI change should preserve this: data
(`collect_checks`) and presentation (`_print_*`) stay decoupled.

### 5.6 — Full analyzer roster after this round

Language analyzers (test + quality + security trio, one build-system
marker each unless noted): Python, Rust, Go, Node.js, C/C++, Java
(Maven/Gradle, defers to Android), Android, Lua, Ruby, PHP,
Dart/Flutter, Zig, Swift (SwiftPM primary, `xcodebuild` fallback for
Xcode-only projects), C# (`dotnet`).

Complementary quality-only analyzers (§5.2): TypeScript (adds `tsc
--noEmit` to a Node.js project), Kotlin (adds `ktlint`+`detekt` to a
Java/Gradle project), CSS (independent, or complements
Node.js/TypeScript), SQL (independent), Shell (independent,
`shellcheck` + optional `bats`).

Format analyzers (§5.4): YAML, JSON (stdlib fallback, §5.4), TOML,
XML.

(See §5.8/§5.9 for the second round: R, Perl, Julia, Objective-C, Groovy, PowerShell, Nix.)

### 5.7 — Release/tag discipline

`pyproject.toml` and `Cargo.toml` versions must be bumped together
(same value) on every release commit. Before tagging, check
`git tag -l 'v*' | sort -V` for the actual latest tag -- earlier
sessions left the local `pyproject.toml` version out of sync with
real tags more than once (a tag existed for a version number that
`pyproject.toml` was about to reuse for an unrelated commit). When in
doubt, `git fetch --tags` and compare against `git log -1 <tag>`
before creating a new one, rather than trusting the working tree's
current version number alone.

### 5.8 — Second post-§4 round: R, Perl, Julia, Objective-C, Groovy, PowerShell, Nix

Same conventions as §5.1-§5.4, applied to seven more ecosystems, plus
one addition: real project-marker languages that had no
ecosystem-standard vulnerability-audit tool at all (not just "gated on
a binary" — genuinely nothing broadly adopted exists) now lean on the
honest-empty precedent (§5.3) far more heavily than the first round
did. R (`DESCRIPTION`), Perl (`cpanfile`), and Julia (`Project.toml`)
all ship `run_security` as an unconditional `[]` — pip-audit/
cargo-audit/npm-audit-style tooling simply doesn't exist for these
ecosystems as of this writing.

Two new marker-detection shapes:

- **Two-signal complementary match**: GroovyAnalyzer (mirrors
  KotlinAnalyzer, §5.2) requires *both* a Gradle marker *and* actual
  Groovy source (`src/main/groovy` or a top-level `.groovy` file)
  before matching — a bare `build.gradle` alone is not enough, since
  nearly every Gradle project has one regardless of source language.
  ObjectiveCAnalyzer's relationship to SwiftAnalyzer is the same
  complementary idea, though its own gate (Podfile / top-level
  `.m`/`.mm` / Xcode project) is single-signal, not two-signal.
- **Self-contained duplication over cross-analyzer imports**:
  ObjectiveCAnalyzer needed the same `xcodebuild -list -json`
  scheme-detection helper SwiftAnalyzer already has. It was
  duplicated locally rather than imported from `swift_analyzer.py` --
  every analyzer file stays self-contained by convention, so adding
  one language never risks touching another analyzer's file or its
  tests.

Extension-fallback additions
(`discovery/project_detector.py::_guess_from_extensions`): `.r`,
`.pl`/`.pm`, `.jl`, `.m`/`.mm`, `.groovy`, `.ps1`/`.psm1`/`.psd1`,
`.nix` all added, same reasoning as §5.6's format analyzers — a lone
script file with no build-system marker should still resolve to
*something* better than "Unknown".

### 5.9 — Full analyzer roster after the second round

30 built-in analyzers total (`grep -c "Analyzer()," \
python/sarand/analyzers/registry.py` to reconfirm after any future
addition). Real project-marker additions this round: R
(`DESCRIPTION`), Perl (`cpanfile`), Julia (`Project.toml`).
Complementary/shallow additions: Objective-C (Podfile/`.m`/`.mm`/
Xcode, complements Swift), Groovy (Gradle + real Groovy source,
complements Java/Kotlin), PowerShell (top-level
`.ps1`/`.psm1`/`.psd1`, no manifest), Nix (top-level `.nix`;
`flake.nix` gets real `nix flake check` tests, unlike the other
shallow analyzers in this round).

### 5.10 — Quality/security depth round (cargo-deny, mypy, rustfmt/clippy independent gating) + external-audit roadmap

Triggered by a maintainer-supplied external report auditing `sarand
--doctor`'s tool coverage (2026-09-18). Two things worth recording
about the report itself before the findings: (1) it claimed Rust only
checked `cargo-audit` — false, `run_quality` already ran `cargo fmt
--check` and `cargo clippy`, so always verify a report's claims
against the actual source before acting on them, same lesson as
§5.6's "user pushed back... some factually wrong" note; (2) its
primary type-checker recommendation was `pyright` — rejected, because
this project already pins `mypy>=1.10` as its type-checker of record
(`pyproject.toml [dev]`, `ci.yml`'s "Run mypy" step); adding pyright
instead would mean `--doctor`/`--quality` disagree with what CI
actually enforces. `mypy` was simply never wired into
`PythonAnalyzer.run_quality` before now — a CI-only gate, exposed
through the tool for the first time here.

What shipped this round:

- `RustAnalyzer.run_quality`: `rustfmt` and `cargo-clippy` binaries
  now checked **independently** (each is its own rustup component,
  not guaranteed just because `cargo` is present) — a missing one
  skips cleanly instead of the subprocess call failing with a
  confusing toolchain error that reads like a real lint failure.
- `RustAnalyzer.run_security`: added `cargo deny check`
  (advisories/bans/licenses/sources — broader than `cargo-audit`'s
  vulnerability-only scope), gated on both the `cargo-deny` binary
  *and* a `deny.toml` in the project root (§4.3 — cargo-deny errors
  confusingly without one, so its presence is the real marker).
  **Real bug caught during review, not shipped**: the first draft
  gated `cargo-deny` behind `cargo-audit`'s own binary/`--skip-audit`
  check, meaning a machine with `cargo-deny` but not `cargo-audit`
  would never run it. Fixed by making `_run_cargo_audit` and
  `_run_cargo_deny` fully independent, run concurrently via
  `asyncio.gather` (§4.7) — same shape as `python_analyzer.py`'s
  pip-audit+bandit pair.
- `PythonAnalyzer.run_quality`: added `mypy .` (mirrors `ci.yml`'s own
  invocation exactly), skips cleanly if not installed.
- `doctor.py`: new rows for `rustfmt`, `cargo-clippy`, `cargo-deny`,
  `mypy`.
- sarand's own `deny.toml` was **not** added as part of this round —
  out of scope (needs a real license/advisory policy decision, not a
  mechanical addition) — so `cargo deny check` will show as skipped
  ("no deny.toml") on this repo itself until that's written.

Roadmap for languages/tools *not* done yet, in the report's own
priority order (P0 = next, P3 = last — and all of it sits behind
Phase H above, which the maintainer flagged as higher priority than
any new language/tool coverage):

**P0 — done 2026-09-19**: Node.js — `eslint` added (project-aware: a
config-file gate, `_ESLINT_CONFIG_FILES`, both legacy `.eslintrc*` and
flat-config `eslint.config.*`; skips cleanly with no config, matching
the report's own "don't run a meaningless check just because the
binary exists" caution), run independently of the pre-existing
"npm run lint" (a project can have an ESLint config with no "lint"
script wired up, or a "lint" script that runs something unrelated).
**`npm audit` was already implemented before this round** — the
report's claim it was missing was stale, second time this exact class
of error has happened (see the Rust claim at the top of this section);
always verify against source before agreeing something is missing.
Go — `staticcheck` added alongside the existing `go vet`, deliberately
not `golangci-lint` (the report's own "core, not a 200-tool installer"
reasoning). C/C++ — `clang-tidy` added, gated on `compile_commands.json`
(root or a known build-dir candidate — clang-tidy without one mostly
produces noise, same §4.3 reasoning as `_configured_build_dir` for
ctest). **`clang-format` was already implemented** (gated on
`.clang-format`) — the one language in this report where the missing-
tool claim was actually correct. Shell — `shfmt -d` added alongside
the existing `shellcheck`, independent binary/skip path (formatting
and linting are unrelated concerns, same split as
`ruff check`/`ruff format` and `cargo clippy`/`cargo fmt`). Swift —
`swiftlint` added alongside the existing `swift-format`, deliberately
**not** config-gated (unlike eslint, swiftlint ships sensible defaults
and is designed to run unconfigured). New `MarkdownAnalyzer` —
`markdownlint`, shallow top-level-file detection, no-manifest, same
shape as YAML/JSON/TOML/XML in §5.4; registered in `registry.py`
alongside the other format analyzers. `doctor.py` gained rows for all
six tools plus a new `"Markdown"` category in `_CATEGORY_ORDER`.
`test_doctor_v2.py::test_p0_language_depth_round_checks_are_registered`
and `test_markdown_analyzer.py` cover the additions; pre-existing
tests that hardcoded a shorter expected tool set for C/C++/Shell/Swift
(`test_cpp_java_analyzers.py`, `test_shell_analyzer.py`,
`test_swift_analyzer.py`) were updated to match.

**P1 — done 2026-09-19 (§5.11)**: `gitleaks` (secret scanning — complements, doesn't replace,
the existing content-regex scanner in `core/secrets.py`); `syft`
(SBOM generation); Java — SpotBugs + Checkstyle; PHP — `phpstan` +
`phpunit` discovered project-locally (`vendor/bin/`) rather than
requiring global installs, plus `composer audit`; Ruby —
`bundler-audit` made visible in `--doctor` specifically (the analyzer
already runs it via `bundle exec`, per §5.1's bundler-wrapped-tool
pattern — this is a doctor-visibility gap, not a missing check).

**P2 — partly done 2026-09-20 (§5.12: lockfile validation, dependency
inventory, advisory license check; per-project license policy still
open)** (supply-chain layer, needs real design, not mechanical
addition): dependency inventory per language (count + list, not just
"audit tool found: yes/no"); license policy/conflict detection
(MIT/Apache-2.0/GPL/LGPL/AGPL/BSD); reproducible-build/lockfile
validation checks.

**P3** (architecture, lower priority than P0–P2 despite sounding
foundational): a structured, machine-readable `--doctor` output mode
(`--doctor --format json`, mirroring the report renderers' own
`json_renderer.py`); project-local tool preference over global
installs, generalized beyond just the PHP case above; tool-version
compatibility checks.

**Explicitly not doing**: adding language coverage for its own sake.
§5.6's negotiation-then-deliver pattern (verify against
`registry.py`/`constants.py` before agreeing something is missing)
applies to this whole list too — re-check each item against the
current source before implementing, the same way this round's own
first draft found the report's Rust claim was already stale.

**Real on-device test bugs found running this round's own test suite**
(confirmed via a real `pytest -v` on the maintainer's device, not
assumed — §4.8): `test_dart_analyzer_run_tests_skips_cleanly_without_dart_or_flutter`,
`..._run_quality_skips_cleanly_without_dart_or_flutter`, and
`test_zig_analyzer_run_tests_skips_cleanly_without_zig` all asserted a
clean-skip path but never monkeypatched `shutil.which` — they silently
relied on the real machine not having `dart`/`flutter`/`zig`
installed. On a machine that has them (this maintainer's — a manual
Zig 0.16.0 install plus the Dart SDK), the tests ran real subprocesses
instead of exercising the skip path, and `zig build test` against an
empty `build.zig` fixture produced a genuine compile error. Fixed by
monkeypatching `shutil.which` to return `None`, the same pattern every
other "skips cleanly without X" test in the suite already uses (e.g.
§5.10's own `mypy`/`cargo-deny` tests above never hit this, precisely
because they did monkeypatch it from the start). The sweep of the
rest of the "without_<tool>" tests was done on 2026-09-20 with a
measured method instead of suspicion — see §5.12.

### 5.11 — P1 round: gitleaks, syft (SBOM), Java checkstyle/spotbugs, Ruby/PHP doctor-text (2026-09-19)

Full P1 list from §5.10 attempted in one round, at the maintainer's
explicit request ("کل لیست P1 ... همه رو با هم شروع کن"). Two of the
five items turned out to already be done -- same "verify against
source before implementing" lesson as every prior round:

- **PHP was already fully implemented** (phpunit + phpstan, both
  preferring `vendor/bin/<tool>` over global, plus `composer audit`) —
  nothing to add. `doctor.py`'s `composer` row already documented this.
- **Ruby's bundler-audit was already fully implemented** (`bundle exec
  bundler-audit check --update`, with the same `bundle exec`-missing-gem
  detection as rspec/rubocop) — the report's complaint was really about
  `doctor.py`'s `bundle` row being too vague ("running tests / --quality
  / --security" names nothing), not a missing feature. Fixed by naming
  the actual sub-tools (rspec/rake, rubocop, bundler-audit) in the
  `used_for` text and explaining *why* it's still one binary check, not
  three (`bundle exec <tool>` — no separate binary to check per tool).

What actually shipped:

- **gitleaks** (`core/gitleaks.py`) — project-wide, not a
  `LanguageAnalyzer` (no single language owns it), so it's invoked
  directly from `cli.py` and its `CommandResult` joins
  `security_results` alongside the per-language ones. Runs with
  `--redact` — not optional: without it gitleaks prints the actual
  matched secret into its own output, which sarand would then embed
  verbatim in the report, exactly the leak §4.10 exists to prevent.
  Detects `.git` presence to add `--no-git` for non-git working trees.
  Explicitly *not* SARAND_SKIP_AUDIT-gated: it's a local/offline scan,
  not a vulnerability-database network call, so that flag's "fixed
  external cost" reasoning (cargo-audit/pip-audit) doesn't apply.
- **syft** (`core/sbom.py`) — same project-wide shape, `syft dir:. -o
  table`. Purely informational (syft's exit code doesn't signal
  pass/fail the way gitleaks' does) — this is the P1-scope version;
  a real structured dependency inventory (counted, per-language,
  license-annotated) stays P2, deliberately not attempted here.
- **Java** `run_quality` was previously an intentional empty return
  (documented reasoning: linter configs vary too much to guess safely)
  — now runs checkstyle + spotbugs for **Maven**, via the same
  ad-hoc-full-coordinate trick `run_security` already used for OWASP
  dependency-check (`mvn -B org.apache.maven.plugins:maven-checkstyle-plugin:check`,
  works without any pom.xml declaration, Checkstyle's bundled Sun
  ruleset is a safe default). **Gradle has no equivalent ad-hoc path**
  — a task only exists if the project's own build file applied the
  plugin — so the Gradle side is genuinely gated on a real project
  marker (§4.3): grep `build.gradle(.kts)` for `"checkstyle"`/
  `"spotbugs"` before ever trying `checkstyleMain`/`spotbugsMain`,
  skip cleanly with a clear reason otherwise. This asymmetry (Maven
  ad-hoc-safe vs. Gradle marker-gated) is inherent to how the two
  build tools work, not an inconsistency to "fix" later.
- **`doctor.py`** — new `"Supply chain"` category (gitleaks, syft),
  Java's `mvn`/`gradle` rows and Ruby's `bundle` row got clearer
  `used_for` text.

Tests: `tests/test_gitleaks.py`, `tests/test_sbom.py` (new files),
Java quality tests added to `tests/test_cpp_java_analyzers.py`,
`test_doctor_v2.py::test_p1_supply_chain_round_checks_are_registered`.
**Not covered**: a `cli.py`-level integration test proving gitleaks/syft
results actually land in `security_results` end-to-end through
`run()` — the existing cli-level tests need substantial mock scaffolding
(`_RENDERERS`, `write_sha256`, `remove_previous_report`, ...) and
duplicating that scaffolding from a partial view risked getting it
subtly wrong; the unit-level tests for `run_gitleaks`/`run_syft`
themselves are solid, and the `cli.py` wiring is a three-line
`asyncio.gather` + list-append, low-risk enough to leave at unit-test
coverage for now. Worth adding the integration test in a future round
if this wiring is ever touched again.

Still open from the original P1 list: nothing — all five items are
now either implemented or confirmed already-done. P2 (dependency
inventory, license policy, reproducible-build/lockfile checks) and P3
(architecture: structured `--doctor` output, project-local-tool
preference generalized, tool-version compatibility) remain, per §5.10.

**Maintainer-found bug, fixed the same day**: clang-tidy's file
selection (§5.10's P0 addition) globbed every `.c`/`.cpp`/`.cc` under
`root`, which sweeps up CMake's own generated compiler-ID probe file
(`build/CMakeFiles/.../CompilerIdCXX/CMakeCXXCompilerId.cpp`) —
confirmed by the maintainer with a real `sarand --quality --format
json` run showing clang-tidy actually processing it alongside
`main.cpp`. Fixed by parsing `compile_commands.json` itself for the
real source-file list (the authoritative record of what was actually
compiled) instead of globbing, explicitly excluding anything under a
`CMakeFiles/` or `cmake-build-*` path even if it somehow ended up in
the compile db anyway. Also added along the way: `--quiet` on the
clang-tidy invocation, and a sane default `-checks=` list (bugprone/
readability/performance/modernize/cppcoreguidelines, a few noisy ones
disabled) applied only when the project has no `.clang-tidy` of its
own — same "existing config wins" precedent as `.clang-format`'s gate
above. `tests/test_cpp_java_analyzers.py` gained a regression test
(`test_cpp_analyzer_clang_tidy_excludes_cmake_generated_probe_files`)
that locks this in by planting a fake compiler-ID-probe entry directly
in a compile db and asserting it never reaches the clang-tidy command
line, plus updated the existing "runs with compile commands" test to
use a real compile-db entry instead of an empty `[]` (which, now that
file selection reads the compile db instead of globbing, would
correctly skip with "no C/C++ source files found" — the old test only
passed before because globbing ignored the compile db entirely).

**Follow-up review (2026-09-20)**: the maintainer's own hand-applied
clang-tidy patch and the assistant's independent rewrite turned out to be
functionally identical; the device copy of `cpp_analyzer.py` was kept as
the source of truth (it had already passed the real run + 538 tests) and
only bilingual comments were added on top. The same review of a fresh
self-scan report fixed three more things: (1) mypy — `find_dirs_named()` in
`device_report/walking.py` typed `names` as `set[str]` although it only
does membership tests and callers pass a `frozenset`; now
`collections.abc.Set` (`AbstractSet[str]`). (2) gitleaks — the P1 call
printed only "leaks found: N" plus ANSI colour codes; it now adds
`--verbose` (findings visible) and `--no-color`. **`--verbose` is only
safe because `--redact` is always present** — never drop `--redact`;
`tests/test_gitleaks.py` asserts the pair. Note `--verbose` also prints
commit author/email for history findings. (3) `test_java_analyzer_gradle_quality_skips_without_plugins_applied`
never monkeypatched `shutil.which`, so it only passed on machines that
happen to have gradle installed (same class of bug as the earlier dart/zig
tests) — now hermetic. The self-scan noise items that were listed here as still open (shfmt,
markdownlint, bandit B101, false "Errors detected") were handled in §5.12.

### 5.12 — Hygiene + P2 first slice (2026-09-20)

**Test-hermeticity sweep (the item §5.10 left open).** Method, so it can
be repeated: run the whole suite twice in a scratch environment — once
with none of the external tools on `PATH`, once with a stub executable
(prints a line, exits 0) for every name any analyzer passes to
`shutil.which` — and diff the outcomes per test. Any test whose result
differs is env-dependent by definition. Found 7 more (3 C# `dotnet`, 1 PHP
`composer`, 2 Ruby `bundle`, 1 Swift `swift`) plus the Java gradle one
already fixed in the §5.11 follow-up; all now monkeypatch `shutil.which`.
After the fix both environments give identical results. Not swept
dynamically: the 7 modules that need `rich` (`test_cli`, `test_doctor*`,
`test_new_renderers`, `test_rc_state`, `test_renderers`,
`test_report_replacement`) — `rich` was unavailable in the sandbox; a
static read found no test in them that depends on a tool being
installed or missing.

**`core/lockfiles.py` — reproducible-build / lockfile validation (P2).**
Project-root only, gated on a real manifest marker (§4.3): Cargo.toml,
package.json *with dependencies*, go.mod *with a `require`*,
Gemfile, composer.json *with real packages* (not just `php`/`ext-*`), and
Python only when a lock-producing tool is configured (`[tool.poetry]`,
`[tool.uv]`, `[tool.pdm]`, Pipfile) — a plain `pyproject.toml` library is
not expected to have a lockfile. Fails (rc 1) only on a definite problem:
no lockfile, or the lockfile is git-ignored (`git check-ignore`; an
unknown result — no git, not a repo — is never a problem). Several
lockfiles for one ecosystem is a warning. Output lines use `problem:` /
`ok:` / `warning:`, **never `error:` or `failed`** — the known-issue
scanner (`KNOWN_ISSUE_PATTERNS`) would otherwise report a lockfile
problem as "Compilation or lint errors" (a test enforces this). Wired
into `cli.py` next to gitleaks/syft. **Not done**: checking the lockfile
is *in sync* with the manifest (needs each ecosystem's own tool).

**`core/sbom.py` — dependency inventory + license check (P2).** syft is
now asked for `-o json`; sarand renders a per-ecosystem count, a license
histogram, a package table with a license column, and **advisory**
`warning:` lines for strong (GPL/AGPL/SSPL/OSL) and weak (LGPL/MPL/EPL/
CDDL/EUPL/CPL) copyleft. `A OR B` takes the most permissive option, `A AND
B` the strictest. It never fails the check: whether copyleft matters
depends on this project's own license and how the dependency is used,
which sarand cannot know. If the JSON cannot be parsed, the P1 table is
run instead (second syft call), so the layer cannot make the check worse
than P1. **Unverified against a real syft binary** — the JSON shape
(`artifacts[].name/version/type/licenses[].value/spdxExpression`) is
implemented from syft's documented schema and tested with synthetic
documents only; confirm with a real `sarand --security` run.

**Still open from P2/P3**: a per-project license *policy* (an allow/deny
list in config, plus comparing against the project's own declared
license) — needs a maintainer decision on where that config lives;
lockfile/manifest sync; the structured `--doctor --format json` mode and
the rest of P3.

**Follow-up after the first real `sarand --security` run (v0.5.0).**
Confirmed on-device: the `lockfile check` passes for this repo, and
**syft's JSON matched the assumed schema** (license column populated,
copyleft advisory fired for `certifi`, MPL-2.0). Findings from the real
report and what was done:

- **gitleaks: all 4 findings were `tests/test_secrets.py` fixtures** (3 AWS
  keys, 1 private-key block), so the check failed on deliberately fake
  credentials. Added `.gitleaks.toml` with a path allowlist. It MUST keep
  `[extend] useDefault = true` — a custom config replaces the built-in
  rules, and dropping that line would silently make gitleaks report zero
  leaks forever (a test guards it). Also note `--verbose` output
  includes the commit author's email for history findings — it appeared
  in the real report.
- **syft: Rust crates report no license** (`-` for all of them): syft reads
  `Cargo.lock`, which carries none. Python and GitHub-Action packages are
  covered. `cargo deny check licenses` remains the source of truth for
  Rust; do not read "no license reported" for rust-crate as unlicensed.
  License strings are not always SPDX (`Apache 2.0`, `PSFL`); they are shown
  as reported and only recognized copyleft families are flagged.
- **The SBOM summary was invisible in the default view** (a passing tool
  shows only its last 80 lines; the summary was first). Moved to the end
  of the output.
- **`scan_for_issues` false positives fixed** (`utils/command.py`): bandit
  context lines (`<lineno>\t<code>`, which quote the project's own test
  strings — including the new lockfile/SBOM tests' `warning:` strings),
  bandit's internal `[tester]`/`[main]` log lines (except `ERROR`), and
  `0 failed` in success summaries are no longer listed under "Warnings
  detected"/"Errors detected". A real `N failed` (N ≥ 1) is still an error.
- **bandit now skips `tests`/`test` directories** (`_BANDIT_EXCLUDE_DIRS`):
  B101 alone gave ~1000 findings on sarand's own tests and buried the real
  ones (B603/B404 on subprocess use). Trade-off: hardcoded-secret style
  findings inside test code are no longer reported.
- **Repo configs added**: `.editorconfig` (`[*.sh]` 4-space indent, which is
  what `install.sh` uses and shfmt honors) and `.markdownlint.json`
  (disables MD013 line length, MD033 inline HTML, MD051 link fragments —
  false positives on the bilingual headings — and MD060 table style).
  The remaining real markdown issues (fence languages, blank lines around
  lists/fences, a bare URL, a heading inside the alert block) were fixed
  in `README.md`, `docs/RC-AI-RECEIVER.md` and this file; `markdownlint`
  0.48 reports zero errors on all three. **Confirmed on-device**: after these configs a real `sarand --full`
  shows `shfmt -d`, `markdownlint` and `gitleaks` all passing, and
  "Errors detected" empty.

- **bandit: the 7 remaining findings are `subprocess` use by design** (B404
  on `import subprocess`, B603 on the calls in `utils/command.py`,
  `rc/transport.py`, `renderers/pdf.py`). sarand exists to run external
  tools, and every call passes a fixed argv list, never a shell string, so
  each site carries `# nosec B404` / `# nosec B603` next to a bilingual
  note. Do not add a *new* `subprocess` call without the same reasoning:
  argv list, no `shell=True`, no user-controlled first element. After this
  the security category should no longer be capped by bandit; it was the
  only failing check in the last full report (health 76.0/C).
- **Observation, not fixed**: the effective ruff rule set (FURB, FLY were
  enforced) is not defined in the repo — `pyproject.toml` has no
  `[tool.ruff]` and there is no `ruff.toml`. If CI runs a different ruff
  configuration than a maintainer's machine, results can differ; pinning
  the rules in the repo is worth deciding on.

### 5.13 — Cross-platform contract (2026-09-20)

Requirement (§2): sarand behaves the same on Linux, macOS, Windows and
Android/Termux. A green run on the maintainer's phone proves only one of
those. Evidence that this was not being met: CI run #44 (commit `d772c61`,
after v0.4.0–v0.5.1 had already been tagged) was **green on macOS** (all
steps, 565 tests), **red on Windows** at `mypy .` (6 `attr-defined`
errors: `os.killpg`, `signal.SIGKILL`, `os.getuid`, `pwd.getpwuid` do not
exist there) — so Windows had not even reached `pytest` — and **red on
Linux** at a step that was not identified when this was written.

Rules (each is enforced by a test or by CI, not by memory):

1. **POSIX-only APIs are guarded with `sys.platform`, not `os.name`.**
   mypy narrows on `sys.platform == "win32"`; it does not on `os.name`, so
   `os.killpg`, `os.getuid`, `signal.SIGKILL`, `pwd.*` were type-errors on
   Windows even behind an `os.name` check.
2. **Text I/O always names its encoding** (`read_text`, `write_text`,
   `open`, text-mode temp files, `subprocess` with `text=True`). Windows
   and a C locale default to a non-UTF-8 codec, which turns Persian/emoji
   content into mojibake or a `UnicodeEncodeError`. Enforced by
   `tests/test_portability.py` (AST scan of `python/sarand`).
3. **No POSIX-only module (`pwd`, `fcntl`, `termios`, `resource`, ...) is
   imported at module level** — it would break `import` on Windows. Same
   test.
4. **Run external tools only through `run_cmd` / `run_cmd_async`.** On
   Windows they resolve the executable with `shutil.which` (PATHEXT), so
   `npm.cmd`, `gradle.bat`, `mvn.cmd`, `composer.bat` run instead of being
   reported as "not found" after the analyzer's own `which` check passed.
   The three direct `subprocess.run` sites (clipboard, two PDF engines) are
   the only exceptions.
5. **Every entry point calls `harden_stdio()`** (`cli.main`,
   `device_report.command.main`): stdout/stderr get `errors="replace"`, so a
   non-UTF-8 stream prints `?` instead of crashing on the first `→`. A new
   entry point must do the same.
6. **Compare paths in the platform's own spelling**
   (`os.path.normcase(os.path.normpath(...))`, see `is_excluded`), never by
   hand-built `"/"` prefixes.
7. **Tests must not assume a filesystem layout or an installed tool**: no
   hardcoded `/tmp` where code touches the filesystem (Windows has none;
   `resolve_config` drops nonexistent scan roots) — use `tmp_path` /
   `tempfile`; monkeypatch `shutil.which` (§5.10); POSIX-only behavior gets
   `skipif(os.name != "posix")`.
8. **`.gitattributes` forces LF** (`* text=auto eol=lf`), so a Windows
   checkout does not turn shell scripts and byte-exact fixtures into CRLF.

CI: the matrix is every OS on Python 3.12 plus Linux on 3.10 (the
`requires-python` floor) and 3.14; `ubuntu` is pinned to `ubuntu-24.04`
so the `ubuntu-latest` migration to a newer image cannot change results
silently. **Release rule from now on: tag only after CI is green on that
commit** — commit, push, wait for every matrix job, then `git tag` and
push the tag. Never tag a red commit.

**Not verified by the assistant** (no Windows/macOS in the build
sandbox; CI is the arbiter): everything above was checked only by static
analysis, guard tests, and running the suite under a C locale and a
temp directory with spaces and non-ASCII characters. **Known gaps, not
bugs fixed here**: `install.sh` is
POSIX-only (Windows installs via pip/pipx); the OSC 52 clipboard path
writes to `/dev/tty`, which does not exist on Windows; `device_report`
classifies paths with POSIX rules (its purpose is Android/Linux storage).

**Memory reporting parity (2026-09-20).** The environment section used to
read memory only from `/proc/meminfo`, so it said `(unknown)` on macOS and
Windows. `scanners/environment.py` now has one reading per platform:
Linux/Android/Termux/WSL from `/proc/meminfo` (output format unchanged),
Windows through `GlobalMemoryStatusEx` via stdlib `ctypes`, macOS through
`vm_stat` (free + inactive + speculative pages, an approximation of
"available") plus `sysconf` for the total, any other POSIX through
`sysconf` (total only, printed as `N MiB total`). The parsing and the
per-platform choice are unit-tested with faked platforms; **the actual
Windows `ctypes` call and macOS `vm_stat` output were not run on those
systems** — CI is the arbiter, and a real macOS/Windows report should be
eyeballed once.

### 5.14 — First real CI results (run #45, commit `22f832f`, 2026-09-20)

- **All three Ubuntu jobs (Python 3.10, 3.12, 3.14) failed on exactly one
  test**: `test_php_analyzer_run_tests_skips_cleanly_without_phpunit` —
  the GitHub Ubuntu image ships PHPUnit, so the analyzer ran it instead of
  skipping. 573 of 574 tests passed. Same class of bug as §5.10/§5.12, and
  the earlier sweep missed it because it stubbed executables named after the
  literal arguments of `shutil.which("...")` calls in the source, and the
  PHP analyzer resolves `phpunit`/`phpstan` through a helper with a variable
  name. **The reliable sweep patches `shutil.which` itself**: run the whole
  suite once as-is and once with `shutil.which` returning a fake path for
  every name it cannot really find; a test whose result changes depends on
  the machine. After fixing PHPUnit/PHPStan (both tests now monkeypatch
  `shutil.which`) this sweep reports no env-dependent test. Keep Ubuntu in
  the matrix: its image has far more tools installed than any developer
  machine, which makes it the strictest check of this rule.
- **The Windows job hung for six hours, and the log named the test**: the
  last line of the `Run pytest -v` step was
  `test_android_analyzer_quality_and_security_skip_cleanly_without_gradle`
  with no result. That test (and eight siblings: cargo-audit/deny,
  govulncheck, cppcheck, mvn, gradle, PDF engine, pip-audit/bandit) did
  `if shutil.which("gradle") is None: assert skipped` — i.e. it ran the
  **real** tool whenever it was installed. The Windows runner has Gradle;
  once §5.13 made `gradle.bat` resolvable through PATHEXT, a real Gradle
  build started in a temp project, and `LONG_CMD_TIMEOUT` is 3600 s per
  call. All nine tests now patch `shutil.which` and assert the skip path
  unconditionally, and `tests/test_portability.py` has a guard
  (`test_no_test_branches_on_whether_a_real_tool_is_installed`) that fails
  on any `if shutil.which(...)` in a test except one deliberate PDF
  integration test. CI keeps `timeout-minutes: 45` and
  `-o faulthandler_timeout=90` so a future hang stays cheap and names
  itself.
- **A second Windows-only failure class, seen in the same log**:
  `test_rust_analyzer_cargo_deny_skips_without_binary`,
  `..._without_deny_toml` and `test_python_analyzer_run_quality_skips_mypy_
  cleanly_without_it` failed. Cause: `_resolve_argv` called
  `shutil.which(name, path=...)`, but those tests patch `shutil.which` with a
  one-argument function, so every such test raised `TypeError` on Windows
  only. `_resolve_argv` now calls `shutil.which(name)` with one positional
  argument (a test pins this). **Technique worth reusing — a forced-Windows
  run on Linux**: in a scratch copy, delete the `os.name != "nt"` condition
  and run the suite; it reproduced exactly the three failures from the
  Windows log plus four more not yet seen (shellcheck, shfmt, swift-format,
  swiftlint), and after the fix it shows none.
- **Tripwire sweep** (stub executables created on demand by a patched
  `shutil.which`, each logging its own invocation, then a per-test list of
  which tools a test really launched): after these fixes only six
  lightweight linter tests still launch a real tool when it is installed
  (`stylelint`, `jsonlint`, `detekt`/`ktlint`, `sqlfluff`, `taplo`). They
  finish in seconds and their assertions tolerate both outcomes, so they
  were left alone; convert them the same way if one ever misbehaves.

### 5.15 — License policy (2026-09-20)

`.sarand.toml` in the project root now holds a per-project license policy
(`core/license_policy.py`, wired into `core/sbom.py`). **Why that file and
not `[tool.sarand]` in `pyproject.toml`**: sarand audits every ecosystem
and most audited projects have no `pyproject.toml`; the policy belongs to
the *audited* project; and `.sarand.toml` sits beside `.gitleaks.toml` and
`deny.toml`, the other per-project scanner configs. Only the project root
is read (no parent lookup), so the result is deterministic.

Semantics (close to `cargo-deny`, full description in the module
docstring and both READMEs): `deny` > not-in-`allow` > `warn`; patterns are
case-insensitive globs; `A OR B` is judged by its best alternative,
`A AND B` needs every part; several license entries on one package count as
alternatives (lenient); a handful of real-world non-SPDX spellings are
aliased (`Apache 2.0`, `PSFL`, ...), any other unknown string is one opaque
license that must be allowed verbatim; exceptions need a written `reason`.
A file with no `[licenses]` table leaves the built-in advisory in place;
with one, **only the policy applies**. A violation fails the `syft (SBOM)`
check (`problem:` lines, never `error:`/`failed`, §5.12); an invalid file
fails it too, because a typo like `alow` must not silently disable the
policy. Parsing uses stdlib `tomllib` (3.11+) and `tomli` on 3.10 (new
dependency `tomli>=2.0; python_version < "3.11"`), a full parser, unlike
`python_analyzer.py`'s regex for `dependencies`, because a mis-parsed policy
is a wrong verdict rather than a skipped optimization.

The repository dogfoods it (`.sarand.toml` at the root), tested against
the license mix a real `sarand --full` SBOM listed for this project (one
`warn`: `certifi`, MPL-2.0). **Not verified**: the Python 3.10 `tomli`
import path (the build sandbox has 3.12; CI's 3.10 job will exercise it),
and a real `syft` run with a policy present.

**Open work as of this section** (ordered; the maintainer decides what next):

1. CI green on all five jobs for the latest push, Windows first: its log
   was cut at about 8 % of the suite by the hang, so failures after that
   point are still unseen; then tag `v0.5.2` (nothing since `v0.5.1` is
   released).
2. Check `README.md` / `README.fa.md` and the banner on GitHub (RTL
   Persian, phone and desktop); never viewed in a browser by the assistant.
3. `LICENSE`: checked, the README commit left it unchanged (empty
   `git diff e9825d5^ e9825d5 -- LICENSE`); nothing to do.
4. Lockfile-vs-manifest sync check (needs each ecosystem's own tool).
5. P3: `--doctor --format json`; project-local tool preference beyond PHP;
   tool-version compatibility checks.
6. Phase F: `makepkg` in a clean chroot for the AUR package, regenerate
   `.SRCINFO`, submit.
7. Pin the ruff rule set in the repo (`pyproject.toml` has no
   `[tool.ruff]`; three lint rounds were spent on rules the assistant could
   not see).
8. CI housekeeping: GitHub Actions on Node 20 are deprecated
   (`actions/checkout@v4`, `setup-python@v5`, `cache@v4`); `ubuntu-24.04`
   is pinned and the `ubuntu-latest` migration to 26 should be tested on
   purpose.
9. Cross-platform known gaps (§5.13): Windows installer (`install.sh` is
   POSIX-only), OSC 52 via `/dev/tty` on Windows, `device_report` path
   rules; a real macOS/Windows report should be eyeballed once.
10. Optional: six lint tests still launch real tools when installed
    (§5.14); a `CHANGELOG.md` / GitHub Releases for the tags `v0.4.0` to
    `v0.5.1`.
11. Phase H (git-history depth) stays deferred.

### 5.16 — Windows run #48 (commit `7678d03`, 2026-09-20)

Ubuntu 3/3 green (the hermetic-test round worked). Windows finished in
under four minutes instead of hanging — **10 failed, 577 passed, 4 skipped**.
Eight failures were visible to the assistant, each a genuine
"same input, different result per OS" bug in a test or in the product:

- `test_default_top_n_when_neither_full_nor_explicit` still used `-r /tmp`
  (Windows has none; `resolve_config` drops nonexistent roots) — missed when
  the sibling tests were fixed in §5.13; now `tmp_path`.
- `test_toolchain_aggregates_pycache_by_default` /
  `..._expand_aggregates_lists_every_pycache` asserted `"/__pycache__"`;
  the report prints native paths — now `os.sep`.
- **`GroovyAnalyzer.entry_points` returned `src\main\groovy` on Windows**
  (`str(path.relative_to(root))`): a product bug, the same project gave a
  different report per OS. Now `.as_posix()`, and
  `test_reported_entry_points_never_use_native_path_separators` bans `str(...)`
  inside any analyzer's `entry_points`.
- `test_harden_stdio_...` compared bytes and got `\r\n` — text streams
  translate newlines on Windows; the test now uses `newline=""`.
- `test_is_excluded_on_posix_...` is correct to fail on Windows (paths are
  case-insensitive there); it is now `skipif(win32)`.
- `test_json_renderer_embeds_source_...`: `tests/_helpers.write` used
  `write_text`, which turns `\n` into `\r\n` on Windows, so `size` was 13,
  not 12. **The helper now writes bytes**, which also protects every other
  fixture from line-ending drift.

**Technique worth reusing**: a *CRLF simulation* on Linux (patch
`Path.write_text` and text-mode `open` to default to `newline="\r\n"`, run
the suite, diff against a normal run) reproduced the last failure and found
no other newline-sensitive test. Path-separator and case differences cannot
be simulated that way; they need the real Windows job.

**Still unseen**: two of the ten Windows failures were not in the copied log
(only eight `FAILED` lines were pasted). Find them with `FAILED` in the
step log before assuming the Windows job is fixed.

### 5.17 — Assembly detection (2026-09-20)

CI is green on all five jobs (Ubuntu ×3 across Python 3.10/3.12/3.14, macOS,
Windows) as of the commit before this round — the first time ever.

**What it does.** "Assembly" is not one language, so sarand reports the
*dialect* of each file and a per-dialect summary, not just "Assembly":
x86 (NASM, GNU as AT&T, GNU as Intel, MASM/TASM, FASM; 16/32/64-bit), ARM
(A32/T32), AArch64, RISC-V, MIPS, PowerPC, 6502, Z80, AVR, Motorola 68000
and 8051. New files: `discovery/assembly.py` (file discovery, classifier,
`AssemblyProfile`), `analyzers/assembly_analyzer.py` (`name = "Assembly"`,
matches on sources, reports entry points, **runs nothing** — there is no
universal assembler or test runner; the right one is the project's own
Makefile). `ProjectDetection` gained `details: dict[str, str]` (a generic
"label -> text" slot; today only Assembly fills it) and the markdown, HTML,
text, JSON and AI-summary renderers show it.

**Design points worth keeping.**

- *Shallow and deterministic*: only the project root plus first-level
  `src/`, `asm/`, `boot/`, `kernel/`, `firmware/` are searched (max 300
  files, first 64 KiB of each, read as bytes), so vendored or nested files
  cannot make a project "an assembly project" (same rule as the other
  extension-based analyzers, §4.3).
- *Transparent heuristic, not a parser*: every dialect owns a few weighted
  regexes (its registers, directives, mnemonics); best score wins; below a
  threshold the file is `Unidentified` rather than guessed. Plain
  Intel-style `mov eax, 1` with no NASM/MASM/FASM marker is labelled
  `Intel syntax`, not NASM — the pattern alone does not prove the assembler.
- *Assembly does not take over a project*: it becomes the primary language
  only when nothing else claims the project (no marker, or a bare Makefile
  with no other source files); a C project with one `startup.s` stays C and
  lists Assembly as a second language.
- Labels use `/` and counts use `x` (`x86-64 / NASM x2`) — plain ASCII, so
  no ambiguous-Unicode lint rule can ever trip on them.

**Not verified.** The classifier was tested on 19 hand-written samples (one
or more per dialect) and negative cases, not on a real-world corpus; large
mixed files, macro-heavy sources and less common dialects (SPARC, MSP430,
Xtensa, LLVM IR, WebAssembly text) are not covered and will show as
`Unidentified`. If a real project is mislabelled, add its snippet as a test
and adjust the weights.

**Lint lessons from this round (all "modern idiom" rules the assistant
cannot run in its sandbox, so they keep showing up as one-line fixes):**
`ISC004` — implicit string concatenation *inside a tuple/list/dict literal*
must be wrapped in its own parentheses (`(("a" "b"), 2)`, not
`("a" "b", 2)`); hit in `sbom.py` and again in `assembly.py` and its test
table (23 sites). `FURB167` — write `re.MULTILINE`, not `re.M`. `FLY002` —
no `"\n".join([literal, literal])`. For big literal fixtures prefer a
triple-quoted string over concatenated pieces. Ruff's effective rule set is
still not pinned in the repo (§5.15 item 7).

### 5.18 — Review of `sarand --doctor` and the Tier-1 ecosystems (2026-09-20)

CI is green on all five jobs at `79cfe3d` (assembly detection included). The
maintainer pasted the `sarand --doctor` output together with an outside
review of it. What was taken, adjusted or refused, and why:

- **"Assembly is missing from `--doctor`" — first refused, then accepted;
  the refusal was wrong.** The assistant argued `--doctor` lists *external
  tools* and Assembly runs none, so it had no row "by design". The
  maintainer objected: `--doctor` is where a user looks to learn what sarand
  supports, and an ecosystem absent from it looks unsupported — a real,
  user-visible defect. Fixed: `core/doctor.py` has `_DETECTION_ONLY` rows
  (`detection_only_catalog()`), shown as a ✓ "built-in dialect detection"
  entry that never counts as a missing tool; the README tables list it too.
  Guards: `test_every_analyzer_is_visible_in_doctor` (an analyzer with no
  `--doctor` presence fails the suite) and the README test now includes the
  detection-only categories. Lesson: judge a feature by what the user can
  *see*, not by how the code is organised. (The other half of the review still
  stands: `pipx install` does **not** refresh an existing installation,
  `./install.sh` does.)
- **Tier 1 implemented**: Haskell (`stack`/`cabal` tests, `hlint`), Elixir
  (`mix test`, `mix format --check-formatted`, `mix hex.audit`; Credo and
  MixAudit only when `mix.exs` names them), Erlang (`rebar3 eunit`, `rebar3
  xref`), Scala (`sbt -batch test`; `scalafmtCheckAll` only when
  `project/plugins.sbt` names `sbt-scalafmt`), Dockerfile (`hadolint`), GitHub
  Actions (`actionlint`, given explicit workflow paths), Terraform
  (`terraform fmt -check`, `tflint`; **never** `init`/`plan`/`apply`),
  Protobuf (`buf lint`). Deviations from the review: **Protobuf uses `buf`, not
  `protoc`** (protoc compiles but cannot lint); **Erlang does not run
  Dialyzer** (its first run builds a PLT of all of OTP, minutes long, and
  would make a scan unpredictable); the plugin-based checks are gated so the
  report never blames a project for a check it never adopted (the same rule as
  RuboCop under Bundler). They share `analyzers/_tooling.py` (`run_tool`,
  which returns a *skipped* result when the binary is missing).
- **Tier 2/3 deferred, on purpose** (Fortran, OCaml, Clojure, Nim, Crystal, D,
  F#, V, GraphQL, Kubernetes manifests): the review itself said not to add
  languages just to raise the count. Kubernetes has no unambiguous root marker
  (any YAML with `apiVersion`/`kind`) and needs schemas; that needs a design
  before code.
- **"Build the matrix first" — done**: `core/coverage.py` derives
  Language → Tests/Quality/Security/Tools/Build tools from the real sources
  (an `ast` read of each analyzer, the doctor catalog, the project markers)
  and writes `docs/COVERAGE.md`; `tests/test_coverage.py` fails when the
  file is stale, when an analyzer is not classified, or when a doctor category
  belongs to no analyzer. Read it before adding another ecosystem.
- **The supply-chain gap is real**: syft produces an SBOM, not vulnerability
  findings. Its `--doctor` text now says so (and that a `.sarand.toml` license
  policy makes it fail on a violation). A multi-ecosystem vulnerability scanner
  (`osv-scanner` or `grype`) is the natural next step, **but its command line
  differs between major versions and could not be checked here**: get
  `osv-scanner --help` (and `--version`) from the maintainer's machine first.
- **Kept and tested**: "a missing tool is not a broken sarand" — every new
  analyzer has a test that all its tools skip cleanly when absent.

New project markers/entry points: `stack.yaml`, `cabal.project`, `mix.exs`,
`rebar.config`, `build.sbt` (`constants.py`). The infrastructure formats
(Dockerfile, GitHub Actions, Terraform, Protobuf) are analyzer-only like YAML
and JSON: they do not become a project's primary language. **Not verified**:
none of the eight tools was run for real (the build sandbox has none of them);
the exact command lines are from each tool's documentation and are tested only
as recorded commands. Expect to fix an option or two on first real use.

### 5.19 — `install.sh` no longer removes the old install first (2026-09-21)

**Incident.** Running `./install.sh` on the maintainer's phone uninstalled
the pipx copy of sarand and then failed to build the new one — `maturin`
could not be downloaded from PyPI (`operation timed out`, uv's message
format). The script had been written to uninstall first (a plain
`pipx install` leaves a stale snapshot), so a transient network failure
left **no `sarand` command at all**. (The dev venv's editable copy still
worked, which is why nothing was lost.) A failed upgrade must never do that.

**Fix.** The old venv is now *set aside* (moved to
`$PIPX_HOME/.sarand-previous-venv`), the new one is built with up to
`SARAND_INSTALL_ATTEMPTS` tries (default 3, `SARAND_INSTALL_RETRY_DELAY`
seconds apart, `PIP_DEFAULT_TIMEOUT`/`UV_HTTP_TIMEOUT` raised to 180 s), and
only a successful build deletes the old copy. On failure, or on Ctrl-C/TERM
(a `trap`), the old venv is moved back exactly as it was. Moving the
directory also works when pipx cannot read its metadata (pypa/pipx#1619),
the case the previous `pipx uninstall` fallback existed for. Tested against a fake `pipx` (`tests/test_install_script.py`: success
replaces, failure restores, transient failure retries, a failed first
install leaves nothing behind, and a guard that no non-comment line runs
`pipx uninstall`). **The interrupt logic is tested without signals**: the
script is now a sourceable `main()` (`SARAND_INSTALL_SOURCE_ONLY=1 .
install.sh` defines the functions and installs nothing) driven by a small
state variable (`idle` / `aside` / `fresh`), and the tests call
`interrupted` in each state. The first version tested this by sending
`SIGINT` to the script's process group; it passed five local runs but
**timed out on the maintainer's Kali proot** — signal delivery there
differs — so it was replaced rather than tuned. Replacing it exposed a real
bug in that first version: the trap handler deleted the pipx venv
unconditionally, so a Ctrl-C *before* the old install had been set aside would
have destroyed it. The `idle` state makes `restore_previous` a no-op then, and
`test_an_interrupt_before_anything_changed_never_touches_an_existing_install`
guards it (checked by re-introducing the bug). Lesson: a test that depends on
OS signal semantics is not portable across the maintainer's own devices. **Not verified**: the script
against real pipx (the sandbox has none).

**Also verified for real in the same session.** `sarand --quality` on the
maintainer's phone ran the new GitHub Actions analyzer against a real
`actionlint`: `### actionlint [PASS]`, and `actionlint -no-color
.github/workflows/ci.yml` printed nothing — the first of the eight §5.18
tools confirmed with the real binary (the command form is right). The other
seven (`stack`, `cabal`, `hlint`, `mix`, `rebar3`, `sbt`, `hadolint`,
`terraform`, `tflint`, `buf`) are still unverified.

### 5.20 — Outside review: report size, health transparency, install confusion, README bidi (2026-09-21)

CI green on all five jobs, `a1c71b4` (Assembly visible in `--doctor`,
confirmed on-device). The maintainer forwarded a structured outside review
of the whole project plus a live symptom from their own terminal, and
disagreed with one part of the review (see below). What was built:

**Report size, made visible, not newly limited.** The review's core
argument — a `--full` report of a real project can exceed the memory of a
2 GB laptop or a 6 GB phone, and there was no warning before the crash —
is correct and was not previously handled. `--max-file-size SIZE` (`512K`,
`2M`, `1G`; default `2M`, parsed in `utils/sizes.py`) caps any one embedded
file and, unlike `--max-depth`/`--max-entries`, is **not** cleared by
`--full` unless given explicitly, because a single huge generated file
(a lockfile, a bundle) has historically been the actual cause of report
bloat, not file count. Before rendering, `core/estimate.py` sums the size
of every file that will be embedded, prints
`Embedding about N of source from M file(s)`, and — reading the same
per-platform memory figure as the Environment section — warns when that
total exceeds 50 MiB or a quarter of free memory. It is advice only: sarand
runs unattended in CI, so it never asks a question or blocks the run,
exactly as the maintainer's own proposal specified.

**Health score transparency.** The review's sharpest point: a check whose
tool is not installed is skipped, not failed, so a project with half its
security tools missing could still show a clean score — the score looked
more certain than the checks behind it. `HealthScore` now carries
`checks_run`, `checks_skipped` (by tool name) and `confidence` (ran /
(ran + skipped)); a security category where *every* check was skipped
drops from 15 to 8 points instead of the full 15 (some skipped, some
clean, still scores 15 — only *total* silence is penalized). All four
renderers and the CLI summary show a "Check coverage: N ran, M skipped,
confidence X%" line, but **only when something was actually skipped** —
an unremarkable report stays unremarkable.

**Refused, then accepted: a live symptom, not covered by the review
itself.** The maintainer's own terminal showed `installed package sarand
0.5.1` immediately followed by `sarand 0.1.5` — pipx had just installed
0.5.1, but the shell ran a stale `.venv` editable install instead. Cause:
several sarand installations can exist on one machine, which one runs
depends on `PATH` order, and an editable install's recorded version does
not follow the source tree. Fixed with real, verified logic (not a lint
rule): `utils/installation.py` compares an editable install's recorded
version against `[project] version` in its own source `pyproject.toml`
and walks `PATH` (resolving symlinks, so pipx's own venv-into-`~/.local/bin`
link is not flagged as "another" copy) for a **different** `sarand`
executable. `--version` now warns to stderr when the running copy is a
stale editable install; `--doctor` gets an "Installation" row (the running
copy, editable or not, and whether it is stale) and an "Other sarand on
PATH" row naming every shadowing copy with its own `--version` output.
`install.sh` verifies its own result: after a successful build it asks the
`pipx`-installed copy directly for its version (not "whatever `sarand`
answers first"), and warns by name if a different copy earlier on `PATH`
would still run instead.

**README: disagreed with the review, on purpose.** The review's own
alternative take called the README's Persian prose "very literal, machine
translated". The maintainer's answer, followed here: keep the README
long and exhaustive — cutting content was never the ask — but write the
Persian side as Persian, not as a sentence-by-sentence mirror of the
English one. `README.fa.md` was rewritten prose-first from the same
information (sentences reordered and merged in the ways Persian
technical writing actually reads, not just word-substituted), with three
mechanical rules applied throughout: (1) every code block, inline command
and file path sits inside `<div dir="ltr">…</div>`, since Latin text and
punctuation inside an RTL paragraph otherwise reorders unpredictably;
(2) a Latin token or `code span` is never followed directly by Persian
text inside the same parenthetical — split into two clauses or reworded
instead of `مثل X (که Y است)`; (3) all half-space (ZWNJ) compounds
(`می‌کند`, `پیش‌فرض`, `فایل‌ها`, …) are checked, not just typed once and
copied. **Not automatically verified**: no browser or phone was available
to render the result; the maintainer should look at both the RTL flow and
the LTR code islands on GitHub, on a phone and on a desktop, exactly as
asked after the first README round in §4.12, which this addresses.

**Review points read and deliberately deferred** (recorded here so they
are not silently dropped): analyzer depth is uneven across ecosystems by
design (§5.18's Tier system) — Kubernetes/Helm, Docker Compose, and a
bare Makefile without another build marker are real, common gaps the
review is right about and are not yet designed; a pure-Python fallback
speed pass, real large-project testing on the maintainer's own low-RAM
Termux device, `--ai-model-hint` output profiles, monorepo/workspace
awareness, and publishing to the AUR and PyPI are all still open and
ranked in §5.15/§5.18's numbered lists, not duplicated here.

`CHANGELOG.md` was added (Keep a Changelog style, newest first, covering
`v0.4.0` through the pending `v0.6.0`) and is linked from both READMEs'
Contributing section. **Not verified**: none of the eight §5.18 tool
integrations beyond `actionlint` has been run for real; the installation
diagnostics were tested with fake `pipx`/`PATH` fixtures, not a real
multi-install machine.


### 5.21 — P0 golden-report regression suite (2026-09-22)

Starting the P0 backlog from the "Engineering Backlog & Gap Audit"
document (post-v0.6.2, `1e99b0c`): item 6.1, golden/representative
report regression infrastructure. Evidence-first check confirmed the
gap was real -- `grep`-ing `tests/` for `golden`/`snapshot`/`fixture`
found nothing before this round; every existing renderer test
(`test_renderers.py`, `test_new_renderers.py`) asserts "output
contains X", never the full report shape.

Scope chosen deliberately narrow (see Non-goals below), not the
"real per-ecosystem source-tree fixtures" the backlog doc describes as
the eventual goal:

- `tests/_golden_fixtures.py` -- two hand-built `ReportData` fixtures
  (`hybrid`: dense multi-language project hitting every truncation
  limit, mixed pass/fail/skipped results, secrets, untracked files;
  `minimal`: an unrecognized empty project hitting every renderer's
  "nothing found" branch). Built directly from the dataclasses in
  `models/results.py`, not from a real scan.
- `tests/test_golden_reports.py` -- renders both fixtures through
  markdown/json/text/sarif/html (not pdf -- see below) and diffs
  against a stored snapshot under `tests/golden/`. A
  `SARAND_UPDATE_GOLDEN=1` env var regenerates the snapshots
  deliberately; a guard test fails loudly if a fixture or renderer is
  ever added without also running that regeneration step once.
- `tests/golden/README.md` -- bilingual, explains what's stored, why,
  and exactly how to update a snapshot (with the "review the diff
  before committing" rule spelled out).

Why renderer-level and not scan-level: `ReportData` is the exact
seam every renderer already shares (`renderers/base.py`'s `Renderer`
protocol), so building it by hand makes every fixture fully
deterministic with zero network access and zero optional-tool
dependency -- both explicit Definition of Done requirements in the
backlog doc. The one non-determinism this doesn't remove for free is
the tempdir's own random name leaking into `project_root.name`
(embedded verbatim in every renderer's title/header); fixed by
creating a fixed-name subdirectory (`f"{fixture_name}-project"`)
inside the tempdir rather than trying to string-scrub it out after
the fact.

`pdf.py` is excluded -- it always shells out to a real,
optionally-installed tool (`wkhtmltopdf`/`weasyprint`) via
`render_to_file`, not an in-process `render(data) -> str`, so there is
no text output to snapshot without installing and invoking a real
external binary (would violate "tests do not require unavailable
optional tools").

Verified locally before handoff (no `pytest`/`rich` available in this
sandbox -- no network to install them): imported the real renderer
modules against a minimal local `rich` stub, ran the exact functions
defined in `test_golden_reports.py` (not a reimplementation) against
all 2×5 fixture/format combinations, confirmed byte-for-byte identical
output across two independent runs from different random tempdirs
(the determinism claim), and confirmed a deliberately corrupted golden
file makes the test fail (the regression-detection claim actually
works, not just "the code runs"). Still needs a real on-device
`pytest tests/test_golden_reports.py` run to fully close item 6.1's
Definition of Done, since this sandbox cannot install the project's
real dependencies.

Non-goals (left for the next phase of this same backlog item, per
its own "minimal implementation scope" discipline):

- Real per-ecosystem source-tree fixtures (Python/Rust/JS/Go/hybrid/
  infra/multi-language) scanned end-to-end through analyzers + real
  tool execution -- the backlog doc's actual stated goal for 6.1.
  Deferred because it needs either bundling small real source trees
  per ecosystem or mocking every analyzer's tool execution, and
  because analyzer/tool-execution regressions are a distinct concern
  (see backlog item 7.1, analyzer capability matrix -- also P0, not
  yet started) from renderer/report-structure regressions (what this
  round covers).
- `pdf.py` -- no in-process output to snapshot (see above); its own
  Definition of Done already lives under backlog item P3 "PDF and
  report portability".
- CLI-level end-to-end golden tests (`sarand --full` on a real repo,
  diffed) -- would reintroduce all the non-determinism (timestamps,
  host info, tool versions, absolute paths) this round deliberately
  sidesteps by building `ReportData` directly.


### 5.22 — P0 analyzer capability matrix + depth classification (2026-09-22)

Second P0 item from the same "Engineering Backlog & Gap Audit" doc
(item 7.1), continuing straight from section 5.21 above in the same
round. Evidence-first check: `docs/COVERAGE.md` already existed
(§5.18) and was already code-derived (`core/coverage.py`) with a
sync test -- but it only covered Tests/Quality/Security/Tools/Build
tools, none of 7.1's other requested columns (Fixture coverage, CI,
Real-project validation, Depth). Confirmed via direct inspection, not
assumed.

Extended `core/coverage.py` (still 100% code-derived, still
regenerated with `python -m sarand.core.coverage > docs/COVERAGE.md`,
still sync-tested) with three new columns, each a mechanical rule
over real evidence -- per the backlog doc's own repeated warning ("do
not invent values", "no analyzer is labeled deep merely because it
has a wrapper"):

- **Fixture coverage** -- true iff the analyzer's class name is
  referenced anywhere under `tests/` (a grep of real test source, not
  a `test_<name>_analyzer.py` filename convention, since several
  analyzers -- Haskell/Elixir/Erlang/Scala/Dockerfile/GitHub Actions/
  Terraform/Protobuf, for instance -- share one test module).
- **CI-installed** -- true iff at least one of the ecosystem's tool
  binaries is a token sarand's own `.github/workflows/ci.yml` actually
  installs *and* invokes (not merely lists as a package extra). Caught
  and fixed a real false positive before shipping: a naive
  whole-file word-boundary search matched Haskell's `stack` binary
  against the workflow's own prose comment "...prints every thread's
  *stack*...". Fixed by stripping `#`-comment lines before matching;
  regression test added
  (`test_ci_installed_does_not_false_positive_on_a_prose_comment`).
  **Finding, not a defect to fix in this round**: only Python and Rust
  show CI-installed=yes. sarand's CI runs its own Python test suite
  and its own Rust core's tests -- it never installs any of the other
  ~35 per-language tools and never runs `sarand --full`/`--quality`/
  `--security` against a real target project in any language. Even
  for Python, `bandit`/`pip-audit` are installed as `[dev]` extras but
  never actually invoked as commands in the workflow (only `ruff`,
  `mypy`, `pytest` are). This is real-tool-validation's actual current
  state, made visible instead of assumed.
- **Depth** -- Deep / Partial / Shallow, from a fixed rule over the
  four booleans above (Deep = Tests and Quality and Security and
  Fixture coverage; Shallow = none of Tests/Quality/Security;
  otherwise Partial), documented in the module and locked in by
  `test_depth_classification_is_a_fixed_rule`. Result: 11 "Deep"
  ecosystems (Python, Rust, Go, Node.js, Elixir, C/C++, Ruby, PHP,
  Android/Kotlin, Java/Kotlin, C#), Assembly alone "Shallow"
  (detection-only, no tool needed), everything else "Partial" --
  including every format analyzer (YAML/JSON/TOML/XML/Markdown/CSS/
  SQL) by the rule itself, matching their own documented category in
  section 5.4 rather than a hand-typed label.

`Real-project validation` (7.1's last requested column) was
deliberately kept OUT of the generated table -- it is a fact about a
past session, not something derivable from the current source tree,
and mixing hand-curated history into a "do not edit by hand" file
would rot silently. Evidence gathered this round instead, cited here:
per the terminal transcript the user supplied in this same session
(commit `1e99b0c`, `sarand --full` run on sarand's own repo, dated
2026-09-22), sarand's Tests/Quality/Security actually executed for
real against a real project (itself) for exactly these seven
ecosystems: **Python, Rust, GitHub Actions, Shell, JSON, TOML,
Markdown** (763 pytest passed, Rust cargo tests included, health
100.0/100). No other ecosystem in the roster has comparable
first-party evidence of a real run in this project's history that
this session can point to; everything else's per-analyzer real-tool
behavior is UNVERIFIED by this standard, whatever earlier session
summaries claim about specific tools (e.g. clang-tidy, actionlint,
Ruby bundler) -- those were real but happened on the user's own
device in unlogged sessions, not evidenced in this repository the way
the Evidence-First Rule asks for. Re-confirming them from repository
evidence (a dated report, a CI log) rather than chat history is
exactly backlog item 7.1's "Real-project validation" column waiting
to be filled in properly, and is left as the explicit next step:
either a real `sarand --full` self-scan log gets committed somewhere
citable, or the CLI-level golden-report work from item 6.1's
deferred "Non-goals" (real per-ecosystem source-tree fixtures,
scanned end-to-end) starts producing that evidence directly.

Verified locally the same way as section 5.21 (no `pytest` available
in this sandbox, no network to install it): ran the actual functions
from `test_coverage.py` (not a reimplementation) directly, all 10
tests passing including the 6 pre-existing ones (confirming nothing
broke) and the 6 new ones (4 targeted at the new columns/rule, 1
locking in the `stack`/comment false-positive fix, 1 confirming the
docs stay in sync). `docs/COVERAGE.md` regenerated and included in
this round's delivery. Still needs a real on-device
`pytest tests/test_coverage.py` (and the full suite) run to fully
close item 7.1's Definition of Done, same caveat as 5.21.

Non-goals (left for later phases of this backlog item, consistent
with 6.1's own "minimal implementation scope" discipline):

- Actually closing the CI gap this round surfaced (installing and
  running the ~35 other per-language tools in CI against real fixture
  projects) -- a large, separate P1-adjacent effort in its own right,
  not a P0.7.1 documentation task.
- A committed, citable real-project validation log/report that this
  table's "Real-project validation" column could eventually read from
  mechanically, the way Fixtures/CI already do.


### 5.23 — Real on-device verification of 5.21/5.22, two fixes (2026-09-22)

User ran both deliveries for real (`pytest`, `ruff check`, `ruff format
--check`, `mypy`, full suite) on-device and reported back -- closing the
"still needs a real on-device run" caveat both sections above ended
with. Two real issues found and fixed; one apparent issue investigated
and attributed to a stale cache, not new code.

**Fixed -- `ruff format --check` (5.21):** `tests/_golden_fixtures.py`
had four call sites (`write(...)`, `TodoItem(...)`, two `Issue(...)`
list literals) ruff's formatter wanted wrapped across lines. `ruff
check` (lint) had already passed clean -- this project has no E501
line-length lint rule selected -- but `ruff format` (the formatter)
enforces its own line-length independent of which lint rules are
selected. Reformatted to match ruff's own diff exactly; reran the
golden-snapshot harness after, still 10/10 (formatting-only change,
no output changed).

**Fixed -- `ruff check` RUF100 (5.22):** `tests/test_coverage.py`'s
`test_fixture_coverage_is_false_for_an_unreferenced_class_name` had a
`# noqa: N801` comment justifying an intentionally non-CamelCase-ish
probe class name. This project's ruff config has no pep8-naming (`N`)
rules selected, so the directive itself was flagged unused
(`RUF100`). Replaced with a plain bilingual comment -- the noqa was
never load-bearing, nothing before it was ever actually being
suppressed.

**Investigated, not changed -- `mypy` "Module has no attribute"
(5.21+5.22):** the user's first mypy run (2 files only, before
applying 5.22's delivery) reported `sarand.models.results` /
`sarand.renderers` as `import-untyped` (no py.typed marker found --
mypy fell back to treating the editable-installed package as an
external, unstubbed library). Their second run (`mypy .`, the same
invocation `ci.yml` actually uses, 174 files) resolved `sarand.*`
correctly as first-party source everywhere else, but replayed 5
`attr-defined` errors on `test_golden_reports.py`'s
`from sarand.renderers import html, json_renderer, markdown, sarif,
text` -- the *exact same statement*, word for word, already lives at
`cli.py:43` and checked clean in that same run. Same line, same
config, one file clean and one file erroring, is not explainable by
anything in the code; it matches `.mypy_cache/` retaining
`test_golden_reports.py`'s analysis from the first (import-untyped)
run and never invalidating it under the second run's different
resolution. Per the Evidence-First Rule, this is a plausible
explanation from the transcript's own evidence, not a confirmed
diagnosis -- asked the user to `rm -rf .mypy_cache` and rerun `mypy .`
to confirm before anything in the code is touched over it. Do not
"fix" `cli.py`'s already-working import pattern on the strength of an
unconfirmed cache theory.

Both fixes delivered in `sarand-golden-reports-fix-v1.zip` (just the
two changed files, since the 5.21/5.22 deliveries are already applied
on-device).


### 5.24 — Second real-device run: two more `ruff format` fixes, one config change (2026-09-22)

Continuation of 5.23. `rm -rf .mypy_cache && mypy .` came back clean
(`Success: no issues found in 174 source files`) -- confirms 5.23's
cache-staleness theory was correct; `cli.py`'s import pattern was never
broken and was rightly left untouched. `ruff check .` and the full
suite (779 passed) were clean too. `ruff format --check .` flagged two
real files:

**`python/sarand/core/coverage.py:356`** -- a string containing both
an escaped `\"-\"` and an apostrophe (`sarand's`); ruff's quote-style
normalization picked single-quote delimiters (one escape) over the
existing double-quote delimiters (two escapes). Applied ruff's own
diff verbatim. Content unchanged (verified `render_markdown()`'s
output is byte-identical before/after -- only the Python source
literal's delimiter style changed, not the string value), so
`docs/COVERAGE.md` did not need regenerating.

**`tests/golden/hybrid.md:458`** -- more interesting: this project's
ruff (>=0.16) formats Python it finds inside `.md` code fences by
default, and `hybrid.md`'s "FILE: src/main.py" section embeds real
Python source verbatim inside a ` ```python ` fence (that's the whole
point of a golden report -- it's supposed to look like a real report).
Two separate problems bundled in one flagged diff:

1. The fixture's own source string used single-quoted
   `print('hi')` -- ruff wanted `print("hi")`. Fixed by changing the
   fixture's source content in `_golden_fixtures.py` to already be in
   ruff's preferred style, so this can't recur.
2. `markdown.py`'s renderer leaves a blank line between a file's
   content and the closing fence (content already ends in `\n`, then
   the line-join adds another). Ruff's embedded-Python formatter
   strips that trailing blank line as part of formatting the snippet
   as a real Python file would be formatted -- but the golden test's
   whole contract is byte-exact match against what the renderer
   *actually* emits, blank line included. Hand-editing the snapshot to
   match ruff's preference would make the golden test assert something
   the renderer doesn't produce -- the snapshot would then be lying
   about report structure, which is exactly the failure mode section
   5.21 exists to catch. Renderer behavior itself is untouched here on
   purpose (Scope Discipline: a real, minor, unrelated formatting
   quirk in `markdown.py`'s file-embedding logic, not this round's
   item -- noted as a backlog candidate, not fixed).

Fix for problem 2, and the real fix here: added a minimal
`[tool.ruff]` section to `pyproject.toml` (none existed before) with
only `extend-exclude = ["tests/golden"]` -- nothing about lint-rule
selection, so this cannot change what `ruff check` enforces anywhere
else. Golden snapshots are recorded tool *output*, not authored
source; a formatter silently rewriting recorded output on every run
(turning a passing snapshot red with zero actual code change) is a
structural conflict between two kinds of file that happen to share an
extension, not a style problem to negotiate away by hand-editing the
snapshot. `hybrid.md` reverted back to exactly what `markdown.py`
actually renders (blank line included); reran the golden-snapshot
harness after every change in this round, still 10/10.

Also regenerated (no manual edits needed, automatic consequence of
fixing the fixture's source content): `hybrid.json` and `hybrid.html`
both embed the same `src/main.py` content and picked up the
`'hi'` -> `"hi"` change too, correctly -- diffed against the
pre-change files to confirm nothing else moved.

Delivered as `sarand-golden-reports-fix-v2.zip`: `pyproject.toml`,
`python/sarand/core/coverage.py`, `tests/_golden_fixtures.py`,
`tests/golden/hybrid.md`, `tests/golden/hybrid.json`,
`tests/golden/hybrid.html`, full `AGENTS.md`. Not yet re-verified on
device -- ask for `ruff check . && ruff format --check .`,
`rm -rf .mypy_cache && mypy .`, and `pytest -q` once more.


### 5.25 — P1 item 8: Monorepo/Workspace architecture, Cargo-only first scope (2026-09-22)

First P1 item from the backlog doc's own priority order, started right
after P0 items 6.1/7.1 were committed, tagged (v0.6.3), and pushed.
Item 8's own text is explicit that this is a big, multi-ecosystem ask
and that the first pass must be narrow ("do not implement all
ecosystems automatically... do not implement every monorepo ecosystem
in one change") -- so 8.1's required audit came first, then exactly
one ecosystem.

**8.1 audit (evidence-first, against current source, not assumed):**
of the eight workspace models the doc names, confirmed via direct
`grep`/inspection that sarand detects none of them structurally.
Two are genuinely out of scope rather than merely deferred -- Bazel
and Nx/Turborepo -- because sarand has no Bazel analyzer at all (Nx/
Turborepo also need an npm/pnpm/Yarn workspace base first), so there
is no existing execution to represent workspace structure *for* yet;
adding either is a new-analyzer item, prior to anything workspace-
shaped. The other five (npm, pnpm, Yarn workspaces; Gradle multi-
project; Maven multi-module) split into two different kinds of gap,
worth recording because it changes what "fixing" them later means:
Gradle/Maven are representation-only gaps (`./gradlew test`/`mvn
test` from the root already build+test every subproject/module via
those tools' own native multi-project support -- sarand's report just
doesn't say so), while npm/pnpm/Yarn are gaps in both representation
*and* execution (`npm test` at the root only runs the root package's
own script; it does not cascade into workspace packages without that
script opting in or a task runner like Turborepo driving it). Full
detail in `core/workspace.py`'s module docstring, not repeated here.

**8.2 implementation, Cargo workspaces only:** new `core/workspace.py`
(`detect_workspace(root)`, generic name on purpose -- the next
ecosystem becomes another internal check in the same function, not a
new `cli.py` call site) parses the root `Cargo.toml` with the same
`tomllib`/`tomli` pattern `core/license_policy.py` already
established. Handles: `[workspace] members = [...]` including glob
patterns (`"crates/*"`) resolved via `Path.glob` and filtered to only
directories that actually contain a `Cargo.toml` (a glob can otherwise
sweep up a non-crate directory that merely matches); `exclude = [...]`
patterns applied the same way; a root manifest with both `[workspace]`
and its own `[package]` counting the root itself as a member (path
`"."`, a common, valid Cargo layout); a member whose own manifest
fails to parse or names no package falling back to its directory name
rather than crashing or being silently dropped; any Cargo.toml parse
failure (malformed TOML, unreadable file) returning `None` rather than
raising -- deliberately not this detector's job to report a bad
`Cargo.toml`, `RustAnalyzer`'s own `cargo test`/`cargo fmt` runs
already do that loudly.

`WorkspaceInfo`/`WorkspaceMember` live in `models/results.py` (the
project's one canonical models module -- every other result type,
`HealthScore`/`GitSnapshot`/etc., lives there too, and that module's
own docstring forbids it importing from anywhere else in sarand, so
`core/workspace.py` imports the types from there rather than each
module defining its own competing copy). New `ReportData.workspace:
WorkspaceInfo | None = None` field, defaulted so every other
`ReportData` construction anywhere in the codebase and test suite
needed zero changes.

Wired into `cli.py` right next to `detect_project`; a new `## Workspace`
markdown section (`_render_workspace`) and a new (conditionally
present) `"workspace"` JSON key, both **only emitted when a workspace
was actually detected** -- an ordinary, non-workspace project's report
must look exactly as it did before this feature existed. This was not
just a style choice: it's what let this land without touching a single
byte of item 6.1's already-shipped, already-verified-on-device golden
snapshots (both `hybrid`/`minimal` fixtures have `workspace=None`, so
`_render_workspace`/the JSON key are no-ops for them) -- confirmed by
rerunning the golden suite after every change in this round, still
10/10. `html.py`/`text.py`/`sarif.py` were not given a workspace
section this round (non-goal below).

**Definition of Done, checked against the checklist item 8.2 itself
lists:** workspace detection implemented for one explicitly selected
ecosystem (Cargo) -- yes. Root/workspace relationship represented
internally -- yes, `WorkspaceMember.path == "."` for the root-as-member
case. Duplicate execution prevented -- yes by construction: this round
only adds representation/metadata, it does not change which analyzers
run or add any per-member execution, so there is nothing to duplicate.
Report distinguishes root from workspace findings -- partially: the
new section lists members and their paths (markdown + json), but does
not yet attribute individual test/quality/security findings to
specific members (see non-goals). Health aggregation rules defined --
not yet needed: `RustAnalyzer` already runs one aggregate `cargo test
--all` for the whole workspace and health scoring already scores that
one aggregate result the same way it always did, so there is no
per-member health to aggregate yet (would only become relevant once
per-member execution/attribution exists). Representative fixture
exists -- yes, built inline in `tests/test_workspace.py` (a 3-member
+ 1 excluded + 1 non-crate-glob-match Cargo workspace, plus the
root-as-member and fallback-naming cases as separate small fixtures)
rather than a committed fixture directory, since these are tiny and
synthesized per-test. Regression tests exist -- yes, 10 in
`tests/test_workspace.py`: 6 for `detect_workspace` itself (no
Cargo.toml, single-package, malformed TOML, glob+exclude, root-as-
member, name-fallback) and 4 for the two renderers (present/absent for
each). Documentation explains unsupported workspace models -- yes,
`core/workspace.py`'s module docstring audit.

**Non-goals (explicitly, for the next phase of this same backlog
item):** the next ecosystem to detect -- npm/pnpm/Yarn workspaces are
the natural pick per the 8.1 audit above, being both representation
*and* execution gaps, versus Gradle/Maven's representation-only gap.
Per-member test/quality/security attribution (today `cargo test --all`
still runs and reports as one aggregate result; splitting that per
member -- e.g. running `cargo test -p <member>` separately, or parsing
`cargo test --all`'s own output back apart by crate -- is real,
separate work item 8.2's "duplicate execution is prevented" /
"report distinguishes root from workspace findings" checklist items
anticipate but this round does not attempt). Workspace-aware health
aggregation (same dependency as the point above). `html.py`, `text.py`,
`sarif.py` workspace sections. README.md/README.fa.md were
deliberately not updated this round -- advertising a single-ecosystem,
detection-only feature as a headline capability felt premature; this
gets revisited once at least one more ecosystem lands.

Verified locally the same way as 5.21-5.24 (no real `pytest`/`rich` in
this sandbox): ran `detect_workspace` directly against several
constructed temp Cargo-workspace trees before writing the pytest
version, then ran the actual `tests/test_workspace.py` functions
directly -- 10/10 passing -- and reran the full golden-report harness
from 5.21 afterward to confirm the new renderer code paths are true
no-ops for every existing fixture (still 10/10). `tests/test_renderers.py`
(10/10) and `tests/test_coverage.py` (10/10) also rerun clean;
`tests/test_new_renderers.py` could not be run in this sandbox's
minimal `pytest` stub (it uses `pytest.mark.slow_external`, a real
marker registered in `pyproject.toml` that the stub does not define --
a sandbox/stub limitation, not evidence of anything wrong with this
round's changes) but was confirmed syntactically valid and contains
no full-output equality assertions that this round's additive-only
changes could disturb.

Learning from 5.23/5.24's real `ruff format --check` diffs (this
sandbox cannot run `ruff` itself), proactively scanned every line
this round touched for anything over ~88 characters and hand-wrapped
the three real function-call offenses found (one in
`core/workspace.py`, one in `markdown.py`, one in
`tests/test_workspace.py`) the same way ruff's own diffs wrapped
similar calls in 5.24 -- long comment/docstring lines (mostly Persian
prose) were left alone, since ruff format does not reflow comments or
break strings, only wrappable code constructs, which is exactly what
5.24's real diffs showed and what the pre-existing, already-clean
codebase's own long comment lines confirm. Not a guarantee this
sandbox's guess matches ruff's actual output byte-for-byte, but a
real reduction in how many rounds this is likely to take.

On-device run: `ruff check .` and `mypy .` (fresh cache, 176 files)
both clean, full suite 789/789 passed (779 + this round's 10). One
`ruff format --check` miss, smaller than 5.23/5.24's: a quote-style
guess, not a wrapping one -- `tests/test_workspace.py:48` used single
quotes for a string with no internal double quotes to protect
(`'[workspace]\n'`), so ruff preferred double quotes there, same rule
as 5.24's `coverage.py` fix but the other direction. Fixed; every
other single-quoted string in that file has internal double quotes
and was correctly left alone. Item 8's Cargo-only scope is now fully
done and verified.
