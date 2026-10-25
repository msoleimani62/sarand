# AGENTS history: rounds 5.61 to 5.74

Moved verbatim out of `AGENTS.md` (round R8a). Nothing was reworded; some
references inside still say "this file" or "section 5.NN" and mean the history
of the project as a whole.

---

### 5.61 — Maven multi-module and Gradle multi-project (2026-10-10)

Backlog status item 6. Both tools already test every module natively from the
root, so the recorded gap was representation only.

**Audit** (fixtures through `detect_workspaces`, `matching_analyzers` and
`plan_component_runs`, v0.6.17 + 5.60): a Maven reactor (parent `pom.xml` with
`core` and `web`) and a Gradle multi-project with a root build file gave no
workspace and an empty plan -- the root `mvn test` / `./gradlew test` covers
them (CONFIRMED, representation only). **A second, execution-level defect
surfaced:** a Gradle multi-project whose root holds only `settings.gradle.kts`
(a very common layout: the build scripts live in the subprojects) matched NO
analyzer at the root, so since 5.56 each subproject (`app`, `lib`) was planned
alone with the Java/Kotlin analyzer in its own directory, where there is no
`./gradlew` (the wrapper is at the root): a system `gradle` or a skipped
result, never the root build. Before 5.56 nothing ran at all. CONFIRMED.

**Change.**

- `core/jvm_workspace.py` (new, nothing is run): `detect_maven_workspace`
  reads the `<modules>` of the root pom (a module is a directory or a pom path;
  nested aggregators to 3 levels; names from `artifactId`; modules outside the
  root, missing ones and profile-only ones are not listed; a pom with a
  DOCTYPE/ENTITY is never parsed) and `detect_gradle_workspace` reads the
  `include` calls of `settings.gradle[.kts]` (`:a:b` is `a/b` and `a` is listed
  first as the parent project; `includeBuild` / `includeFlat`, comments and a
  custom `projectDir` are not followed; a project whose default directory does
  not exist is left out). At most 200 members each.
- `core/workspace.py`: `detect_workspaces` now returns Cargo, npm / Yarn / pnpm,
  Maven, Gradle in that order, so the report, the JSON `workspaces` list and
  `ReportData.extra_workspaces` carry them with no renderer change. The planner
  only reads the Cargo and Node kinds, so the new kinds are inert there.
- `analyzers/java_analyzer.py`: `settings.gradle[.kts]` at the root counts as a
  Gradle project, so `./gradlew test` runs once at the root and the subprojects
  are skipped by the planner (the root already ran them).
  `constants.PROJECT_MARKERS` gets the two settings files (build tool
  `gradle`), so Detected Project says Java/Kotlin for such a root.

**Deliberately not changed.** No execution change for Maven or Gradle (the root
build is the right unit); Android multi-module projects keep their own analyzer
(`is_android_project` is untouched, so a settings-only Android root is a
separate question); no per-module result table beyond the generic one;
Maven `<profile>` modules and Gradle dynamic includes stay invisible.

Tests: `tests/test_jvm_workspace.py` (15) -- Maven reactor with artifact ids,
nested aggregators and pom paths, missing/escaping modules, no modules / profile
modules / bad XML, DOCTYPE never parsed; Gradle Kotlin and Groovy DSL,
multi-line includes, nested paths with parents, `includeBuild` / comments / URLs
/ missing directories, none, the member cap; the workspace order; the
settings-only root matching Java/Kotlin and its subprojects not planned alone;
the markers. **Not covered:** a real `mvn` / `gradle` run (nothing is executed
by this change); a Maven module path with a property placeholder
(`${module.dir}`), which names no directory and is dropped.
\n
### 5.62 — PyPI readiness that does not depend on the name (2026-10-10)

Backlog status item 8, first part. The user chose PyPI first (AUR waits for a
laptop: `updpkgsums` runs on Arch).

**Audit.** (1) The distribution name `sarand` is already taken on PyPI by an
unrelated bioinformatics tool (beiko-lab/sarand 1.1.1, which also installs a
`sarand` command), so publishing under it is impossible and `pip install
sarand` would install the wrong program. A different distribution name is
required; the import package `sarand` and the command can stay (a conflict only
exists if both are installed in one environment). The name is the user's
decision and is not changed here. (2) `README.md` is the package's long
description (`readme = "README.md"`) and had 10 relative references (the
banner image, `LICENSE` twice, four `docs/` files, `AGENTS.md`, the plugin
example directory and the language switch), which PyPI cannot resolve.
(3) The PyO3 module is built without `abi3`, so a release would need one wheel
per Python version (3.10 to 3.14) on every platform; the Rust source uses only
`PyDict`, `pyfunction` and `pymodule`, so `abi3-py310` looks viable, but it
changes the Rust build and is left for the step that can be proved by CI
together with the release workflow. (4) No release workflow exists.

**Change.** Only what is independent of the name and provable by the next CI
run:

- `README.md` links are absolute: files and directories as
  `https://github.com/msoleimani62/sarand/blob/main/<path>` (`tree/main` for a
  directory), the banner as the `raw.githubusercontent.com` URL. They work on
  GitHub too. `README.fa.md` is not a package description and is left
  relative.
- CI: a step after "Build the release wheel" installs `twine`, builds the sdist
  (`maturin sdist --out dist-sdist`, so the source distribution is exercised on
  every run) and runs `twine check --strict` on the wheel and the sdist.
- `tests/test_pypi_readiness.py` (3): no relative reference in `README.md`;
  every link into this repository names a path that exists; CI keeps the
  `twine check --strict` and `maturin sdist` step.

**Trade-offs.** The links point at `main`, not at the tagged version, so a
PyPI page shows the latest docs; a version-pinned rewrite would need a build
step that edits the README and is not worth it yet. Whether PyPI renders the
SVG banner (served by `raw.githubusercontent.com`) is unverified; if it does
not, the page loses an image, nothing else.

**Not done (needs the name or a decision).** The name in `pyproject.toml`,
`abi3-py310`, the release workflow, the README install section for PyPI, the
trusted publishers on pypi.org and test.pypi.org (a manual step for the user).

### 5.63 — The distribution is `sarand-cli` (2026-10-10)

Backlog status item 8. The PyPI name `sarand` belongs to an unrelated
bioinformatics tool (beiko-lab/sarand, from the Beiko Lab at Dalhousie
University, with a peer-reviewed paper and its own `sarand` command), so the
project cannot be published under it and `pip install sarand` would install the
wrong program. `sarand-cli` returned 404 on PyPI on 2026-10-10 (the user
checked); a name is only claimed by the first upload, so a pending publisher
does not reserve it.

**What the name is, and is not.** It is the *distribution* name, the one in
`pyproject.toml`: what PyPI lists, what `pip show` and `pipx list` call the
package, and what `pipx inject` / `pipx uninstall` take. It is not the command
(`sarand`), the import package (`sarand`, `sarand._core`), the repository, the
product name in reports and docs, or the AUR package (`pkgname=sarand`, a
separate namespace). A publish-time `sed` of the name was rejected: what CI
tests would differ from what is shipped, and a source install and a PyPI install
would carry two different names for the same program.

**Audit of what depends on the name.** `python/sarand/__init__.py` and
`utils/installation.py` read the version / distribution by name;
`_source_pyproject` recognises a checkout by `name = "sarand"`; `install.sh`
keeps its safety logic around the pipx environment `venvs/sarand`; the hints in
`core/doctor.py` and `renderers/pdf.py`, both READMEs and `docs/PLUGINS*.md`
say `pipx inject sarand ...` / `pipx uninstall sarand`; four test modules pin
those strings. No other code uses the name (the AUR build and `release.py`
do not).

**Change.**

- `pyproject.toml`: `name = "sarand-cli"` (with a comment), Python 3.10 to 3.14
  classifiers and a `[project.urls]` table (Homepage, Source, Changelog,
  Issues) for the PyPI sidebar.
- The two runtime lookups use `sarand-cli`. There is deliberately no fallback to
  `sarand`: that name may be the other project's, and reporting its version
  would be wrong. An old editable install recorded under `sarand` therefore
  reads as `0.0.0+unknown` until it is refreshed, and the existing stale-install
  note says so.
- `install.sh`: the pipx environment is `venvs/sarand-cli`. An install under the
  old name (`venvs/sarand`) is moved to `.sarand-legacy-venv` before the build
  (both would expose the same `sarand` command), deleted only after a good
  build, and put back by the same restore path on a failed build or an
  interrupt (`LEGACY_STATE`). `pipx install` gets `--force` so the old command
  link is replaced. The rule "never `pipx uninstall`" still holds (a test
  pins it).
