# Changelog

All notable changes to sarand are listed here, newest first. Versions follow
[Semantic Versioning](https://semver.org/); while sarand is 0.x, a minor
version may include behaviour changes.

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
