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
│   ├── discovery/                 language/project-type detection
│   ├── scanners/                  git, environment, stats, tree, TODOs
│   ├── analyzers/                 one file per language, pluggable (§4.4, §4.9)
│   │   ├── base.py                 LanguageAnalyzer Protocol
│   │   ├── registry.py             built-in list + entry_points plugin loading
│   │   └── {python,rust,go,node,cpp,java}_analyzer.py
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
| Automated test suite (pytest) | **Implemented and confirmed** — 100 tests across `test_project_detector.py`, `test_rust_bridge.py`, `test_analyzers.py`, `test_health.py`, `test_renderers.py`, `test_config.py`, `test_secrets.py`, `test_doctor.py`, `test_cpp_java_analyzers.py`, `test_new_renderers.py`, `test_cache.py`. Real `pytest -v` run on the maintainer's device confirmed 86/86 at the Phase D checkpoint (including the Rust-vs-Python cross-check and the real, installed `cargo-audit`/`wkhtmltopdf` paths); Phase E's additional 14 were verified with the same stdlib-only collector pre-delivery, plus a manual 3-run end-to-end cache sequence (cold/warm/changed-file) confirmed on the build side — confirm the new total with a real `pytest -v` run next. `pytest` runs everything by default (no `addopts` filtering, §4.8); use `pytest -m "not slow_external"` for a fast local-iteration subset. Test-bug lesson from Phase B, still worth repeating: two security-check tests once hardcoded a "tool not installed" assumption that only held in the original sandbox — both now branch on `shutil.which(...)` instead of assuming either way |
| `--security` checks | **Implemented and tested** — per-language `run_security` (pip-audit + bandit / cargo-audit / govulncheck / npm audit), all gated on real markers + toolchain presence, run concurrently via `run_security_concurrently` |
| Secrets exclusion from reports (§4.10) | **Implemented and tested** — filename-based exclusion (`.pem`, `.env*`, `id_rsa`, service-account JSON, ...) always on; content-based regex scan (`core/secrets.py`) always on; any file with a content-level finding is moved out of the source-embed list entirely (`exclude_flagged_files`), not just flagged — regression-tested end-to-end (`tests/test_secrets.py::test_end_to_end_flagged_file_content_never_reaches_markdown_report`) |
| `sarand doctor` command (§4.11) | **Implemented and tested** — `sarand --doctor` (flag, not a subcommand — see Phase C note below): checks Python version (critical), Rust core, persisted config, and 15 tool binaries (13 per-language + wkhtmltopdf/weasyprint for PDF export, added during Phase D); never fails on a missing optional tool |
| HTML dashboard renderer | **Implemented and tested** — `renderers/html.py`, self-contained single file (inline CSS, no external assets), dark-mode, collapsible `<details>` sections, properly HTML-escaped |
| PDF / SARIF renderers | **Implemented and tested** — `renderers/sarif.py` (valid SARIF 2.1.0 JSON: secret findings as located errors, TODOs as located notes, tool warnings/errors unlocated). `renderers/pdf.py` shells out to an installed `wkhtmltopdf`/`weasyprint` on the HTML renderer's output rather than adding a heavy Python PDF dependency — gates cleanly with a fix-it message if neither is present. Verified end-to-end: real PDF produced (`%PDF-1.4` magic bytes, 42 KB) via `wkhtmltopdf` |
| Incremental scan cache | **Implemented and tested** — opt-in via `--cache` (deliberately NOT default; see the rationale in Phase E notes below and §4.8). Scoped to the Python side only: skips re-scanning TODOs/secrets in files whose content hash is unchanged since the last `--cache` run for the same project; does not change how `walker.rs` itself works. Cache lives under the *output* dir (`.sarand-cache/`), never inside the scanned project. Auto-invalidates if the detection rules themselves change (`rules_fingerprint`). `--clear-cache` wipes it. Verified end-to-end on a real 3-run sequence: cold run, warm run (byte-identical report, confirmed via matching SHA256), and a changed-file run that correctly found a newly added FIXME marker while still skipping the untouched file |
| Additional language analyzers (C/C++, Java/Kotlin, Zig, Dart, Ruby, PHP, Lua, Swift, C#) | **C/C++ and Java/Kotlin implemented and tested** (`analyzers/cpp_analyzer.py`, `analyzers/java_analyzer.py`). Remaining: Zig, Dart, Ruby, PHP, Lua, Swift, C# — not started, add as actually needed (§8 Phase C guidance still applies) |
| Packaging (pipx, Docker, AUR, Homebrew, deb/rpm, standalone binary) | Not started — currently `maturin develop` / `pip install -e .` (in a venv) only |
| CI | Not set up |

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

In this order: `pipx` (works today via the existing `pyproject.toml` entry
point — just needs prebuilt wheels via `maturin build --release` per
target platform), then Docker, then AUR (the maintainer runs Arch), then
Homebrew, then deb/rpm, then a standalone binary as a stretch goal. One
packaging target per phase, verified working, before starting the next.

### Phase G — CI

GitHub Actions (once the repo has a remote): matrix build across
Linux/macOS/Windows × the Rust core, running Phase A's test suite plus a
`maturin build --release` smoke test on each platform.

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