- Hints and docs name `sarand-cli`; both READMEs carry a short "not to be
  confused with" note linking the other project. The PyPI install line is NOT in
  the READMEs yet: it is added by the release that actually publishes.

**Migration for an existing machine** (the user's phone and laptop): run
`./install.sh`; the old pipx environment is replaced automatically. A
development virtualenv with an editable install under the old name needs one
refresh: `pip uninstall sarand` in it, then `maturin develop --release` (until
then `sarand --version` there prints `0.0.0+unknown`).

**Not verified here.** The sandbox has no `pipx`: the installer logic is tested
with the fake pipx of `tests/test_install_script.py` (a good build, a failed
build, both names present, an interrupt), not with the real tool; the real
behaviour of `pipx install --force` over a dangling command link is the thing
to watch on the first real run.

Tests: `tests/test_distribution_name.py` (5) -- the name in `pyproject.toml`,
the command / import name kept, the runtime lookups, no stale
`pipx inject|uninstall sarand` anywhere, the README note; and five new tests in
`tests/test_install_script.py` for the old name (replaced after a good build,
restored after a failed one, both names present, an interrupt, `--force`).


**5.63 follow-up -- what the first CI run of the rename found (2026-10-11).**
The rename commit passed every local check and failed CI twice, for two
reasons the local chain could not show:

- `scripts/smoke_install.py` (the fresh-install smoke test) globbed
  `sarand-*.whl`; the `sarand-cli` wheel is `sarand_cli-*.whl` (PEP 427 writes
  the hyphen of the name as an underscore). The unit test of `find_wheel` used
  made-up file names, so nothing local ever built a real wheel. My search for
  what depends on the name had grepped the metadata lookups and missed this
  glob; the lesson is to grep a renamed identifier everywhere, including
  `scripts/` and `.github/`, in every spelling (`sarand-`, `sarand_`).
- `tests/test_pyproject_valid.py` imported `tomllib` (3.11+). CI runs
  `mypy .` -- the tests and scripts too, not only `python/` as the local chain
  did -- on Python 3.10, where the module does not exist. The project already
  had the idiom for this (`if sys.version_info >= (3, 11): import tomllib /
  else: import tomli as tomllib`, used in `core/components.py`,
  `core/workspace.py` and `core/license_policy.py`); the test now follows it and
  runs on every Python. Standing rules: the local type check is `mypy .` (as
  CI), and a module newer than Python 3.10 is imported only through that idiom.

### 5.64 — A release workflow with PyPI trusted publishing (2026-10-10)

Backlog status item 8, the building part. 5.62 prepared the README and CI,
5.63 renamed the distribution to `sarand-cli`; this adds the pipeline.

**Design.** `.github/workflows/release.yml` (the file name is part of the PyPI
trusted-publisher form):

- *Triggers:* a pushed tag `v*`, or a manual run. A tag builds everything and
  publishes to PyPI; a manual run only builds, and uploads to TestPyPI when its
  box is ticked (the dry run). PyPI is never published from a branch or a manual
  run.
- *Jobs:* `check` (the tag must equal the version in `pyproject.toml`);
  `wheels` (a matrix: Linux x86_64 and aarch64 in the manylinux container, macOS
  arm64 and x86_64 -- the latter cross-compiled on the arm runner -- and Windows
  x64, through `PyO3/maturin-action@v1`); `sdist`; `smoke` (installs the Linux,
  macOS and Windows wheels on Python 3.10, and the Linux one also on 3.14, runs
  `sarand --version`, imports `sarand._core` so a wheel without the compiled
  core cannot pass, and on a tag checks that the wheel's version names the tag);
  `publish-testpypi` and `publish-pypi`, each needing `wheels`, `sdist` and
  `smoke`.
- *Safety:* trusted publishing (OIDC) through `pypa/gh-action-pypi-publish@
  release/v1`, so no token or password exists anywhere; the default permission
  is `contents: read` and only the two publish jobs get `id-token: write`; each
  publish job has its own environment (`pypi`, `testpypi`), and `pypi` is meant
  to carry a required reviewer, so a real upload waits for a human. The action
  attaches PEP 740 attestations by default. Artifacts move between jobs with
  `upload-artifact@v6` and `download-artifact@v8` (the Node 24 majors; versions
  checked from the official release pages on 2026-10-10).
- *abi3:* `pyproject.toml` enables `pyo3/abi3-py310`, so there is one wheel per
  platform for every Python from 3.10 on (matching `requires-python`) instead
  of five per platform, and cross-compiling needs no target interpreter. The
  Rust source uses only `PyDict`, `pyfunction`, `pymodule`, `Bound` and
  `Python::detach`, all abi3-safe. The `Cargo.toml` feature list is left
  alone, so `cargo test` and clippy still build the full API; only the maturin
  build is limited to abi3, which is exactly what CI's "Build the release
  wheel" step and the release workflow exercise.
- *Docs:* `docs/PUBLISHING.md` and `.fa.md`: the one-time setup with the exact
  fields of the two PyPI forms and the two GitHub environments, the TestPyPI
  dry run, a real release, and a troubleshooting table taken from PyPI's own
  documentation (a pending publisher does not reserve the name; the form
  cannot name a reusable workflow; the environment name must match).

**Not verified here.** Nothing can run a workflow in the sandbox. What is
checked is that the file parses and that its safety properties hold
(`tests/test_release_workflow.py`, 11 tests). The first real proof is the
TestPyPI dry run described in the guide; the macOS x86_64 cross build, the
aarch64 manylinux build and the abi3 compile of the Rust core are the three
things most likely to need a fix there.

**Not done (needs the user or a decision).** The accounts, the two pending
publishers, the two GitHub environments and the first upload (all in the guide);
the `pipx install sarand-cli` line in the READMEs (added by the release that
publishes); a GitHub Release with the files attached.


**5.64 follow-up -- the first real run of `release.yml` (2026-10-12).** The
dry run built all five wheels (so the aarch64 manylinux build, the macOS x86_64
cross build and the abi3 compile of the Rust core all work on CI) and failed
only in the Windows smoke test: `pip install dist/*.whl` ran in PowerShell,
which does not expand the glob for a native command (`ci.yml` forces bash on
every OS for this reason; `release.yml` did not). `release.yml` now sets
`defaults.run.shell: bash` and a test pins it. Nothing was uploaded: the
publish jobs need the smoke job.

### 5.65 — The first PyPI release, v0.6.19 (2026-10-12)

The result of 5.62 to 5.64: the project is published as `sarand-cli`.

**What was verified before this release.** CI is green on every job with the
abi3 wheel (the Rust core compiles with `pyo3/abi3-py310`; the fresh-install
smoke test installs `sarand_cli-*.whl` and runs `sarand --version` and
`--doctor`), `twine check --strict` passes on the wheel and the sdist (also run
by hand on the phone), and a TestPyPI dry run through `release.yml` built the
five wheels and the sdist, installed three of them and uploaded to
test.pypi.org (docs/PUBLISHING.md, "A dry run on TestPyPI").

**The release.** Version 0.6.19 (the tag v0.6.18 predates `release.yml` and the
rename, so the first published version is the next one). The READMEs show
`pipx install sarand-cli` first and keep the source install as the second way.
A tag `v0.6.19` runs `release.yml`; `publish-pypi` waits for the approval of
the `pypi` environment.

**Known limits.** Wheels exist for glibc Linux (manylinux), macOS and Windows
only: Alpine (musllinux), Termux on Android and free-threaded Python builds
install from the sdist and need a Rust toolchain. The README links point at
`main`. No GitHub Release is created. PyPI does not allow replacing a file: a
mistake is fixed by the next version (a bad one can be yanked).

### 5.66 — The Persian README rewrite (2026-10-13)

The user rewrote `README.fa.md` (741 lines against 684): a more formal and more
careful text, PyPI install first, an explicit statement that CI covers desktop
systems only and that Termux is designed for but not tested by CI, the
distinction between "a tool is missing" and "a check passed", the report and
health-score sections, the output-directory priority, the RC tools and an
uninstall table.

**Review.** Every checkable claim was compared with the code: the options of
`cli.py` (all documented, none invented; `tests/test_readme_sync.py` agrees),
the `--full` rule (it lifts the file-size, depth and entry limits and an
explicit `--max-file-size` still wins), the defaults, the output-directory order
(`--output-dir`, `SARAND_OUTPUT_DIR`, the saved setting, `~/Downloads`), the
health-score weights and the A to D thresholds, and the RC options. All were
right. One guard test failed: the ecosystem table named three rows in Persian
("C و C++", "Dart و Flutter", "Java، Kotlin و Android") while
`test_every_ecosystem_sarand_can_drive_is_listed_in_both_readmes` needs the
doctor's category names (`C/C++`, `Dart / Flutter`, `Java / Kotlin / Android`).

**Corrections made while adopting it.** The three row names; the Zig, Ruby and
C# rows now list what `--doctor` lists (quality and security, not only tests);
the install paragraph says that `install.sh` replaces an install made under
the old pipx name (0.6.19); the workspace paragraph names Maven and Gradle, the
several-workspaces report and the Package results table (5.58 to 5.61); the
uninstall and the stale-version notes cover an editable install made under the
old distribution name `sarand`; the contributing check is `mypy .` as in CI
(5.63 follow-up), not `mypy python`.

**Left as the author wrote it.** The sample output and the tip box of the old
text are gone; that is an editorial choice (a sample output helps a first-time
reader), not an error.


### 5.67 — Audit remediation R1: secrets (2026-10-15)

First round of `docs/AUDIT_FIX_PROMPT.md` (findings A1, A2, A2b, A3). Each
finding was re-checked against the code before anything changed.

**CONFIRMED, with a correction to the audit.**

- **A1 filenames — confirmed, but the audit overstated it.** It said the
  listed files are "embedded in the report". Measured on a fixture tree with
  `collect_essential_files`: only the files whose extension is in
  `ESSENTIAL_EXTENSIONS` were embedded — `secrets.yaml`, `secrets.json`,
  `secrets.toml`, `firebase-adminsdk-*.json`, `kubeconfig.yaml`,
  `*.tfvars.json`, `wp-config.php`, `.docker/config.json`. The rest
  (`.aws/credentials`, `.pypirc`, `.git-credentials`, `*.tfstate`, `*.tfvars`,
  `.htpasswd`, `kubeconfig`, `*.ppk`, `*.p8`, `id_ecdsa_sk`) never reach the
  report because the extension check runs first, but they are silently
  skipped and not listed as "excluded".
- **A2 content patterns — confirmed.** Only AWS `AKIA`, `ghp_`-style, Slack,
  RSA/EC/OPENSSH/DSA key headers and an `api_key=` assignment were detected;
  `github_pat_`, `sk-ant-`, `sk-proj-`, `AIza`, `sk_live_`, `pypi-`, `npm_`,
  `ASIA`, JWT, URL passwords, `password = '...'`, PGP and encrypted key
  blocks were missed (run, not read).
- **A2b gitleaks — confirmed.** gitleaks runs after the embedding decision,
  only with `--security`, and its result never changed what was embedded.
- **A3 fixture guess — confirmed.** `startswith("tests/")` marked any
  finding under `tests/` as a fixture.

**BUILT.**

1. `SECRET_FILENAME_PATTERNS` gained 16 patterns and there is a new
   `SECRET_PATH_PATTERNS` (`.docker/config.json`, `.aws/credentials`,
   `.kube/config`, `.gnupg/`). `looks_like_secret_path` applies both and is
   what `essential_files` now calls.
2. `core/secrets.py` has 16 content rules (data, in `_RULES`), each with
   lowercase "needles" and an optional validator (placeholder filter,
   Shannon entropy, a digit-or-uppercase check for assignments). One unified
   needle regex rejects almost every ordinary line first: scanning this
   repo's 262 files takes 0.116 s against 0.102 s before (best of 5). One
   credential on one line is one finding (the password rule is a catch-all
   that yields to any more specific rule). The cache fingerprint now hashes
   every rule's regex text plus `RULES_VERSION`, so a rule change invalidates
   caches (before, only names were hashed).
3. Every regex is linear: no nested quantifiers, and each "run then literal"
   shape has a lookbehind so a match can only start at the start of a run.
   `eyJ` * 30000 and similar 100k-character lines are pinned by a test.
4. gitleaks: `gitleaks_flagged_paths` parses the `File:` lines of the redacted
   verbose output already captured; `cli.py` calls `exclude_paths` after the
   security phase. Only files actually slated for embedding move; paths that
   exist only in git history are ignored; absolute and `..` paths are ignored.
5. `[secrets] fixture_paths` in `.sarand.toml` (`core/secrets_config.py`):
   unknown key, bad type, invalid TOML and a glob that matches everything are
   errors; `cli.py` turns an error into a warning and counts every finding
   (the safe direction). `mark_fixture_findings` recomputes the flag for every
   finding, cached ones included, so a stale cached flag cannot survive.
   `scan_for_secrets` no longer sets `is_test_fixture`. sarand's own
   `.sarand.toml` lists `tests/test_secrets.py`, the file `.gitleaks.toml`
   already allow-lists.

**Deviations from the prompt (deliberate).**

- No per-line length cap: truncating a line is a silent false negative in a
  minified bundle, and the patterns are linear, so the cap buys nothing.
- gitleaks is parsed from its text output rather than from a second JSON
  report: no temp file, no signature change, and a format change only means
  "nothing extra is excluded". The report names the exclusion in a warning
  and in the existing excluded-files section, not with a per-engine label.

**Non-goals (recorded).** Listing credential-shaped files that have a
non-essential extension as "excluded" (a visible behaviour change in every
report); scanning git history ourselves; a user-extensible rule list;
changing health weights. Known limit: `password = "correcthorsebattery"`
(all lowercase, no digit) is not reported by the assignment rule on purpose;
the entropy and character-class gate trades that miss for far fewer false
positives.

**Verification.** 41 tests added (1081 to 1122 in the whole suite, run with a
stand-in `pytest` and `rich` in a sandbox that has neither). The same 5
tests fail before and after (they need `filelock`/pip internals missing in
that sandbox). `ruff`, `mypy` and `cargo` were NOT run; the
delivery's check chain runs them on the device. The repo itself yields the
same 5 findings as before, all in the allow-listed `tests/test_secrets.py`:
no new false positive.

**Lessons.** A claim about impact needs the measurement that decides it
(here: which extensions are embedded). Ruff's modern-idiom rules (FLY002,
ISC) are why the new fixtures are joined through a small `_cat(*parts)`
helper instead of `"a" + "b"` or `"".join([...])`.

**Follow-up (first CI run).** Three tests in `tests/test_cli_secrets.py`
failed on `windows-latest` only: `SecretFinding.path` is `str(rel)`, so it
carries a backslash there and the test compared it with a POSIX string. The
feature was right (`matches_fixture_path` already normalises); the test
helper now normalises too. Any test that reads a finding path must do so.


### 5.68 — Audit remediation R2: truthful issue extraction (2026-10-16)

Second round of `docs/AUDIT_FIX_PROMPT.md` (findings A6, A7, C2). Each finding
was re-checked against the code and the self-report before anything changed.

**CONFIRMED.**

- **A6 — confirmed, two layers.** `scan_for_issues` classified lines by bare
  substrings (`failed`, `exception`, `panic`, `error:`) over the output of
  every tool, passing ones included: syft's healthy line "License policy:
  0 violation(s), 0 warning(s), 0 exception(s) applied" was listed under
  *Errors detected* (it contains `exception`). On top of that,
  `detect_known_issues` ran over every result and its `error:` pattern made
  Quick Context claim "Compilation or lint errors were detected." although
  ruff, mypy and clippy had all passed.
- **A7 — confirmed.** `cargo audit` printed "couldn't check if the package is
  yanked ... timeframe" three times, exited 0 and was reported as PASS.
- **C2 — confirmed.** 583 TODO-style rows on this repo, 390 of them in golden
  fixtures and Markdown prose.

**BUILT.**

1. Diagnostics are recognised by line shape: `constants.WARNING_LINE_PATTERNS`
   and `ERROR_LINE_PATTERNS` (`error:` / `error[E0308]:` after a line start,
   `:` or whitespace, a traceback header, a column-0 `...Error:` line,
   `panicked at`, `FAILED `/`ERROR ` summary lines, `npm ERR!`, go `FAIL`,
   `test result: FAILED`, a non-zero `N failed`). `OSError:` and a quoted
   `"error: boom"` no longer match; `0 failed` needs no special case.
2. `make_command_result` drops the errors of a command that exited 0 (the
   warnings stay). `detect_known_issues` only reads results that failed
   (non-zero exit, not skipped, not inconclusive) and its patterns are
   regexes (`KNOWN_ISSUE_PATTERNS`).
3. INCONCLUSIVE: `CommandResult.inconclusive_reason` (the `inconclusive`
   property is derived from it, and `passed` is false for it). It is set only
   for audit-style kinds (`audit` / `vuln` in the kind: cargo audit, pip-audit,
   npm audit, govulncheck, bundler-audit, composer audit, dotnet
   `--vulnerable`) and only when the exit code was 0, from
   `constants.INCONCLUSIVE_SIGNATURES` (yanked-check timeout, advisory DB
   fetch failure, name resolution, connection timeouts, ETIMEDOUT/ENOTFOUND,
   "error sending request"). **A failing exit is never downgraded**: a tool that
   found real vulnerabilities may also print a network warning.
4. Health: an inconclusive check is "did not run" (decision D5 of the prompt,
   default as recommended): no security penalty and no critical finding, but
   it lowers `confidence`, is listed in the new
   `HealthScore.checks_inconclusive`, and a recommendation says to re-run with
   network access. A real failure next to an inconclusive one still takes the
   security penalty.
5. Renderers: markdown `[INCONCLUSIVE]` plus a one-line reason, HTML badge,
   Quick Context status and risk line, package summary counts it with the
   skipped ones. JSON carries `inconclusive_reason` and
   `health.checks_inconclusive` only when set, following the file's own rule
   that an ordinary run must not gain keys, so **all golden snapshots stay
   byte-identical** (the full suite is the proof).
6. TODO noise: `scanners/todos.py` `is_todo_excluded` / `filter_todos`. Default
   exclusions (recorded as deliberate): any directory segment named `golden`,
   `fixtures`, `snapshots`, `__snapshots__` (case-insensitive) and prose files
   (`.md`, `.mdx`, `.rst`). `[todo] exclude_globs` in `.sarand.toml`
   (`core/todo_config.py`, same strict rules as `[secrets]`) adds more. The
   filter runs after the cache merge, so stale cached markers of newly excluded
   files disappear too. `ReportData.todos_suppressed` is printed under the TODO
   heading (the section stays visible even when every marker was suppressed) and
   appears in JSON only when non-zero. On this repo the defaults remove 390 of
   583; sarand's own `.sarand.toml` adds the two fixture-heavy test files.

**Deviations from the prompt (deliberate).**

- JSON keys appear only when set (not always), to keep the established
  byte-identical-goldens convention.
- `inconclusive_reason` is one string field (the boolean is derived), not a
  boolean plus a separate reason.
- Inconclusive detection is limited to audit-style kinds and exit code 0. The
  prompt allowed generic kinds; that would mislabel a passing test suite that
  merely prints a network error line.
- A failing audit tool with a network error stays FAIL (the pre-existing
  behaviour). Telling "found vulnerabilities" apart from "could not reach the
  service" in a non-zero exit needs per-tool structured output: not done.

**Non-goals (recorded).** Parsing every tool's structured output; changing
sarand's own exit codes; per-tool configurable warning rules; making the
network-failure case of a *failing* audit inconclusive; rewriting the
`Known issues` wording.

**Verification.** New tests: `tests/test_issue_extraction.py` (A6/A7, health,
renderers, package counts) and `tests/test_todo_filter.py` (C2 and the config
table). The whole existing suite passes unchanged, including every golden
snapshot. `ruff`, `mypy` and `cargo` were NOT run in the sandbox; the delivery's
check chain runs them on the device.

**Lessons.** Fixing the symptom twice (bandit context lines, `OSError:`) hid
the cause: the scan ran over output it had no business reading. The durable
fix was to decide *which results may speak* (failed ones) before deciding
*which lines count*.

**Lint follow-up (first run).** `ruff` (ISC004) rejected two multi-line
strings written as implicit concatenation *inside a tuple or list*: they
must be wrapped in their own parentheses (or joined with an explicit
comma-free expression). The rule was already written down in this file;
the delivery did not apply it. Before shipping, scan changed files for
adjacent string literals inside `[...]`, `{...}` and tuple parentheses.


### 5.69 — Audit remediation R3: scan-engine parity (2026-10-17)

Third round of `docs/AUDIT_FIX_PROMPT.md` (findings A5, A8). The two scan
engines (compiled Rust core, pure-Python fallback) must report the same files
for the same tree; they did not.

**CONFIRMED.**

- **A8 — confirmed by running it.** `_pure_python_scan` pruned every directory
  whose name starts with `.git`, so `.github/workflows/ci.yml` was missing from
  the scan records on a machine without the compiled core, while the Python
  tree view (and the Rust core) showed it. A second difference found while
  writing the parity test: the fallback stored `rel_path` with the platform
  separator (`str(Path)`), Rust always stores `/`.
- **A5 — confirmed by reading, not by running.** `src/walker.rs` pruned with
  `entry.path().components().any(...)`: the *absolute* path, so a project whose
  root sits below a directory named `build`, `dist`, `target`, `.cache`, `venv`,
  ... (a Docker `WORKDIR /build`, a checkout under `~/build/`) lost every file.
  The sandbox has no `cargo`; the proof is the new Rust test plus the Python
  parity test that runs against the compiled core in CI.

**BUILT.**

1. `walker.rs`: the ignore list is applied with `WalkBuilder::filter_entry` to
   *directories only*, at depth > 0, by the directory's own name. The old
   post-filter is gone, so an ignored directory is no longer traversed at all
   (the walk used to descend into `node_modules` of a non-git tree and discard
   the result). The root's ancestors are never examined and the root itself is
   never pruned. A symlink to a directory with an ignored name is pruned too (as
   `os.walk` and the old behaviour did). A *plain file* that happens to be named
   like an ignored directory (`dist`) is kept, as the fallback always did. The closure owns a
   `HashSet<String>` because `filter_entry` requires `'static`.
2. `rust_bridge._pure_python_scan`: prunes exactly `ignore_dirs` (so
   `.github`, `.gitlab`, `.gitea` are kept; `.git` stays ignored because it is
   in `IGNORE_DIRS`) and stores POSIX `rel_path`.
3. Tests: two Rust tests in `walker_tests.rs`, and `tests/test_scan_parity.py`
   (fallback behaviour; and, when the compiled core is present, that both
   engines return the same file set for a plain tree and for a tree under
   `build/dist/`). CI builds the wheel before pytest, so the parity test runs
   there on all three operating systems.

**Single ignore semantics (now the contract).** A directory is ignored when its
own name is in `IGNORE_DIRS`, at any depth below the root. Nothing else about the
path matters. `.gitignore`/`.ignore` handling remains Rust-only (known and
documented: the fallback never had it).

**Deviation from the prompt.** None in substance. The prompt said the Rust
change "could not be executed in the sandbox"; this round's delivery therefore
tells the owner to run `cargo fmt`, `cargo clippy` and `cargo test` before
committing, and to rebuild the extension before pytest.

**Non-goals (recorded).** Walk error reporting and `git_global` (R7, B4);
hashing, line counting, binary sniffing; the cache format; making the fallback
honour `.gitignore`; the tree builder (`tree.rs` already compared the entry's own
name, so it was never affected).

**Verification.** In the sandbox: the Python tests pass and the A8 test was
confirmed failing before the fix; the whole existing suite is unchanged. The Rust
code was NOT compiled here. The owner's check chain compiles it with
`cargo fmt`, `cargo clippy --all-targets --all-features -- -D warnings`,
`cargo test` and `maturin develop --release`, and CI repeats all of it.

**Lessons.** A filter that runs on `entry.path()` is a filter on a string the
caller partly chose. Match on the entry's own name, and prune at the directory
so the intent ("never look inside") is also the behaviour.


### 5.70 — Audit remediation R4: trust model and community files (2026-10-17)

Fourth round of `docs/AUDIT_FIX_PROMPT.md` (finding A4, part of C6). Released
rounds R1-R3 as v0.6.20 first (see the CHANGELOG); this round is documentation
plus guard tests, no behaviour change.

**CONFIRMED.** The README said sarand "runs its tests" and nothing more, and
the repository had no `SECURITY.md` / `CONTRIBUTING.md`. Reading the analyzers
showed that the exposure is wider than the test phase: the node analyzer starts
`npm test` and `npm run lint` (project scripts), the Java and Android analyzers
prefer the project's own `./gradlew` wrapper over a system Gradle, `cargo
clippy` runs build scripts and procedural macros, ESLint/stylelint execute
JavaScript config files, `bundle exec` evaluates the Gemfile, and several audit
tools contact the network. Defaults: tests on, `--quality` / `--security` off,
`--full` enables both.

**Clarification of §4.3.** "An analyzer never executes project code itself"
means sarand never interprets or imports project files; the *toolchains it
launches* do run them. The README now says so plainly.

**BUILT.**

1. `README.md` / `README.fa.md`: a "Trust model: scanning runs project code"
   section (a table of what each flag starts and whether project code can run,
   what sarand never does, and four safer ways to scan untrusted code), a
   warning callout in Quick start, and a corrected Contributing block
   (`mypy python` was wrong: CI runs `mypy .`). The Persian file has an explicit
   `<a id="trust-model">` anchor because Persian heading slugs are fragile.
2. `SECURITY.md` (private reporting through GitHub, scope, what is not a
   vulnerability) and `CONTRIBUTING.md` (setup, the exact CI check chain,
   conventions that cost a CI run in the past, how to add an analyzer).
3. `sarand --help` epilog: a "Trust model" paragraph (no new flags).
4. `tests/test_trust_model.py` turns the README's claims into checks: no
   `shell=True`; no argv-shaped list starting with `make` and none that
   installs dependencies; every `npm` invocation is `test`, `run lint` or
   `audit`; both READMEs carry the section; the help epilog mentions it; the
   community files exist and are linked with absolute URLs; the CONTRIBUTING
   check chain matches ci.yml. The first three passed against the unchanged
   code before any documentation was written.

**Deviations from the prompt (deliberate).** None in substance. The prompt
suggested "run inside a container" generically; the README does not give a
Docker command because a read-only mount breaks the tools that write caches.
`SECURITY.md` names GitHub private vulnerability reporting, which the owner
must enable (Settings, Code security); the 7-day acknowledgement is a stated
goal of a one-person project, not a guarantee.

**Non-goals (recorded).** Sandboxing or containers built into sarand; an
interactive consent prompt; a flag that forbids project code (it would need
per-analyzer plumbing).

**Verification.** The whole suite plus the new guard tests; README and help
text were read against the code listed above. `ruff`, `mypy` and `cargo` were
not run in the sandbox (no behaviour change in Rust).

**Lessons.** After `maturin develop`, an older version-specific
`python/sarand/_core.cpython-3xx-*.so` shadows the fresh `_core.abi3.so`
(Python prefers it), so pytest silently loads a stale core. Delete the
`cpython-*` ones; CONTRIBUTING says so. A parity test that runs against the
compiled core is what exposed it.


### 5.71 — Audit remediation R5a: Python 3.11 is the new floor (2026-10-17)

First half of R5 in `docs/AUDIT_FIX_PROMPT.md` (finding B6, owner decision D1:
"drop Python 3.10 inside R5"). The second half (CI/release hygiene) follows
as R5b.

**Why now.** The CPython devguide gives October 2026 as the end of life of 3.10,
and two news reports say the final release (3.10.22) shipped on 1 October. Those
two are secondary sources; the devguide is the primary one, and its month is
enough. The audit's "about two weeks left" was wrong: 3.10 is at or past the end.
Python 3.15.0 is out too (reports differ between 1 and 9 October; the
`actions/python-versions` manifest has it since 10 October).

**BUILT.**

1. `pyproject.toml`: `requires-python = ">=3.11"`, the 3.10 classifier and the
   `tomli` dependency are gone, the wheel is `cp311-abi3` (`pyo3/abi3-py311`).
2. Five modules and one test dropped the `sys.version_info`/`tomli` shim and just
   `import tomllib` (license_policy, components, workspace, secrets_config,
   todo_config, test_pyproject_valid).
3. `doctor` checks for 3.11; the example plugin and `docs/PUBLISHING*.md`, both
   READMEs (badge, requirements table, the `tomli` notes) and CONTRIBUTING say 3.11.
4. CI: the oldest blocking job is Python 3.11 (Linux), 3.12 stays on every OS,
   3.14 on Linux, and **3.15 runs as a non-blocking job** (`continue-on-error`,
   `experimental: true`): a failure there is information, it does not turn the
   workflow red or stop `release.py tag`. Release smoke tests start at 3.11.
5. `tests/test_python_floor.py` reads the floor from `pyproject.toml` and requires
   the classifiers, the abi3 feature, the doctor check, the CI matrix, the release
   smoke matrix and both README badges to agree, and that `tomli` is gone. The
   next floor change is a one-line edit plus whatever this test lists.

**Consequences for users.** `pip` enforces `requires-python`: a user on 3.10 keeps
resolving to 0.6.20 and is not offered the new wheel. Because dropping a Python
version is a compatibility break, the next release should be a minor bump
(**0.7.0**), not 0.6.21; that is chosen at `release.py bump` time.

**Non-goals (recorded).** Rewriting code to 3.11-only idioms (`Self`, `StrEnum`,
`ExceptionGroup`, `tomllib` everywhere else): possible later, no behaviour gain
now. Raising mypy's target (it follows the interpreter). Python 3.15 as a
*blocking* job: wait until a full green run shows PyO3 and every dependency
accept it (PyO3's `cargo test` builds without the abi3 feature and may reject an
interpreter newer than it knows).

**Verification.** In the sandbox: the whole suite plus the new floor test. The
CI matrix and release workflow edits are checked by their own tests and by the
first CI run; `ruff`, `mypy`, `cargo` and `actionlint` were not run here.

**Lessons.** A constraint written in a dozen places is a constraint nobody can
change safely. Make one place the truth and make a test read it.


### 5.72 — Audit remediation R5b: CI, audit and release hygiene (2026-10-18)

Second half of R5 in `docs/AUDIT_FIX_PROMPT.md` (findings B1, B2, B5, C5; owner
decisions: add every static check, add the GitHub Release).

**CONFIRMED.** CI ran none of bandit, pip-audit, cargo deny, gitleaks,
actionlint, markdownlint (the owner's own self-report listed bandit and
markdownlint as failing), had no `permissions:`, no concurrency control and no
Dependabot. `release.yml` smoke-tested only three of the five wheels, never
asked whether CI had been green for the tagged commit, and created no GitHub
Release. A new, unplanned finding while verifying: both READMEs still said
"Python 3.10" in three places after R5a (the Persian one with Persian digits and
the Arabic decimal separator, which an ASCII search cannot see).

**Verified against sources before writing** (no versions from memory):
`ubuntu-24.04-arm` and `macos-15-intel` are listed GitHub-hosted runners for
public repositories (docs.github.com, supported runners); the gitleaks action's
README now says `gitleaks/gitleaks-action@v3` (v2 is going away); `markdownlint`
0.48.0 exists (it was run here, for real, over every document in scope).

**BUILT.**

1. `ci.yml`: `permissions: contents: read`, concurrency that cancels a
   superseded *pull-request* run (never a push to main), and a `static` job
   (Ubuntu only) running bandit, markdownlint, actionlint (pinned Docker image),
   `cargo deny check licenses bans sources` and gitleaks. Every check after the
   first has `if: !cancelled()`, so one run reports all problems. The checkout is
   complete (`fetch-depth: 0`) because gitleaks reads history.
2. `audit.yml` (new): `pip-audit` on the runtime dependencies and
   `cargo deny check advisories`, weekly, on demand and on pull requests that
   touch a dependency file. **Separate from CI on purpose** (deviation from the
   prompt, which put them in `static`): they need the network and an advisory
   database, and an outage there must not turn an ordinary push red or block
   `release.py tag`, which only accepts a green CI workflow.
3. `dependabot.yml`: GitHub Actions, Cargo and pip, weekly, one grouped pull
   request per ecosystem.
4. `release.yml`: `ci-gate` (a tag is only released if the CI workflow succeeded
   for its commit; `publish-pypi` needs it), native smoke tests for the two
   cross-built wheels (`ubuntu-24.04-arm` for linux-aarch64, `macos-15-intel` for
   macos-x86_64), and `github-release` after `publish-pypi`: wheels, sdist and a
   generated `SHA256SUMS` attached to a release whose notes are the CHANGELOG
   section of that version. It runs only for tags, so TestPyPI dry runs never
   create one.
5. `scripts/pin_actions.py` + `tests/test_action_pins.py`: pins every `uses:` to
   a commit SHA (needs the network, so the maintainer runs it). The test enforces
   "tag, documented branch or SHA" today and requires SHAs once `ENFORCE_PINNED`
   is flipped. **Not enforced yet**: this environment has no network and a
   fabricated SHA would be worse than a tag.
6. bandit: `[tool.bandit]` in `pyproject.toml`, reasoned `# nosec` markers on
   exactly the lines the owner's report named (release.py, smoke_install.py,
   jvm_workspace.py), and the one new `try/except/continue` of R1 (B112) now logs.
