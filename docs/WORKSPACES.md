# Monorepos and workspaces

sarand understands four kinds of multi-package repositories.

| Model | How it is detected | What sarand does |
|---|---|---|
| **Cargo workspace** | `[workspace]` in the root `Cargo.toml` | Lists the members. `cargo test --all` already covers every crate. |
| **npm / Yarn / pnpm workspace** | `"workspaces"` in the root `package.json` (array, or Yarn's `{"packages": [...]}`), or `pnpm-workspace.yaml` | Lists the members and runs tests and lint **inside each member**. |
| **Maven multi-module** | `<modules>` of the root `pom.xml`, followed into nested aggregators (3 levels) | Lists the modules. `mvn test` already covers every module. |
| **Gradle multi-project** | the `include` calls of `settings.gradle[.kts]` | Lists the projects. `./gradlew test` already covers every project. |

The report gets a **Workspace** section (kind and members) and, in JSON, a
`workspace` key. A repository with **both** a Cargo and a Node workspace gets
one section per workspace (`## Workspace (cargo)`, `## Workspace (npm)`) and,
in JSON, a `workspaces` list next to the unchanged `workspace` key (the first
entry). Results from a member are labelled with its path, for
example `packages/api: npm test`, so they are never confused with the root's.

## How Node workspaces are run

`npm test` at the root only runs the **root's** `test` script; it does not
reach the packages. So sarand runs the Node.js analyzer in every member
directory (`npm test` when the member has a `test` script, `npm run lint` and
`eslint` when it is configured). Members run one after another, at most **20**
of them; if there are more, one skipped result tells you how many were left
out. This holds when the repository also has a Cargo workspace: the Node
members are run as members (tests and lint, never `npm audit`) and the Cargo
members are covered by `cargo test --all`.

To avoid reporting anything twice, sarand skips a phase for the members when
the root already covers it:

- **Tests:** the root `test` script fans out (`--workspaces`, `-ws`,
  `pnpm -r` or `--filter`, `yarn workspaces`, `turbo`, `nx`, `lerna`, `wireit`).
- **Lint:** the root `lint` script fans out the same way, **or** the root has
  an ESLint configuration (`eslint .` at the root already recurses into the
  packages).
- **Security:** never run per member. `npm audit` at the root already reads the
  one workspace lockfile.

A member that is also an application of a hybrid project (for example a React
app and an Express API in one workspace) is merged into a single run per
analyzer. Set `SARAND_NO_COMPONENTS=1` to turn off member runs and
per-component runs together.

## How the health score treats workspaces

There is **one repository-level score**. The report also gets a **Package
results** table (and a `package_results` list in JSON) whenever checks ran
inside packages: one row per package with the tests, quality and security
results it passed (`2/3`, `0/1 failed`, `skipped`, `-`), the root first.
There is deliberately no per-package 0-100 score, because the formula also
holds repository-level parts (git hygiene, TODOs, tooling).
Member results go into the same lists as the root's results and each check is
counted once. A failing member test suite lowers the shared test ratio and
adds "One or more test suites failed" to the critical list, exactly as a
failing root suite would.

## What is not supported

- **Maven modules that exist only in a `<profile>`**, `includeBuild` /
  `includeFlat` and a custom `projectDir` in Gradle, and includes built by a
  loop: the structure is read statically, so these are not seen. A Maven
  module or Gradle project whose directory does not exist is left out, not
  guessed.
- **Bazel, Nx and Turborepo** as workspace models. Bazel has no analyzer at
  all. Nx and Turborepo sit on top of an npm/Yarn/pnpm workspace: that
  workspace is detected, and a root script that calls them is recognised as
  fanning out, but their task graphs are not read.
- **Package-manager-specific commands.** Members are still tested with
  `npm test`, even in a pnpm or Yarn repository; the scripts run, but a repo
  that forbids `npm` through corepack needs its own tooling.
- **Relationships between member packages** (which package depends on which).

## Nested packages in hybrid projects

In a hybrid project (for example a Node root with a React `web/` and an Express
`api/` behind a compose file), a nested package of Node.js, Go or Rust is also
analysed even though the same analyzer matches the root, because the root run
does not reach it: `npm test` stops at the package boundary, `go test ./...`
skips nested modules, and `cargo test --all` covers only workspace members. It
is **not** analysed again when the root already covers it: a Node or Cargo
workspace member, or anything in a repository with a `go.work`. Root test and
lint scripts that fan out, or a root ESLint configuration, drop those phases
exactly as for workspace members. Python needs no such rule, because the root
`pytest` and `ruff` recurse. A project that is not hybrid (one package kind, no
compose, Kubernetes or Terraform) is planned by the same rule: an analyzer
that does not match the root runs inside each nested package, one that does is
not repeated (except the three above).

Persian: [WORKSPACES.fa.md](WORKSPACES.fa.md)
