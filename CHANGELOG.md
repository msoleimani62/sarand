# Changelog

All notable changes to sarand are listed here, newest first. Versions follow
[Semantic Versioning](https://semver.org/); while sarand is 0.x, a minor
version may include behaviour changes.

## [0.6.15] - 2026-10-08

### Fixed

- Node.js projects: the `build system` shown in Detected Project, Quick
  Context, text and HTML said `npm` even in pnpm, Yarn and Bun repositories.
  It is now read from the `packageManager` field, then from the lockfile
  (`pnpm-lock.yaml`, `yarn.lock`, `bun.lock`/`bun.lockb`, `package-lock.json`),
  then from a root `pnpm-workspace.yaml`.
- With `--security`, `npm audit` no longer shows up as a FAILED check (and no
  longer lowers the health score or appears under Risks) in a project that has
  no `package-lock.json`. `npm audit` only reads that file, so it exited with
  `ENOLOCK` although nothing was wrong. The check is now SKIPPED, with the real
  reason and the right command (`pnpm audit`, `yarn npm audit`, `npm install`).

### Documentation

- `AGENTS.md` section 5.54 is a session handoff: current state, working loop,
  release procedure and the lint and CI lessons, so a new working session can
  start from the repository itself.

## [0.6.14] - 2026-10-06

### Changed

- The "Detected Project" section describes a hybrid repository by its
  components. With only a `Makefile` at the root it used to say `Generic`
  and `unknown`, and with a root `pyproject.toml` it listed `Python, Generic`
  and missed the frontend's Node.js. It now lists every component language,
  drops the `Generic` placeholder, keeps a real root language as the primary
  one, and otherwise says for example `Python + Node.js` and `hybrid: backend
  (Python), frontend (Node.js)`. Component markers appear as
  `backend/pyproject.toml`.
- In a hybrid project, nested Node.js, Go and Rust packages are now analysed
  even when the same analyzer matches the root, because the root run does not
  reach them (`npm test` stops at the package boundary, `go test ./...` skips
  nested modules, `cargo test --all` covers only workspace members). They are
  not analysed twice: workspace members and anything under a `go.work` count
  as covered, and a root script that already fans out or a root ESLint
  configuration drops that phase. Python is unchanged because the root
  `pytest` and `ruff` recurse.

### Fixed

- In a pnpm workspace without a root `package.json` that is also a hybrid
  project, workspace members no longer get `npm audit` run per member.

## [0.6.13] - 2026-10-05

### Added

- npm, Yarn and pnpm workspaces are detected (`workspaces` in `package.json`,
  or `pnpm-workspace.yaml`, including `**` and `!` patterns). The report lists
  the members, and tests and lint now run **inside each member**, labelled
  `packages/api: npm test`, because `npm test` at the root does not reach the
  packages. A pnpm workspace without a root `package.json` is covered too.
- Nothing is reported twice: a root `test` or `lint` script that already fans
  out (`--workspaces`, `pnpm -r`, `turbo`, `nx`, `lerna`, ...) skips that phase
  for the members, a root ESLint configuration skips member linting, `npm
  audit` is never run per member, and a member that is also a hybrid-project
  component runs each analyzer once. At most 20 members run; the rest are
  counted in one skipped result.
- `docs/WORKSPACES.md` (and a Persian version) explain the model, the
  duplicate-prevention rules, how the health score treats members (one score
  for the repository, each check counted once) and what is not supported.

### Changed

- `SARAND_NO_COMPONENTS=1` also turns off the workspace member runs.
- Maintainers: `scripts/release.py tag` now refuses to tag a commit unless
  every GitHub Actions run for it finished successfully (it asks the `gh`
  CLI), and fails closed when CI cannot be checked. `--skip-ci-check`
  overrides it.

## [0.6.12] - 2026-10-02

### Added

- If a PDF cannot be produced, the full report is now written as Markdown next
  to the intended PDF path and sarand exits non-zero, instead of discarding the
  whole scan.

### Changed

- PDF failures report each engine's own error (with a hint about the Pango
  system library) instead of always saying "No PDF engine found".
