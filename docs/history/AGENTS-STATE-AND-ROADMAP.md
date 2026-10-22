# AGENTS history: state snapshot and roadmap

Moved verbatim out of `AGENTS.md` (round R8a). Nothing was reworded; some
references inside still say "this file" or "section 5.NN" and mean the history
of the project as a whole.

Section 6 (current state, a snapshot of 2026-10) and section 8 (phases A to H).

---

## 6. Current state (as of this commit)

| Area | Status |
|---|---|
| Rust core (walker/linecount/hasher/tree + PyO3 bindings) | **Compiles and runs** (`maturin develop --release`, verified on aarch64/Termux; `PyDict::new_bound` fix applied for the pyo3 0.22 pin — see §4.6) |
| Pure-Python fallback | Implemented and tested; produces identical report structure |
| Language analyzers | Python, Rust, Go, Node.js — all gated on real markers (§4.3) |
| Async concurrent test/quality execution | Implemented (`asyncio.gather`) |
| Single shared filesystem scan | Implemented — tree/stats/essential-files/TODOs all read from one `scan_project()` call |
| Persisted output-dir config | Implemented (`sarand --set-output-dir`, OS-appropriate path) |
| Markdown / JSON / text renderers | Implemented |
| Health score engine | Implemented (tests/quality/security/git/code/tooling breakdown) |
| Automated test suite (pytest) | **Implemented and confirmed — 565 tests passing on-device** (`pytest -q`, 2026-09-20, after the §5.12 follow-up on top of v0.5.0; the §5.13 round adds 9 more, confirmed 574; the README round adds 4 more, confirmed 578; the memory-reporting round adds 12, confirmed 590; the hang-fix round adds 1, confirmed 591; the license-policy round adds 26, confirmed only up to the ruff step (its `ruff check` stopped the chain); the Windows-portability round adds 1 more, confirmed 618; the `/tmp` guard round adds 1, confirmed 619; the assembly round adds 34, confirmed 653 with all five CI jobs green; the §5.18 round adds 43, confirmed 696 with `ruff`/`mypy` clean; the doctor-visibility fix adds 2, confirmed 698; the `install.sh` fix adds 6, confirmed 707; the §5.20 round (report-size guard, health-check transparency, installation diagnostics, README rewrite) adds 47, expected 754 — re-confirm), covering every analyzer/renderer/core module added through §5. CI green on all five jobs (Ubuntu x3 on Python 3.10/3.12/3.14, macOS, Windows) at commit `79cfe3d`; re-confirm after each push before tagging (see the release rule in the 5.13 section). `pytest` runs everything by default (no `addopts` filtering, §4.8); use `pytest -m "not slow_external"` for a fast local-iteration subset. Two lasting lessons from this project's test-bug history: (1) don't hardcode a "tool not installed" assumption in a test — branch on `shutil.which(...)` (Phase B); (2) don't fake a platform-specific mechanism (env var, well-known dir) — monkeypatch the function that reads it directly, or the test only really runs on whichever OS wrote it (Phase G) |
| `--security` checks | **Implemented and tested** — per-language `run_security` (pip-audit + bandit / cargo-audit / govulncheck / npm audit), all gated on real markers + toolchain presence, run concurrently via `run_security_concurrently` |
| Secrets exclusion from reports (§4.10) | **Implemented and tested** — filename-based exclusion (`.pem`, `.env*`, `id_rsa`, service-account JSON, ...) always on; content-based regex scan (`core/secrets.py`) always on; any file with a content-level finding is moved out of the source-embed list entirely (`exclude_flagged_files`), not just flagged — regression-tested end-to-end (`tests/test_secrets.py::test_end_to_end_flagged_file_content_never_reaches_markdown_report`) |
| `sarand doctor` command (§4.11) | **Implemented, tested, and redesigned for readability** — `sarand --doctor` (flag, not a subcommand — see Phase C note below): checks Python version (critical), Rust core, persisted config, and 15 tool binaries, now grouped into two `rich.table.Table`s (Core, then per-language tools) inside `rich.panel.Panel`s instead of a flat list — a maintainer read the flat version as "many things sarand doesn't support" rather than "optional external tools you can install if you use that language"; each row now states explicitly what it's used for (e.g. "--security", "Gradle & Android projects"). Real `rich` isn't available in the build sandbox, so the visual result is unverified by the assistant — confirm it looks right on-device |
| HTML dashboard renderer | **Implemented and tested** — `renderers/html.py`, self-contained single file (inline CSS, no external assets), dark-mode, collapsible `<details>` sections, properly HTML-escaped |
| PDF / SARIF renderers | **Implemented and tested** — `renderers/sarif.py` (valid SARIF 2.1.0 JSON: secret findings as located errors, TODOs as located notes, tool warnings/errors unlocated). `renderers/pdf.py` shells out to an installed `wkhtmltopdf`/`weasyprint` on the HTML renderer's output rather than adding a heavy Python PDF dependency — gates cleanly with a fix-it message if neither is present. Verified end-to-end: real PDF produced (`%PDF-1.4` magic bytes, 42 KB) via `wkhtmltopdf` |
| Incremental scan cache | **Implemented and tested** — opt-in via `--cache` (deliberately NOT default; see the rationale in Phase E notes below and §4.8). Scoped to the Python side only: skips re-scanning TODOs/secrets in files whose content hash is unchanged since the last `--cache` run for the same project; does not change how `walker.rs` itself works. Cache lives under the *output* dir (`.sarand-cache/`), never inside the scanned project. Auto-invalidates if the detection rules themselves change (`rules_fingerprint`). `--clear-cache` wipes it. Verified end-to-end on a real 3-run sequence: cold run, warm run (byte-identical report, confirmed via matching SHA256), and a changed-file run that correctly found a newly added FIXME marker while still skipping the untouched file |
| Additional language analyzers (C/C++, Java/Kotlin, Android, Zig, Dart, Ruby, PHP, Lua, Swift, C#, TypeScript, CSS, SQL, Kotlin, Shell, YAML, JSON, TOML, XML, R, Perl, Julia, Objective-C, Groovy, PowerShell, Nix) | **All implemented and tested — 40 analyzers total (Markdown added in the P0 round, Assembly in §5.17, eight more in §5.18).** C/C++, Java/Kotlin, Android landed first (Phase C); Lua, Ruby, PHP, Dart/Flutter, TypeScript, CSS, Zig, Swift, SQL, Kotlin, C#, Shell, and the YAML/JSON/TOML/XML format analyzers (§5.4) landed in the first post-§4 round; R, Perl, Julia, Objective-C, Groovy, PowerShell, and Nix landed in a second round (§5.8) — see §5 for the conventions established along the way (bundler-wrapped-tool pattern, complementary-match analyzers, honest-empty precedent, format-analyzer category). Full roster in §5.6/§5.9 |
| Packaging (pipx, Docker, AUR, Homebrew, deb/rpm, standalone binary) | **pipx: implemented and confirmed** — `pipx install ~/sarand` builds the Rust extension inside pipx's isolated venv and installs cleanly; `sarand --doctor` confirmed "Rust core: compiled and loaded" post-install, no manual venv/PATH steps needed. `install.sh` added (§4.13) so upgrading an existing pipx install actually picks up new code — a raw `pipx install` over a stale copy silently doesn't, since pipx installs aren't editable by default. LICENSE (MIT) and full `pyproject.toml` metadata (classifiers, keywords) added. **AUR: `pkgs/aur/PKGBUILD` written**, not yet verified with a real `makepkg -si` in a clean chroot (see Phase F, still open). Docker/Homebrew/deb/rpm/binary: not started |
| Report replacement (§4.13) | **Implemented and tested** — `cli.py::remove_previous_report` explicitly checks for, removes, and announces a previous report (+ its `.sha256`) at the exact output path before writing a new one, for the same "check, remove, announce, create fresh" reason as `install.sh` |
| `--full` flag | **Implemented and tested — completeness gaps found and fixed 2026-09-18.** Forces `--quality`+`--security` on and removes the file-size/tree-depth/tree-entry truncation limits (raised to effectively-unlimited sentinel values), while still letting an explicit `--max-depth`/`--max-entries`/`--max-file-size` win over `--full`'s own defaults. An external audit of a real `--full` report found this description was not the whole truth: the **rendering layer** ignored `--full` entirely — a *passing* tool's output was always cut to an 80-line tail (raw output only shown on FAIL), issue lists capped at 500 rows and TODOs at 100 regardless of `--full`, and **`--format json` never embedded source code at all** (`include_source` was accepted in the signature and silently never read — the one format most likely to be piped straight into another AI's context had zero source, full stop). All four fixed: `config.full` is now stored on `SarandConfig` and threaded into every renderer as `full_output`; JSON gained a real `source_files: [{path, size, content}]` array; markdown/html now show a passing tool's full raw output and uncap issues/TODOs under `--full`. See §5.10 for what's still open (git history/contributor/hotspot depth) |
| `scripts/paste_chunks.py` | **Rewritten from a maintainer-supplied script and merged in** — chunked, resumable paste helper for chat UIs without file upload (e.g. pasting a `sarand --full` report into ChatGPT). Generalized from a hardcoded README.md/BiMarz-specific tool to work on any file, with per-source-file state namespacing (mirrors `core/cache.py`'s per-project namespacing). Fixed three real bugs found on review (dead `initialize` param, a shallow-copy rollback that only worked by accident, a UX trap where re-running with no flags mid-block silently repeated chunk 0 instead of continuing) — see the module's own docstring for details. Added OSC52 terminal-escape-sequence clipboard support as the primary copy mechanism, since it is the *only* clipboard method that works at all on the maintainer's actual hardware (non-rooted Android, Termux/Kali NetHunter proot, no X11/Wayland session) — `xclip`/`xsel`/`wl-copy` have no display server to talk to there. `OSC52_MAX_BYTES = 6000` applies to the raw text *before* base64 encoding (an empirically-tested ceiling on that hardware/terminal combination, not the final escape-sequence length) |
| CI | **Was green on all three OSes at run #3; NOT confirmed green since run #44 (see §5.13/§5.14) — re-confirm after the latest push** — public at `github.com/msoleimani62/sarand`. Two real issues found and fixed across the first three runs (see Phase G notes): a CI-infra bug (`maturin develop` needs a virtualenv CI runners don't have) and a genuine cross-platform test-isolation bug (two tests relied on `XDG_CONFIG_HOME`, which the product code only honors on Linux by design — the product code was correct, the tests weren't platform-independent). Run #3: `ubuntu-latest`, `macos-latest`, `windows-latest` all passed |

---
| pipx install robustness | **A real pipx bug hit and worked around** — pipx's own internal per-venv metadata can get corrupted independently of anything sarand does ("Unknown metadata version N. Perhaps it was installed with a later version of pipx" — a known upstream issue, <https://github.com/pypa/pipx/issues/1619>). When it happens, `pipx list` silently omits the corrupted entry AND `pipx uninstall` fails the same way trying to read it, so `install.sh` now falls back to removing `~/.local/share/pipx/venvs/sarand` directly if either the venv is present-but-untracked or `pipx uninstall` itself fails |
| Android/Kotlin priority | **Implemented ahead of the general "more languages" backlog**, per an explicit maintainer request (upcoming Android tooling work). `.kts`/`.xml`/`.gradle`/`.properties` added to essential extensions (Kotlin build scripts, manifests, layouts, config); `local.properties`/`*.jks`/`*.keystore`/`google-services.json` added to the secret-filename exclusion list (§4.10) — Android projects commonly put SDK paths and sometimes signing credentials in exactly those files. `discovery/android.py` holds the shared detection logic (`is_android_project`) so both `discovery/project_detector.py` (report's top-line language label) and `analyzers/android_analyzer.py` use the same signal, in the dependency direction the architecture diagram implies (analyzers depend on discovery, not the reverse) |

---

## 8. Roadmap (in priority order)

### Phase A — Test suite ✅ done, confirmed with real `pytest`

`tests/` exists with pytest-compatible coverage of every module marked
"Implemented" in §6. Next concrete step: maintainer runs `pytest -v` for
real and reports the output back. **Confirmed** — 42/42 passed, including the Rust-vs-fallback cross-check (`test_rust_and_python_paths_agree_on_fixture_project`).

### Phase B — Security checks + secrets exclusion ✅ done

Implemented exactly as scoped: `LanguageAnalyzer.run_security` per
language (pip-audit/bandit, cargo-audit, govulncheck, npm audit), wired
behind `--security`, plus §4.10's filename- and content-based secret
exclusion (both always-on, not gated behind any flag). One design
refinement made during implementation, worth noting for future readers:
a content-level secret finding now removes that file from source
embedding entirely (`core/secrets.py::exclude_flagged_files`) rather than
just recording a warning next to an unredacted dump of the same file —
the first version of this phase had exactly that gap, caught by writing
the end-to-end regression test before declaring it done (§4.8 in
practice).

### Phase C — `sarand doctor` + more language analyzers ✅ done (Lua/Ruby/PHP/Dart added later; Zig/Swift/C# still deferred)

- `sarand doctor` implemented as a **flag** (`sarand --doctor`), not a
  subcommand — the CLI is argparse-flag-based throughout (see
  `--set-output-dir` for the same early-exit pattern), and introducing
  subcommands would be a separate, larger CLI restructuring not scoped
  into this phase. Checks Python version (the one critical check), Rust
  core availability, the persisted config location, and 13 per-language
  tool binaries — every failing check prints a fix-it command, nothing
  fails silently (§4.11).
- Added `analyzers/cpp_analyzer.py` (CMakeLists.txt → `ctest` if a
  configured build dir exists, `clang-format --dry-run` if configured,
  `cppcheck` for security) and `analyzers/java_analyzer.py` (pom.xml or
  build.gradle(.kts) → `mvn`/`gradle`, preferring a project's own
  `./gradlew` wrapper over a system Gradle). Both deliberately never
  invoke `cmake configure`/`cmake --build`/a full Gradle sync themselves
  — see the "heavy dependency" warning rule in §3; they only run
  against a build the user already configured.
- `analyzers/lua_analyzer.py` added later (rockspec/init.lua/main.lua,
  `busted` for tests, `luacheck` for quality, no standard security-audit
  tool for Lua so `run_security` returns `[]`).
- `analyzers/ruby_analyzer.py`, `analyzers/php_analyzer.py`,
  `analyzers/dart_analyzer.py` added later:
  - Ruby: `Gemfile`/`*.gemspec` → `bundle exec rspec` (or `bundle exec
    rake test` if no `spec/` but a `Rakefile` exists) for tests,
    `bundle exec rubocop` for quality, `bundle exec bundler-audit` for
    security. Everything goes through `bundle exec` deliberately, never
    a bare global binary, so the `Gemfile.lock`-pinned tool versions are
    what actually runs.
  - PHP: `composer.json` → PHPUnit for tests, PHPStan for quality,
    `composer audit` for security. Prefers a project-local
    `vendor/bin/<tool>` over a global binary of the same name — a
    globally-installed PHPUnit/PHPStan can easily be a different major
    version than what the project's own `composer.json` expects.
  - Dart/Flutter: `pubspec.yaml` → `dart test`/`dart analyze`, or
    `flutter test`/`flutter analyze` instead when the project actually
    declares a `flutter:` dependency (checked by content, not just
    whether the `flutter` binary happens to be installed on the
    machine). No `run_security`: no broadly standard vulnerability-audit
    tool exists yet for this ecosystem (as of this writing) — returning
    `[]` here is honest about that rather than reaching for something
    that doesn't fit, same precedent as Lua.
- Zig, Swift, C#, TypeScript, CSS, SQL, Kotlin, Shell, and the
  YAML/JSON/TOML/XML format analyzers were added in later rounds —
  see §5 for the conventions established along the way. Phase C is
  now fully closed.

### Phase D — Additional renderers ✅ done

- `renderers/html.py`: dashboard-style HTML report (dark mode, collapsible
  sections). Reuses `ReportData` as-is — no data-model changes needed.
- `renderers/sarif.py`: valid SARIF 2.1.0, following the `Renderer`
  protocol exactly like every other text-based renderer.
- `renderers/pdf.py`: **does not** implement the `Renderer` protocol —
  PDF is binary, not a string. It shells out to an installed
  `wkhtmltopdf`/`weasyprint` against the HTML renderer's own output
  (reuse, not reinvention) via `render_to_file(data, output_path)`, and
  `cli.py` special-cases `"pdf"` in its output-writing branch for exactly
  this reason. This was a deliberate deviation from "each renderer
  implements the same `render() -> str` signature" — forcing PDF into
  that shape would have meant either a heavy new Python PDF dependency
  (risky to compile on Termux, see §3) or awkwardly base64-encoding
  binary bytes through a string return. Document any future
  protocol-breaking renderer the same way: state why, right here.

### Phase E — Incremental scan cache ✅ done, scoped down from the original plan

Implemented as `core/cache.py`, opt-in via `--cache`. Deliberately
narrower than the original plan of "skip re-hashing/re-counting
unchanged files" at the `walker.rs` level: making the Rust walker itself
cache-aware means it has to accept and consult a cache map from Python,
which is a real Rust-code change that can't be compile-verified without
a local toolchain (§4.8) — too risky to ship unverified after the
`PyDict::new` lesson (§4.6). Instead this phase stays entirely on the
Python side of the `rust_bridge.py` boundary: it reuses the
`content_hash` Rust/the fallback already compute for free, and skips the
*Python-side* re-scan of file content for TODOs and secrets when a
file's hash is unchanged. `walker.rs` still processes every file on
every run — which is fine, since Rust's own pass was never the
bottleneck this phase was meant to address; the redundant *Python*
regex scanning over full file content (once for TODOs, once for
secrets, on every included file, every run) was.

Opt-in, not default, for the same reason `slow_external` pytest tests
are opt-in-to-skip rather than opt-in-to-run: a stale-cache bug's
failure mode is a silently wrong report (a real finding hidden because
the cache claimed "unchanged"), and the safe direction to fail is doing
more work than necessary, not less. A `rules_fingerprint` (hash of every
TODO/secret pattern) auto-invalidates the whole cache if detection logic
ever changes, so a future Phase-B-style pattern addition can't silently
miss findings in files a stale cache still thinks are "clean."

If a *deeper* cache (skipping Rust-side hash/linecount work too) is
ever wanted, that's a distinct, larger follow-up requiring an actual
Rust change and real compile verification — don't conflate the two.

### Phase F — Packaging

**pipx: done and confirmed on-device.** `pipx install ~/sarand` builds
the Rust extension inside pipx's own isolated environment and installs
cleanly — confirmed via `sarand --doctor` reporting "Rust core:
compiled and loaded" post-install, with no manual venv activation or
PATH editing needed. `LICENSE` (MIT) added, `pyproject.toml` gained
classifiers/keywords, README's install section now leads with pipx
specifically *because* this project's history includes several rounds
of manual venv-activation/PATH confusion that pipx sidesteps entirely.

**AUR: PKGBUILD written, not yet submitted/confirmed by a real
`makepkg` build.** `pkgs/aur/PKGBUILD` builds from the GitHub release
tarball (`v$pkgver`) via the standard Arch PEP517 pattern
(`python -m build --wheel --no-isolation` + `python -m installer`),
with `rust`/`python-maturin` as makedepends so the PyO3 extension
compiles the same way `pipx install` already does. `check()` runs the
real pytest suite (minus the Rust-vs-fallback parity test, which
needs the compiled `._core` module installed into the *same*
environment pytest runs in, not just built as a wheel) — everything
else already tolerates missing optional tools by design (Phase A/C),
so this is a meaningful check, not a rubber stamp. Still open before
this counts as done: run an actual `makepkg -si` in a clean chroot
(`extra-x86_64-build` or similar) to catch anything only a real build
surfaces, regenerate `.SRCINFO` from that build
(`makepkg --printsrcinfo > .SRCINFO`, never hand-edited), confirm the
`sarand` name is free on aur.archlinux.org, then `git push` to the AUR
git remote.

**Reordering the remaining targets from the original plan:** the
original order was Docker → AUR → Homebrew → deb/rpm → binary. Nothing
in this project's actual usage (Android/Termux/Kali NetHunter phone +
Arch Linux laptop) involves Docker — there's no described workflow that
needs it, and running a container inside a Termux proot is its own can
of worms. AUR is directly useful (the maintainer runs Arch daily).
Remaining order once AUR is confirmed: Docker/Homebrew/deb/rpm/binary
only if a real need for them shows up later — don't build packaging
for platforms nobody described using, mirroring the same "don't
pre-build analyzers for languages nobody asked to scan" principle from
Phase C.

One packaging target per phase, verified working, before starting the
next -- this is the rule that kept Phase F from becoming "try to do 6
packaging systems in one pass and verify none of them."

### Phase G — CI ✅ done, confirmed green on all three OSes

The repo is now public at `github.com/msoleimani62/sarand`.

**Run #1 (CI infra)**: `maturin develop --release` requires an active
virtualenv (`VIRTUAL_ENV`, `CONDA_PREFIX`, or a `.venv` folder) to know
where to install into -- the maintainer's own machine always has one
(the pipx/dev-venv setup), but a fresh GitHub Actions runner does not.
Fixed by switching the workflow from `maturin develop` to `maturin
build --release --out dist` + `pip install dist/*.whl` -- `build` has
no virtualenv requirement, and installing that wheel covers both "the
code works" and "a release wheel actually builds" in one step. Also
added `defaults: run: shell: bash` so wheel-glob installs behave
identically across the OS matrix.

**Run #2 (real product-vs-test bug, worth remembering)**:
`ubuntu-latest` passed clean. `macos-latest` and `windows-latest` both
failed on `test_output_dir_uses_persisted_config_when_present` (and
`..._falls_back_to_default_when_nothing_set` was quietly relying on the
same shaky isolation). Root cause: the tests set `XDG_CONFIG_HOME` to
redirect where `get_config_dir()` looks -- but `get_config_dir()` only
honors that variable on Linux, by design (§ its own docstring: macOS
uses `~/Library/Application Support`, Windows uses `%APPDATA%`). **The
product code was correct the whole time**; the test's isolation
technique just wasn't cross-platform. This is exactly the kind of bug
CI exists to catch -- it had been silently passing locally (Linux-only
development environment) since the test was written. Fixed by
monkeypatching `sarand.userconfig.get_config_dir` directly (save the
original, replace with a lambda returning a temp path, restore in
`finally`) instead of the env var -- this isolates the test from every
platform's real config location at once, correctly, rather than only
happening to work on whichever OS wrote the test.

**Confirmed**: run #3 passed on all three OSes (Linux, macOS, Windows).
Phase G is done -- CI is now the scheduled safety net §4.8 talks about,
not just an aspiration.

### Phase H — `--full` git-history depth ⏸️ DEFERRED (kept as a reminder, not a priority)

**2026-09-19 update**: maintainer decision — this is *not* worth
building right now. `sarand`'s own projects (this one, `ramz`, `odl`,
etc.) are all solo-developer repos, so `contributors`
(`git shortlog -sn`) would always render as one name at 100% — a field
with zero signal for a single-author project. `total_commits`/
`full_log`/`hotspots` were judged individually reasonable but the
maintainer chose to prioritize language/tool coverage (P0 below)
instead for now. Kept here, unimplemented, specifically so a future
session doesn't have to rediscover the git-stats gap from scratch --
re-read this whole section before starting it, don't just skim the
one-line summary. Re-evaluate `contributors` specifically if this ever
gets picked up in a context with multiple committers; it stays
low-value for every project this maintainer currently runs it on.

Flagged directly by the maintainer (2026-09-18): `--full` is supposed to
be sarand's single most-complete artifact — full tests, full source,
full git statistics, built specifically to hand to an AI model without
the maintainer having to assemble any of it by hand. The rendering-layer
half of that promise was broken and is now fixed (§6's `--full` row,
§5.10). The **git-statistics half is still genuinely shallow** and is
the next thing to fix, before any further language analyzers or
supply-chain tooling (§5.10's P0–P3 list stays lower priority than this).

Current state (`scanners/git.py::collect_git_snapshot`), confirmed by
reading the module directly, not assumed:

- `git log --oneline -20` — **hardcoded to the last 20 commits only**,
  regardless of `--full`. No total commit count, no full history.
- No `git shortlog -sn` (or equivalent) — zero contributor/authorship
  stats anywhere in the report.
- `git diff --stat` only covers the current uncommitted working-tree
  diff — no per-file change-frequency / "hotspot" analysis (which files
  churn most across history is exactly the kind of signal an AI
  reviewer benefits from and a human wouldn't compute by hand).
- No repo age / first-commit date, no branch count, no `.gitattributes`
  or submodule awareness.

Scoped plan for next session:

1. Extend `GitSnapshot` (`models/results.py`) with new fields: `total_commits`,
   `contributors: list[tuple[str, int]]` (name, commit count, via
   `git shortlog -sn --no-merges`), `full_log: str | None` (only populated
   under `--full` — normal runs keep the existing `-20` summary to stay
   fast and readable), `hotspots: list[tuple[str, int]]` (path, times
   changed, via `git log --format= --name-only | sort | uniq -c | sort -rn`,
   capped like everything else *except* under `--full`), `first_commit_date`.
2. Every new call joins the existing `asyncio.gather` in
   `collect_git_snapshot` (§4.7 — independent commands, run concurrently,
   not appended sequentially).
3. Thread `full: bool` into `collect_git_snapshot(root, *, full: bool = False)`
   the same way renderers now take `full_output` (§5.10) — `full_log`/
   uncapped `hotspots` only computed when true, so a normal run's git
   step doesn't get slower for data most runs don't need.
4. Render in markdown/html/json — a `## Git history` section (commit
   count, top contributors, hotspot files) alongside the existing
   branch/commit/dirty/tags/stash block, not replacing it.
5. Regression test mirroring `tests/scanners`'s existing git test
   pattern (real repo in a tmpdir, `git init` + a few commits, assert
   `total_commits`/`contributors`/`hotspots` come back correct) — not
   yet written, since this whole phase is not yet started.

---
