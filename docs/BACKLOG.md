Sarand — Engineering Backlog & Gap Audit

Post-v0.6.2 Engineering Reference

---

0. Context

Project: "sarand"
Repository: "msoleimani62/sarand"
Latest release: "v0.6.2"
Latest "main": "1e99b0c"
Latest post-release commit: "1e99b0c — style: format health module"

Relevant completed work

v0.6.1

Health Score TODO/FIXME counting was corrected so that only explicitly actionable markers are counted:

- "TODO:"
- "TODO -"
- "FIXME:"
- "FIXME -"

v0.6.2

Health Score Tooling scoring was corrected.

Tooling score is now based on the ratio of checks that actually ran for the project, rather than the number of tools installed on the host.

Health Score maximum is explicitly:

Tests       25
Quality     20
Security    15
Git         10
Code        15
Tooling     15
----------------
Total      100

The post-release formatting fix was committed separately on "main" as:

1e99b0c style: format health module

Do not treat that formatting commit as a new release unless explicitly requested.

---

1. Purpose

This document is the engineering reference for identifying and resolving remaining Sarand weaknesses, missing capabilities, architectural gaps, insufficient validation, and product limitations.

The goal is not to invent features.

The goal is to:

1. inspect the current repository;
2. distinguish confirmed limitations from assumptions;
3. identify the highest-value remaining engineering gaps;
4. prioritize them objectively;
5. define measurable completion criteria;
6. prevent unrelated changes from being mixed together;
7. preserve regression safety while the project evolves.

---

2. Evidence-First Rule

Before treating any item in this document as an actual defect or missing capability, inspect the current repository.

Do not assume that a previously documented limitation still exists.

For every investigated item, classify it as exactly one of:

CONFIRMED
PARTIALLY RESOLVED
RESOLVED
UNVERIFIED
OUT OF SCOPE

Evidence should come from, in order of preference:

1. current source code;
2. current tests;
3. current fixtures;
4. current generated reports;
5. current documentation;
6. actual execution of the relevant tools;
7. real-project validation;
8. historical documentation.

Historical documentation must not override current repository evidence.

If documentation and implementation disagree, report the discrepancy explicitly.

Do not silently "fix" the documentation while investigating unless documentation correction is part of the selected task.

---

3. Scope Discipline

Work on one major backlog item at a time.

Do not combine unrelated architectural changes.

For each selected item:

Audit
→ Define current behavior
→ Identify exact gap
→ Design minimal change
→ Implement
→ Add/update tests
→ Run targeted validation
→ Run relevant regression tests
→ Update documentation
→ Review diff
→ Commit

Do not modify unrelated files merely because an improvement is noticed while working on another item.

Record unrelated findings as backlog items instead.

---

4. Priority Model

Use the following priority levels.

P0 — Correctness / Regression Infrastructure

Issues that can cause incorrect reports, hidden regressions, or make major future changes unsafe.

P1 — Core Architecture / High Impact

Features or architectural improvements that materially affect Sarand's ability to analyze modern real-world projects.

P2 — Important Product Capability

Useful improvements with significant value but which are not blocking core architecture.

P3 — Completion / Ecosystem Expansion

Nice-to-have features, niche ecosystems, portability improvements, or lower-impact extensions.

Priority must be justified by evidence.

Do not assign priority merely because an item sounds technically interesting.

---

5. Definition of Done

Every backlog item must have an explicit Definition of Done before implementation begins.

A feature is not considered complete merely because its implementation exists.

Where applicable, completion requires:

[ ] Implementation
[ ] Unit tests
[ ] Integration tests
[ ] Representative fixture
[ ] Regression coverage
[ ] Real-tool validation
[ ] Documentation
[ ] Error/skip behavior defined
[ ] Report output verified
[ ] Performance impact checked
[ ] Backward compatibility checked

Only check items that are actually relevant to the selected feature.

---

6. P0 — Regression and Observability Foundation

6.1 Golden / Representative Reports

Problem

Sarand has unit and integration tests, but structural and semantic regressions in complete reports can be difficult to detect.

Large changes to:

- analyzers;
- report structure;
- health scoring;
- workspace handling;
- AI context;
- security findings;
- source inclusion;

