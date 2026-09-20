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
| Automated test suite (pytest) | **Implemented and confirmed — 565 tests passing on-device** (`pytest -q`, 2026-09-20, after the §5.12 follow-up on top of v0.5.0; the §5.13 round adds 9 more, confirmed 574; the README round adds 4 more, confirmed 578; the memory-reporting round adds 12, confirmed 590; the hang-fix round adds 1, expected 591 — re-confirm), covering every analyzer/renderer/core module added through §5. CI confirmed green on Linux/macOS/Windows as of the last verified run (see Phase G); re-confirm CI on the current test count next. `pytest` runs everything by default (no `addopts` filtering, §4.8); use `pytest -m "not slow_external"` for a fast local-iteration subset. Two lasting lessons from this project's test-bug history: (1) don't hardcode a "tool not installed" assumption in a test — branch on `shutil.which(...)` (Phase B); (2) don't fake a platform-specific mechanism (env var, well-known dir) — monkeypatch the function that reads it directly, or the test only really runs on whichever OS wrote it (Phase G) |
| `--security` checks | **Implemented and tested** — per-language `run_security` (pip-audit + bandit / cargo-audit / govulncheck / npm audit), all gated on real markers + toolchain presence, run concurrently via `run_security_concurrently` |
| Secrets exclusion from reports (§4.10) | **Implemented and tested** — filename-based exclusion (`.pem`, `.env*`, `id_rsa`, service-account JSON, ...) always on; content-based regex scan (`core/secrets.py`) always on; any file with a content-level finding is moved out of the source-embed list entirely (`exclude_flagged_files`), not just flagged — regression-tested end-to-end (`tests/test_secrets.py::test_end_to_end_flagged_file_content_never_reaches_markdown_report`) |
| `sarand doctor` command (§4.11) | **Implemented, tested, and redesigned for readability** — `sarand --doctor` (flag, not a subcommand — see Phase C note below): checks Python version (critical), Rust core, persisted config, and 15 tool binaries, now grouped into two `rich.table.Table`s (Core, then per-language tools) inside `rich.panel.Panel`s instead of a flat list — a maintainer read the flat version as "many things sarand doesn't support" rather than "optional external tools you can install if you use that language"; each row now states explicitly what it's used for (e.g. "--security", "Gradle & Android projects"). Real `rich` isn't available in the build sandbox, so the visual result is unverified by the assistant — confirm it looks right on-device |
| HTML dashboard renderer | **Implemented and tested** — `renderers/html.py`, self-contained single file (inline CSS, no external assets), dark-mode, collapsible `<details>` sections, properly HTML-escaped |
| PDF / SARIF renderers | **Implemented and tested** — `renderers/sarif.py` (valid SARIF 2.1.0 JSON: secret findings as located errors, TODOs as located notes, tool warnings/errors unlocated). `renderers/pdf.py` shells out to an installed `wkhtmltopdf`/`weasyprint` on the HTML renderer's output rather than adding a heavy Python PDF dependency — gates cleanly with a fix-it message if neither is present. Verified end-to-end: real PDF produced (`%PDF-1.4` magic bytes, 42 KB) via `wkhtmltopdf` |
| Incremental scan cache | **Implemented and tested** — opt-in via `--cache` (deliberately NOT default; see the rationale in Phase E notes below and §4.8). Scoped to the Python side only: skips re-scanning TODOs/secrets in files whose content hash is unchanged since the last `--cache` run for the same project; does not change how `walker.rs` itself works. Cache lives under the *output* dir (`.sarand-cache/`), never inside the scanned project. Auto-invalidates if the detection rules themselves change (`rules_fingerprint`). `--clear-cache` wipes it. Verified end-to-end on a real 3-run sequence: cold run, warm run (byte-identical report, confirmed via matching SHA256), and a changed-file run that correctly found a newly added FIXME marker while still skipping the untouched file |
| Additional language analyzers (C/C++, Java/Kotlin, Android, Zig, Dart, Ruby, PHP, Lua, Swift, C#, TypeScript, CSS, SQL, Kotlin, Shell, YAML, JSON, TOML, XML, R, Perl, Julia, Objective-C, Groovy, PowerShell, Nix) | **All implemented and tested — 31 analyzers total (Markdown added in the P0 round).** C/C++, Java/Kotlin, Android landed first (Phase C); Lua, Ruby, PHP, Dart/Flutter, TypeScript, CSS, Zig, Swift, SQL, Kotlin, C#, Shell, and the YAML/JSON/TOML/XML format analyzers (§5.4) landed in the first post-§4 round; R, Perl, Julia, Objective-C, Groovy, PowerShell, and Nix landed in a second round (§5.8) — see §5 for the conventions established along the way (bundler-wrapped-tool pattern, complementary-match analyzers, honest-empty precedent, format-analyzer category). Full roster in §5.6/§5.9 |
| Packaging (pipx, Docker, AUR, Homebrew, deb/rpm, standalone binary) | **pipx: implemented and confirmed** — `pipx install ~/sarand` builds the Rust extension inside pipx's isolated venv and installs cleanly; `sarand --doctor` confirmed "Rust core: compiled and loaded" post-install, no manual venv/PATH steps needed. `install.sh` added (§4.13) so upgrading an existing pipx install actually picks up new code — a raw `pipx install` over a stale copy silently doesn't, since pipx installs aren't editable by default. LICENSE (MIT) and full `pyproject.toml` metadata (classifiers, keywords) added. **AUR: `pkgs/aur/PKGBUILD` written**, not yet verified with a real `makepkg -si` in a clean chroot (see Phase F, still open). Docker/Homebrew/deb/rpm/binary: not started |
| Report replacement (§4.13) | **Implemented and tested** — `cli.py::remove_previous_report` explicitly checks for, removes, and announces a previous report (+ its `.sha256`) at the exact output path before writing a new one, for the same "check, remove, announce, create fresh" reason as `install.sh` |
| `--full` flag | **Implemented and tested — completeness gaps found and fixed 2026-09-18.** Forces `--quality`+`--security` on and removes the file-size/tree-depth/tree-entry truncation limits (raised to effectively-unlimited sentinel values), while still letting an explicit `--max-depth`/`--max-entries`/`--max-file-size` win over `--full`'s own defaults. An external audit of a real `--full` report found this description was not the whole truth: the **rendering layer** ignored `--full` entirely — a *passing* tool's output was always cut to an 80-line tail (raw output only shown on FAIL), issue lists capped at 500 rows and TODOs at 100 regardless of `--full`, and **`--format json` never embedded source code at all** (`include_source` was accepted in the signature and silently never read — the one format most likely to be piped straight into another AI's context had zero source, full stop). All four fixed: `config.full` is now stored on `SarandConfig` and threaded into every renderer as `full_output`; JSON gained a real `source_files: [{path, size, content}]` array; markdown/html now show a passing tool's full raw output and uncap issues/TODOs under `--full`. See §5.10 for what's still open (git history/contributor/hotspot depth) |
| `scripts/paste_chunks.py` | **Rewritten from a maintainer-supplied script and merged in** — chunked, resumable paste helper for chat UIs without file upload (e.g. pasting a `sarand --full` report into ChatGPT). Generalized from a hardcoded README.md/BiMarz-specific tool to work on any file, with per-source-file state namespacing (mirrors `core/cache.py`'s per-project namespacing). Fixed three real bugs found on review (dead `initialize` param, a shallow-copy rollback that only worked by accident, a UX trap where re-running with no flags mid-block silently repeated chunk 0 instead of continuing) — see the module's own docstring for details. Added OSC52 terminal-escape-sequence clipboard support as the primary copy mechanism, since it is the *only* clipboard method that works at all on the maintainer's actual hardware (non-rooted Android, Termux/Kali NetHunter proot, no X11/Wayland session) — `xclip`/`xsel`/`wl-copy` have no display server to talk to there. `OSC52_MAX_BYTES = 6000` applies to the raw text *before* base64 encoding (an empirically-tested ceiling on that hardware/terminal combination, not the final escape-sequence length) |
| CI | **Confirmed green on all three OSes** — public at `github.com/msoleimani62/sarand`. Two real issues found and fixed across the first three runs (see Phase G notes): a CI-infra bug (`maturin develop` needs a virtualenv CI runners don't have) and a genuine cross-platform test-isolation bug (two tests relied on `XDG_CONFIG_HOME`, which the product code only honors on Linux by design — the product code was correct, the tests weren't platform-independent). Run #3: `ubuntu-latest`, `macos-latest`, `windows-latest` all passed |

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