7. markdownlint: `.markdownlintignore` lists the three files that still have
   violations (AGENTS.md and docs/BACKLOG.md for round R8, the AI prompt
   docs/AUDIT_FIX_PROMPT.md); every other document passes, after fixing the
   Persian README's ten anchor-above-heading errors, two of my own R4 slips
   (bold text used as a heading; two callouts separated by a blank line), and a
   file-level `MD029` directive for BACKLOG_STATUS, whose numbered items continue
   across sections on purpose (other documents cite "item 8").
8. `tests/test_ci_workflows.py` pins the shape of all of the above;
   `tests/test_python_floor.py` gained a check that no document names a dropped
   Python version (in ASCII or Persian digits).

**Deviations from the prompt (deliberate).** pip-audit/cargo advisories moved to
`audit.yml` (above). cargo-deny is installed with `cargo install --locked` and a
cache instead of a third-party action, because its version could not be verified.
actionlint runs from the `rhysd/actionlint:1.7.7` image: that tag is an existing
release, but it was not re-checked against the latest. The release workflow's
header comment still says "after the approval ...", which stays true.

**Non-goals (recorded).** SHA pins (script provided); zizmor (it would fail
today on every unpinned action); a blocking Python 3.15 job (its first run was
green, so this is now a decision, not a blocker); Windows ARM wheels; attestation
changes.