may pass existing tests while changing the resulting report unexpectedly.

Required investigation

Determine whether Sarand already has any equivalent golden-report or snapshot mechanism.

Do not assume that none exists.

Desired capability

Create a small, stable collection of representative projects covering:

Python
Rust
JavaScript/TypeScript
Go
Hybrid project
Infrastructure-oriented project
Multi-language project

The fixtures should be intentionally small.

Avoid storing unnecessarily large source trees.

Definition of Done

[ ] Representative fixtures exist
[ ] Report structure can be regression-tested
[ ] Dynamic/non-deterministic fields are normalized
[ ] Tests do not depend on network access
[ ] Tests do not require unavailable optional tools
[ ] Expected report changes are reviewable
[ ] At least one hybrid fixture exists
[ ] Documentation explains how snapshots are updated

---

7. P0/P1 — Analyzer Capability Matrix

7.1 Analyzer Depth

Problem

Sarand has a large number of analyzers, but analyzer depth is not necessarily uniform.

Some analyzers may provide:

- detection only;
- build metadata;
- test execution;
- quality tooling;
- security tooling;

while others may provide substantially deeper analysis.

Important rule

Do not call an analyzer "shallow" without evidence.

Inspect its implementation, tests, fixtures, actual tool execution, and documentation.

Required capability matrix

Create or update a machine-readable or clearly structured capability matrix containing, where applicable:

Detection
Build
Test
Quality
Security
CI
Dependency analysis
Real-tool validation
Fixture coverage
Real-project validation

Example conceptual structure:

Analyzer| Detection| Build| Test| Quality| Security| Fixtures| Real-project validation| Depth
Python| ✓| ✓| ✓| ✓| ✓| ✓| ✓| Deep
Rust| ✓| ✓| ✓| ✓| ✓| ✓| ✓| Deep
Example| ✓| ✓| ?| ?| ?| ✓| ?| Partial

Do not invent values. Every cell should be evidence-backed.

Definition of Done

[ ] All current analyzers are inventoried
[ ] Capabilities are evidence-backed
[ ] Missing validation is explicitly marked
[ ] Shallow/partial analyzers are clearly documented
[ ] COVERAGE.md or equivalent reflects reality
[ ] No analyzer is labeled deep merely because it has a wrapper

---

8. P1 — Monorepo / Workspace Architecture

8.1 Current-State Audit

Investigate current support for:

Cargo workspace
npm workspaces
pnpm workspace
Yarn workspace
Gradle multi-project
Maven multi-module
Bazel
Nx/Turborepo or equivalent structures

Do not implement all ecosystems automatically.

First determine which workspace models Sarand can already detect.

8.2 Desired Architecture

Sarand should eventually distinguish:

Repository root
├── workspace/package A
├── workspace/package B
├── workspace/package C
└── shared infrastructure

The report should be capable of representing:

Root-level information
Workspace-level information
Cross-workspace relationships
Overall project summary

Health scoring should eventually support:

Workspace health
Overall repository health

without double-counting the same checks.

Definition of Done

For the first implementation scope:

[ ] Workspace detection implemented for explicitly selected ecosystems
[ ] Root/workspace relationship represented internally
[ ] Duplicate execution is prevented
[ ] Report distinguishes root from workspace findings
[ ] Health aggregation rules are defined
[ ] Representative workspace fixture exists
[ ] Regression tests exist
[ ] Documentation explains unsupported workspace models

Do not implement every monorepo ecosystem in one change.

---

9. P1 — Report Size and Low-Memory Operation

9.1 Current-State Audit

Inspect:

core/estimate.py
source collection
embedding
report rendering
temporary data
PDF generation
memory-heavy transformations

Determine which operations actually consume the most memory.

Do not claim OOM risk without measurement.

9.2 Desired Capabilities

Potential capabilities:

--low-memory

and/or:

summary + separate source artifacts

and/or intelligent source truncation.

The exact interface must be designed after profiling.

Required measurements

Where practical, benchmark:

small project
medium project
large project

on constrained environments.

Record:

runtime
peak memory
report size
source size

Definition of Done

