# AGENTS.md — sarand project constitution

> [!IMPORTANT]
> **⚠️ Binding directive**
>
> Before performing any action in this repository — writing code, modifying files, running commands, reviewing changes, or proposing architectural decisions — every AI agent (Claude Code, Aider, Cursor, Codex, or equivalent) and every human contributor **must** read this document in full. It is the single source of truth for this project. Where anything here conflicts with general "best practice" you might otherwise default to, this file wins, for this repository.
>
> Work done without following this document is not accepted.

---

> [!NOTE]
> **Backlog first pass complete (2026-10-04).** Every item of the
> engineering backlog (`docs/BACKLOG.md`, adopted 2026-09-22) has an
> evidence-first audit and a first-scope delivery, or an out-of-scope reason.
> `docs/BACKLOG_STATUS.md` holds the final state, the working rules and the
> list of what remains -- read it before re-deriving priorities or
> re-auditing something already resolved. `docs/BACKLOG.md` is kept until the
> follow-ups listed there are done, because their Definition of Done lives in
> it; then both files get deleted. The permanent historical record lives in
> `docs/history/`.
>
> **Starting a new session?** Read `docs/BACKLOG_STATUS.md` (the live state and the
> audit program), then section 5.54 (the session handoff: working loop, release
> procedure, lint and CI lessons) in `docs/history/AGENTS-HISTORY-5.27-5.60.md`, then only the
> sections they point to.

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

3. **Explicit fixture allowlist** (since 5.67) — whether a finding counts
   against the health score is decided by `[secrets] fixture_paths` in the
   project's `.sarand.toml` (`core/secrets_config.py`), never by guessing
   from the path. The default is empty. Allow-listed files are still never
   embedded and their findings are still listed.

Since 5.67 the content scan has 16 rules (provider tokens, private-key
blocks incl. PGP and encrypted, JWT, credentials in URLs, assignments to
password-like names), every one linear-time on adversarial input, and with
`--security` a file that `gitleaks` names is moved out of the source dump too
(`gitleaks_flagged_paths`, `secrets.exclude_paths`).

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

## 6. Current state

This section was a snapshot of 2026-10 and went stale with every round. The live
state is `docs/BACKLOG_STATUS.md`; the snapshot itself is kept, unchanged, in
`docs/history/AGENTS-STATE-AND-ROADMAP.md`.

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

Phases A to H (all done except the deferred phase H) are kept, unchanged, in
`docs/history/AGENTS-STATE-AND-ROADMAP.md`. What remains is listed in `docs/BACKLOG_STATUS.md`.

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

## History: the dated rounds (5.1 and on)

Every development round used to append a dated section here, which grew this file
to about 300 KB and made every agent session start by loading 75k tokens. The
rounds are cited throughout the code as `AGENTS.md 5.NN`; they now live, word for
word, in:

- `docs/history/AGENTS-HISTORY-5.1-5.26.md`: rounds 5.1 to 5.26
- `docs/history/AGENTS-HISTORY-5.27-5.60.md`: rounds 5.27 to 5.60
- `docs/history/AGENTS-HISTORY-5.61-5.74.md`: rounds 5.61 to 5.74

The session handoff (5.54) is in `docs/history/AGENTS-HISTORY-5.27-5.60.md`. To find a round, search
`docs/history/` for its number. A new round is still recorded as a dated section,
in the newest history file (not here), and its rules, if it adds any, are added to
sections 1 to 4 above.