**Verification.** `markdownlint` 0.48.0 over every in-scope document (zero
errors); every workflow and config file parsed; the whole suite plus the new
tests; the pin script's rewrite logic against a fake resolver. **NOT run here:**
bandit, actionlint, cargo-deny, gitleaks and the workflows themselves. The first
CI run is their real test, and a small follow-up commit after it is expected.

**Lessons.** Two checks silently covered less than they claimed: a search for
"3.10" does not find "۳٫۱۰", and a step without `if: !cancelled()` does not run
after a failure, so a multi-tool job reports one problem per push.

**Follow-up (first local run).** bandit reads every word after `# nosec`
as a test id, so `# nosec B404 -- some reason` logged a warning per word;
write the reason on the line above and keep only the ids on the marker.
A marker inside a multi-line statement applies to every line of it and
warns on those with nothing to suppress: keep the suppressed construct on
one line. `scripts/pin_actions.py` now refuses any URL that is not
`https://api.github.com/` before it opens it (B310).

**Follow-up (first CI run, 2026-10-18).** The `static` job failed on one check
of five: actionlint 1.7.7 did not know the label `macos-15-intel` (a real
runner), so it is declared in `.github/actionlint.yaml`. bandit, markdownlint,
cargo-deny and gitleaks 8.24.3 passed on their first run. Dependabot opened its
first pull requests within minutes of the merge (Actions major bumps and
dependency groups); each must pass CI before it is merged.


