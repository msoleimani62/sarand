# Backlog status (temporary tracking file)

**Purpose:** `docs/BACKLOG.md` (the full "Engineering Backlog & Gap
Audit" doc) defines the process and every item. This file is the
*current, actively-updated* status against that doc -- read this
first, in a new conversation, to see what's done and what's next
without re-reading every dated round in `AGENTS.md`.

**This file is temporary.** Once every item in `docs/BACKLOG.md` is
CONFIRMED done (or explicitly OUT OF SCOPE with reasons recorded),
delete both `docs/BACKLOG.md` and this file -- their job is
cross-session continuity while the backlog is in progress, not
permanent documentation. `AGENTS.md` keeps the full historical
record either way.

**How to pick up work in a new conversation:** read this file, then
`docs/BACKLOG.md` sections 2-5 and 20-21 (Evidence-First Rule, Scope
Discipline, Priority Model, Definition of Done, Investigation/
Validation Protocol -- the process itself, unchanged since adoption).
Continue with the next "Not started" item in priority order below,
unless the person says otherwise. Do not re-verify already-CONFIRMED
items without a specific reason to doubt them.

Last updated: 2026-10-01. Latest tag: v0.6.6. `main` is ahead of that
tag by the in-progress Kubernetes/Helm/Kustomize work (uncommitted as
of this update).

---

## P0

### 6.1 — Golden / representative report regression infrastructure
**Status: RESOLVED.** `tests/test_golden_reports.py` +
`tests/_golden_fixtures.py`, two hand-built `ReportData` fixtures
(`hybrid`, `minimal`), all 5 text renderers covered (not `pdf.py` --
no in-process text output to snapshot). `tests/golden/README.md`
documents how to update a snapshot. Shipped in v0.6.3; the CI breakage
that followed (see the "CI saga" entry below) was in supporting code,
not this item's own scope, and is separately resolved.
Non-goal, not done: real per-ecosystem source-tree fixtures scanned
end-to-end through analyzers (this item's fixtures are renderer-level,
built directly from `ReportData`, not from a real scan).

### 7.1 — Analyzer capability matrix
**Status: RESOLVED.** `core/coverage.py` generates `docs/COVERAGE.md`
(sync-tested, never hand-edited) with Tests/Quality/Security/Tools/
Build-tools/**Fixture-coverage**/**CI-installed**/**Depth** columns,
all code-derived -- no hand-typed values anywhere. Depth
(Deep/Partial/Shallow) is a fixed rule over the other columns, not a
per-analyzer judgment call. Shipped in v0.6.3.
Real finding worth knowing: only Python and Rust are actually
CI-installed and exercised by `ci.yml`; the other ~35 per-language
tools are real and tested with mocked subprocess calls, but never run
for real in CI.

---

## P1

### 8 — Monorepo / Workspace architecture
**Status: PARTIALLY RESOLVED -- Cargo only, by design.** `core/
workspace.py` detects Cargo workspaces (`[workspace]` in `Cargo.toml`,
glob `members`/`exclude`, root-as-member). `ReportData.workspace` +
markdown `## Workspace` section + JSON `workspace` key, both only
emitted when detected. Shipped in v0.6.4.
8.1 audit results (still accurate, re-use rather than re-derive):
- **npm / pnpm / Yarn workspaces** -- CONFIRMED gap in both
  representation *and* execution (`npm test` at root doesn't cascade
  into workspace packages without opt-in). **Next natural candidate**
  for this item's next phase.
- **Gradle / Maven multi-project/module** -- CONFIRMED gap, but
  representation-only (`gradlew`/`mvn` already test every
  subproject/module natively).
- **Bazel** -- OUT OF SCOPE, not deferred: no Bazel analyzer exists in
  the roster at all; would need a new-analyzer item first.
- **Nx / Turborepo** -- OUT OF SCOPE for now: both need an npm/pnpm/
  Yarn workspace base detected first.
Non-goals recorded, not done: per-member test/quality/security
attribution (today one aggregate `cargo test --all` result covers the
whole workspace); workspace-aware health aggregation; `html.py`/
`text.py`/`sarif.py` workspace sections; README.md mention (felt
premature for a single-ecosystem, detection-only feature).

### 9 — Report Size and Low-Memory Operation
**Status: RESOLVED -- closed without a new flag.** Real on-device
profiling (`scripts/benchmark_report.py`, a dev tool now in the repo)
**refuted** the natural first guess (embedded source content as the
memory driver -- removing it moved peak RSS only ~4-7%). Isolating
phases found the `--security` phase alone ≈ the whole run's peak;
`syft dir:.` with zero excludes (cataloging `.venv`/`target`/etc.
unrestricted, not just declared deps) was the real cause. Fixed at the
source in `core/sbom.py` (`_SYFT_EXCLUDE_ARGS`) -- confirmed on-device:
security-phase peak RSS 327.6 MiB -> 186.8 MiB (43% reduction).
Remaining ~187 MiB is understood (syft's own inherent runtime cost),
not mysterious, and not further fixable without losing functionality.
Shipped in v0.6.6.
Non-goals recorded, not done: profiling `--quality` (176.7 MiB,
never decomposed by which of its several tools) or the test-execution
phase (never profiled at all, every benchmark used `--skip-tests`) --
revisit only if a future real report names one specifically.

### 5 — Kubernetes / Helm / Kustomize
**Status: PARTIALLY RESOLVED, in progress -- IN-PROGRESS ROUND NOT
YET COMMITTED as of this update.** `core/kubernetes.py` detects Helm
charts (`Chart.yaml`) and Kustomize overlays (`kustomization.yaml`/
`.yml`) by marker file, bounded 5-level walk reusing the same
build/dependency/VCS exclude list as item 9's syft fix. `ReportData.
kubernetes` + markdown `## Kubernetes` section + JSON `kubernetes`
key, both only emitted when detected. 10 new tests in `tests/
test_kubernetes.py`. Local `pytest -q` 800/800 passed; two on-device-
only issues found and fixed this same round: (1) a `ruff format` diff
in the test file (fixed), (2) `mypy` flagged `import yaml` as
untyped-stub (real gap: **PyYAML was never a direct dependency**,
only present transitively on the dev machine -- fixed by adding
`PyYAML>=6.0` to `[project] dependencies` and `types-PyYAML` to the
`dev` extra in `pyproject.toml`). **Next action: apply this round's
fix, rerun `ruff`/`mypy`/`pytest` once more to confirm clean, then
commit+push+tag.**
Non-goals recorded, not done (this item's own next phase, once the
above is committed): raw Kubernetes manifests with no fixed filename
(needs content-parsing every `.yaml`, a materially bigger scan than a
marker-file check); any lint/validation execution (`helm lint`,
`kubeconform`/`kubeval`, `kustomize build --dry-run`) once something
is detected.

### 6 — Docker Compose
**Status: PARTIALLY RESOLVED -- detection only, delivered 2026-09-30,
verified on-device.** `core/compose.py` finds
`compose.y(a)ml`, `docker-compose.y(a)ml` and one-segment variants
(`docker-compose.override.yml`, `compose.prod.yaml`) by filename
under a bounded 5-level walk (same exclude list as items 5/9), reads
each file's `services` (name, image, has-`build`). Malformed files
are reported with no services, never dropped. `ReportData.compose` +
markdown `## Docker Compose` + JSON `compose` key, only emitted when
detected. 15 tests in `tests/test_compose.py`. Audit result: the only
prior trace was `YamlAnalyzer._ENTRY_POINTS` (entry-point listing).
Non-goals recorded, not done: execution (`docker compose config`,
`hadolint`), `include:`/`extends:` resolution, override merging,
Dockerfile detection.

### 7 (backlog doc's own §10, "Makefile")
**Status: PARTIALLY RESOLVED -- detection only, delivered 2026-09-30,
verified on-device.** `core/makefile.py` finds
`GNUmakefile`/`makefile`/`Makefile` (one per directory, make's own
precedence) under a bounded 5-level walk (same exclude list as items
5/6/9) and lists explicit targets, `.PHONY` names and the default
target (`.DEFAULT_GOAL` else first target) by a line-based heuristic.
Caps: 25 files, 100 targets/file, with true totals kept so nothing is
silently lost. `make` is never run. `ReportData.makefile` + markdown
`## Makefile` + JSON `makefile` key, only emitted when detected. Audit
result: the only prior trace was `constants.py`'s exact-name `Makefile`
project marker (build system "make"); no content was read.
Non-goals recorded, not done: `make` execution, `include` resolution,
`.mk` fragments, macro/conditional evaluation, per-target `## help`
descriptions.

### 11 — Hybrid project model (backlog doc's own §11)
**Status: PARTIALLY RESOLVED -- representation only, delivered
2026-10-01, NOT yet verified/committed on-device.** `core/components.py`
builds a component view (application / infrastructure / ci /
documentation / configuration) from concrete markers only, plus one
relationship (Compose service `build:` context -> application
directory). Emitted only for a *hybrid* project (>=2 application
components with different (languages, kind) signatures, or an
application plus Helm/Kustomize/Compose/Terraform); an ordinary
project's report is unchanged. `kind` frontend/backend only from
declared dependencies (npm / Python), never from directory names.
Adds no findings, runs nothing. `ReportData.components` + markdown
`## Project Components` + conditional JSON `components` key.
Hybrid fixture built in `tests/test_components.py`.
**Next action: apply, run `ruff`/`mypy`/`pytest`, commit+push.**
Non-goals recorded, not done: database/service-role inference,
relationships beyond Compose builds, Nx/Turborepo/Bazel graphs,
changing `detect_project()`. **The bigger gap this audit found is
listed separately below ("Root-only detection and analyzer matching").**

---

## P2 (13 and 14 below are Not started)
### 12 -- AI-oriented Quick Context / layered context
**Status: PARTIALLY RESOLVED -- L2 layer delivered 2026-10-01, NOT yet
verified/committed on-device.** `core/quick_context.py` builds a short,
bounded, deterministic block from existing `ReportData` only; rendered
as a `## Quick Context` section at the very top of the Markdown report
and a `quick_context` key near the top of the JSON. Fields: project /
languages / type / build system, components (hybrid only), top-level
structure, test/quality/security tools with pass/fail/skip status,
health (with confidence), critical findings (health critical failures
+ known issues), factual risks (failed/skipped checks, tool error and
warning counts, secret-pattern COUNT never paths, excluded files, git
dirty/behind), first 10 of the reading order. Budget: worst case ~6 KiB
(~1.5K tokens), typical 1-2 KiB; pinned by a test. Audit findings that
drove it: L1 "AI Summary" lacked test/security status and findings; the
reading order's first 40 entries were alphabetical analyzer plugins
(fixed: shallow paths first). Golden snapshots (md, json) updated.
**Next action: apply, run `ruff`/`mypy`/`pytest`, commit+push.**
Non-goals recorded, not done: frameworks (not in report data),
inferential risk model, L3 (architecture/risks) and L4 (relevant source
subset), HTML/text renderer sections, model-specific presets (no
evidence of a need).
### 13 -- Distribution and installation reliability
**Status: PARTIALLY RESOLVED -- versioning and AUR draft fixed 2026-10-01,
NOT yet verified/committed on-device.** Audit by channel (separating
availability / reliability / optional deps / docs, per the backlog):
- **PyPI:** not published (README says install from source). Publishing
  is a decision, not a defect; it needs per-platform wheel builds and a
  publish workflow. NOT started.
- **pipx / source install:** works; `install.sh` has retry and rollback.
  Needs a Rust toolchain by design. CI builds the wheel and runs the
  suite against it. Added: a fresh-virtualenv smoke test
  (`scripts/smoke_install.py`, CI step on all platforms) that installs
  ONLY the wheel, checks `--version`, `--doctor` and a Helm scan (which
  imports PyYAML).
- **Versioning (CONFIRMED defect, fixed):** `pyproject.toml`/`Cargo.toml`
  said 0.6.0 while tags reached v0.6.10, so every build reported 0.6.0;
  CHANGELOG stopped at 0.6.0. Now `scripts/release.py` (bump / tag) keeps
  pyproject, Cargo.toml, Cargo.lock and PKGBUILD in sync and
  `tests/test_distribution.py` enforces it. First aligned release: 0.6.11.
- **AUR (draft, unpublished -- not treated as critical):** PKGBUILD said
  pkgver 0.1.1 and lacked `python-yaml` (a clean Arch install would
  `ImportError` on a Kubernetes scan). Fixed and guarded by a test that
  every runtime dependency has an Arch package in `depends`. Still to do
  at publish time: `updpkgsums` after the tag exists.
- **Termux:** NOT verified. README claims `pip install -e .` gives a
  pure-Python fallback when the Rust extension will not build; the build
  backend is maturin, so this very likely fails without cargo too.
  Needs an on-device check before the README is corrected.
- **Optional deps:** unchanged; `--doctor` already reports them and
  checks are skipped, not failed.
Non-goals recorded, not done: PyPI publishing, wheel matrix workflow,
`filelock==3.32.3` exact pin review, Termux-specific documentation.
**Next action: apply, run `ruff`/`mypy`/`pytest`, commit+push, wait for
CI (the new smoke step runs there for the first time), then
`python3 scripts/release.py tag`.**
### 14 -- Plugin system maturity
**Status: RESOLVED (first scope) 2026-10-01, NOT yet verified/committed
on-device.** Audit of the existing `sarand.analyzers` entry-point
mechanism: load-time isolation only (a plugin raising in `matches`,
`run_*` crashed the whole run and dropped every other analyzer's
results); README documented 4 methods while the registry calls a 5th
(`run_security`) so README-era plugins crashed the security phase; no
version story; a plugin named like a built-in ran every check twice;
no tests, no example, no author docs. Delivered:
`analyzers/plugin_adapter.py` (every plugin wrapped: exceptions and
wrong return types become one skipped result naming plugin/phase/error;
`run_security` optional; `api_version` gate), hardened
`discover_analyzers` (stable order, name-clash skip, unreadable metadata
tolerated), `PLUGIN_API_VERSION = 1`, `docs/PLUGINS.md` + `.fa.md`
(contract, lifecycle, isolation, version policy, author workflow incl.
`pipx inject`), `examples/sarand-plugin-justfile`, README EN/FA
pointers, `tests/test_plugins.py` (real importlib-metadata discovery,
isolation at every phase, example conformance). All six Definition-of-Done
boxes covered. Built-in analyzers are NOT wrapped (unchanged).
Non-goals recorded, not done: plugin timeouts/sandboxing, a
`--doctor` plugin listing, a plugin marketplace (the backlog says not
until the API is stable), isolating crashes inside built-in analyzers.

## P3 -- all Not started
### 15 -- PDF and report portability
**Status: PARTIALLY RESOLVED 2026-10-02, NOT yet verified/committed
on-device.** Audit of the PDF pipeline (wkhtmltopdf / WeasyPrint via
`renderers/pdf.py`): (1) a failed PDF returned exit 1 and wrote NOTHING,
discarding the whole scan; (2) the fall-through message always said "No
PDF engine found" even when an engine WAS found and crashed, hiding the
real error; (3) WeasyPrint installed with `pipx inject sarand weasyprint`
could never be found (pipx keeps scripts off PATH and discovery was
PATH-only); (4) the only real-PDF test returned silently without an
engine, so no PDF path was ever tested in CI. Delivered: engine discovery
(PATH, script beside the interpreter, importable module), each failing
engine's own reason (clipped, with a Pango hint), non-PDF output and
timeouts handled, no partial file left; on failure the full report is
written as Markdown next to the intended PDF path and the run exits 1;
hermetic fake-engine tests (`tests/test_pdf_pipeline.py`) run the whole
path on every OS; the silent `return` became a visible skip; README
EN/FA state the real requirements and the failure behaviour.
NOT verified (documented as such): Termux/Android for either engine,
real-engine output quality, wkhtmltopdf packaging per distribution.
Non-goals recorded, not done: a real engine in CI (Debian's wkhtmltopdf
may need an X server -- unverified, would risk a red CI for
environmental reasons), `--doctor` rows still PATH-based (a
pipx-injected WeasyPrint shows "missing" there), a pure-Python PDF
backend, `--format pdf` output-size limits.
- 16 (doc §16) -- Cross-ecosystem vulnerability analysis (SBOM vs.
  vulnerability scanning, kept explicitly separate per the doc)
- 17 (doc §17) -- Additional ecosystems (Deno, Bun, Vue, Svelte,
  Astro, OCaml, Clojure, Crystal, Nim, V, Solidity)

---

## Root-only detection and analyzer matching (found 2026-10-01 while auditing item 11)
**Status: PARTIALLY RESOLVED 2026-10-01 (per-component execution
for hybrid projects, see AGENTS.md 5.42; NOT yet verified/committed
on-device). Original finding, not a numbered backlog item --
arguably larger than item 11 itself.** `detect_project()` inspects only
root marker files and keeps one primary language; analyzers'
`matches(root)` are root-only too. On a realistic hybrid fixture
(`backend/pyproject.toml`, `frontend/package.json`, root
`docker-compose.yml`, `Makefile`, CI, docs) the report says "Generic /
unknown / make", Python and Node.js are not detected, and only GitHub
Actions, YAML and Markdown analyzers run: **no tests, quality or
security checks for either real component.** Same root cause as item
8's npm/pnpm/Yarn execution gap. Fixing it means deciding how analyzers
run per component directory (working dir, result attribution in the
flat test/quality/security lists, no duplicate findings) -- a real
design decision, deliberately not folded into item 11's
representation-only scope. Needs an explicit go-ahead before starting.

## Also worth knowing (not backlog items, but real and unresolved)

- **CI saga (v0.6.3/v0.6.4 broken for ~2 weeks, resolved 2026-09-25,
  tagged v0.6.5):** not itself a numbered backlog item, but blocked
  everything above while it was open. Root causes: `core/coverage.py`
  breaking under CI's wheel-install step (fixed with cwd-based repo-
  root discovery); real Windows path bugs (`.as_posix()` vs `str()`)
  predating the golden-test work; a genuine replace-order bug in the
  golden test's own path normalization (never actually a Windows bug,
  despite three rounds of chasing Windows-specific theories first).
  Full account in `AGENTS.md` §5.27-5.32 if the exact mechanism ever
  matters again.
- `markdown.py` leaves a trailing blank line before a file's closing
  code fence when embedding source (cosmetic, found 2026-09-22, still
  not fixed -- small, standalone, worth fixing whenever `markdown.py`
  is next touched for something else).
- `CHANGELOG.md` has no entries for v0.6.1 through the current tag
  (noted repeatedly across many rounds) -- still out of scope until
  asked for directly.
