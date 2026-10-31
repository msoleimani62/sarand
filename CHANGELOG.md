# Changelog

All notable changes to sarand are listed here, newest first. Versions follow
[Semantic Versioning](https://semver.org/); while sarand is 0.x, a minor
version may include behaviour changes.

## [Unreleased]

### Added

- The report has a new "Architecture and Risks" section (and `architecture` and
  `risks` keys in the JSON report). It lists the components, workspace members,
  entry points, Compose services and Kubernetes items the scan found, with file
  counts, and a list of rule-based risks. There are nine fixed rules (failed
  security checks, critical health failures, secret-pattern matches outside test
  fixtures, skipped checks, repository state, low check coverage, files with many
  TODO markers, large files, duplicate files). Each risk names the report fields
  it comes from and says what it does not show, and a rule whose data is missing
  is listed as not evaluated instead of counted as fine.
- Quick Context now lists the frameworks that your manifests declare
  (`package.json`, `pyproject.toml`, `requirements.txt`), in a "Declared
  frameworks (from manifests, not verified in code)" line and a
  `quick_context.frameworks_declared` JSON key. It reads declarations only: a
  name in the table is not proof that the code uses it, and Cargo and Go
  manifests are not read yet. The HTML and plain-text reports now carry the
  Quick Context block too (Markdown and JSON already did).
- The report shows the declared tasks of Turborepo (`turbo.json`) and the
  declared targets and projects of Nx (`nx.json` with its `project.json`
  files), in a "Monorepo tooling" section and a `monorepo_tools` JSON key that
  exist only when one of them is found. It reads files only and never runs
  `turbo`, `nx` or project code; targets that Nx plugins infer and the computed
  task graph are not shown, and the report says so.
- Docker Compose files are checked with `docker compose config --quiet
  --no-interpolate` under `--quality`: a base file alone and with each
  override or variant next to it. Nothing is built, pulled or started;
  a variable that is only set on your machine is not a failure; a file that
  loads a remote `include:` is skipped. Without `docker` or its Compose
  plugin the check is skipped, not failed.
- Opt-in schema validation of Kubernetes charts and overlays: with
  `SARAND_KUBECONFORM_SCHEMAS` pointing at a local directory of Kubernetes
  JSON schemas, `--quality` renders each chart (`helm template`) and overlay
  (`kustomize build`) into a temporary directory and checks it with
  `kubeconform`, offline. Nothing rendered is kept in the report. See
  `docs/KUBERNETES.md`.
- `sarand --doctor` lists the installed plugins and, for a plugin that was
  skipped, the reason.
- `musllinux` wheels for x86_64 and aarch64: `pipx install sarand-cli` on
  Alpine no longer builds from the source distribution. Each wheel is
  installed and run inside an Alpine container before a release is published.

### Changed

- A plugin phase that does not finish within one hour and one minute is
  cancelled and reported as a skipped check, instead of hanging the scan.
- `filelock` 4.x is allowed (`>=3.14,<5`); the full test suite passed with it.

## [0.7.0] - 2026-10-24

### Changed

- Building from source needs Rust 1.88 or newer: `rust-version` is declared in
  `Cargo.toml` and a CI job builds with exactly that version. The PyPI wheels
  need no Rust. pyo3 moved to 0.30 and sha2 to 0.11.
- The package declares its license as the SPDX expression `MIT` with the
  `LICENSE` file (PEP 639); building the source distribution needs maturin
  1.14.1 or newer.
- sarand no longer starts every tool of a project at once. At most N external
  commands run together: `--jobs N` or `SARAND_JOBS`, otherwise one per CPU and
  per GiB of free memory (at most 8), so a 2 GB laptop runs one at a time.
- A command's output is capped at 8 MiB: the head and the tail are kept and the
  middle is replaced by a one-line marker.
- **Python 3.11 or newer is required.** Python 3.10 reached end of life in
  October 2026, so the `tomli` backport is gone and the compiled wheel is now
  `cp311-abi3`. Users on Python 3.10 keep installing 0.6.20.
- CI runs Python 3.11, 3.12 (all systems), 3.14 and, as a non-blocking check,
  3.15.

### Added

- A `static` CI job (bandit, markdownlint, actionlint, cargo-deny licenses/bans/
  sources, gitleaks), a scheduled `Audit` workflow (pip-audit and the RustSec
  advisories), Dependabot for Actions, Cargo and pip, least-privilege `permissions`
  and cancellation of superseded pull-request runs.
- Releases now check that CI succeeded for the tagged commit, smoke-test the
  Linux aarch64 and macOS x86_64 wheels on native runners, and create a GitHub
  Release with the wheels and a `SHA256SUMS` file.
- Every workflow action is pinned to a commit SHA (`scripts/pin_actions.py`
  does it and a test enforces it).
- `scripts/bench_scan.py` measures the Rust scan core against the pure-Python
  scan on a synthetic tree or on a real project.
- A "Trust model" section in both READMEs, a warning in Quick start and a note
  in `sarand --help`: scanning a project runs its test suite (and, with
  `--quality` / `--security` / `--full`, its linters and audit tools), so
  scanning code you do not trust means running it. `sarand --skip-tests` alone
  starts no project toolchain.
- `SECURITY.md` (private vulnerability reporting) and `CONTRIBUTING.md`.

### Fixed

- The Rust scan no longer applies your global gitignore (`core.excludesFile`), so a
  project gives the same file list on every machine. The project's own `.gitignore`
  files still apply.
- A directory sarand may not enter, or a file that vanished during the scan, no
  longer disappears silently from the counts: the report shows a "Scan warning"
  with how many paths were skipped and the first few reasons (without the absolute
  project path), and the command line prints a warning.
- Both READMEs still named Python 3.10 after the floor moved to 3.11.
- The English README's Contributing block said `mypy python`; CI runs
  `mypy .`.

## [0.6.20] - 2026-10-17

### Fixed

- A project located under a directory named `build`, `dist`, `target`, `.cache`,
  `venv`, ... (for example a Docker `WORKDIR /build`) produced an empty report
  with the compiled Rust core: the ignore list was matched against every
  component of the absolute path. It now applies to directories below the
  project root only, by their own name, and ignored directories are no longer
  walked at all.
- Without the compiled core, `.github/` (and any other directory starting with
  `.git`) was missing from the scan, and file paths used the platform separator.
  Both engines now return the same files.

- A healthy tool line such as syft's "0 exception(s) applied" was listed as an
  error, and "Compilation or lint errors were detected." appeared in Quick
  Context although every lint and type check had passed. Errors now come only
  from commands that exited non-zero, are recognised by line shape, and known
  issues are read only from failed checks.
- An audit tool that exits 0 but could not finish (for example `cargo audit`
  timing out on the yanked-crate check) is now reported as `INCONCLUSIVE`
  instead of `PASS`: it lowers the report's confidence, not the score. A failing
  exit is never downgraded.
- The TODO scan no longer counts golden/fixture/snapshot directories or
  Markdown/reStructuredText prose, says how many markers it suppressed, and
  accepts extra `[todo] exclude_globs` in `.sarand.toml`.

### Security

- The credential-file denylist is wider (`secrets.yaml/json/toml`,
  `*-adminsdk-*.json`, `kubeconfig`, `*.tfvars`, `*.tfstate`, `.pypirc`,
  `.git-credentials`, `.htpasswd`, `*.p8`, `*.ppk`, `wp-config.php`, ...) and
  also matches paths such as `.docker/config.json` and `.aws/credentials`.
  Before, `secrets.yaml`, `secrets.json`, `secrets.toml`,
  `firebase-adminsdk-*.json`, `kubeconfig.yaml`, `*.tfvars.json`,
  `wp-config.php` and `.docker/config.json` were copied into reports.
- The built-in secret scan recognises 16 kinds of credential instead of 5
  (GitHub fine-grained, Anthropic, OpenAI, Google, Stripe, PyPI, npm, AWS
  temporary keys, JWT, credentials in URLs, PGP and encrypted private keys,
  password-like assignments), with placeholder and entropy checks.
- With `--security`, a file that `gitleaks` flags is also left out of the
  source dump.

### Changed

- Whether a secret finding is a test fixture is no longer guessed from a
  `tests/` path: list the files in `.sarand.toml` (`[secrets]
  fixture_paths = [...]`). The default is empty, so findings under `tests/`
  now count toward the health score unless listed.

## [0.6.19] - 2026-10-12

### Added

- **sarand is on PyPI** as `sarand-cli`: `pipx install sarand-cli` installs the
  `sarand` command with no Rust toolchain. Prebuilt wheels cover Linux (glibc)
  on x86_64 and aarch64, macOS on Intel and Apple silicon, and Windows on x64,
  each one wheel for every Python from 3.10 on (the Rust core is built with
  `pyo3/abi3-py310`), plus a source distribution.
- A release workflow (`.github/workflows/release.yml`) that builds the wheels
  and the sdist, installs them on three systems as a smoke test and publishes
  with PyPI trusted publishing: no token is stored anywhere, only a tag
  `vX.Y.Z` publishes to PyPI (after a manual approval), and a manual run can do
  a dry run on TestPyPI. `docs/PUBLISHING.md` (and `.fa.md`) is the step-by-step
  guide.

### Changed

- The distribution is named `sarand-cli`, because the name `sarand` on PyPI
  belongs to an unrelated bioinformatics tool. The command, the import package
  and the repository stay `sarand`. `./install.sh` replaces an installation
  made under the old pipx name (it is set aside first and put back if the
  build fails); the pipx hints in `--doctor`, the PDF messages and the docs say
  `pipx inject sarand-cli ...`. A development virtualenv with an old editable
  install needs `pip uninstall sarand` once, then a reinstall.

### Documentation

- Both READMEs show the PyPI install first and say they are not to be confused
  with the bioinformatics tool Sarand; `AGENTS.md` sections 5.62 to 5.65.

## [0.6.18] - 2026-10-10

### Added

- A **Package results** table (Markdown) and a `package_results` list (JSON)
  whenever checks ran inside packages (hybrid components, workspace members,
  nested packages): one row per package with the tests, quality and security
  results it passed, failed or skipped, the root first. There is deliberately
  no per-package 0-100 score: the repository score also holds parts that belong
  to no package. Ordinary reports are unchanged.
- **Kubernetes**: raw manifests (YAML files whose documents carry `apiVersion`
  and `kind`) are found by content and listed under the Kubernetes section,
  bounded by file count, bytes read and file size. A new Kubernetes analyzer
  (the 41st) runs `helm lint` on each chart and `kustomize build` on each
  overlay with `--quality`; the rendered output goes to a temporary file that
  is deleted, so a rendered `Secret` never reaches a report. A chart whose
  dependencies are not vendored, an overlay with a remote base or a
  `helmCharts` generator, and a missing tool are SKIPPED with the reason, never
  failed. `kubeconform` is not run (its schemas come from the network).
- **Maven multi-module and Gradle multi-project** structure appears as a
  Workspace section (`maven` / `gradle`; `<modules>` of the root pom, the
  `include` calls of `settings.gradle[.kts]`). Nothing is executed differently:
  the root build already tests every module.

### Fixed

- A Gradle multi-project whose root holds only `settings.gradle[.kts]` (the
  build scripts live in the subprojects) matched no analyzer, so each
  subproject was checked alone without the root wrapper. The root is now a
  Gradle project: `./gradlew test` runs once there and the subprojects are not
  planned again.
- The Markdown report no longer leaves a blank line before the closing code
  fence of an embedded source file.

### Changed

- The `filelock` dependency is the range `>=3.14,<4` instead of the exact pin
  `3.32.3`, so it can be installed next to packages that need another version.

### Documentation

- `AGENTS.md` sections 5.59 to 5.61 and `docs/WORKSPACES.md` /
  `docs/WORKSPACES.fa.md`; the READMEs count 41 analyzers and list Kubernetes.

## [0.6.17] - 2026-10-08

### Fixed

- A repository with both a Cargo and a Node.js workspace recorded only the
  Cargo one. The Node members were therefore planned as stray nested packages
  and got a per-member `npm audit` (which no workspace member should get),
  and the report listed a single workspace. Every workspace is now detected
  (Cargo, then npm / Yarn / pnpm): Node members run as members (tests and
  lint, never `npm audit`) and Cargo members are covered by `cargo test --all`.

### Changed

- The Markdown report names each workspace when there are several
  (`## Workspace (cargo)`, `## Workspace (npm)`); with one it is unchanged.
  The JSON report keeps `workspace` (the first) and adds a `workspaces` list
  only when there is more than one, so ordinary reports are byte-identical.
- CI: `actions/checkout`, `actions/setup-python`, `actions/cache` and
  `actions/upload-artifact` moved to their Node.js 24 majors (the Node 20
  runtime is deprecated). The first run after the change has a cold cache.

### Documentation

- `docs/WORKSPACES.md` and `docs/WORKSPACES.fa.md` describe repositories with
  both workspaces and no longer claim that a project that is not hybrid gets no
  nested runs. `AGENTS.md` sections 5.57 and 5.58 record the CI change and the
  workspace model.

## [0.6.16] - 2026-10-08

### Fixed

- Projects that are not hybrid (one package kind and no compose, Kubernetes or
  Terraform) never had their nested packages tested, linted or audited: a
  standalone `tools/cli/package.json`, a nested Go module or Rust crate, or the
  services of a repository whose root has no project file at all (a `Makefile`
  plus `services/a` and `services/b`, or two Maven modules) produced no runs.
  They are now planned exactly like the components of a hybrid project: an
  analyzer that does not match the root runs inside each nested package, one
  that does is not repeated (except the non-recursive Node.js, Go and Rust
  analyzers, with the existing workspace, Cargo-member and `go.work` coverage
  rules). Runs are labelled `<dir>: <check>`, capped at 8 directories with an
  omitted note, and `SARAND_NO_COMPONENTS=1` turns them off. `examples/`,
  `tests/`, `fixtures/` and `vendor/` are never scanned.

### Changed

- In a workspace-only Node.js root (`pnpm-workspace.yaml` without a root
  `package.json`) the members now also get the JSON analyzer, which did not
  match the root.

### Documentation

- `AGENTS.md` sections 5.55 and 5.56 record the audit, the change, the accepted
  trade-off and what is not covered.

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