[ ] Memory-heavy stages identified
[ ] Benchmark data exists
[ ] Low-memory strategy defined
[ ] Behavior is deterministic
[ ] Large reports remain usable
[ ] No silent loss of important findings
[ ] Tests cover the new mode
[ ] CLI documentation exists

---

10. P1 — Infrastructure Ecosystem Coverage

Investigate the current state of:

Kubernetes
Helm
Kustomize
Docker Compose
Makefile

Do not automatically add all of them.

For each ecosystem determine:

Detection
Validation
Linting
Security
Dependency/configuration analysis
Report representation
Available host tools
Test fixtures

Initial suggested order

Kubernetes / Helm / Kustomize
Docker Compose
Makefile

But reorder if repository evidence shows another gap is materially larger.

---

11. P1/P2 — Hybrid Project Model

Modern repositories may combine:

Frontend
Backend
Infrastructure
CI/CD
Containerization
Database
Documentation

Investigate whether Sarand currently represents these as independent analyzers only or whether it can express their relationships.

Desired future model:

Project
├── Application
│   ├── Backend
│   └── Frontend
├── Infrastructure
├── CI/CD
└── Supporting configuration

The first implementation should focus on representation and context, not on building a universal software architecture detector.

Definition of Done

[ ] Current limitations documented
[ ] Hybrid fixture created
[ ] Components are distinguishable
[ ] Cross-component context can be represented
[ ] No duplicate findings are introduced

---

12. P2 — AI-Oriented Context

12.1 Current Problem

Investigate whether the current:

- AI summary;
- suggested reading order;
- project context;
- report structure;

are sufficiently useful for downstream LLM analysis.

Do not redesign them based only on subjective preference.

12.2 Preferred Architecture

Prioritize context layers instead of model-specific presets:

L0 — Full report
L1 — Project summary
L2 — Quick Context
L3 — Architecture / risks
L4 — Relevant source subset

Quick Context

A compact, deterministic section should ideally contain:

Project type
Languages
Frameworks
Build systems
Test systems
Security tooling
Health score
Critical findings
Important risks
Repository structure
Recommended reading order

The exact fields must be based on current report data.

Model-specific presets

Claude/GPT/Gemini/Grok-specific presets should not be implemented unless evidence shows a concrete need.

Prefer model-agnostic structured context.

Definition of Done

[ ] Context schema defined
[ ] Quick Context is deterministic
[ ] Token/size budget is documented
[ ] Important findings are preserved
[ ] Representative reports tested
[ ] AI-oriented output does not change core analysis results

---

13. P2 — Distribution and Installation

Investigate the actual current state of:

PyPI
pipx
AUR
Termux
optional PDF dependencies
native/system dependencies

Separate:

package availability
installation reliability
optional dependency availability
documentation quality

Do not assume that an unpublished AUR draft is necessarily a critical product problem.

Definition of Done

For each distribution channel:

[ ] Installation path documented
[ ] Fresh-install test exists where practical
[ ] Versioning is correct
[ ] Optional dependencies fail gracefully
[ ] Termux limitations documented

---

14. P2 — Plugin System

Investigate the current "entry_points" mechanism before changing it.

Determine:

Plugin discovery
Plugin registration
Plugin API stability
Plugin lifecycle
Error isolation
Version compatibility
Documentation
Example plugin

A plugin architecture is not considered mature merely because entry points exist.

Definition of Done

[ ] Public plugin contract documented
[ ] Minimal example plugin exists
[ ] Plugin discovery tested
[ ] Failure isolation tested
[ ] Version compatibility documented
[ ] Third-party author workflow documented

Do not build a plugin marketplace or ecosystem before the API itself is stable.

---

15. P3 — PDF and Report Portability

Investigate the current PDF pipeline.

Determine:

wkhtmltopdf dependency
WeasyPrint dependency
Termux compatibility
native library requirements
failure behavior

The goal is not necessarily to remove the current backend.

The goal is to make PDF generation:

predictable
documented
optional
gracefully degradable

Definition of Done

[ ] Dependency requirements documented
[ ] Unsupported environments fail clearly
[ ] Markdown report remains available when PDF fails
[ ] At least one supported PDF path is tested

---

