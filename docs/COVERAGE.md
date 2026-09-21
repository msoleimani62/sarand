# Coverage matrix

What sarand does for each ecosystem, derived from the code (see
`sarand/core/coverage.py`). **Do not edit by hand:** regenerate with
`python -m sarand.core.coverage > docs/COVERAGE.md`; a test fails when
this file is stale.

- **Tests / Quality / Security**: the analyzer implements that check.
- **Tools**: external tools `sarand --doctor` lists for it (all optional;
  a missing tool is skipped, never fatal).
- **Build tools**: recognised from the project's marker files.

| Ecosystem | Tests | Quality | Security | Tools | Build tools |
|---|---|---|---|---|---|
| Python | yes | yes | yes | `pytest`, `ruff`, `mypy`, `pip-audit`, `bandit` | pip/poetry/uv, setuptools, pip |
| Rust | yes | yes | yes | `cargo`, `rustfmt`, `cargo-clippy`, `cargo-audit`, `cargo-deny` | cargo |
| Go | yes | yes | yes | `go`, `govulncheck`, `staticcheck` | go |
| Node.js | yes | yes | yes | `npm`, `eslint` | npm |
| TypeScript | - | yes | - | `tsc` | npm/tsc |
| CSS | - | yes | - | `stylelint` | - |
| Zig | yes | yes | - | `zig` | zig |
| Assembly | - | - | - | none needed (detection only) | - |
| Haskell | yes | yes | - | `stack`, `cabal`, `hlint` | stack, cabal |
| Elixir | yes | yes | yes | `mix` | mix |
| Erlang | yes | yes | - | `rebar3` | rebar3 |
| Scala | yes | yes | - | `sbt` | sbt |
| Dockerfile | - | yes | - | `hadolint` | - |
| GitHub Actions | - | yes | - | `actionlint` | - |
| Terraform | - | yes | - | `terraform`, `tflint` | - |
| Protobuf | - | yes | - | `buf` | - |
| Swift | yes | yes | - | `swift`, `swift-format`, `swiftlint`, `xcodebuild` | swift package manager |
| Objective-C | yes | yes | - | `xcodebuild` | - |
| C/C++ | yes | yes | yes | `cmake`, `cppcheck`, `clang-tidy` | cmake |
| Lua | yes | yes | - | `busted`, `luacheck` | - |
| Ruby | yes | yes | yes | `bundle` | bundler |
| PHP | yes | yes | yes | `composer` | composer |
| Dart | yes | yes | - | `dart` | pub |
| R | yes | yes | - | `Rscript` | renv (optional) |
| Perl | yes | yes | - | `prove`, `perlcritic` | cpanm |
| Julia | yes | - | - | `julia` | Pkg |
| SQL | - | yes | - | `sqlfluff` | - |
| Android/Kotlin | yes | yes | yes | `mvn`, `gradle` | gradle |
| Java/Kotlin | yes | yes | yes | `mvn`, `gradle` | maven, gradle |
| Kotlin | - | yes | - | `ktlint`, `detekt` | - |
| Groovy | - | yes | - | `codenarc` | - |
| C# | yes | yes | yes | `dotnet` | - |
| Shell | yes | yes | - | `shellcheck`, `shfmt`, `bats` | - |
| PowerShell | yes | yes | - | `pwsh` | - |
| Nix | yes | yes | - | `nix`, `nixpkgs-fmt` | - |
| YAML | - | yes | - | `yamllint` | - |
| JSON | - | yes | - | `jsonlint` | - |
| TOML | - | yes | - | `taplo` | - |
| XML | - | yes | - | `xmllint` | - |
| Markdown | - | yes | - | `markdownlint` | - |

Project-wide checks (`--security`, any ecosystem): gitleaks, syft (SBOM and license policy), lockfile check.