### 5.73 — Audit remediation R6: limits on parallel tools and on output (2026-10-18)

Sixth round of `docs/AUDIT_FIX_PROMPT.md` (finding B3).

**CONFIRMED.** `run_tests/quality/security_concurrently` gathered every matching
analyzer at once, per component and per workspace member, and the project-wide
trio (gitleaks, syft, lockfile check) ran beside them: in a polyglot project
`cargo test`, `pytest`, `npm test` and the audits could all start together, on the
owner's 6 GB phone and 2 GB laptop. `run_cmd_async` also buffered a command's whole
output with `communicate()`, so a chatty tool could hold hundreds of MiB.

**BUILT.**

1. **One limit at the single choke point.** Every analyzer subprocess goes through
   `utils/command.run_cmd_async`, so the limit lives there as a process-wide
   `asyncio.Semaphore` (`set_max_concurrent_commands`), rebuilt per event loop.
   It bounds real *processes*, not tasks, so it covers analyzers, components,
   workspace members and the gitleaks/syft/lockfile trio without touching any of
   those call sites. The timeout starts when a command gets its slot, not while it
   waits. By default the library does not limit (callers and tests that import it
   behave as before); the CLI always sets a value.
2. **`--jobs N`** (1 to 64) and **`SARAND_JOBS`**. Precedence: command line, then
   the variable, then the default of `core/concurrency.py`: one tool per CPU and
   per GiB of *free* memory (read when the scan starts, so a busy machine gets
   fewer), at most 8, never less than 1. The 2 GB laptop therefore runs one tool at
   a time and a workstation up to eight. An invalid `SARAND_JOBS` warns and falls
   back to the default; an invalid `--jobs` is an argparse error.