16. P3 — Cross-Ecosystem Vulnerability Analysis

Current SBOM generation must not automatically be described as vulnerability scanning.

Investigate separately:

SBOM generation
Dependency identification
Vulnerability database integration
Vulnerability matching
Severity representation
Offline behavior
False-positive handling

Potential future tools may include ecosystem-specific or universal vulnerability scanners, but tool selection must be evidence-based.

Definition of Done

[ ] SBOM and vulnerability scanning are clearly separated
[ ] Current capabilities documented accurately
[ ] At least one real vulnerability fixture exists before claiming support
[ ] Findings include source/tool attribution
[ ] Offline behavior is defined

---

17. P3 — Additional Ecosystems

Only after higher-priority architectural work is stable, consider:

Deno
Bun
Vue
Svelte
Astro
OCaml
Clojure
Crystal
Nim
V
Solidity

Niche ecosystems should remain lower priority unless real-project evidence demonstrates demand.

---

18. Explicitly Avoid Premature Work

Do not prioritize the following merely because they are technically interesting:

Complete rewrite of the analyzer architecture
Complete rewrite of the Rust core
Model-specific AI prompt presets
Large UI redesign
Support for every programming language
Support for every build system
Plugin marketplace
Cosmetic CLI changes
Health Score changes without a concrete scoring defect

Every such change requires a concrete problem statement and evidence.

---

19. Backlog Item Template

For every future item, use this structure:

## [ID] Title

Priority:
P0 / P1 / P2 / P3

Status:
CONFIRMED / PARTIALLY RESOLVED / RESOLVED / UNVERIFIED / OUT OF SCOPE

Problem:
<precise description>

Evidence:
<files, tests, commands, reports, real-project results>

Current behavior:
<what Sarand actually does today>

Gap:
<what is missing>

Impact:
<technical/user impact>

Proposed scope:
<minimal implementation scope>

Non-goals:
<what this change must NOT attempt to solve>

Definition of Done:
[ ] ...
[ ] ...
[ ] ...

Regression coverage:
[ ] ...

Documentation:
[ ] ...

Dependencies:
<other backlog items if any>

Notes:
<additional evidence or constraints>

---

20. Investigation Protocol

Before modifying code:

1. Inspect repository state.
2. Inspect relevant implementation.
3. Inspect existing tests.
4. Inspect relevant documentation.
5. Search for existing partial implementations.
6. Run the smallest useful reproduction.
7. Classify the item.
8. Define exact scope.
9. Define Definition of Done.
10. Only then implement.

Do not start coding simply because an item appears in this document.

---

21. Validation Protocol

After implementation:

Targeted tests
→ Relevant integration tests
→ Full test suite when appropriate
→ Ruff / static checks
→ git diff --check
→ Report generation
→ Generated report inspection

For analyzer changes, whenever practical:

Fixture
→ Real tool execution
→ Expected finding verification

For report changes:

Representative project
→ Generate report
→ Compare against regression expectations

For performance changes:

Before benchmark
→ After benchmark
→ Compare runtime/memory/report size

---

22. Current Working Priority

The current backlog should initially be investigated in this order:

P0

1. Golden / representative report regression infrastructure
2. Analyzer capability matrix and evidence-based depth classification

P1

3. Monorepo / Workspace architecture
4. Low-memory and large-report handling
5. Kubernetes / Helm / Kustomize
6. Docker Compose
7. Hybrid project representation

P2

8. AI-oriented Quick Context and layered context
9. Distribution / installation reliability
10. Plugin API maturity

P3

11. PDF portability
12. Cross-ecosystem vulnerability scanning
13. Additional ecosystem expansion

This is a starting investigation order, not a permanent ranking.

If repository evidence demonstrates that another item is materially more urgent, update the priority with explicit evidence.

---

23. Final Rule

The objective is not to maximize the number of Sarand features.

The objective is to maximize:

Correctness
+
Depth
+
Real-world validation
+
Regression safety
+
Resource efficiency
+
Useful project context

Every change should make Sarand more reliable on real repositories, not merely make its feature list longer.

Never claim that a capability is complete until its implementation, tests, documentation, and relevant real-world validation support that claim.
