# Coverage matrix

What sarand does for each ecosystem, derived from the code (see
`sarand/core/coverage.py`). **Do not edit by hand:** regenerate with
`python -m sarand.core.coverage > docs/COVERAGE.md`; a test fails when
this file is stale.

- **Tests / Quality / Security**: the analyzer implements that check.
- **Tools**: external tools `sarand --doctor` lists for it (all optional;
  a missing tool is skipped, never fatal).
- **Build tools**: recognised from the project's marker files.
- **Fixtures**: the analyzer's class is referenced by a real test under
  `tests/` (several analyzers share one test module, so this is a grep of
  test source, not a filename convention).
- **CI**: at least one of the ecosystem's tools is actually installed *and*
  invoked by sarand's own `.github/workflows/ci.yml` -- not merely listed as
  a package extra. **This is almost always "-"**: sarand's CI runs its own
  Python test suite and its own Rust core's tests, it does not install the
  ~35 other per-language tools and run `sarand --full`/`--quality`/
  `--security` against a real target project in any language. See AGENTS.md
  section 5.22 for what real-project validation evidence exists instead, and
  backlog items 6.1/7.1 for the CLI-level golden-report and real-tool-
  validation work this gap motivates.
- **Depth**: Deep / Partial / Shallow, a fixed rule over the four columns
  above (Deep = Tests and Quality and Security and Fixtures; Shallow = none
  of Tests/Quality/Security; otherwise Partial) -- never a per-analyzer
  judgment call.

| Ecosystem | Tests | Quality | Security | Fixtures | CI | Depth | Tools | Build tools |
|---|---|---|---|---|---|---|---|---|
| Python | yes | yes | yes | yes | yes | Deep | `pytest`, `ruff`, `mypy`, `pip-audit`, `bandit` | pip/poetry/uv, setuptools, pip |
| Rust | yes | yes | yes | yes | yes | Deep | `cargo`, `rustfmt`, `cargo-clippy`, `cargo-audit`, `cargo-deny` | cargo |
| Go | yes | yes | yes | yes | - | Deep | `go`, `govulncheck`, `staticcheck` | go |
| Node.js | yes | yes | yes | yes | - | Deep | `npm`, `eslint` | npm |
| TypeScript | - | yes | - | yes | - | Partial | `tsc` | npm/tsc |
| CSS | - | yes | - | yes | - | Partial | `stylelint` | - |
| Zig | yes | yes | - | yes | - | Partial | `zig` | zig |
| Assembly | - | - | - | yes | - | Shallow | none needed (detection only) | - |
| Haskell | yes | yes | - | yes | - | Partial | `stack`, `cabal`, `hlint` | stack, cabal |
| Elixir | yes | yes | yes | yes | - | Deep | `mix` | mix |
| Erlang | yes | yes | - | yes | - | Partial | `rebar3` | rebar3 |
| Scala | yes | yes | - | yes | - | Partial | `sbt` | sbt |
| Dockerfile | - | yes | - | yes | - | Partial | `hadolint` | - |
| GitHub Actions | - | yes | - | yes | - | Partial | `actionlint` | - |
| Terraform | - | yes | - | yes | - | Partial | `terraform`, `tflint` | - |
| Protobuf | - | yes | - | yes | - | Partial | `buf` | - |
| Swift | yes | yes | - | yes | - | Partial | `swift`, `swift-format`, `swiftlint`, `xcodebuild` | swift package manager |
| Objective-C | yes | yes | - | yes | - | Partial | `xcodebuild` | - |
| C/C++ | yes | yes | yes | yes | - | Deep | `cmake`, `cppcheck`, `clang-tidy` | cmake |
| Lua | yes | yes | - | yes | - | Partial | `busted`, `luacheck` | - |
| Ruby | yes | yes | yes | yes | - | Deep | `bundle` | bundler |
| PHP | yes | yes | yes | yes | - | Deep | `composer` | composer |
| Dart | yes | yes | - | yes | - | Partial | `dart` | pub |
| R | yes | yes | - | yes | - | Partial | `Rscript` | renv (optional) |
| Perl | yes | yes | - | yes | - | Partial | `prove`, `perlcritic` | cpanm |
| Julia | yes | - | - | yes | - | Partial | `julia` | Pkg |
| SQL | - | yes | - | yes | - | Partial | `sqlfluff` | - |
| Android/Kotlin | yes | yes | yes | yes | - | Deep | `mvn`, `gradle` | gradle |
| Java/Kotlin | yes | yes | yes | yes | - | Deep | `mvn`, `gradle` | maven, gradle |
| Kotlin | - | yes | - | yes | - | Partial | `ktlint`, `detekt` | - |
| Groovy | - | yes | - | yes | - | Partial | `codenarc` | - |
| C# | yes | yes | yes | yes | - | Deep | `dotnet` | - |
| Shell | yes | yes | - | yes | - | Partial | `shellcheck`, `shfmt`, `bats` | - |
| PowerShell | yes | yes | - | yes | - | Partial | `pwsh` | - |
| Nix | yes | yes | - | yes | - | Partial | `nix`, `nixpkgs-fmt` | - |
| YAML | - | yes | - | yes | - | Partial | `yamllint` | - |
| JSON | - | yes | - | yes | - | Partial | `jsonlint` | - |
| TOML | - | yes | - | yes | - | Partial | `taplo` | - |
| XML | - | yes | - | yes | - | Partial | `xmllint` | - |
| Markdown | - | yes | - | yes | - | Partial | `markdownlint` | - |

Project-wide checks (`--security`, any ecosystem): gitleaks, syft (SBOM and license policy), lockfile check.