- WeasyPrint is found on `PATH`, beside the Python that runs sarand, or as an
  importable module, so `pipx inject sarand weasyprint` works.
- `sarand --doctor` uses the same WeasyPrint lookup as `--format pdf`.

### Fixed

- The README claimed `pip install -e .` installs sarand without Rust. It does
  not: the build backend needs a Rust toolchain. The README now says so and
  documents running from the source tree, which uses the pure-Python scanner.

## [0.6.11] - 2026-10-01

Releases 0.6.1 to 0.6.10 were tagged without changelog entries and without
bumping the version in `pyproject.toml`, so every build reported 0.6.0. This
entry lists the user-visible changes since 0.6.0 that are known;
`git log v0.6.0..v0.6.10 --oneline` has the full detail.

### Added

- Kubernetes: Helm charts and Kustomize overlays are detected and listed in
  the report (detection only; `helm` and `kubectl` are never run).
- Docker Compose: `compose.yaml`, `docker-compose.yml` and their override
  variants are found at any depth and their services listed.
- Makefile: `Makefile`, `GNUmakefile` and `makefile` targets, `.PHONY` names
  and the default target are listed. `make` is never run.
- Hybrid projects get a "Project Components" section that separates
  applications (with frontend or backend only when a declared dependency says
  so), infrastructure, CI, documentation and configuration, and links Compose
  services to the directories they build. JSON has a matching `components` key.
- For hybrid projects, analyzers that do not match the project root now run
  inside each application component, and their results are labelled
  `<component>: <check>`. Set `SARAND_NO_COMPONENTS=1` to turn this off.
- A "Quick Context" block at the top of the Markdown report (and a
  `quick_context` JSON key): project, structure, test, quality and security
  status, health, critical findings, risks and what to read first, in a bounded
  size.
- `scripts/release.py` keeps the version in sync across `pyproject.toml`,
  `Cargo.toml`, `Cargo.lock` and the AUR `PKGBUILD`; `scripts/smoke_install.py`
  installs the built wheel into a fresh virtual environment and uses it. CI
  runs the smoke test on every platform.
- Plugin system maturity: every plugin is wrapped so one that raises or
  returns the wrong type produces a skipped result instead of crashing the
  scan; `run_security` is optional; plugins declare an `api_version`
  (`PLUGIN_API_VERSION` is 1) and are skipped with a reason when they target a
  newer one; a plugin named like an existing analyzer is skipped. See
  `docs/PLUGINS.md` and the example in `examples/sarand-plugin-justfile`.

### Changed

- The suggested reading order lists manifests first, then entry points and core
  modules, then documentation; shallow paths come first and test files are no
  longer promoted.
- `PyYAML` is now a declared dependency (Helm chart parsing imports it).

### Fixed

