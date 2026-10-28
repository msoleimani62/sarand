<!-- markdownlint-disable-file MD029 -->

# Backlog status (first pass complete) and remaining work

**The first pass of the engineering backlog is complete as of 2026-10-04.**
Every item of the "Engineering Backlog & Gap Audit" (`docs/BACKLOG.md`,
adopted 2026-09-22) got an evidence-first audit and a first-scope delivery,
or was recorded as out of scope with its reason. This file records the final
state and lists what is still open, so a new conversation does not have to
re-derive it. `AGENTS.md` keeps the full dated history of every round.

**`docs/BACKLOG.md` is deliberately kept for now.** The follow-ups below
(especially 1 to 3) continue items 8 and 11, and the Definition of Done for
those items lives only in that document. When follow-ups 1 to 4 are done (or
dropped with a reason recorded here), delete `docs/BACKLOG.md` and this file;
git history keeps both.

Latest release: **v0.7.0**. Every released version carries its own number
in `pyproject.toml`, `Cargo.toml`, `Cargo.lock` and the AUR `PKGBUILD`
(`scripts/release.py` and `tests/test_distribution.py` enforce it).

## Working rules (summary of docs/BACKLOG.md sections 2 to 5)

1. **Evidence first.** Audit the current code (and a realistic fixture or a
   real report) before changing anything; record what was CONFIRMED and what
   was only suspected. Do not "fix" a guess.
2. **Smallest scope that closes the gap.** Detection or representation before
   execution; never a universal solution first.
3. **Record non-goals.** What was deliberately not done, and why, goes in
   `AGENTS.md` with the round that decided it.
4. **A claim in the docs is a claim to verify.** Two README statements were
   wrong until tested on a real device (the no-Rust install).
5. **Tag only on a green commit.** CI catches what a newer local Python
   cannot (a py3.10 mypy error, a Windows path bug).

## Final state

| Item | What shipped | Release |
|---|---|---|
| 6.1 Golden reports | Snapshot tests for representative reports | resolved |
| 7.1 Capability matrix | `docs/COVERAGE.md`, generated from the analyzers | resolved |
| 8 Monorepo / workspace | Cargo workspaces (v0.6.4); npm, Yarn and pnpm workspaces with member test and lint runs (v0.6.13) | v0.6.4 |
| 9 Report size, low memory | Fixed at the source: `syft` excludes (peak RSS 328 to 187 MiB) | v0.6.6 |
| 5 Kubernetes | Helm charts and Kustomize overlays (detection) | v0.6.7 |
| 6 Docker Compose | Compose files and services (detection) | v0.6.8 |
| 7 Makefile | Targets, `.PHONY`, default target (detection) | v0.6.8 |
| 11 Hybrid model | Project Components view, plus analyzers run inside each application component | v0.6.9 |
| 12 Quick Context | Bounded L2 block on top of the report; saner reading order | v0.6.10 |
| 13 Distribution | Version sync tooling, fresh-install smoke test in CI, AUR fixed | v0.6.11 |
| 14 Plugin system | Failure-isolating adapter, API version 1, docs, example plugin | v0.6.11 |
| 15 PDF portability | Engine discovery, honest errors, Markdown fallback, doctor fix | v0.6.12 |

## What remains

### Real follow-ups (CONFIRMED gaps, not out of scope)

1. **npm / pnpm / Yarn workspaces -- first scope done 2026-10-04**
   (AGENTS.md 5.50, `docs/WORKSPACES.md`). Members are detected and their
   tests and lint run inside each member, with duplicate prevention.
   Package-manager awareness (2026-10-07, AGENTS.md 5.53): the `build
   system` label is now pnpm/yarn/bun where it applies and a missing
   lockfile no longer turns `npm audit` into a false FAILED check. Test and
   lint commands deliberately still use `npm` (they work in pnpm/Yarn repos;
   switching would skip checks where those tools are absent). A repo with
   both a Cargo and a Node workspace is modelled since 2026-10-08
   (AGENTS.md 5.58). Per-package results are in the report since
   2026-10-09 (AGENTS.md 5.59, as a table, not a per-package score). Still
   open: Nx/Turborepo task graphs.
2. **A root analyzer that does not cascade hides its components -- fixed
   2026-10-06** (AGENTS.md 5.52) for Node.js, Go and Rust in hybrid
   projects, and since 2026-10-08 (AGENTS.md 5.55, 5.56) in non-hybrid
   projects too, with the same rule. Nothing remains open in this item.
3. **`detect_project()` is root-only -- description fixed 2026-10-05**
   (AGENTS.md 5.51). For hybrid repositories `refine_detection` now lists the
   components' languages, drops the `Generic` placeholder and no longer says
   `Generic / unknown`. `detect_project()` itself stays root-only on purpose
   (it decides which analyzers match the root).
4. **Release safety -- done 2026-10-04.** `scripts/release.py tag` now
   refuses unless every CI run for `HEAD` finished with success (via `gh`);
   `--skip-ci-check` overrides it. See AGENTS.md section 5.49.
5. **Kubernetes next phase -- done 2026-10-09** (AGENTS.md 5.60): raw
   manifests are found by content, and `helm lint` / `kustomize build` run
   on charts and overlays. Opt-in `kubeconform` validation done in R10c
   (history 5.85, `docs/KUBERNETES.md`): the analyzer's own rules forbid
   network checks and capturing a rendered `Secret`, so it runs only when
   `SARAND_KUBECONFORM_SCHEMAS` names a local schema directory, with
   `helm template --output-dir` into a temporary directory that is deleted.
   Not done: validating loose manifest files.
