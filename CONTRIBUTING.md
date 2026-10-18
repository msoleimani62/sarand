# Contributing

[AGENTS.md](AGENTS.md) is the source of truth for architecture, conventions and
the roadmap; read its first sections before a larger change. This page is the
short version.

## Set up

```bash
git clone https://github.com/msoleimani62/sarand.git
cd sarand
python3 -m venv .venv && source .venv/bin/activate
pip install maturin
maturin develop --release --extras dev
```

If the extension will not build on your platform (some Termux toolchains), see
"Development install" in the [README](README.md) for running from the source tree.

`maturin develop` builds the Rust core into `python/sarand/_core.abi3.so`.
An **older** `_core.cpython-3xx-*.so` left in that folder is loaded in
preference to it, so after a rebuild delete any `python/sarand/_core.cpython-*.so`
(they are git-ignored) or you will test a stale core.

## Before you open a pull request

Run exactly what CI runs:

```bash
cargo fmt
cargo clippy --all-targets --all-features -- -D warnings
cargo test
maturin develop --release
ruff check --fix . && ruff format .
mypy .
pytest -q
```

CI repeats this on Linux, macOS and Windows (Python 3.11, 3.12, 3.14, plus 3.15 as a non-blocking check), so a test
must not depend on the platform path separator: compare POSIX-style paths.

The `static` job also runs these; run them yourself before you push:

```bash
bandit -c pyproject.toml -r python scripts -q
markdownlint "**/*.md"
cargo deny check licenses bans sources
```

`markdownlint` skips the files listed in `.markdownlintignore`.

## Conventions that bite

- Every comment you add gets a Persian line and an English line.
- A claim in the documentation must be backed by code or a test; a README
  sentence about behaviour needs the test that pins it.
- A test that needs a credential-shaped value builds it from fragments at
  runtime and lives in `tests/test_secrets.py` (the only file allow-listed in
  `.gitleaks.toml`).
- `ruff` rejects implicit string concatenation *inside* a tuple or list literal
  (ISC004): wrap such a string in its own parentheses.
- English and Persian READMEs are two separate files that must stay in step;
  `tests/test_readme_sync.py` pins the command-line options.
- Add dated notes to `AGENTS.md` and an entry to `CHANGELOG.md` for user-visible
  changes. Use conventional commit messages (`fix(scan): ...`, `docs: ...`).

## Adding an analyzer

An analyzer is gated on real project markers and must never crash when a tool
is missing (it returns a skipped result). Adding one touches several guard
tests: the doctor category order, both README tables, the analyzer count, and
the generated coverage matrix (`python -m sarand.core.coverage > docs/COVERAGE.md`).
`tests/test_trust_model.py` also fails if a new analyzer installs dependencies,
runs `make`, or uses a shell.

## Security

Please report vulnerabilities privately; see [SECURITY.md](SECURITY.md).
