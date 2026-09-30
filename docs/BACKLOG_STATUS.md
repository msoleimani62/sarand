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

Last updated: 2026-09-30. Latest tag: v0.6.6. `main` is ahead of that
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
**Status: Not started.**

---

## P2 -- all Not started
- 12 (doc §12) -- AI-oriented Quick Context / layered context
- 13 (doc §13) -- Distribution and installation reliability (PyPI/
  pipx/AUR/Termux)
- 14 (doc §14) -- Plugin system maturity

## P3 -- all Not started
- 15 (doc §15) -- PDF and report portability
- 16 (doc §16) -- Cross-ecosystem vulnerability analysis (SBOM vs.
  vulnerability scanning, kept explicitly separate per the doc)
- 17 (doc §17) -- Additional ecosystems (Deno, Bun, Vue, Svelte,
  Astro, OCaml, Clojure, Crystal, Nim, V, Solidity)

---

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
