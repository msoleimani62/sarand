# AGENTS.md — sarand project constitution

This file is the source of truth for any AI agent (Claude Code, Aider, Cursor,
Codex, or a human) working on this repository. Read this in full before
touching any code. If an instruction here conflicts with something you
"know" about good practice in general, this file wins for this repo.

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
directory it is pointed at, full stop. This was the very first bug fixed in
this project's history and must never regress.

---

## 2. Architecture

```
sarand/
├── Cargo.toml, src/*.rs        Rust core, compiles to `sarand._core`
│   ├── walker.rs                parallel, .gitignore-aware file walk
│   ├── linecount.rs              binary detection + LOC counting
│   ├── hasher.rs                 SHA-256 (duplicate-file detection)
│   ├── tree.rs                   ASCII project tree builder
│   └── lib.rs                    PyO3 bindings (thin translation layer only)
│
└── python/sarand/
    ├── models/results.py         dependency-free dataclass layer (see rule 3)
    ├── constants.py               all tunables, project markers, ignore lists
    ├── rust_bridge.py             THE ONLY file allowed to import sarand._core
    ├── discovery/                 language/project-type detection
    ├── scanners/                  git, environment, stats, tree, TODOs
    ├── analyzers/                 one file per language, pluggable (see rule 6)
    │   ├── base.py                 LanguageAnalyzer Protocol
    │   ├── registry.py             built-in list + entry_points plugin loading
    │   └── {python,rust,go,node}_analyzer.py
    ├── core/                      health.py, ai_summary.py, issues.py
    ├── renderers/                 one file per output format (see rule 7)
    ├── userconfig.py              persisted config (~/.config/sarand/config.json)
    ├── config.py                  CLI-argument → runtime config resolution
    ├── progress.py                Rich-based terminal output
    └── cli.py                     argparse + async orchestration
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

---

## 3. Coding rules (non-negotiable)

These are established project conventions. Follow them exactly; do not
"improve" them without discussing first.

### 3.1 Layering — no import cycles, ever

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

### 3.2 Never hardcode a specific project

No file path, project name, or user-specific assumption is ever allowed in
core logic (constants.py, discovery/, scanners/, analyzers/, cli.py). Every
project sarand analyses is discovered at runtime from the target directory
alone. This is the #1 rule this project exists to enforce on itself.

### 3.3 Gate every external tool call on a real project marker

Never run `pytest`, `ruff`, `npm test`, etc. just because the binary
happens to be on PATH. Each `LanguageAnalyzer.matches(root)` must check for
a real marker file (`pyproject.toml`, `Cargo.toml`, `go.mod`,
`package.json`, ...) before that analyzer's `run_tests`/`run_quality` are
ever called. `NodeAnalyzer` additionally requires a real `"test"` script in
`package.json` before running `npm test` — running it unconditionally just
produces a useless "no test specified" failure. This class of bug (bxt used
to run `pytest` on non-Python projects just because pytest was installed
globally) must never come back.

### 3.4 One file per unit

One file per language analyzer (`analyzers/*.py`), one file per output
renderer (`renderers/*.py`), one file per scanning concern
(`scanners/*.py`). Never merge two languages or two output formats into one
file "for convenience" — the whole point of this architecture is that
adding a language or format means adding one file, not editing a
monolithic module.

### 3.5 `rust_bridge.py` is the only Rust import boundary

No file other than `rust_bridge.py` may `import sarand._core`. Every public
function in `rust_bridge.py` must have a pure-Python fallback that produces
the **exact same data shape** (same dict keys, same semantics) as the Rust
path. This is what makes the Rust core optional rather than required —
sarand must keep working on a platform where `maturin develop` fails to
compile (this has real precedent: exotic Termux/aarch64 toolchains).
Never let a downstream module (`scanners/`, `analyzers/`, `cli.py`) branch
on `RUST_CORE_AVAILABLE` itself — that decision belongs in `rust_bridge.py`
alone.

### 3.6 Async for independent work

Independent external command invocations (different languages' test/lint
runs) run concurrently via `asyncio.gather`, never chained sequentially
without a reason. See `analyzers/registry.py`
(`run_tests_concurrently`/`run_quality_concurrently`) and
`utils/command.py` (`run_cmd_async`). If you add a new kind of independent
work, make it async and fan it out the same way.

### 3.7 Bilingual comments in code

Wherever a comment is genuinely needed to explain *why* (not what), write
it in Persian **and** English, back to back, no exceptions:

```python
# دلیل فارسیِ این تصمیم
# The English reason for this decision
```

Comments that just restate the code ("# increment counter") should not
exist at all in either language. Do not add decorative comments; only
comment where the reasoning isn't obvious from the code itself.

### 3.8 Verification requirements

- Every Python change must be import-tested and, where practical, run
  end-to-end against a throwaway test project before being considered done.
- Rust changes cannot always be compile-verified by an assistant without a
  local toolchain — they must be verified by actually running
  `maturin develop --release` and reporting the exact compiler output back.
  Do not claim a Rust change "works" without that confirmation.
- Never claim test coverage or verification that didn't actually happen.

### 3.9 Working-session conventions (for Claude Code / assistant sessions)

- Respond to the maintainer in Persian; keep code/comments per rule 3.7.
- No comments inside standalone terminal/shell command blocks — put any
  needed explanation before or after the command block instead.
- When a deliverable spans multiple files, bundle them into a single zip
  rather than presenting file-by-file.
- Give complete, production-ready file contents, not partial diffs, unless
  a `sed`/`str_replace`-style targeted patch is clearly smaller and safer.
- No flattery, no unnecessary praise. If something the maintainer proposes
  doesn't make sense, say so plainly and explain why, with a better
  alternative.
- Prefer the objectively best language/tool for a given task; if a project
  already has an established language and a sub-task genuinely needs a
  different one, say so explicitly rather than silently picking one.
- If a task is left unfinished and the maintainer says "continue", resume
  exactly where the previous session stopped rather than restarting.

---

## 4. Current state (as of the initial commit)

| Area | Status |
|---|---|
| Rust core (walker/linecount/hasher/tree + PyO3 bindings) | **Compiles and runs** (`maturin develop --release`, verified on aarch64/Termux, `PyDict::new_bound` fix applied for pyo3 0.22 pin) |
| Pure-Python fallback | Implemented and tested; produces identical report structure |
| Language analyzers | Python, Rust, Go, Node.js — all gated on real markers |
| Async concurrent test/quality execution | Implemented (`asyncio.gather`) |
| Single shared filesystem scan | Implemented — tree/stats/essential-files/TODOs all read from one `scan_project()` call |
| Persisted output-dir config | Implemented (`sarand --set-output-dir`, OS-appropriate path) |
| Markdown / JSON / text renderers | Implemented |
| Health score engine | Implemented (tests/quality/security/git/code/tooling breakdown) |
| **Automated test suite (pytest)** | **Not implemented — highest-priority gap** |
| `--security` checks | Not implemented (flag exists, prints a warning and no-ops) |
| HTML dashboard renderer | Not implemented |
| PDF / SARIF renderers | Not implemented |
| Incremental scan cache | Not implemented (Rust hasher exists and is ready to be reused for this) |
| Additional language analyzers (C/C++, Java/Kotlin, Zig, Dart, Ruby, PHP, Lua, Swift, C#) | Not implemented — `discovery` can *detect* several of these via `PROJECT_MARKERS`, but no `LanguageAnalyzer` exists for them yet |
| Packaging (pipx, Docker, AUR, Homebrew, deb/rpm, standalone binary) | Not started — currently `maturin develop` / `pip install -e .` only |
| CI | Not set up |
| Plugin authoring docs beyond the README snippet | Not written |

---

## 5. Roadmap (in priority order)

### Phase A — Test suite (do this first, before any new feature)

Add `tests/` with pytest. Minimum coverage:
- `discovery/project_detector.py`: each marker type, multi-marker (polyglot)
  repos, the extension-guessing fallback with no markers at all.
- `rust_bridge.py`: run the *same* test cases against both the Rust path
  and the pure-Python fallback (parametrize on `RUST_CORE_AVAILABLE`) and
  assert identical output shape — this is the contract in rule 3.5 and it
  needs an automated check, not just manual verification.
- `analyzers/*`: `matches()` gating (true/false cases), and that
  `run_tests`/`run_quality` return a skipped `CommandResult` (not a crash)
  when the toolchain binary is missing.
- `core/health.py`: score boundaries for each grade band.
- `renderers/*`: given a fixed `ReportData` fixture, snapshot-test the
  output of each renderer.
- `cli.py`: `--set-output-dir` round-trip, `SarandConfig.from_args` default
  resolution (project/output-dir/output-name priority chains).

Target: every module in the table above marked "Implemented" gets real
coverage before Phase B starts.

### Phase B — Security checks

Extend `LanguageAnalyzer` (base.py) with an `async def run_security(self,
root: Path) -> list[CommandResult]` method. Implement per language,
gated the same way as `run_quality`:
- Python: `pip-audit` (dependency CVEs), `bandit` (static analysis)
- Rust: `cargo audit`
- Go: `govulncheck`
- Node.js: `npm audit`

Wire into `cli.py` behind the existing `--security` flag (currently a
no-op warning — replace it). Also add a lightweight secrets scan
(regex-based, no external tool dependency) as a cross-language check, not
tied to any one analyzer.

### Phase C — More language analyzers

Add one file per language under `analyzers/`, matching the existing
pattern exactly (`matches`, `entry_points`, `run_tests`, `run_quality`,
later `run_security`). Suggested order based on likely real-world use:
C/C++ (CMake), Java/Kotlin (Gradle/Maven), then the rest from the original
wishlist (Zig, Dart, Ruby, PHP, Lua, Swift, C#) as actually needed —
`discovery/PROJECT_MARKERS` already has some of these; extend it as new
analyzers are added rather than ahead of time.

### Phase D — Additional renderers

- `renderers/html.py`: dashboard-style HTML report (dark mode, collapsible
  sections). Reuse `ReportData` — no changes to the data model needed.
- `renderers/pdf.py`, `renderers/sarif.py`: same pattern.
Each is purely additive: implement `render(data, *, include_source=True) ->
str`, register in `cli.py`'s `_RENDERERS` dict, add to the `--format`
choices and `SarandConfig.validate()`'s allowed set.

### Phase E — Incremental scan cache

Use `rust_bridge`'s existing per-file SHA-256 hashes: store a
`{rel_path: (mtime, hash)}` map from the previous run (e.g.
`.sarand-cache/scan.json` inside the *output* dir, never inside the
scanned project itself), skip re-hashing/re-counting unchanged files on
the next run. This is additive to `walker.rs`/`rust_bridge.py`, not a
rewrite.

### Phase F — Packaging

In this order: `pipx` (works today via the existing `pyproject.toml`
entry point — just needs prebuilt wheels via `maturin build --release` for
each target platform), then Docker, then AUR (since the maintainer runs
Arch), then Homebrew, then deb/rpm, then a standalone binary as a stretch
goal. Do not attempt all of these in one pass — one packaging target per
phase, verified working, before starting the next.

### Phase G — CI

GitHub Actions (once the repo has a remote): matrix build across
Linux/macOS/Windows × the Rust core, running Phase A's test suite plus a
`maturin build --release` smoke test on each platform.

---

## 6. Definition of done (applies to every phase above)

A task in this repo is not done until:
1. Python changes are import-tested and run end-to-end against a real or
   throwaway project directory.
2. Any Rust change has been confirmed by the maintainer actually running
   `maturin develop --release` and reporting success.
3. The pure-Python fallback path (rule 3.5) still produces equivalent
   output — verify by temporarily renting `sarand._core` import or running
   in an environment where it was never built.
4. `AGENTS.md` (this file) is updated if the change affects architecture,
   adds a new rule, or changes the roadmap/status table in section 4.
5. No project-specific hardcoding was introduced (rule 3.2) and no
   external tool runs unconditionally (rule 3.3).