- The SBOM scan with `syft` skips build and dependency directories.
- The AUR `PKGBUILD` was missing `python-yaml` and still said version 0.1.1.
- `sarand --version` reported 0.6.0 for every later release.
- The suggested reading order used backslash paths on Windows and never
  recognised `docs\` there; it now uses forward slashes everywhere.

## [0.6.0] - 2026-09-21

### Added

- Assembly detection: every assembly file is classified by dialect (x86 with
  NASM, GNU as AT&T or Intel syntax, MASM/TASM or FASM in 16, 32 and 64-bit;
  ARM; AArch64; RISC-V; MIPS; PowerPC; 6502; Z80; AVR; Motorola 68000; 8051)
  and the breakdown appears in every report format. Nothing is assembled or run.
- Eight new analyzers, 40 in total: Haskell (`stack` or `cabal`, `hlint`),
  Elixir (`mix test`, `mix format`, `mix hex.audit`, plus Credo and MixAudit
  when the project uses them), Erlang (`rebar3 eunit` and `xref`), Scala
  (`sbt`, plus scalafmt when the project adopted it), Dockerfile (`hadolint`),
  GitHub Actions (`actionlint`), Terraform (`terraform fmt`, `tflint`; never
  `init`, `plan` or `apply`) and Protobuf (`buf lint`).
- A per-project license policy in `.sarand.toml` (`allow`, `deny`, `warn`,
  `unknown`, `exceptions`), enforced against the SBOM by `--security`. Python
  3.10 needs the new `tomli` dependency.
- A lockfile check for `--security`: each manifest must have a lockfile that is
  not git-ignored.
- `docs/COVERAGE.md`, a coverage matrix generated from the code and kept in sync
  by tests.
- `sarand --doctor` now lists built-in, detection-only ecosystems (Assembly).
- Memory reporting on macOS and Windows in the Environment section (it used to
  say "unknown").
- English and Persian READMEs as two separate files, with an option reference
  that a test keeps in sync with the command line.
- CI runs Python 3.10 and 3.14 on Linux next to 3.12 on every OS, lists failed
  tests on the run's summary page, and stops a job after 45 minutes.

### Changed

- `install.sh` builds the new version before it replaces the old one, retries
  slow-network failures, and restores the previous installation on failure or
  Ctrl-C. Before, a failed build could leave no `sarand` command at all.
- The SBOM summary comes last in the report, so it stays visible in the default
  80-line view.
- Issue scanning no longer reports "0 failed" summaries, bandit context lines or
  internal log lines as errors, and bandit skips test directories.
- The `syft` entry in `--doctor` says it fails the check only when a license
  policy is violated.

### Fixed

- Windows: `mypy` errors on POSIX-only APIs; `.cmd` and `.bat` tools (npm,
  gradle, mvn, composer) were reported as "not found"; non-UTF-8 consoles
  crashed on the first arrow; Groovy entry points used backslashes; the device
  report ignored exclude paths written with forward slashes.
- Tests no longer depend on which tools are installed (a real Gradle build once
  ran for six hours on a Windows CI runner), and none uses a hardcoded `/tmp`.
- The `--output-dir` help text now matches the real priority order (option,
  `SARAND_OUTPUT_DIR`, saved setting, `~/Downloads`). The README no longer
  documents a `--max-file-size` option that never existed.

### Known limitations

- The external tools of seven of the eight new analyzers (`stack`, `cabal`,
  `hlint`, `mix`, `rebar3`, `sbt`, `hadolint`, `terraform`, `tflint`, `buf`) have
  not been run for real yet; only `actionlint` has. Their command lines follow
  each tool's documentation and are tested as recorded commands.
- Assembly dialect detection is a heuristic tested on hand-written samples;
  unusual dialects are reported as "Unidentified".
- The macOS and Windows memory readings are covered by unit tests and CI but
  have not been checked against a real report on those systems.
- There is no cross-ecosystem vulnerability scan yet: `syft` produces an SBOM,
  not findings.

## [0.5.1] - 2026-09-20

### Fixed

- `gitleaks` no longer fails on the deliberately fake credentials in the test
  suite (an allowlist in `.gitleaks.toml`).
- False positives in the "Errors detected" and "Warnings detected" sections.
- `bandit` accepts sarand's intentional use of `subprocess` and skips tests.
- The SBOM summary is shown in the default report view.
- Added `.editorconfig` and `.markdownlint.json`.

## [0.5.0] - 2026-09-20

### Added

- Lockfile check and an SBOM dependency inventory with an advisory copyleft
  warning, both under `--security`.

### Fixed

- Tests that depended on whether a tool such as `dotnet`, `composer` or `bundle`
  happened to be installed.

## [0.4.0] - 2026-09-20

### Added

- `gitleaks` secret scanning and `syft` SBOM generation under `--security`.
- Java `checkstyle` and `spotbugs` checks.

### Fixed

- The C/C++ `clang-tidy` check now takes its file list from
  `compile_commands.json`, so it no longer picks up CMake's own generated
  probe file.
- A `mypy` error, and the useless `gitleaks` output ("leaks found: N" with no
  detail).