3. **Bounded output.** `run_cmd_async` reads the merged output in chunks and keeps
   the first and last half of `MAX_COMMAND_OUTPUT_BYTES` (8 MiB); the middle is
   dropped and replaced by one marker line, `[sarand: N bytes omitted from the
   middle of this output]`. The pipe is **drained to the end** after the cap so the
   child never blocks on a full pipe, and the tail is trimmed only when it doubles
   (amortised O(1) per chunk, peak about 1.5 times the cap). Timeout and
   cancellation behave as before (a timed-out command still returns 124 with what
   it printed). The new keyword `max_output_bytes` exists for tests.

**Deviations from the prompt (deliberate).** The prompt asked for a
`gather_limited` helper applied at the three registry helpers and at the
component/workspace runners, and for `truncated: bool` on `CommandResult`. A
limit on the subprocess itself is stronger (it also covers the trio and any future
caller) and needs no new plumbing; the visible marker line in the output replaces
the boolean, which would have needed every analyzer to pass it along. The
prompt's fixed default (4, or 2 under 2 GiB) became the proportional rule above
after the owner asked whether a stronger machine would use its hardware.

**Non-goals (recorded).** Per-tool limits and priorities; changing timeouts; the
synchronous `run_cmd` (short probes of installed tools only); throttling work a
tool does internally (`cargo` still uses every core of its own slot).

**Verification.** New tests: `tests/test_concurrency.py` (the default rule, parsing,
precedence, argparse) and `tests/test_command_limits.py` (a limit of 1 never
overlaps two commands, a limit of 2 never has three alive, the limit follows each
event loop, the timeout excludes the wait, output over the cap keeps head and tail
and says so, a command filling the pipe and then timing out still returns, a 25 MiB
output stays under the cap). The overlap tests read timestamps written by the
child processes, not the parent's clock. `ruff`, `mypy` and `cargo` were not run in
the sandbox.

**Lessons.** Put a resource limit where the resource is consumed (the process
start), not where the work is scheduled (the call sites): the first is one place,
the second is every place and the next one added.


### 5.74 — Audit remediation R7: unreadable paths are reported (2026-10-19)

Seventh round of `docs/AUDIT_FIX_PROMPT.md` (finding B4, part 1 and 2; part 3, the
`git_global` default, is a pending owner decision, D2).

**CONFIRMED.** The Rust walker used `filter_map(|entry| entry.ok())` and
`build_record` returned `Option` through `?`, and the Python fallback did
`except OSError: continue`: a directory the process may not enter, or a file that
vanished between the walk and the `stat`, left every count of the report short with
no trace. (R3 already removed the other half of B4, the walk into ignored
directories.)

**BUILT.**

1. Rust: `walker::scan_report` returns the records plus `ScanProblems` (how many
   entries were skipped and the first five messages). `scan` stays as a thin wrapper
   so every existing caller and test is untouched, and so does the `scan_project`
   Python function; the new `scan_project_report` is an addition, not a change
   (`src/lib.rs`, `src/walker.rs` are delivered as whole files).
2. Messages never contain the absolute scan root (it is replaced by `.`), because a
   report is often shared with an AI or a colleague and an absolute path names the
   user and the machine. Only five messages are kept, so a million unreadable files do
   not become a million strings.
3. Python: `rust_bridge.scan_project_report(root)` returns `(records, ScanProblems)`
   from the compiled core, or from the fallback (`os.walk(onerror=...)` and the
   per-file `stat`). If the compiled core is an **older** build without the new
   function (the stale `_core*.so` trap, AGENTS.md 5.69/5.70), it falls back to the
   old function and reports nothing instead of crashing.