6. **Gradle / Maven multi-module -- done 2026-10-10** (AGENTS.md 5.61): the
   structure is a `maven` / `gradle` workspace in the report (no execution
   change: the root build already tests every module), and a Gradle root
   that holds only `settings.gradle[.kts]` is now a Gradle project.
7. **Small items -- closed 2026-10-09** (AGENTS.md 5.59): the blank line
   before a file's closing code fence is gone, and `filelock` is a range
   (`>=3.14,<4`) instead of an exact pin.

### Decisions and optional work

8. **PyPI publishing -- done with v0.6.19** (AGENTS.md 5.62 to 5.65):
   `pipx install sarand-cli` (the name `sarand` is another project's; the
   command and the import name are unchanged), abi3 wheels for Linux
   x86_64 / aarch64, macOS arm64 / x86_64 and Windows x64, published by
   `.github/workflows/release.yml` with trusted publishing (guide:
   `docs/PUBLISHING.md`). Every release also creates a GitHub Release with
   the files and a `SHA256SUMS` file (AGENTS.md 5.72; seen working with
   v0.7.0). `musllinux` wheels (Alpine) are built since R9a (history 5.80);
   free-threaded Python builds have none and build from the sdist.
9. **AUR:** the `PKGBUILD` is correct but unpublished; run `updpkgsums` once a
   release tag exists.
10. **Quick Context -- designed 2026-10-25, not implemented.** The full design
    and every decision are in `docs/QUICK_CONTEXT_DESIGN.md` (history 5.84):
    R11a frameworks as declared dependencies plus the HTML and text sections,
    R11b layer L3 with rule-based risks that cite their evidence (the
    "inferred risk model" became a fixed rule table), R11c layer L4 behind
    `--relevant-source[=TOKENS]`.
11. **Plugins -- done in R10a** (history 5.81): a plugin phase is cancelled
    after one hour and a minute and reported as a skipped check, and
    `--doctor` lists the plugins and why one was skipped. Sandboxing is a
    recorded non-goal: a plugin is Python code in the same process and cannot
    be confined; a real boundary needs a separate process and a new plugin
    API version. A marketplace stays out of scope until the API has been
    stable for a while.
12. **PDF:** both real engines run in CI (job `pdf`, history 5.82 and 5.83).
    Verified on Ubuntu 24.04: WeasyPrint renders a PDF, and wkhtmltopdf
    0.12.6-2 from apt renders one without an X server (it also works under
    `xvfb-run`, so that is not needed). Debian, Kali, Termux and Android are
    unverified; on Termux and Android use `--format html` and print from a
    browser.
13. **Docker Compose -- `docker compose config` done in R10e** (history 5.86):
    `--quiet --no-interpolate`, a base file checked alone and with each override
    or variant, remote `include:` / `extends:` skipped, missing docker or Compose
    plugin skipped. `hadolint` already ran on Dockerfiles. Not done, by decision:
    running `make` targets (it would run project code; only ever behind an
    explicit opt-in flag, history 5.84) and `dclint`.
14. **Memory profiling of `--quality` and the test phase** (item 9 follow-up);
    only if a real report names one of them.

**Order agreed on 2026-10-25** (details and reasons in history 5.84): the real
follow-ups above, one verifiable round each, are done in this order: items 12
and 11 (done), then 5 (opt-in), 13, 10 (R11a, R11b, R11c), 1 (design first),
and last the packaging in the roadmap file (Docker first). Item 14 stays
skipped by its own rule. Item 9 (AUR) needs the owner's Arch machine and an
AUR account.

### Audit remediation (started 2026-10-15)

The audit of v0.6.19 and its eight rounds are written in
`docs/AUDIT_FIX_PROMPT.md`. Round R1 (secrets: wider filename and content
rules, gitleaks-driven exclusion, explicit fixture allowlist) is delivered
(AGENTS.md 5.67), and so is R2 (truthful issue extraction, inconclusive
audit tools, TODO noise; AGENTS.md 5.68), and R3 (scan-engine parity: Rust walker ancestor-path bug,
Python fallback dropping `.github/`; AGENTS.md 5.69; released as v0.6.20) and R4 (trust model, SECURITY.md,
CONTRIBUTING.md; AGENTS.md 5.70) and the Python 3.11 floor of R5 (AGENTS.md
5.71) and the CI/release half of R5 (AGENTS.md 5.72) and R6 (`--jobs` and bounded command output; AGENTS.md
5.73) and R7 (unreadable paths reported, and the project-only gitignore decision
D2; AGENTS.md 5.74), R8a (AGENTS.md diet, history moved to `docs/history/`)
and R8b (`scripts/bench_scan.py`, `.benchmarks/` ignored; history 5.75).
R8c is delivered too (history 5.76). R8d is delivered too (history 5.77: `docs/BACKLOG.md` is linted). Still
open: decision D3 once the benchmark numbers of both devices exist. The
actions are pinned to SHAs (R8e, then R8f, history 5.78 and 5.79); v0.7.0 is
released; D1 (Python 3.10) was closed by its 3.11 floor and D4 (musllinux
wheels) by R9a (history 5.80).

### Out of scope, with reasons

- **Bazel:** no Bazel analyzer exists in the roster; it would need a
  new-analyzer item first.
- **Nx / Turborepo:** both need an npm/pnpm/Yarn workspace base detected first
  (follow-up 1).
- **A plugin marketplace:** the API has to stay stable first.

## Notes

- `CHANGELOG.md` has individual entries from 0.6.11; versions 0.6.1 to 0.6.10
  were tagged without entries and are summarised inside the 0.6.11 entry
  (`git log v0.6.0..v0.6.10 --oneline` has the detail).
- The CI saga of v0.6.3 and v0.6.4 and the later platform bugs are recorded in
  `AGENTS.md`; read those sections before suspecting a Windows-only theory.
