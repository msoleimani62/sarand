# AGENTS.md — sarand project constitution

> [!IMPORTANT]
> ### ⚠️ Binding directive
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

```
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
| Automated test suite (pytest) | **Implemented and confirmed, CI-green on all 3 OSes as of the 104-test checkpoint** — 119 tests now (added `test_report_replacement.py`, `test_android_analyzer.py`, `test_doctor_v2.py`; not yet re-confirmed on CI, do that next). Real `pytest -v` confirmed 100/100 on the maintainer's device pre-CI, and CI's own run #3 confirmed all 104 passing on Linux/macOS/Windows (see Phase G). `pytest` runs everything by default (no `addopts` filtering, §4.8); use `pytest -m "not slow_external"` for a fast local-iteration subset. Two lasting lessons from this project's test-bug history: (1) don't hardcode a "tool not installed" assumption in a test — branch on `shutil.which(...)` (Phase B); (2) don't fake a platform-specific mechanism (env var, well-known dir) — monkeypatch the function that reads it directly, or the test only really runs on whichever OS wrote it (Phase G) |
| `--security` checks | **Implemented and tested** — per-language `run_security` (pip-audit + bandit / cargo-audit / govulncheck / npm audit), all gated on real markers + toolchain presence, run concurrently via `run_security_concurrently` |
| Secrets exclusion from reports (§4.10) | **Implemented and tested** — filename-based exclusion (`.pem`, `.env*`, `id_rsa`, service-account JSON, ...) always on; content-based regex scan (`core/secrets.py`) always on; any file with a content-level finding is moved out of the source-embed list entirely (`exclude_flagged_files`), not just flagged — regression-tested end-to-end (`tests/test_secrets.py::test_end_to_end_flagged_file_content_never_reaches_markdown_report`) |
| `sarand doctor` command (§4.11) | **Implemented, tested, and redesigned for readability** — `sarand --doctor` (flag, not a subcommand — see Phase C note below): checks Python version (critical), Rust core, persisted config, and 15 tool binaries, now grouped into two `rich.table.Table`s (Core, then per-language tools) inside `rich.panel.Panel`s instead of a flat list — a maintainer read the flat version as "many things sarand doesn't support" rather than "optional external tools you can install if you use that language"; each row now states explicitly what it's used for (e.g. "--security", "Gradle & Android projects"). Real `rich` isn't available in the build sandbox, so the visual result is unverified by the assistant — confirm it looks right on-device |
| HTML dashboard renderer | **Implemented and tested** — `renderers/html.py`, self-contained single file (inline CSS, no external assets), dark-mode, collapsible `<details>` sections, properly HTML-escaped |
| PDF / SARIF renderers | **Implemented and tested** — `renderers/sarif.py` (valid SARIF 2.1.0 JSON: secret findings as located errors, TODOs as located notes, tool warnings/errors unlocated). `renderers/pdf.py` shells out to an installed `wkhtmltopdf`/`weasyprint` on the HTML renderer's output rather than adding a heavy Python PDF dependency — gates cleanly with a fix-it message if neither is present. Verified end-to-end: real PDF produced (`%PDF-1.4` magic bytes, 42 KB) via `wkhtmltopdf` |
| Incremental scan cache | **Implemented and tested** — opt-in via `--cache` (deliberately NOT default; see the rationale in Phase E notes below and §4.8). Scoped to the Python side only: skips re-scanning TODOs/secrets in files whose content hash is unchanged since the last `--cache` run for the same project; does not change how `walker.rs` itself works. Cache lives under the *output* dir (`.sarand-cache/`), never inside the scanned project. Auto-invalidates if the detection rules themselves change (`rules_fingerprint`). `--clear-cache` wipes it. Verified end-to-end on a real 3-run sequence: cold run, warm run (byte-identical report, confirmed via matching SHA256), and a changed-file run that correctly found a newly added FIXME marker while still skipping the untouched file |
| Additional language analyzers (C/C++, Java/Kotlin, Android, Zig, Dart, Ruby, PHP, Lua, Swift, C#) | **C/C++, Java/Kotlin, and a dedicated Android/Kotlin analyzer implemented and tested** (`analyzers/cpp_analyzer.py`, `analyzers/java_analyzer.py`, `analyzers/android_analyzer.py`). Android was prioritized ahead of the rest of this row per an explicit maintainer request. Remaining: Zig, Dart, Ruby, PHP, Lua, Swift, C# — not started, add as actually needed (§8 Phase C guidance still applies) |
| Packaging (pipx, Docker, AUR, Homebrew, deb/rpm, standalone binary) | **pipx: implemented and confirmed** — `pipx install ~/sarand` builds the Rust extension inside pipx's isolated venv and installs cleanly; `sarand --doctor` confirmed "Rust core: compiled and loaded" post-install, no manual venv/PATH steps needed. `install.sh` added (§4.13) so upgrading an existing pipx install actually picks up new code — a raw `pipx install` over a stale copy silently doesn't, since pipx installs aren't editable by default. LICENSE (MIT) and full `pyproject.toml` metadata (classifiers, keywords) added. Docker/AUR/Homebrew/deb/rpm/binary: not started |
| Report replacement (§4.13) | **Implemented and tested** — `cli.py::remove_previous_report` explicitly checks for, removes, and announces a previous report (+ its `.sha256`) at the exact output path before writing a new one, for the same "check, remove, announce, create fresh" reason as `install.sh` |
| `--full` flag | **Implemented and tested** — shorthand for maximum-completeness reports: forces `--quality`+`--security` on and removes the file-size/tree-depth/tree-entry truncation limits entirely (raised to effectively-unlimited sentinel values), while still letting an explicit `--max-depth`/`--max-entries`/`--max-file-size` win over `--full`'s own defaults |
| `scripts/paste_chunks.py` | **Rewritten from a maintainer-supplied script and merged in** — chunked, resumable paste helper for chat UIs without file upload (e.g. pasting a `sarand --full` report into ChatGPT). Generalized from a hardcoded README.md/BiMarz-specific tool to work on any file, with per-source-file state namespacing (mirrors `core/cache.py`'s per-project namespacing). Fixed three real bugs found on review (dead `initialize` param, a shallow-copy rollback that only worked by accident, a UX trap where re-running with no flags mid-block silently repeated chunk 0 instead of continuing) — see the module's own docstring for details. Added OSC52 terminal-escape-sequence clipboard support as the primary copy mechanism, since it is the *only* clipboard method that works at all on the maintainer's actual hardware (non-rooted Android, Termux/Kali NetHunter proot, no X11/Wayland session) — `xclip`/`xsel`/`wl-copy` have no display server to talk to there. `OSC52_MAX_BYTES = 6000` applies to the raw text *before* base64 encoding (an empirically-tested ceiling on that hardware/terminal combination, not the final escape-sequence length) |
| CI | **Confirmed green on all three OSes** — public at `github.com/msoleimani62/sarand`. Two real issues found and fixed across the first three runs (see Phase G notes): a CI-infra bug (`maturin develop` needs a virtualenv CI runners don't have) and a genuine cross-platform test-isolation bug (two tests relied on `XDG_CONFIG_HOME`, which the product code only honors on Linux by design — the product code was correct, the tests weren't platform-independent). Run #3: `ubuntu-latest`, `macos-latest`, `windows-latest` all passed |

---
| pipx install robustness | **A real pipx bug hit and worked around** — pipx's own internal per-venv metadata can get corrupted independently of anything sarand does ("Unknown metadata version N. Perhaps it was installed with a later version of pipx" — a known upstream issue, https://github.com/pypa/pipx/issues/1619). When it happens, `pipx list` silently omits the corrupted entry AND `pipx uninstall` fails the same way trying to read it, so `install.sh` now falls back to removing `~/.local/share/pipx/venvs/sarand` directly if either the venv is present-but-untracked or `pipx uninstall` itself fails |
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

### Phase C — `sarand doctor` + more language analyzers ✅ done (Zig/Dart/Ruby/PHP/Lua/Swift/C# deferred)

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
- Zig, Dart, Ruby, PHP, Lua, Swift, C# remain unimplemented. Add them the
  same way, one file each, only when actually needed — don't pre-build
  analyzers for languages nobody has asked to scan yet.

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

**Reordering the remaining targets from the original plan:** the
original order was Docker → AUR → Homebrew → deb/rpm → binary. Nothing
in this project's actual usage (Android/Termux/Kali NetHunter phone +
Arch Linux laptop) involves Docker — there's no described workflow that
needs it, and running a container inside a Termux proot is its own can
of worms. AUR is directly useful (the maintainer runs Arch daily) and
is a natural next step once a package is installable via pipx/PyPI-style
tooling. Revised order: **AUR next**, then Docker/Homebrew/deb/rpm/
binary only if a real need for them shows up later — don't build
packaging for platforms nobody described using, mirroring the same
"don't pre-build analyzers for languages nobody asked to scan" principle
from Phase C.

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