4. `cli.py` calls it once, prints a warning when anything was skipped, and carries
   `ReportData.scan_skipped` and `scan_skipped_samples`. The markdown report shows a
   "Scan warning" under the statistics; the JSON keys appear only when something was
   skipped (the file's rule: an ordinary run does not gain keys).
5. Tests: four Rust tests (clean tree, the sample cap, the root redaction, and a real
   unreadable directory on Unix) and `tests/test_scan_problems.py`.

**Not done here.** `git_global`: the Rust walker honours the user's global gitignore
(`core.excludesFile`), so the same project can scan to different file lists on two
machines. Recommended default `false`; it changes which files appear, so it waits for
the owner's decision (D2). A separate `--git-global` override would then be added.

**Non-goals (recorded).** Retrying unreadable paths; a flag that makes unreadable
paths an error; reporting hashing/line-count failures of a file that was readable
(they are races on a file already stat'd).

**Verification.** The Python tests and the whole suite in the sandbox; the markdown
and JSON renderers; the stale-core fallback. The Rust code was **not compiled** here
(no `cargo`): `cargo fmt`, `cargo clippy --all-targets --all-features -- -D warnings`
and `cargo test` run in the delivery's check chain and again in CI. The unreadable
directory tests skip themselves when the account can read anything (root), which is
the owner's phone, so CI is the real test of that scenario.

**Lessons.** A silent `.ok()` is a decision to lie by omission. When a tool's output
is shared, even its error messages are data to scrub.

**D2 decided (2026-10-20): the Rust walker no longer applies the user's global
gitignore.** The owner chose "the project's own ignore files only" so that one
project gives the same file list, and the same report, on every machine.
`git_global(false)` is the whole code change; the Python fallback never applied a
global ignore. Still applied, on purpose: the project's `.gitignore` files,
`.git/info/exclude` (it belongs to the clone) and the ignore files of parent
directories (git's own rule when a subdirectory of a repository is scanned). A new
Rust test builds a global ignore file under `XDG_CONFIG_HOME` and checks that a
file it names is still listed; it proves the change only where the global ignore
comes from that default location, as on CI. No `--git-global` option was added.

### 5.75 — Audit remediation R8b: a benchmark for the Rust core (2026-10-23)

**Finding B7.** The Rust core is about 900 lines and the dominant cost of a scan is
the external tools, yet nothing in this repository measured what the core buys.
**C5.** `.benchmarks/` was not in `.gitignore`.

**Done.** `scripts/bench_scan.py` builds a deterministic synthetic tree (10000
small files in nested directories plus `node_modules`, `target` and `__pycache__`
with files that must be pruned), and times `_core.scan_project` against
`rust_bridge._pure_python_scan`: one warm-up, then N runs (default 5), median
reported. Each engine runs in its own child process so peak memory
(`ru_maxrss`, converted to MiB) is not shared. `--path DIR` adds real projects,
`--json` prints machine-readable output. The table also says whether both engines
listed the same files; on a project with a `.gitignore` they may differ on
purpose, because the Rust walker honours the project's own ignore files and the
fallback does not. `tests/test_bench_scan.py` covers the tree builder, the median,
the comparison, the table and the Python engine, and checks `.benchmarks/`.

**Decision D3 is NOT taken here.** The Rust core is unchanged. The owner runs
`python3 scripts/bench_scan.py` and `python3 scripts/bench_scan.py --path .` on both
devices and pastes the output; the numbers are recorded below and D3 is decided on
them.

**Recorded non-gap (C4).** Both READMEs already lead with `pipx install sarand-cli`
and describe `install.sh` as the source route; nothing to change.

**Not done (R8c).** The SPDX license form needs a verified maturin and a passing
`twine check --strict`; the MSRV needs the `rust_version` of `pyo3` from the
owner's `cargo metadata`.

**Verification.** The tests and the script's Python engine ran in the sandbox. The
Rust engine path was **not** run there (no `cargo`); the owner's run is its first
real execution, so a failure on that side is expected to be small and local.

**Lesson (CI run 399).** `mypy .` failed only on Windows: `resource.getrusage`
does not exist there, and `try/except ImportError` does not tell mypy that. Guard
platform-specific stdlib calls with `if sys.platform == "win32": return`.

**Benchmark numbers.** Pending the owner's runs.

### 5.76 — Audit remediation R8c: SPDX license and Rust MSRV (2026-10-23)

**Finding C3.** `license = { text = "MIT" }` is the legacy form and `Cargo.toml`
had no `rust-version`.

**Facts from the owner's machine (not guessed).** `maturin 1.14.1`; `cargo
metadata` gave `rust_version` 1.88 for `ignore 0.4.33`, 1.83 for `pyo3 0.29.2`
and 1.80 for `rayon 1.12.0` (`hex` and `sha2` declare none). The minimum is the
largest of them, **1.88**, set by `ignore`.

**Done.** `pyproject.toml`: `license = "MIT"` plus `license-files = ["LICENSE"]`;
the `License ::` classifier is removed (PEP 639 does not allow both); the build
floor is `maturin>=1.14.1,<2.0`, the one version that was actually run, because
the exact version that first supported PEP 639 was not verified here. `Cargo.toml`:
`rust-version = "1.88"`. CI: a separate `msrv` job (`dtolnay/rust-toolchain@stable` with `toolchain: "1.88"`,
`cargo check --locked --all-targets`); `tests/test_package_metadata.py` fails if the
declared number and the job's toolchain ever drift apart. Both READMEs name the
minimum version. `twine check --strict` already runs in every `quality` job on
the wheel and the sdist, so it is the proof for the metadata change.

**Risk.** The `msrv` job is new and was not run before the push. It checks the
whole `Cargo.lock`, while only five crates were inspected; if it fails, its log
names the crate that needs a newer Rust and 1.88 is raised to that fact.

**Lesson (first R8c attempt).** The job first used `dtolnay/rust-toolchain@1.88`;
`tests/test_action_pins.py` rejected that ref. It would also have lost the
version once `scripts/pin_actions.py --write` replaces refs with SHAs, because
that action reads the toolchain from the ref name. Give the version as
`with: toolchain:` and keep the ref `@stable`.

### 5.77 — Audit remediation R8d: docs/BACKLOG.md passes markdownlint (2026-10-23)

**Finding.** `docs/BACKLOG.md` was the last guide file excluded from the `static`
job: 37 errors, almost all MD029, because it is plain text that Markdown misreads
(every numbered section title is a one-item ordered list, the Health Score table
became one giant setext heading, and the item template holds a real heading).

**Done, by anchored rules, no word changed.** The first line became `# `; the 24
section titles (recognised by the `---` plus blank line above them) became `## N.
Title`, so the numbers the text refers to ("items 8 and 11") are unchanged; the
score table and the item template are fenced as `text`; the one list that
continues its numbering across P0/P1/P2/P3 groups (section 22, a ranking) sits
between `markdownlint-disable/enable MD029` comments instead of being
renumbered. The apply script removes its own additions from the result and
requires the original text back, byte for byte, before it writes anything.
`docs/BACKLOG.md` left `.markdownlintignore`; `docs/history/` stays there.

### 5.78 — Audit remediation R8e: make the Rust toolchain explicit before pinning (2026-10-23)

**Why.** `dtolnay/rust-toolchain` chooses the toolchain from the ref it is called
with (`@stable`, `@1.88`). `scripts/pin_actions.py --write` replaces every ref with
a commit SHA, after which that action has no ref to read and fails unless the
`toolchain` input is given. Three steps (`audit.yml` cargo-deny job and two in
`ci.yml`) relied on the ref alone; the `msrv` job already used the input.

**Done.** `toolchain: stable` added to those three steps and
`tests/test_rust_toolchain_inputs.py` requires the input on every step that uses
the action, so the pinning round cannot break CI and a future step cannot forget
it. No behaviour changes before pinning: `@stable` plus `toolchain: stable` is the
same toolchain.

### 5.79 — Audit remediation R8f: every workflow action is pinned to a SHA (2026-10-23)

**Done.** `scripts/pin_actions.py --write` rewrote every `uses:` in `audit.yml`,
`ci.yml` and `release.yml` to `owner/repo@<40-hex commit> # <old ref>` (34
references; the SHAs came from the GitHub API, annotated tags peeled to the
commit). `ENFORCE_PINNED = True` in `tests/test_action_pins.py` now fails any
workflow that brings back a tag or branch.

The one test that asserted the gitleaks tag (`test_ci_workflows.py`) now checks the
action name only, because the tag moved into the trailing comment. The same
was needed in `tests/test_release_workflow.py`, which required the exact ref
`pypa/gh-action-pypi-publish@release/v1`; the offline simulation before the
round ran only four test files and missed it, the full suite found it.

**Two things to know.** Branch refs (`dtolnay/rust-toolchain@stable`,
`pypa/gh-action-pypi-publish@release/v1`) were pinned to the branch tip of that
day, and Dependabot cannot tell from the `# stable` or `# release/v1` comment
when a newer commit exists; those two are refreshed by hand with
`pin_actions.py` after removing the SHA (or when a security notice arrives).
`release.yml` is not run by CI; the pins point at the same commits the tags did
that day, so it behaves as before, and the first tagged release is its real test.

### 5.80 — Audit remediation R9a: musllinux wheels (D4) and a documentation sync (2026-10-24)

**Decision D4** (musllinux wheels or a pure-Python wheel; feasibility unknown):
musllinux wheels, because the workflow already builds with `maturin-action` and
only needed `manylinux: musllinux_1_2` for the two Linux targets. A pure-Python
wheel was not pursued: it would be a second build of the same distribution name,
and the musllinux wheels remove the main reason for it (Alpine users compiling
Rust from the source distribution). D1 (Python 3.10) was closed earlier by the
3.11 floor of v0.7.0.

**Done.** `release.yml`: two matrix entries (`musllinux-x86_64`,
`musllinux-aarch64`), a `smoke-musl` job that installs each wheel with the
`python:3.12-alpine` image's pip and runs `sarand --version`, the compiled core
import and (on a tag) the version check, and both publish jobs now `need` it.
No new action was added (it uses `docker run`), so there is no new SHA to pin.
`tests/test_musllinux_release.py` keeps this shape;
`tests/test_release_workflow.py` now expects seven platforms and the extra job.
`docs/PUBLISHING.md`, the CHANGELOG (`Unreleased`) and `BACKLOG_STATUS.md` say so;
`BACKLOG_STATUS.md` also stops saying that the latest release is v0.6.19 and that a
GitHub Release is still open (v0.7.0 created one with five wheels, the sdist and
`SHA256SUMS`).

**Not verified.** The workflow runs only on a tag or by hand, so CI on the
push cannot exercise it. The first proof is the manual dry run
(`gh workflow run release.yml --ref main -f publish_to_testpypi=true`): the two
musllinux builds, the Alpine smoke test and the TestPyPI upload. Do not tag a
release before that run is green.

### 5.81 — Round R10a: plugin hardening (item 11) and the filelock range (2026-10-24)

**filelock.** The owner ran the whole suite with `filelock>=4,<5` installed over
the project venv: 1236 passed. The range is now `>=3.14,<5`. (My first command
for that test conflicted with the editable install's own pin and proved nothing;
the second, with `--no-deps`, is the evidence.)

**Plugin time limit (confirmed gap).** `PluginAnalyzer._call` awaited the
plugin with no limit; the module docstring said so. Each phase now runs under
`asyncio.timeout(PLUGIN_PHASE_TIMEOUT)` (`LONG_CMD_TIMEOUT` plus a minute, so a
plugin that legitimately runs a long command is not cut short). On expiry the
phase is cancelled (`run_cmd_async` already kills its process group on
cancellation) and one skipped result says `did not finish within N s and was
cancelled`. A `TimeoutError` raised by the plugin itself is told apart with
`scope.expired()` and reported as an ordinary failure. Limit: blocking code
that never awaits cannot be interrupted by asyncio; docs/PLUGINS.md says so
and points to `to_thread`.

**Doctor listing.** `registry._load_plugins()` is now the single loader (same
log lines as before, plus one `PluginStatus` per entry point), `discover_analyzers`
uses it, `plugin_statuses()` exposes the statuses and `--doctor` prints a Plugins
panel. Plugin-supplied text is escaped before it reaches rich.

**Sandboxing: recorded non-goal.** A plugin is Python code in sarand's own
process with the user's rights; nothing in-process confines it. A real boundary
needs plugins in a separate process with reduced rights, which means a new plugin
API version; not worth building before a plugin author asks for it.
The marketplace stays out of scope.

**Not verified here.** The sandbox has no `rich`, so the doctor panel was run
through a stub and by reading; the real rendering is checked by the owner's full
`pytest` (`tests/test_doctor_plugins.py`).

### 5.82 — Round R10d: the real PDF engines in CI (item 12) (2026-10-24)

**Gap.** Every PDF test used a fake engine, and the one real-engine test
(`test_new_renderers.py`) skipped silently because CI had no engine installed;
so `renderers/pdf.py` had never been run against WeasyPrint or wkhtmltopdf in
CI, and "Debian's wkhtmltopdf may need an X server" stayed a rumour.

**Done.** `tests/test_pdf_real_engines.py` runs the real engines named in
`SARAND_REAL_PDF_ENGINES` (skipped visibly otherwise) and a guard that the CI job
keeps WeasyPrint a hard check. The CI job `pdf` installs Pango and WeasyPrint
(must pass), then wkhtmltopdf with and without `xvfb-run` (reported only, with
`continue-on-error`), and writes the four outcomes into the job summary.

**Next.** The first run decides: record the facts in `renderers/pdf.py` and
`BACKLOG_STATUS.md`, and add `xvfb-run` handling or a clearer hint if wkhtmltopdf
needs an X server. Nothing was changed in the renderer itself on a guess.

### 5.83 — Round R10d2: what the first PDF run proved (2026-10-25)

**Facts** (CI run 40110801760, ubuntu-24.04). WeasyPrint rendered a real PDF.
wkhtmltopdf 0.12.6-2build2 installed from the Ubuntu archive and rendered one
without an X server and again under `xvfb-run` (3 tests passed each time). The
worry that Debian's wkhtmltopdf needs an X server therefore does not hold for the
Ubuntu 24.04 build; Debian itself, Kali, Termux and Android were not tested.

**Changed.** Both engines are now hard checks in the `pdf` job and the xvfb step is
gone. Lesson about the first version: a step with `continue-on-error` shows a green
tick in `gh run watch` even when it failed (`conclusion` is success, `outcome` is
failure) and the job summary text is not shown by `gh`; the facts had to be read from
the step log. The summary step was removed along with the information-only steps.

### 5.84 — Design record: Quick Context L2/L3/L4 and the plan for the rest of the product backlog (2026-10-25)

No code changed. The owner asked for every remaining product item, even the ones
marked out of scope, and for the design of Quick Context to be as good and as fast
as possible; this section records what was decided so it cannot be forgotten.

**Quick Context.** Full design in `docs/QUICK_CONTEXT_DESIGN.md`, decisions
D-QC1 to D-QC7, an outside review dispositioned point by point, three rounds
R11a, R11b, R11c with acceptance criteria, thresholds deliberately left to be set
from evidence. Findings that shaped it: the report has no import graph, no
file/line on `Issue` and no per-file line counts; `included_files` already holds
every exclusion, so L4 uses it as its only universe; `scan_line` in
`core/secrets.py` can be reused to re-check snippets.

**The rest of the product backlog (BACKLOG_STATUS items), with the reasons found
by reading the code.**

- Item 5 (`kubeconform`, `helm template`): the Kubernetes analyzer states two
  rules in its docstring (5.60): no check that needs the network, and a rendered
  `Secret` must never be captured. `kubeconform` downloads schemas by default and
  `helm template` prints Secrets. So: opt-in only, run when a local schema
  directory is configured, render with `--output-dir` into a temporary directory
  that is deleted, never on by default.
- Item 12 (PDF): done in 5.82 and 5.83.
- Item 11 (plugins): done in 5.81; sandboxing is a recorded non-goal.
- Item 13: `hadolint` already runs on Dockerfiles; the new part is
  `docker compose config`. `make` stays out unless an explicit opt-in flag, because
  it executes project code (the Makefile analyzer's decision is that `make` is
  never run on purpose).
- Item 1 (Nx and Turborepo task graphs): design first, as a separate round.
- Item 14 (memory profiling): not done, by its own rule (only if a real report
  names a problem).
- Packaging (Docker, Homebrew, deb, rpm, a standalone binary): the roadmap file
  says to build them only when a real need shows up; the owner overrode that, so
  they come **last**, one target per round, Docker first, each verified by a
  real build in CI. Homebrew needs a separate tap repository; deb and rpm are low
  value for a Python tool with a Rust core that `pipx` already covers. This is
  recorded so the decision can be revisited with the facts in hand.
- Item 9 (AUR publication): needs `makepkg` in a clean Arch chroot and an AUR
  account, so it is the owner's step.

**Process lessons kept for the next rounds.** The sandbox has no `mypy`, `ruff` or
`rich`, so type-annotate test helpers exactly and do not use `object` plus
attribute access. A `continue-on-error` step shows a green tick in `gh run watch`;
read its log. When a script anchors on the end of a block, search the end after
the start, because other jobs end the same way. Run every test file that reads
workflows after a workflow change, not a hand-picked few.
