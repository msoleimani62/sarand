# Security evidence

A security tool that exits with a non-zero code can mean four different things.
sarand keeps them apart, because a report that mixes them tells the reader
something the evidence does not support.

| What happened | What sarand reports | Is it a vulnerability? |
|---|---|---|
| The tool could not run (timeout, not installed, operating-system error) | An execution-coverage gap; a recommendation to re-run it | No: the check gave no verdict |
| The tool reported an advisory | A "security finding" and one entry per advisory in `advisories` | A tool result; applicability is not assessed |
| A dependency violates a configured policy (cargo deny: licenses, bans, sources) | A "dependency policy violation" | No |
| The tool failed and printed no recognised finding | "failed without a recognised finding" | No evidence either way |

Nothing in sarand reports a **confirmed application-level vulnerability**: that
needs concrete evidence of exploitability, and a tool exit code is not evidence.

## What an advisory entry holds

Each entry in the JSON key `advisories`, in the SARIF results and in the Markdown
section "Dependency advisories" has these facts, all read from the tool output:

- `id`, `package`, `version`: for example `RUSTSEC-2026-0385`, `ctutils`, `0.4.2`.
- `kind`: the advisory database's word, `vulnerability`, `unsound`,
  `unmaintained`, `yanked` or `notice`.
- `title` and `url`.
- `fixed_versions`: the versions the tool names, empty when no safe upgrade exists.
- `severity`: the upstream value when the tool printed one, **`null` when it did
  not**. The RustSec text output prints a severity only for advisories with a CVSS
  score, so a missing value is common and is never replaced by a guess.
- `sources`: every check that reported it. cargo audit and cargo deny report the
  same advisory once.
- `database`: the advisory database and how many advisories the tool loaded. It
  does not claim the database was refreshed.
- `applicability`: **`unknown` for every entry.**

## Severity and applicability are two facts

An advisory can have a high upstream severity while nobody knows whether this
project reaches the affected code. sarand shows both facts and never turns an
unknown applicability into a low severity, or a high severity into a claim of
exploitability.

Deciding applicability needs evidence sarand does not collect: which API of the
dependency the project calls, which Cargo features are enabled, and which target
platforms are supported (an advisory about a WebAssembly allocator does not apply
to a native-only build, and an advisory about one decoder does not apply to
another). The presence of a crate in `Cargo.lock` proves none of this. Until that
evidence is gathered the value stays `unknown`.

## How it affects the health score

The security weights did not change: 15 points when every security check that ran
passed, 5 when one failed with a verdict, 8 when none could run.

- A check the runner could not execute is no longer a failure. Before, a timeout
  or a missing binary counted as "Security tool reported issues." and cost 10
  points.
- The critical message now says what the tool reported. "Security finding
  reported by cargo audit (a tool result; exploitability is not assessed)", or
  "Dependency policy violation reported by cargo deny check (licenses, bans or
  sources); not a vulnerability", or "Security tool X failed without a recognised
  finding".
- The risk `SEC-CHECK-FAILED` ignores a check that could not run.

A check that could not run still shows up: execution coverage names it as a gap,
and a recommendation says why it gave no verdict.

## What this does not do

- **No reachability analysis.** Applicability stays `unknown`.
- **No refresh.** sarand reads what cargo audit and cargo deny printed. It does
  not fetch the advisory database or check an advisory against a newer copy.
- **The tools run as before.** The text output is parsed; no JSON mode was added.
- **cargo audit and cargo deny only.** `pip-audit`, `npm audit` and the other
  security tools still produce a classified failure, not advisory entries.
- **HTML and text reports** do not list the advisories yet; Markdown, JSON and
  SARIF do.
