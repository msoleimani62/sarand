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

Latest release: **v0.6.12**. Every released version carries its own number
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
| 8 Monorepo / workspace | Cargo workspaces (v0.6.4); npm, Yarn and pnpm workspaces with member test and lint runs (unreleased) | v0.6.4 |
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
   Still open: package-manager-specific commands (members are tested with
   `npm test` even in pnpm/Yarn repos and the `build system` label still
   says `npm`), a repo with both a Cargo and a Node workspace, Nx/Turborepo
   task graphs, per-package scores.
2. **A root analyzer that does not cascade hides its components.** Per-component
   execution never re-runs an analyzer that matches the root (that is what
   prevents duplicate findings), so e.g. a root `package.json` without
   workspaces plus a `frontend/` Node package leaves `frontend/` unchecked.
   Same root cause as 1.
3. **`detect_project()` is root-only -- description fixed 2026-10-05**
   (AGENTS.md 5.51). For hybrid repositories `refine_detection` now lists the
   components' languages, drops the `Generic` placeholder and no longer says
   `Generic / unknown`. `detect_project()` itself stays root-only on purpose
   (it decides which analyzers match the root).
4. **Release safety -- done 2026-10-04.** `scripts/release.py tag` now
   refuses unless every CI run for `HEAD` finished with success (via `gh`);
   `--skip-ci-check` overrides it. See AGENTS.md section 5.49.
5. **Kubernetes next phase.** Raw manifests with no fixed filename, and any
   lint or validation run (`helm lint`, `kubeconform`, `kustomize build`).
6. **Gradle / Maven multi-module** representation (they already test every
   module natively; only the report is blind to the structure).
7. **Small items:** `markdown.py` leaves a blank line before a file's closing
   code fence when embedding source (cosmetic); the exact pin
   `filelock==3.32.3` in `pyproject.toml` is harmless under pipx but a conflict
   risk for `pip --user` and distro packaging, so review it.

### Decisions and optional work

8. **PyPI publishing.** Not published; install is from source with pipx and a
   Rust toolchain (verified: neither `pip` nor `pipx` installs without Rust).
   Publishing needs a trusted-publishing workflow and wheels for Linux
   (x86_64, aarch64), macOS and Windows. Worth doing only if people should
   install without Rust.
9. **AUR:** the `PKGBUILD` is correct but unpublished; run `updpkgsums` once a
   release tag exists.
10. **Quick Context:** frameworks and an inferred risk model (not in the report
    data), layers L3 (architecture and risks) and L4 (relevant source subset),
    HTML and text renderer sections.
11. **Plugins:** timeouts for non-subprocess work, sandboxing, a plugin listing
    in `--doctor`. A marketplace stays out of scope until the API has been
    stable for a while.
12. **PDF:** a real engine in CI (Debian's `wkhtmltopdf` may need an X server,
    unverified); Termux and Android PDF export is unverified, use
    `--format html` and print from a browser.
13. **Docker Compose, Makefile and Kubernetes execution** (`docker compose
    config`, `hadolint`, running targets). Detection only today; `make` is
    never run on purpose.
14. **Memory profiling of `--quality` and the test phase** (item 9 follow-up);
    only if a real report names one of them.

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
