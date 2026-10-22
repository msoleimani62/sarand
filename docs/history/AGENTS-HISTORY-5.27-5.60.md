# AGENTS history: rounds 5.27 to 5.60

Moved verbatim out of `AGENTS.md` (round R8a). Nothing was reworded; some
references inside still say "this file" or "section 5.NN" and mean the history
of the project as a whole.

---

### 5.27 — CI broke on two releases (v0.6.3, v0.6.4): wheel-install path bug + real Windows cross-platform bugs (2026-09-23)

User reported CI red on both of the last two tags. This interrupted
the P1 item 9 work (5.26) -- fixing a regression on `main` takes
priority over starting new backlog items, per the doc's own P0
framing ("correctness / regression infrastructure" outranks
everything). Investigated the actual GitHub Actions failure summary
the user pasted (all three of ubuntu/macos/windows py3.12 "quality"
jobs failed; py3.10/py3.14 ubuntu jobs' own failures were not shown in
the pasted summary but are presumably the same root cause) rather than
guessing.

**Bug 1 -- `core/coverage.py`'s `_REPO_ROOT` broke under CI's own
"test the real wheel" step (all 3 platforms, root cause of the
`test_coverage.py` failures from 5.22 onward).** `_REPO_ROOT` was
`Path(__file__).resolve().parent.parent.parent.parent` -- correct only
when the *imported* `sarand.core.coverage` is the source-tree copy.
`ci.yml`'s "quality" job does not stop at the editable dev install: it
then runs `maturin build --release` and `pip install dist/*.whl`,
deliberately testing the real installed artifact, before running
`pytest`. From that point on `__file__` points into site-packages, so
`tests/`/`.github/workflows/ci.yml` silently resolved to nonexistent
paths, every `fixture_coverage`/`ci_installed` check went to `False`,
every depth was miscomputed, and `docs/COVERAGE.md` looked "stale"
against that -- explains all three `test_coverage.py` failures, on
every OS, and explains why this passed every local verification round
(5.22-5.24): the user's local dev environment is always editable-mode,
never rebuilds+installs a wheel mid-session, so nothing ever exercised
this path locally. Real lesson, not just a fixed bug: **local
verification in an editable install is not equivalent to what CI's
own "quality" job actually tests**, for any project-introspection code
that relies on `__file__`. Fixed with a new `_find_repo_root()`:
search upward from `Path.cwd()` for `pyproject.toml` + `.github/`
first (both the documented `python -m sarand.core.coverage >
docs/COVERAGE.md` invocation and CI's own `pytest` step always run
with the checkout as cwd, in *every* install mode), falling back to
the old `__file__`-relative guess only if that search finds nothing.
Verified directly: `_find_repo_root()` returns the correct root both
from the repo root itself and from a nested subdirectory
(`python/sarand/core`), confirming the upward search actually walks.

**Bug 2 -- three renderers embedded relative file paths without
`.as_posix()` (Windows-only, real correctness bugs beyond golden-test
failures, pre-existing before item 6.1 ever touched these files).**
`markdown.py`'s `f"### FILE: \`{rel}\`"`, `html.py`'s
`escape(str(rel))`, and `json_renderer.py`'s `"path": str(rel)` (plus
the same pattern for `skipped_files`/`excluded_secret_files` in all
three, and `included_files` in `json_renderer.py`) all implicitly
`str()`-format a `Path`, which uses native separators -- backslashes
on Windows. Two distinct consequences, both real: (a) cosmetic --
report headers/JSON showed `src\main.py` on Windows instead of
`src/main.py`, which is what made `md-hybrid`/`html-hybrid`/parts of
`json-hybrid` fail the byte-exact golden comparison (item 6.1's
snapshots were captured on Linux) -- **this validates the whole point
of golden-report testing**: this bug predates item 6.1 entirely
(untouched by any of my edits to these files) and no "contains X"
style test ever caught it, because the text still *contained* enough
to pass a loose check, just not byte-exact. (b) functional, not just
cosmetic -- `markdown.py`/`html.py`'s filename-vs-content exclusion
split compares `str(p)` (backslash form) against
`{f.path for f in data.secret_findings}` (always forward-slash
strings, from the scanner) -- on Windows this comparison silently
never matches, so every excluded-secret file would be mis-labeled
"credential-shaped filename" even when it was really a content match.
Fixed all of it: every `Path` embedded in rendered text or compared
against a plain-string set now goes through `.as_posix()`. Confirmed
this is a pure Windows-only fix and changes nothing on Linux/macOS:
reran the full golden-report harness after, still 10/10 with *zero*
snapshot changes needed (`.as_posix()` and `str()` are identical for
an already-relative path on POSIX).

**Bug 3 -- `test_golden_reports.py`'s own `_normalize()` did not
account for JSON string-escaping of the tempdir's absolute path
(Windows-only, explains the remaining `json-*`/`sarif.json-*`
failures).** `json_renderer.py`/`sarif.py` embed `data.project_root`
inside a JSON string; `json.dumps` escapes every backslash as `\\`.
The single-backslash `str(root)` the test replaced never appears
literally in that escaped text on Windows, so normalization silently
did nothing and the real (un-normalized, machine-specific) path leaked
into the "normalized" output, which could then never match a snapshot
captured on Linux. Fixed by also trying the JSON-escaped form of the
path. Same as Bug 2, confirmed a no-op on Linux (no backslashes to
escape there) -- golden harness still 10/10, zero snapshot changes.

All three bugs independently explain a disjoint subset of the observed
failures and were each verified in isolation before combining: Bug 1
-> the 3 `test_coverage.py` failures (all platforms); Bug 2 -> the
Windows-only `md-hybrid`/`html-hybrid` failures (and contributes to
`json-hybrid`); Bug 3 -> the remaining Windows-only `json-*`/
`sarif.json-*` failures. Together they account for everything in the
pasted summary. **Not independently confirmed against the real Windows
CI run yet** (this sandbox is Linux-only, same limitation as every
prior round) -- confidence is high (each bug was traced to an exact
line via direct code reading, not guessed from symptoms alone, and the
"which combos fail vs pass" pattern in the user's paste matches each
bug's predicted footprint exactly: `txt` never embeds paths so never
fails, `minimal` has no `included_files` so only the Bug-1/Bug-3
failures apply to it, `hybrid` has both), but the honest status is
"strongly evidenced, not yet reproduced" until the next CI run
confirms it.

On-device run of the 5.27 fixes: `pytest -q` clean (789/789), but two
small misses caught by tools this sandbox can't run. `ruff check`
(I001): the new `_find_repo_root` def needed a second blank line
before it (PEP 8 two-blank-lines-before-a-top-level-def) -- one-line
fix. `mypy .`: `scripts/benchmark_report.py`'s `_parse_gnu_time_elapsed`
reassigned `parts` from `list[str]` to `list[float]` in the same
variable -- mypy fixes a variable's type at first assignment in a
scope and does not allow narrowing it differently on reassignment
without an explicit annotation; renamed the second list to `values`
instead of fighting the type checker. Both fixed, verified locally
(`docs/COVERAGE.md` still byte-identical, `_parse_gnu_time_elapsed`
re-tested against the `m:ss.cc` and `h:mm:ss.cc` sample strings from
5.26, both still correct).


### 5.28 — Real CI progress: 9 failures -> 3, one more fix shipped, one still needs more evidence (2026-09-23)

Pushed 5.27 (ea3442e). Real GitHub Actions result: ubuntu (all 3
Python versions) and macOS both fully green; Windows down from 9
failures to 3 -- confirms all three 5.27 bugs were real and correctly
fixed (the 6 golden-report failures and 3 coverage failures that
disappeared). Remaining 3, investigated with the same evidence-first
standard:

**Fixed -- `test_run_cmd_async_timeout_preserves_output` (unrelated
pre-existing flake, not caused by 5.21-5.27):** failed at
`duration == 0.9953488999999536` against `assert duration >= 1` -- a
~4.6ms shortfall. Windows' asyncio event-loop timer resolution is
well-documented as coarser than Linux/macOS, so a `timeout=1` can
legitimately fire a few ms before the wall clock hits exactly 1.0s;
this is the OS's timer granularity, not a bug in `run_cmd_async`.
Loosened to `>= 0.9` (a 10% tolerance -- still meaningfully checks
"fired around the 1s mark", not sub-10ms precision no Windows runner
can promise). Deliberately left the sync `run_cmd` version of the same
test and the POSIX-only process-group test untouched -- neither was
reported flaky in this run, and changing them without evidence would
be guessing, violating the Evidence-First Rule as much as fabricating
a fix would.

**Not yet fixed -- `test_renderer_output_matches_golden_snapshot
[sarif.json-hybrid]` and `[sarif.json-minimal]`, still failing after
5.27's Bug 3 fix.** `sarif.py` has exactly one absolute-path-derived
field (`originalUriBaseIds.PROJECTROOT.uri`, via
`data.project_root.as_uri() + "/"` -- confirmed by rereading the whole
file, nothing else in it touches `project_root` or any `Path` object;
`finding.path`/`todo.path` are plain strings the fixtures set
directly, OS-independent). `_normalize()`'s existing
`root.as_uri() + "/"` replace should, in principle, match exactly
since both the renderer and the test call `.as_uri()` on the *same*
`Path` object -- deterministic, no reason to differ. The GitHub
summary box's truncated diff (`...OT_URI>/'}}}]}` vs `...T_ROOT>/'}}}]}`)
is not enough to tell whether this is a drive-letter-casing quirk in
Windows `Path.as_uri()`, a `pytest` diff-truncation artifact showing
two different truncation points that are actually identical
underneath, or something not yet considered. Rather than guess and
ship a fix for the wrong mechanism, asked the user for the full,
untruncated pytest diff for just these two tests (the raw log, not the
summary box) before touching `sarif.py`/`_normalize()` again.


### 5.29 — SARIF Windows failure resolved with a robust match, not a pinned-down cause (2026-09-23)

Second real-CI round after 5.28's timing fix: `test_run_cmd_async_
timeout_preserves_output` confirmed fixed (dropped out of the failure
list entirely) -- ubuntu/macOS stayed fully green throughout. Only the
two `sarif.json` golden tests remained, with the identical truncated
diff as before. Asked the user for the full raw log to pin down the
exact mechanism; decided not to keep blocking on that a third time and
instead shipped a fix robust enough to not need to know the exact
cause.

`sarif.py` has exactly one absolute-path-derived field
(`originalUriBaseIds.PROJECTROOT.uri`, confirmed by rereading the
whole file again). The test's `_normalize()` matched it with an exact
string replace of `root.as_uri() + "/"`, which in principle should be
deterministic (same `Path` object, same method, called twice) -- but
evidently is not, on Windows, for a reason not fully pinned down from
the GitHub summary box's truncation (leading theory: `Path.as_uri()`
drive-letter casing; Windows temp paths can also resolve through an
8.3 short name like `RUNNER~1` inconsistently between calls). Rather
than keep guessing at the exact mechanism, replaced the exact-match
with a pattern match that doesn't need to know it: any `file://...`
URI ending in this fixture's own (unique, known) directory name,
case-insensitive. Tested locally against three plausible Windows
`Path.as_uri()` variants (uppercase drive, lowercase drive, 8.3
short-name path) -- all three normalize correctly to the same
placeholder, so this should hold regardless of which of those turns
out to be the real cause. Confirmed a no-op change on Linux: golden
suite still 10/10 after, zero snapshot changes.

This is a different kind of fix than 5.21-5.28's: those pinned an
exact root cause before touching code; this one is a defensively
robust fix shipped *without* full certainty of the mechanism, because
the alternative was a third round of asking the user to dig through
raw CI logs for a single-field JSON diff. If this run also fails,
that itself becomes real evidence (this fix's assumptions -- one
`file://` URI, ending in a unique known directory name -- would need
revisiting), not a call to try to guess a fourth pinpoint fix.


### 5.30 — SARIF fix didn't work; pivoting to actually diagnosing it (2026-09-25)

5.29's regex-based, mechanism-agnostic fix shipped (commit `5a28dea`)
and the real CI result came back **identical** to before -- same two
tests, same byte-for-byte truncated diff text. That identical-ness
across three different code changes (the JSON-escape fix in 5.27, the
regex rewrite in 5.29) is itself evidence: if the actual normalized
output were changing in response to these edits, the truncated repr
GitHub shows would very likely shift at least slightly. It not moving
at all across genuinely different fixes suggests the real divergence
was never in the `project_root`/URI area this whole time -- three
rounds spent fixing a plausible-looking but wrong target, because the
only evidence available (GitHub's summary-box diff, `assert
{'$schema': '...OT_URI>/'}}}]} == {'$schema': '...T_ROOT>/'}}}]}`) was
never enough to actually tell.

Rather than propose a fourth guess, this round changes nothing about
render or normalize behavior at all -- it only makes the *next*
failure (if there is one) show the real difference. Added
`_json_diff_message()`: on a JSON/SARIF mismatch, pretty-prints both
sides with `json.dumps(..., indent=2, sort_keys=True)` and runs
`difflib.unified_diff` over them, passed as the assertion's message.
This replaces reliance on pytest's own dict-repr truncation (a head-
and-tail summary of one giant single-line repr, which is exactly what
made three rounds of this un-diagnosable from the GitHub Actions
summary box) with a real, complete, field-aligned diff that will show
up directly in the failure output -- no more back-and-forth asking for
raw logs. Verified locally: the helper produces a correct, readable
diff against a deliberately mismatched pair; golden suite still 10/10
on Linux (comparison logic itself is unchanged, only the message on
failure).

Delivered as a diagnostics-only change. Next step is unavoidable: push
this, and if Windows still fails, the unified diff in that failure
output finally shows what's actually different -- paste that (not the
GitHub summary box) and the real fix can be evidence-based instead of
a fourth theory.


### 5.31 — Found the real reason four rounds were undiagnosable: our own `cut -c1-220` (2026-09-25)

User called out the pattern directly after 5.30's diagnostics-only
round still showed the exact same truncated one-line message
("AssertionError: --- expected (golden)", cut off immediately, not
even one line of the new unified diff reaching them). That was the
right call -- rereading `ci.yml` itself (not just the test code, which
is where every prior round of this investigation looked) found the
actual cause in one line: the "List failed tests in the job summary"
step does `grep -E "^(FAILED|ERROR) " pytest.log | cut -c1-220`. Every
`FAILED` line -- assertion message included -- gets hard-truncated to
220 characters before it ever reaches the GitHub Actions summary page.
This is *this project's own CI script*, not a GitHub UI limitation,
not a pytest truncation, not anything about `_normalize()` or
`_json_diff_message()`. No fix to the assertion message, however
complete, could ever have shown up past column 220 -- 5.27 through
5.30's diagnostic improvements were all real and correct, they just
had no way to reach anyone through this one line. Confirmed via
`git log -p` reasoning (not shown here, but this line's own comment
explicitly says why it exists): added deliberately in an earlier round
specifically because "long logs are hard to copy from a phone" --
solving a real problem (this user works from a phone) by creating a
new one (no way to ever see more than 220 chars of a failure without
already knowing what to look for).

Fixed by keeping the short, phone-readable summary exactly as it was
(still genuinely useful for quick triage) and adding a real fix
alongside it instead of widening the character limit (which just
moves the same problem to a different fixed number): an
`actions/upload-artifact@v4` step, `if: failure()`, uploading the
complete, untruncated `pytest.log` as
`pytest-log-{os}-py{version}`, 14-day retention, `if-no-files-found:
warn` (so a build/install failure *before* pytest ever ran doesn't
turn into a second, confusing "artifact not found" failure on top of
the real one). The short summary now also prints one line pointing at
exactly where to find it (Summary page, Artifacts section, bottom of
the page) -- no more "check the raw log" instructions that assume the
person knows GitHub's UI well enough to find it themselves.

Verified: `.github/workflows/ci.yml` still parses as valid YAML after
the edit (checked with `python3 -c "import yaml; yaml.safe_load(...)"`
in this sandbox, since `actionlint` itself needs a Go toolchain this
sandbox does not have). Could not verify `actionlint`-specific lint
rules or that GitHub actually accepts this workflow shape without a
real push -- ordinary limitation of this sandbox, same as every other
CI-facing change in this whole saga.

**Lesson for next time a Windows-only or otherwise hard-to-reproduce
CI failure needs real diagnosis: pull the `pytest-log-*` artifact
first, before touching any code.** It will have been available this
whole time once this round's fix lands; nothing past this round should
need another cycle of "the summary was too short, try again."


### 5.32 — The real sarif bug, found from the actual log: replace-order, not Windows at all (2026-09-25)

The `pytest-log-*` artifact from 5.31 wasn't even needed in the end --
the user downloaded GitHub's own raw workflow log archive (always
available, a different mechanism from the job-summary truncation) and
found the real diff themselves:

```
-          "uri": "file://<PROJECT_ROOT>/"
+          "uri": "<PROJECT_ROOT_URI>/"
```

**This was never a Windows bug.** `_normalize()` (since 5.21) replaced
the plain absolute path FIRST and the dedicated `file://` URI match
SECOND. On Linux, `str(root)` ("/tmp/.../hybrid-project") is a literal
substring of `root.as_uri()` ("file:///tmp/.../hybrid-project/") --
both use forward slashes -- so the plain-path replace *accidentally*
already consumed the path portion inside the URI on its own pass,
leaving a half-normalized "file://<PROJECT_ROOT>/" behind; the
dedicated URI step that ran second found nothing left to match and was
silently a no-op. That accidental half-normalized string is exactly
what got captured into the golden files in 5.21 and never revisited.
On Windows, `str(root)` uses backslashes while `.as_uri()` always uses
forward slashes, so the plain-path replace never touches the URI at
all -- it survives fully intact down to the dedicated URI step, which
*does* fire there and produces a fully-normalized
"<PROJECT_ROOT_URI>/" with no "file://" left in front. Two platforms,
two different amounts of normalization applied via the exact same
code, purely because of which replace happened to run first and what
it accidentally touched -- not a Windows quirk in `Path.as_uri()` at
all, contrary to every theory in 5.27/5.29. Both of those were real,
defensible fixes for real (if secondary) issues -- the JSON-escaping
handling and the case-insensitive URI match are both still correct and
needed -- they just weren't *this* bug, which is why identical failure
text kept coming back no matter which one changed.

Fixed by making the URI match unconditional and first, before the
plain-path replace ever runs, so both platforms produce the same
`<PROJECT_ROOT_URI>/` deterministically regardless of separator style.
Verified two ways: (1) reran the golden suite locally on Linux with
the reordered function -- for the first time, `sarif.json-hybrid`/
`sarif.json-minimal` **failed on this sandbox too**, with the *exact*
diff from the Windows CI log, proving the mechanism is real and
platform-independent, not something that only manifests on a runner
this sandbox can't reach. (2) A synthetic side-by-side simulation
feeding both a Linux-shaped and a Windows-shaped `(raw, uri)` pair
through the corrected function confirmed both converge to the
identical `<PROJECT_ROOT_URI>/` output.

Regenerated `tests/golden/hybrid.sarif.json` and
`tests/golden/minimal.sarif.json` to match the new, correct, and now
*actually* deterministic output -- diffed against the previous
versions to confirm the single expected field changed and nothing
else drifted. Golden suite back to 10/10 on Linux.

**Retrospective note, for next time:** the `_json_diff_message()` work
from 5.30 was correct and is what made this instantly diagnosable the
moment real log content was available -- the four-round delay was
entirely about *reaching* that content (the job-summary's own
`cut -c1-220`, fixed in 5.31), not about the quality of the diagnostic
itself. Once the real diff was visible, the actual bug -- a replace-
order issue neither platform-specific nor exotic -- took minutes to
find and fix, not another round of theorizing.


### 5.33 — Real peak-RSS numbers arrived; the 5.26 audit's main theory is refuted (2026-09-26)

User installed GNU `time` for real (`sudo apt install -y time` on the
Kali/Termux phone -- their actual target constrained device) and ran
both the standalone `/usr/bin/time -v sarand --full` and
`scripts/benchmark_report.py` (with real peak-RSS now, not `n/a`)
against sarand itself, `bimarz`, and `bina`. First real measurement
data for item 9's "Required measurements" step -- and it contradicts
5.26's leading theory.

5.26 identified the selected renderer's in-memory string-building of
embedded source as the primary suspected memory-heavy stage, based on
code reading alone (no device to measure on at the time). Real data:

| project | `--full` peak RSS | `--no-source` peak RSS | drop | source removed from report |
|---|---|---|---|---|
| sarand | 382.1 MiB | 368.0 MiB | ~14 MiB (~4%) | ~1.45 MiB |
| bina | 267.4 MiB | 248.0 MiB | ~19 MiB (~7%) | ~180 KiB |
| bimarz | 333.8 MiB | 319.9 MiB | ~14 MiB (~4%) | ~659 KiB |

Removing megabytes of embedded source from the report barely moves
peak RSS at all. **5.26's main theory is refuted by real measurement,
exactly the outcome the Evidence-First Rule and item 9's "do not claim
OOM risk without measurement" exist to catch.** Peak RSS (250-380 MiB)
is wildly disproportionate to report content (hundreds of KiB to a few
MiB) -- something else entirely dominates, and building
`--low-memory` around source truncation (the plan going into this
round) would have solved a problem that isn't the real one.

Notably, these runs used `--skip-tests` (tests did not even execute)
and RSS was still hundreds of MiB -- ruling out `cargo test`
compilation as the sole cause. Quality/security still ran, though,
and both invoke the Rust toolchain (`cargo clippy`, `cargo audit`,
`cargo deny` for sarand/bimarz; a real memory cost independent of
report rendering) alongside several other subprocesses per language.
Leading candidate now: subprocess/toolchain overhead during the
quality and security phases, not sarand's own Python-side report
generation at all -- but this is itself an unconfirmed theory until
measured the same way 5.26's was.

**Next measurement, not yet run:** isolate which phase actually drives
peak RSS, using flags that already exist (no new tooling needed) --
`sarand --skip-tests` (baseline: scan/detect/embed only, no tool
execution), `sarand --skip-tests --quality` (quality tools only),
`sarand --skip-tests --security` (security tools only), each under
`/usr/bin/time -v`, on sarand itself (the largest, most Rust-toolchain-
heavy of the three measured projects). Whichever phase's peak RSS
approaches the full-run number is the real target for a
`--low-memory` mode -- which, if it turns out to be Rust-toolchain
subprocess overhead, is a very different feature (e.g. running
`cargo clippy`/`cargo audit` with tighter resource limits, or simply
documenting that quality/security checks are inherently memory-hungry
and unrelated to report size) than anything about source embedding.


### 5.34 — Found and fixed the real memory hog: `syft dir:.` scanning the entire working tree (2026-09-26)

Continuation of 5.33's isolation. User ran
`sarand --skip-tests --security --skip-audit` (removing cargo-audit/
cargo-deny from the mix): peak RSS 343.4 MiB -- statistically the same
as the 327.6 MiB with them included (well within phone-under-varying-
load run-to-run noise), definitively clearing cargo-audit/cargo-deny
as a memory contributor. Remaining suspects: bandit, pip-audit,
gitleaks, syft.

Reread `core/sbom.py` directly rather than requesting another
isolation round: `run_syft()` invokes `syft dir:. -o json --quiet`
(and the plain-table fallback identically) with **no exclusions at
all**. Confirmed via syft's own `--exclude` documentation
(web-searched, not guessed) that this means syft catalogs *every*
file under the project root it can reach -- `.venv/` (every installed
dev dependency's full metadata), `target/` (Rust's build directory,
routinely the largest thing in a Cargo project by far), `.git/`,
`node_modules/`, etc. -- not just the project's own declared
dependencies, which syft already gets directly from `Cargo.lock`/
`pyproject.toml`/`requirements.txt`/lockfiles. Re-walking the already-
materialized installed/compiled copies on top of that adds scan cost
without adding any package syft wouldn't already find from the
manifests. This is a strong, evidence-backed explanation for the
~328 MiB security-phase number: `target/` alone in a Rust project with
any real dependency tree is commonly hundreds of MiB to low GiB of
already-compiled objects and cached dependency sources.

Fixed by adding `_SYFT_EXCLUDE_ARGS` (a fixed set of `--exclude`
patterns for `.git`, `.venv`, `venv`, `target`, `node_modules`,
`__pycache__`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `.tox`,
`dist`, `build`, each syntactically valid per syft's own
`--exclude`-flag rules -- must start with `./`, `*/`, or `**/` for a
directory-source scan) and appending them to both `syft` invocations.
This is a correctness fix, not a feature trade-off: nothing about
*which packages* syft finds should change (they all come from
manifests it reads directly regardless), only how much filesystem it
has to walk to find them.

Updated the two existing `test_sbom.py` tests that asserted the exact
`syft` argv (they now expect `_SYFT_EXCLUDE_ARGS` appended, imported
from the module rather than hand-duplicated, so the test can't drift
from the real exclude list), and added a new
`test_syft_excludes_build_and_dependency_directories` locking in that
every one of those twelve directories is covered and every pattern
uses syntax syft actually accepts. Verified locally (this sandbox's
usual `pytest`-stub limitation, no real `pytest`/`rich`): all 9/9
`test_sbom.py` tests pass, including the new one; `test_license_policy.py`
(which also exercises `run_syft` via a fake command runner that
ignores the exact argv, so unaffected) still 18/19, the one "failure"
a pytest-parametrize stub limitation unrelated to this change.

**Not yet measured for real:** this fix has not been run on-device
with `/usr/bin/time -v` yet to confirm it actually brings the
security-phase peak RSS down from ~328 MiB toward the ~68 MiB
baseline. That is the natural next step once this lands -- if `target/`
and `.venv/` really are what syft was walking, the drop should be
large and immediately obvious; if it isn't, that's real evidence
gitleaks (or bandit/pip-audit, less likely given their normal
footprint) needs the same scrutiny next, not another guess.

Also considered, not changed: `gitleaks`'s `--source .` invocation
(`core/gitleaks.py`). Its own docstring already notes it deliberately
runs a git-history-aware scan rather than a bare working-tree walk
when `.git` exists, which inherently only sees *committed* content --
`.venv`/`target`/etc are (on any well-set-up project, sarand's own
included) gitignored and therefore never enter git history at all.
Less obviously implicated than `syft`'s unrestricted directory walk,
and no code-level evidence of a problem there yet -- left alone rather
than fixed on suspicion alone, consistent with the Evidence-First
Rule.


### 5.35 — Item 9 closed: gitleaks cleared, syft's own baseline cost is the honest remainder (2026-09-27)

Final isolation round, both tools restored to their real paths
afterward and confirmed working (`syft version`, `which gitleaks`).

Removing `gitleaks` alone (syft present, already fixed) changed
**nothing**: 186.8 MiB with both present, 186.8 MiB with only
`gitleaks` removed. Removing both together dropped to 78.3 MiB --
essentially the 67.4 MiB baseline. The only way to reconcile "removing
gitleaks alone does nothing" with "removing both drops it back to
baseline" is that `/usr/bin/time -v`'s "Maximum resident set size" is
a single peak across the whole run, not a sum -- external tools run
one at a time (not concurrently), each releasing its memory before
the next starts, so the reported number is whichever single tool's own
peak was largest. `gitleaks`'s peak is smaller than `syft`'s, so
removing `gitleaks` alone can never move the reported maximum; only
removing `syft` (the actual peak-holder) does. This reverses 5.34's
tentative "gitleaks might be the larger remaining contributor" --
wrong guess, corrected by the next measurement rather than left
standing.

**Conclusion: `syft` itself, even after 5.34's exclude fix, still
carries roughly 108-120 MiB of its own overhead** (186.8 MiB with it
vs 78.3 MiB without) reading the project's actual manifests and
building the SBOM -- likely inherent to the Go binary's own runtime
and whatever vulnerability/license metadata it loads, not a further
sarand-side misconfiguration. No code-level evidence points to another
fixable cause here, and the Evidence-First Rule cuts against inventing
one on suspicion after 5.34's real fix already delivered the large,
confirmed win (43% reduction in the security phase, ~141 MiB).

**Item 9 status: closed for this round, not via a new `--low-memory`
flag.** The backlog doc's own suggested interface ideas (`--low-memory`
flag, summary+separate-source-artifacts, intelligent truncation) were
all designed around the *wrong* hypothesis -- 5.26's code-only audit
guessed report-content/source-embedding as the driver, and 5.33's real
measurement refuted that outright (removing 1.4+ MiB of embedded
source moved peak RSS by only ~4-7%). The real fix that emerged from
following the evidence wasn't an opt-in mode at all: it was a genuine
bug (`syft dir:.` scanning `.venv`/`target` unrestricted) fixed once,
at the source, benefiting every user automatically with no flag to
remember and no report-completeness trade-off. That is this round's
"low-memory strategy" -- fix real over-broad tool invocations as
they're found, rather than build a parallel reduced-fidelity mode.
Remaining ~186 MiB peak for `--security` on a project sarand's own
size is now understood to be dominated by `syft`'s own inherent
runtime cost, documented here as an accepted, external, currently-
unfixable-without-losing-functionality cost rather than left as an
open mystery.

Not done, explicitly out of scope for now: profiling `--quality`
(176.7 MiB baseline-relative cost, never decomposed by tool) or `tests`
(the largest wall-clock phase in every run, never profiled for memory
at all since these benchmarks all used `--skip-tests`). Revisit only
if a future real report of memory pressure on a constrained device
names one of these phases specifically -- not speculatively.


### 5.36 — P1 item 5: Kubernetes/Helm/Kustomize, detection-only first scope (2026-09-27)

Next P1 item per the backlog doc's own priority order, started right
after item 9 closed. Evidence-first audit: grepped `analyzers/` and
`core/` for any k8s/helm/kustomize awareness -- CONFIRMED gap, none
exists. `YamlAnalyzer` is a plain format analyzer (lints top-level
`.yaml`/`.yml` with `yamllint`, never inspects content), so it has no
concept of a file being a Kubernetes manifest versus anything else.

Scope, following item 8's own "Cargo-only first pass" discipline:
detection only, for the two ecosystems with an unambiguous marker
file -- a Helm chart (`Chart.yaml`) and a Kustomize overlay
(`kustomization.yaml`/`.yml`). Raw Kubernetes manifests (a bare
`Deployment`/`Service`/etc. YAML has no fixed filename -- finding them
needs reading and parsing every `.yaml` in the project, not a marker-
file check) and any execution (`helm lint`, `kubeconform`, `kustomize
build`) are both explicitly deferred, matching item 8's own
representation-before-execution split.

New `core/kubernetes.py` (`detect_kubernetes(root)`), `HelmChart`/
`KustomizeOverlay`/`KubernetesInfo` in `models/results.py` (the one
canonical models module, same rule `WorkspaceInfo` already follows),
new `ReportData.kubernetes` field defaulted `None`. Walks the tree
itself (bounded to 5 levels deep, no symlink-following) pruning the
exact same build/dependency/VCS directory list `core/sbom.py`'s syft
fix uses (`.git`/`.venv`/`target`/`node_modules`/etc.) -- same
philosophy, same list: those directories only ever hold third-party or
generated content, walking them costs real time for zero signal.
Malformed `Chart.yaml` falls back to the directory name rather than
crashing or being dropped (same posture as `core/workspace.py`'s
malformed-`Cargo.toml` handling). New markdown `## Kubernetes` section
and conditional JSON `"kubernetes"` key, both only emitted when
something is actually detected -- confirmed a no-op for every existing
golden fixture (still 10/10, zero snapshot changes) the same way item
8's workspace feature was.

10 new tests in `tests/test_kubernetes.py`: empty project -> `None`,
a chart found with name+version read from `Chart.yaml`, both
`kustomization.yaml`/`.yml` extensions found, a root-level chart gets
path `"."`, all four excluded directories confirmed never searched
(decoys planted inside each, none found), malformed `Chart.yaml`
falls back correctly, and 4 renderer tests (markdown/json,
absent/present) mirroring item 8's own test shape.

Verified locally the usual way (no real `pytest`/`rich` in this
sandbox): ran the actual test functions directly, 10/10 passing;
reran the golden-report harness after, still 10/10 untouched;
`test_workspace.py`/`test_renderers.py`/`test_coverage.py` all still
clean. Proactively hand-wrapped 3 lines over ~88 characters found via
the usual `awk` scan before delivery (one in `core/kubernetes.py`'s
directory-listing comprehension, one in its `KubernetesInfo(...)`
return, one in `markdown.py`'s Helm-table-header `lines.extend`) --
same lesson from 5.23 onward, applied without needing another
ruff-format round to catch it. Still needs a real on-device
`ruff`/`mypy`/`pytest` run to close this round.

**Non-goals, explicit, for a later phase of this same backlog item:**
raw Kubernetes manifest detection (content-based, no fixed filename --
materially bigger scan, deserves its own scoped round); any
lint/validation execution once detected (`helm lint`, `kubeconform`/
`kubeval`, `kustomize build --dry-run`); Docker Compose and Makefile
detection (items 6/10 in the doc's original numbering, next after this
ecosystem is further along or explicitly reprioritized).


### 5.37 — Two on-device fixes for item 5, plus portability restructuring for a fresh conversation (2026-09-28)

**On-device fixes (item 5, Kubernetes/Helm/Kustomize):** `ruff format`
wanted `tests/test_kubernetes.py`'s `payload["kubernetes"] == {...}`
dict-literal assertion collapsed onto one line (a real fixed-content
kwargs-list, not a comment/docstring -- fixed to match ruff's own
diff, same class of miss as many earlier rounds). `mypy` flagged
`core/kubernetes.py`'s `import yaml` as untyped
(`import-untyped`) -- tracing this further than "just add
`type: ignore`" found a real gap: **`PyYAML` was never declared as a
direct dependency anywhere in `pyproject.toml`**; `import yaml` only
worked on the dev machine because PyYAML happened to already be
present as some *other* installed package's transitive dependency.
A fresh `pip install sarand` with no such transitive dependency
already on the target system would `ImportError` the first time a
Kubernetes scan ran -- a real, user-facing bug this round's own new
feature would otherwise have shipped with. Fixed properly: added
`PyYAML>=6.0` to `[project] dependencies` (not just `dev` -- this
module is part of the shipped package) and `types-PyYAML` to the
`dev` extra for mypy. Verified locally: `tests/test_kubernetes.py`
still 10/10 after the format fix; `pyproject.toml` still valid TOML
after both dependency additions (`tomllib.load`).

**Portability restructuring, at the person's request** (this
conversation has grown very long and slow; they want to continue in a
fresh one without re-deriving context): added `docs/BACKLOG.md`
(the full original backlog document, verbatim -- process, every item,
Definition of Done template, Investigation/Validation Protocol,
unchanged since adoption) and `docs/BACKLOG_STATUS.md` (a new,
actively-maintained status file: what's RESOLVED/PARTIALLY RESOLVED/
not-started against every item, in the doc's own vocabulary, with
just enough evidence cited to avoid re-deriving it -- e.g. item 8's
full npm/pnpm/Yarn/Gradle/Maven/Bazel/Nx audit results restated
concisely rather than requiring a re-read of section 5.36's original
longer version). Both files are explicitly marked temporary in their
own text -- meant to be deleted once every backlog item is resolved or
explicitly marked out of scope, with `AGENTS.md`'s own dated round
history (this section included) remaining as the permanent record
either way. Added a short pointer note at the very top of this file
(right after the binding-directive callout) so a fresh conversation
starting from `AGENTS.md` sees the pointer to `BACKLOG_STATUS.md`
before anything else, rather than needing to scroll the full round-by-
round history to reconstruct current status.

This section itself (5.37) is the last thing `BACKLOG_STATUS.md`
should need updating for once item 5's pending commit lands -- from
that point, a fresh conversation reading `BACKLOG_STATUS.md` should be
able to pick the next "Not started" item (item 6, Docker Compose, per
the doc's own priority order) without reading this file's history at
all, only consulting it if a specific past decision needs re-checking.

### 5.38 — P1 item 6: Docker Compose, detection-only first scope (2026-09-30)

Next "Not started" item in `docs/BACKLOG_STATUS.md` after item 5.
Evidence-first audit: grepped `analyzers/` and `core/` for compose
awareness. The only traces are `YamlAnalyzer._ENTRY_POINTS`
(`docker-compose.yml`/`.yaml` surfaced as entry points) and the fact
that `YamlAnalyzer` lints top-level YAML with `yamllint` and never
reads content. So: `compose.yaml` (the current Compose Specification
name), override files (`docker-compose.override.yml`), and anything
below the project root are all invisible, and the report cannot say
which services a project defines. CONFIRMED gap, representation only
(no execution gap is claimed -- no compose tool is in the roster).

Scope, same discipline as items 8 and 5: detection only. Compose files
have a small fixed naming convention, so the name is the marker
(`^(docker-)?compose(\.<segment>)?\.ya?ml$`, anchored both ends so
`my-compose.yml`/`compose.yml.bak` never match) -- no content sniffing
of arbitrary YAML. Per file: top-level `services` mapping read for
name, `image`, and whether a `build` key exists, in file order. A
malformed, undecodable, oversized (>1 MiB, not parsed) or oddly-shaped
file is still reported with an empty services list rather than dropped
or crashing.

New `core/compose.py` (`detect_compose(root)`); `ComposeService`/
`ComposeFile`/`ComposeInfo` in `models/results.py`; new
`ReportData.compose` defaulted `None`; wired in `cli.py` next to
`detect_kubernetes`. Walk is bounded to 5 levels, no symlink-following
(files or dirs), and prunes the same build/dependency/VCS list as
`core/kubernetes.py` and the syft fix. That list is deliberately
copied locally rather than imported from `core/kubernetes.py`
(self-contained-module convention); if a third module ever needs it,
that is the moment to extract a shared constant, not before. New
markdown `## Docker Compose` section and conditional JSON `"compose"`
key, both emitted only when something is detected -- no effect on any
existing golden snapshot (10/10 unchanged).

15 new tests in `tests/test_compose.py`: none -> `None`; services with
image/build read in file order; all six supported names found;
lookalike names rejected; nested posix relative path; four excluded
dirs never searched; depth bound; malformed YAML; non-dict/odd shapes
(list root, `services` as list, null service, non-string image);
undecodable bytes; 4 renderer tests (markdown/json, absent/present).

Verified in the sandbox (no real `pytest`/`rich`/`ruff`/`mypy`; ran
test functions directly with stubs): 63/63 across compose, kubernetes,
workspace, golden, renderers. Full-suite comparison against the
pristine input zip showed the identical set of sandbox-only failures
before and after (stub `pytest.raises(match=)`, git/tool-dependent
tests) -- nothing new introduced. Still needs a real on-device
`ruff format --check`/`ruff check`/`mypy`/`pytest` run to close this
round.

**Non-goals, explicit:** any execution (`docker compose config`,
`hadolint`, `dclint`); `include:`/`extends:` resolution; merging
override files into one effective model; Dockerfile detection;
`html.py`/`text.py`/`sarif.py` sections; README mention (same
"premature for detection-only" call as items 8 and 5).

### 5.39 — P1 item 7: Makefile, detection-only first scope (2026-09-30)

Next "Not started" item after item 6 (verified on-device with small
local fixes by the user). Evidence-first audit: the only prior trace
is `constants.py`'s project-marker table mapping the exact filename
`Makefile` to `("Generic", "unknown", "make")` (plus `ai_summary.py`
ranking `makefile` as a high-priority file to read). No content was
ever read: no targets, no default target, `GNUmakefile`/`makefile`
unrecognised, Makefiles below the root invisible. CONFIRMED gap,
representation only.

Scope, same discipline as items 8/5/6: detection only. `make` is never
run (not even `make -n`): a Makefile is arbitrary shell, so executing
it during a scan is neither safe nor deterministic. Parsing is a
deliberate line-based heuristic, not a Make implementation: backslash
continuations joined; recipe lines, comments, conditionals, includes,
`define..endef` bodies and variable assignments (`=`, `:=`, `::=`,
`?=`, `+=`, `!=`) skipped; pattern rules (`%`), special `.`-targets
and `$`-expanded names not listed; `.PHONY` collected; default =
`.DEFAULT_GOAL` else first listed target. Per directory only the file
GNU make itself would pick (`GNUmakefile` > `makefile` > `Makefile`).

New `core/makefile.py` (`detect_makefiles`), `MakefileEntry`/
`MakefileInfo` in `models/results.py`, `ReportData.makefile`, wiring
in `cli.py`, markdown `## Makefile` and conditional JSON `"makefile"`
key. Same 5-level bound and skip-dir list as items 5/6 (local copy,
per the 5.38 convention). New this round: report-size guards (25
files, 100 targets/file, 1 MiB parse limit) because C monorepos can
carry hundreds of Makefiles and thousands of object-file targets --
item 9's concern -- with `total_files`/`total_targets` kept and
rendered as "(+N more)" so nothing is silently lost.

Delivered as `apply_makefile_v1.py` (anchored edits + new files)
rather than whole replacement files, because the user had made local
fixes to the files it touches after item 6; the script aborts without
writing anything if an anchor is missing and is idempotent.

**Non-goals, explicit:** `make` execution; `include` resolution;
`.mk` fragment files; macro/conditional evaluation; per-target
`## help` descriptions; `html.py`/`text.py`/`sarif.py` sections;
README mention.

### 5.40 — P1/P2 item 11: Hybrid project model, representation only (2026-10-01)

Items 6 and 7 closed first: verified on-device (ruff/mypy/834 tests
green), committed as af86c72, tagged v0.6.8 (v0.6.7 was already the
Kubernetes round, af8c0c2).

Evidence-first audit of item 11 against a hand-built hybrid fixture
(`backend/` FastAPI, `frontend/` React, root compose building both,
CI workflow, Makefile, Kustomize overlay, `docs/`). Findings:
`detect_project()` reads root markers only and keeps a single primary
language -- the fixture came out "Generic / unknown / make", with
neither Python nor Node.js detected. Analyzer `matches(root)` is also
root-only, so only GitHub Actions, YAML and Markdown ran: **no tests,
quality or security for either real component.** Nothing expressed
that compose services build `backend/`/`frontend/`. The execution gap
is larger than the representation gap, but the backlog doc scopes this
item to "representation and context, not a universal architecture
detector", so it is recorded separately in BACKLOG_STATUS.md and NOT
fixed here (needs a design decision on per-component analyzer runs and
result attribution).

Implemented the representation only: new `core/components.py`
(`detect_components(root, kubernetes, compose, makefile)`), `Component`/
`ComponentLink`/`ComponentsInfo` in `models/results.py`,
`ReportData.components`, wiring in `cli.py` after the makefile step,
markdown `## Project Components` (placed right after Detected Project)
and conditional JSON `"components"` key. A *view* over evidence: adds
no findings (DoD "no duplicate findings"), runs nothing, never touches
`primary_language`/health/issues/existing sections. Roles only from
concrete markers: application (`PROJECT_MARKERS`, 3 levels, weak
markers `requirements.txt`/`setup.cfg` alone don't count below the
root -- `docs/requirements.txt` is the classic false positive);
infrastructure (existing Helm/Kustomize/Compose results + `*.tf` +
`Dockerfile` dirs); ci (GitHub Actions/GitLab/Jenkins/CircleCI/Azure
markers); documentation (non-empty root `docs/`); configuration
(existing Makefile results). `kind` frontend/backend only from
declared dependencies (package.json / pyproject / requirements.txt),
never from directory names; conflicting hints -> empty. Skips
`tests`/`fixtures`/`examples`/`vendor`-style dirs for precision.
One relationship: Compose service `build:` context resolving to a
detected application directory ("builds"); components.py re-reads the
compose files itself (self-contained-module convention) so the compose
model/JSON from 5.38 is unchanged.

Emitted only for a hybrid project: >=2 application components with
different (languages, kind) signatures (a Cargo/npm workspace of
same-kind members is not hybrid), or an application plus
Helm/Kustomize/Compose/Terraform. A plain project with Dockerfile, CI
and docs gets nothing new. Caps 50 components / 100 links with true
totals kept and rendered as "N more ... not shown".

Delivered as `apply_components_v1.py` (anchored edits + new files), the
same mechanism as 5.39, because the user's checkout has local fixes.

**Non-goals, explicit:** per-component analyzer execution (see
BACKLOG_STATUS.md); database/service-role inference; relationships
beyond Compose builds; Nx/Turborepo/Bazel graphs; changing
`detect_project()`; `html.py`/`text.py`/`sarif.py` sections; README.

### 5.41 — CI py3.10 mypy failure: `tomllib` import in components.py (2026-10-01)

The item-11 round (`fbf8e24`) was green locally (Python 3.14: ruff,
mypy, 853 tests) and on every CI job except ubuntu py3.10, where mypy
reported `Cannot find implementation or library stub for module named
"tomllib"` at `core/components.py`. Cause: the new module used
`try: import tomllib / except ModuleNotFoundError: import tomli`, which
mypy (targeting 3.10) cannot resolve, while `core/workspace.py` and
`core/license_policy.py` already used the `sys.version_info >= (3, 11)`
form. Fixed by switching to that form. Lesson: any new module that needs
a TOML parser must copy the `sys.version_info` pattern -- a local run on
a newer Python can never reveal this, only the py3.10 CI job can.

### 5.42 — Per-component analyzer execution for hybrid projects (2026-10-01)

Closes the gap recorded in BACKLOG_STATUS.md ("Root-only detection and
analyzer matching") that the item-11 audit uncovered: on a hybrid repo
(`backend/pyproject.toml` + `frontend/package.json` + root compose)
only the GitHub Actions/YAML/Markdown analyzers ran, so neither real
component got tests, quality or security checks. Go-ahead given by the
user ("A, then B") after the design question at the end of 5.40.

New `core/per_component.py`; `cli.py` calls `plan_component_runs(...)`
after `matching_analyzers` and appends `run_component_{tests,quality,
security}` results to the existing three lists. The `LanguageAnalyzer`
protocol is untouched (plugins unaffected): every analyzer already
takes its working directory as `root`.

Rules, each chosen to make duplicate findings impossible by
construction: (1) only for hybrid projects (driven by 5.40's
`ComponentsInfo`; ordinary projects behave exactly as before);
(2) **root first, never both** -- an analyzer that matches the root is
not re-run in a component, because root-level ruff/pytest/cargo already
recurse into subdirectories and Cargo workspace members; (3) outermost
component wins for nested components; (4) results are relabelled
`"<component>: <kind>"` and each issue's `source` likewise
(`CommandResult.kind` is display-only downstream -- only health's
skipped-check names and the markdown/html headings read it, checked by
grep); (5) at most 8 components, the rest become one skipped
"components" result, never silently dropped; components run one after
another (analyzers within one run concurrently, as at the root) to keep
peak memory close to a normal run on 2 GB machines; (6)
`SARAND_NO_COMPONENTS=1` disables it -- an env var, like
`SARAND_SKIP_AUDIT`, so no new CLI option, README-sync test change or
plugin-contract change.

Known limitation, documented not hidden: a root analyzer that does not
cascade (e.g. a root `npm test` in a repo whose root package.json has no
workspaces) still hides components of that same analyzer -- rule 2 is
the price of "no duplicates". Health score for a hybrid project now
includes the component results (intended: it finally reflects real
checks) so its score can change after this round.

Tests: 13 in `tests/test_per_component.py`, including the exact audit
scenario with the real builtin analyzers on the hybrid fixture
(Python runs in `backend`, Node.js in `frontend`, nothing that matched
the root runs twice). Not covered: gitleaks/syft/lockfile (project-wide,
unchanged).

### 5.43 — P2 item 12: Quick Context, the L2 layer (2026-10-01)

Per the backlog doc: context layers, not model presets; no redesign on
subjective preference. Evidence-first audit on a REAL report (sarand
scanning itself: 1.6 MB, ~410K tokens by chars/4) and the golden
fixtures:

- The existing "AI Summary" (L1) is orientation only. It has no
  test/quality/security status, no critical findings, no risks, no
  components. Those exist elsewhere in the report, after Environment,
  Git and the TODO table, which is unbounded under `--full`.
- The "Suggested reading order" was misleading: its first 40 entries
  were 33 alphabetically ordered analyzer plugins -- each bucket kept
  scan order and only the substrings "analyzers"/"scanners" (names from
  sarand's own layout) promoted files, so `cli.py` and `core/` never
  appeared. Fixed minimally in `suggest_reading_order`: shallow paths
  first within each bucket (classification untouched).
- Frameworks and an inferential risk model are not in the report data,
  so they are NOT invented ("exact fields must be based on current
  report data").

New `core/quick_context.py`: `build_quick_context(data)` -> a
`QuickContext` dataclass; a pure function of `ReportData` (no clock, no
environment, stable ordering) that never mutates it and adds no
finding. Rendered by `_render_quick_context` as `## Quick Context`
before "Detected Project" in the Markdown report, and as
`quick_context` (second key) in JSON. HTML/text unchanged on purpose.
No model change and no cli.py change: renderers compute it.

Size budget (documented, pinned by test): every list capped, every
string clipped to 120 chars, dropped items counted as "(+N more)";
worst case ~6 KiB (~1.5K tokens), typical 1-2 KiB (~250-500 tokens).
Important findings preserved: failed checks, health critical failures,
known issues, tool error/warning counts, skipped checks, secret-pattern
COUNT (never paths or content), excluded-file count, git dirty/behind.

Golden snapshots `*.md` and `*.json` for both fixtures were regenerated
(`SARAND_UPDATE_GOLDEN=1`); the diff is exactly the new block (+ the
JSON key). Shipped inside the delivery zip.

**Non-goals, explicit:** frameworks; inferential risks; L3/L4;
HTML/text sections; model-specific presets; README mention.

### 5.44 — P2 item 13: distribution and installation (2026-10-01)

Backlog: investigate per channel, separate availability / reliability /
optional dependencies / docs, and do not treat an unpublished AUR draft
as critical. Evidence from the repo (PyPI state cannot be checked from
the sandbox; the README says it is not published):

- **Versioning was broken.** `pyproject.toml` and `Cargo.toml` said
  0.6.0 while tags reached v0.6.10, so `sarand --version` reported 0.6.0
  for every build and CHANGELOG stopped at 0.6.0. Tags were created by
  hand on commits that never carried their own version.
- **The AUR draft was stale and wrong:** `pkgver=0.1.1` and no
  `python-yaml` in `depends`, i.e. the exact undeclared-PyYAML failure
  `pyproject.toml`'s own comment describes, on a clean Arch install.
- **The existing CI installs the wheel into an environment that already
  has all dev dependencies,** so a missing runtime dependency cannot
  fail there. That is why the PyYAML omission survived.
- README's Termux fallback (`pip install -e .` "runs on the pure-Python
  fallback") is doubtful: the build backend is maturin, which compiles
  the Rust crate. UNVERIFIED -- needs a run without cargo on a device
  before the README is touched.

Changes: `scripts/release.py` (`bump X.Y.Z` edits pyproject, Cargo.toml,
the `sarand_core` entry of Cargo.lock and `pkgver`, requires a
CHANGELOG heading, a clean tree and an unused tag, then commits;
`tag` creates the annotated tag; neither pushes -- tag only after CI is
green, as in 5.41); `scripts/smoke_install.py` + a CI step after the
wheel install (fresh venv, wheel only, `--version` equals pyproject,
`--doctor` exits 0, Helm scan works); PKGBUILD gets `python-yaml`;
CHANGELOG entry 0.6.11 (0.6.1-0.6.10 never had entries; it summarises
the known user-visible changes and points at `git log`);
`tests/test_distribution.py` pins version agreement across all five
places and AUR dependency coverage (a new runtime dependency fails the
test until it is mapped to an Arch package).

The smoke step runs in CI for the first time with this commit and could
not be executed in the sandbox (no network, no cargo/maturin); only its
helpers and the CLI calls it makes (`--version`, a Helm scan) were run
locally. Treat the first CI result as its real test.

**Non-goals, explicit:** PyPI publishing and a wheel-matrix workflow;
the exact `filelock==3.32.3` pin (harmless under pipx, a conflict risk
for `pip --user`/distro packaging -- review separately); README Termux
text; AUR publication.

### 5.45 — P2 item 14: plugin system maturity (2026-10-01)

Backlog: investigate the existing `sarand.analyzers` entry-point
mechanism before changing it; "not mature merely because entry points
exist". Findings on the pre-change code:

1. **Load-time isolation only.** `discover_analyzers` caught import and
   instantiation errors, but `matches()` ran bare in `matching_analyzers`
   and the `run_*_concurrently` helpers use `asyncio.gather` without
   `return_exceptions`. One plugin raising anywhere crashed the run and
   discarded all other analyzers' results.
2. **Incomplete documented contract.** README listed 4 methods; the
   registry calls `run_security` too -> `AttributeError` in the security
   phase for any plugin written from the README.
3. **No version compatibility** although the protocol had already grown
   once.
4. **Duplicate names:** the README's own example (a Zig plugin) clashes
   with the built-in Zig analyzer and would run every check twice.
5. No tests of discovery or failure isolation, no example, no docs.

Fix keeps the author-facing protocol unchanged: new
`analyzers/plugin_adapter.py` wraps every plugin instance
(`PluginAnalyzer`): `matches`/`entry_points` swallow exceptions;
`run_*` turn an exception, wrong type or invalid list item into a single
SKIPPED `CommandResult` named `"<plugin> plugin: <phase>"` -- visible in
the report, listed by health as a skipped check, never a failing test of
the user's project (a returncode-only failure would have lowered health
for a plugin bug). `run_security` is optional. `adapt_plugin` rejects
(with a logged reason) a missing/blank `name`, a missing required method
or an `api_version` newer than `PLUGIN_API_VERSION` (new constant in
`analyzers/base.py`, = 1; adding optional members does not bump it).
`discover_analyzers`: stable order by (entry-point name, value), first
name wins (case-insensitive) against built-ins and earlier plugins,
unreadable metadata tolerated. Built-ins are deliberately NOT wrapped.

Public plugin surface (documented, everything else may change):
`LanguageAnalyzer`, `PLUGIN_API_VERSION`, `CommandResult`, `Issue`,
`make_command_result`, `run_cmd_async`. Docs: `docs/PLUGINS.md` and
`docs/PLUGINS.fa.md` (contract table, lifecycle, isolation, version
policy, author workflow incl. `pipx inject sarand ./plugin` -- a plugin
in another environment is invisible -- and how to verify discovery);
README EN/FA now list the 5 methods and link them. Example:
`examples/sarand-plugin-justfile` (`just test`).

Tests (`tests/test_plugins.py`): REAL discovery through a temporary
dist-info + entry_points.txt on `sys.path` (not a mock), isolation at
every phase and for sync/wrong-type/invalid-item returns, other
analyzers keep their results through `run_*_concurrently`, optional
`run_security`, version gate, duplicate names, stable order, and the
example plugin against the documented contract.

Known limits, documented: no timeout for non-subprocess awaits, no
sandboxing, no `--doctor` plugin listing (verification uses a Python
one-liner or `sarand --verbose`), crashes inside built-in analyzers are
still unisolated (they are trusted code; revisit if one ever bites).

### 5.46 — P3 item 15: PDF and report portability (2026-10-02)

Backlog: investigate whether PDF output is robust across environments;
"PDF should remain optional"; failures must be clear and the Markdown
report must stay available. Audit of the pre-change pipeline
(`renderers/pdf.py`, the PDF branch of `cli.run`):

1. **A failed PDF discarded the scan.** `cli.run` printed the error,
   returned 1 and wrote nothing; the report only existed in memory, so
   minutes of tests and checks were lost. Violates the Markdown DoD.
2. **Misleading failure text.** The fall-through always said "No PDF
   engine found. Install one" even when an engine WAS found and failed
   (the real stderr was dropped).
3. **pipx-injected WeasyPrint was invisible.** Discovery was
   `shutil.which` only; pipx keeps a venv's scripts off PATH, so
   `pipx inject sarand weasyprint` (the natural fix for a pipx install)
   could never work.
4. **No PDF path was tested.** The one real-PDF test `return`ed silently
   when no engine existed, i.e. passed vacuously on every CI platform.

Changes: `renderers/pdf.py` rewritten around `_run_engine` (exit 0 AND a
file starting `%PDF-`, timeout and `OSError` handled, partial file
removed, "pango"/"cannot load library" stderr gets a system-library
hint) and `_weasyprint_command` (PATH, then the script beside
`sys.executable`, then `python -m weasyprint`); `render_to_file` returns
either install guidance (nothing installed) or every failing engine's own
reason; `available_engines()` for diagnostics. Engine order unchanged
(wkhtmltopdf first). `cli.py`: new `_write_pdf_fallback` writes the same
report as Markdown beside the intended PDF path and keeps going; the run
still exits 1 because the requested artifact does not exist, so scripts
notice (`pdf_failed` threads through to the final `return`). Existing
tests hardened: the no-engine test also stubs `_weasyprint_command`
(else a machine with WeasyPrint importable breaks it) and the vacuous
`return` became `pytest.skip`.

Tests (`tests/test_pdf_pipeline.py`): hermetic fake `weasyprint` package
run through the real interpreter (`python -m weasyprint`) on every OS:
success, crash (own error + Pango hint, not "no engine"), non-PDF output,
exit-0-without-file, timeout, engine fallthrough and combined messages,
discovery order, `available_engines`, and two `cli.main` runs (failure ->
Markdown fallback + exit 1; success -> only the PDF + exit 0).

Deliberately NOT done: a real PDF engine in CI (Debian/Ubuntu's
wkhtmltopdf is built without the patched Qt and may need an X server --
unverified, and a CI failure for environmental reasons is worse than the
gap), `--doctor` still probes PATH only, Termux/Android verification
(documented as unverified), a pure-Python backend.

### 5.47 — `--doctor` and WeasyPrint discovery (2026-10-02)

Follow-up recorded as a non-goal in 5.46: the doctor's WeasyPrint row
probed `shutil.which` only, while `--format pdf` (5.46) also looks beside
the Python interpreter and for the importable module. After
`pipx inject sarand weasyprint` the doctor therefore said "not found"
while PDF export worked. `_tool_check` now asks
`renderers.pdf.available_engines()` for the `weasyprint` row, so there is
one definition of "available". The row's fix text names `pipx inject` and
the Pango system library. Other tools are unchanged. Caveat: a machine
where WeasyPrint is importable will now report it present even when
nothing is on PATH (correct, and what the renderer would use).

### 5.48 — Backlog first pass complete (2026-10-04)

Every item of the 2026-09-22 backlog has an evidence-first audit and a
first-scope delivery (5.37 to 5.47), or is recorded out of scope with its
reason. `docs/BACKLOG_STATUS.md` had gone stale (it still said latest tag
v0.6.6, called finished rounds "not yet committed" and P2/P3 "not
started"), and its own header said to delete it once the backlog was done.
It was rewritten, not deleted, because four follow-ups are real CONFIRMED
gaps (npm/pnpm/Yarn workspaces, root analyzers that do not cascade into
components, root-only `detect_project()`, and tagging without a green-CI
check). `docs/BACKLOG.md` is kept on purpose for the same reason: the first
three follow-ups continue items 8 and 11 and their Definition of Done lives
only there. Delete both files once the follow-ups are done or dropped with a
recorded reason. Source docstrings that cite `BACKLOG_STATUS.md` stay valid.

### 5.49 — Release safety: `release.py tag` checks CI (2026-10-04)

Follow-up 4 of the backlog status. Three tags were created before CI had
finished on their commit (v0.6.10, v0.6.12, and v0.6.11 within minutes);
v0.6.10 sits on a commit whose Windows job was red. Telling the person to
wait did not hold, so the script now enforces it. `scripts/release.py tag`
asks the GitHub CLI for the recent runs (`gh run list --json
databaseId,headSha,status,conclusion,name`) and refuses unless every
workflow that ran for exactly `HEAD` has finished with `success`. Rules,
all in the pure function `ci_verdict` (no network): only runs for this
commit count; for a workflow that ran more than once the newest run decides
(a green re-run after a red run is accepted, a red re-run after a green one
is not); no run at all means "not pushed or CI not started" and blocks;
queued, waiting and in-progress block; any conclusion other than `success`
(failure, cancelled, timed_out, skipped, neutral) blocks. The gate fails
closed: `gh` missing, offline, unauthenticated or returning garbage stops
the tag with the reason and names the escape hatch. `--skip-ci-check`
overrides it and prints a warning; `--dry-run` still runs the check.
The version-file check, clean-tree check and changelog check are unchanged.

Tests (`tests/test_release_ci_gate.py`, hermetic: `subprocess.run` is
patched, `gh` is never executed): verdict rules incl. re-runs, other
commits and multiple workflows; `fetch_runs` parsing and every failure
mode; `require_green_ci` refusal text, fail-closed and skip; flag wiring.
Also checked end to end in a throwaway git repo with a fake `gh` on PATH.

Not covered: `gh run watch`-style waiting (the person re-runs the command),
required status checks on the branch (a GitHub setting, not this script).

### 5.50 — Follow-up 1: npm / Yarn / pnpm workspaces (2026-10-04)

Item 8's next phase, from the Definition of Done in the retired-but-kept
backlog: workspace detection for the next ecosystems, root/workspace
relationship represented, duplicate execution prevented, root vs workspace
findings distinguishable, health aggregation defined, fixtures, regression
tests, unsupported models documented.

**Audit** (a fixture per model against v0.6.12): npm and Yarn workspaces
(`"workspaces"` array or `{"packages": [...]}`) and pnpm workspaces
(`pnpm-workspace.yaml`) all gave `detect_workspace() == None`, plain Node.js,
`npm test` at the root only -- and `npm test` at the root runs the root's own
script, it does not reach the packages. So no member got tests or lint
(CONFIRMED execution gap). A pnpm workspace with no root `package.json`
matched no analyzer but YAML: nothing ran at all. Per-component execution
(5.42) did not help: it only runs for hybrid projects (a monorepo of same-kind
packages is not one) and never re-runs an analyzer that matches the root.

**Change.** New `core/node_workspace.py`: `detect_node_workspace` resolves
members from the declared globs (`*`, `**`, `?`, `!negation`) with its own
bounded walk (6 levels, never `node_modules`/VCS/build dirs, no symlinks) and
returns the existing `WorkspaceInfo` with kind `npm`, `yarn` or `pnpm`;
`workspace.py` calls it after the Cargo detector, so the Markdown and JSON
workspace sections work unchanged. `root_script_cascades` recognises a root
`test`/`lint` script that already fans out (`--workspaces`, `-ws`,
`pnpm -r/--filter`, `yarn workspaces`, `turbo`, `nx`, `lerna`, `wireit`;
`pnpm -w` = root only is deliberately not one). `core/per_component.py`
takes the workspace as a fifth argument (default None, old callers
unchanged), `ComponentTarget` gained `phases`, `ComponentPlan` gained
`omitted_members`. Members run the Node.js analyzer's tests and lint inside
their own directory, labelled `<member>: <check>`.

**Duplicate prevention**, all pinned by tests: a fanning-out root test script
drops the members' test phase; a fanning-out root lint script or any root
ESLint config drops their lint phase (root `eslint .` already recurses);
nothing is planned when both are dropped; the security phase is never given
to a member (`npm audit` at the root reads the single workspace lockfile);
a member that is also a hybrid component is merged into one target so each
analyzer runs once; at most 20 members run (true count of the rest reported
as a skipped `workspace members` result); `SARAND_NO_COMPONENTS=1` disables
members too.

**Health aggregation rule** (was undefined): member results join the same
flat result lists as the root's, each check counted once, one repository
score, no per-package score. A failing member suite lowers the shared test
ratio and adds the usual critical entry (test:
`test_health_counts_each_check_once_in_one_repository_score`).

Verified beyond unit tests: the real CLI on an npm workspace fixture printed
`npm test`, `packages/a: npm test` and `packages/b: npm test`, all passing,
plus the Workspace section. `docs/WORKSPACES.md` / `.fa.md` document the model,
the rules and the unsupported cases; README EN/FA link to them.

**Not covered, recorded:** a repo with both a Cargo and a Node workspace
(Cargo wins, single `WorkspaceInfo`); package-manager-specific commands
(members are still tested with `npm test`, also in pnpm/Yarn repos, and
`build system` still says `npm` for them); Lerna/Rush/Bolt without one of the
three declarations; Nx/Turborepo task graphs; per-package scores; Gradle and
Maven modules.

### 5.51 — Follow-up 3: "Detected Project" on hybrid repositories (2026-10-05)

`detect_project()` is root-only (it also decides which analyzers match the
root, so it stays that way). Audit on the hybrid fixture (`backend/` FastAPI,
`frontend/` React, root compose and Makefile), run against v0.6.13: with only
a `Makefile` at the root the section said primary language `Generic`, type
`unknown`, languages `['Generic']` -- neither Python nor Node.js -- while
`Project Components` and Quick Context, two sections later, listed both. With
a root `pyproject.toml` added it said `Python` but listed
`['Python', 'Generic']`: the frontend's Node.js was missing from "All detected
languages". CONFIRMED, description only (what runs was fixed in 5.42 and 5.50).

New `core/detection_refine.py::refine_detection(detection, components)`,
called in `cli.py` right after the component view is built, so the status
line, every renderer and Quick Context all see the corrected value. It
corrects the description only, for hybrid projects only (others get the very
same object back): component languages are appended without duplicates and
the placeholder `Generic` is dropped; a real root language stays primary (the
root's own marker is the strongest evidence); with none (`Generic`/`Unknown`)
no component is arbitrarily promoted -- the label lists them (`Python +
Node.js`, max 3 then `+N more`) and the type says what each part is (`hybrid:
backend (Python), frontend (Node.js)`, max 4 parts); the build system is
untouched (`make` stays `make`); component markers are appended as
`path/marker` (`backend/pyproject.toml`) so each language claim is traceable
(max 20). Input objects are never mutated.

Tests (`tests/test_detection_refine.py`): the audited case, root-language case,
non-hybrid identity, infrastructure-only components, no mutation, label and
marker caps, root component without prefix, and a real `cli.main` run whose
report is checked end to end. Golden snapshots are unaffected (they build
`ReportData` by hand).

**Not covered:** picking a "main" component, component entry points, and any
change to which analyzers match; `build system` still says `npm` for pnpm and
Yarn repos.

### 5.52 — Follow-up 2: nested packages when the root matches the same analyzer (2026-10-06)

The planner's rule "an analyzer that matches the root is never re-run in a
component" (5.42) is what prevents duplicate findings, but it assumes the
root run covers the subdirectories. It does for Python (pytest and ruff
recurse). It does not for three tools whose root run stops at its own package
boundary: `npm test` (Node.js), `go test ./...` (a nested `go.mod` is a
separate module) and `cargo test --all` (workspace members only).

**Audit** (four hybrid fixtures, each with a root compose file so the project
counts as hybrid, run against v0.6.13): Node root with a React `web/` and an
Express `api/`; Go root with a nested module; Rust root with a nested crate
that is not a workspace member; and a Python control. The plan was EMPTY for
all four -- the nested Node, Go and Rust packages were never tested, linted or
audited, while the Python control was (correctly) covered by the root.

**Change** (`core/per_component.py` only; no model or CLI change):
`_NON_RECURSIVE = (NodeAnalyzer, GoAnalyzer, RustAnalyzer)`. These analyzers
are now also planned in nested component directories even when they match the
root, unless the root already covers the directory (`_covered_paths`): a Node
workspace member (that path is planned separately with its own restricted
phases), a Cargo workspace member, or anything at all when the root has a
`go.work`. For Node the phases come from `_node_phases`: root `test` fan-out
drops `tests`, a root `lint` fan-out or root ESLint config drops `quality`
(same rules as 5.50); `security` stays because a separate package has its own
lockfile. Targets are keyed by (directory, phases), so a directory can hold
two targets (the Node one with its restricted phases plus the ordinary one),
and each analyzer still runs at most once per phase; the member and component
caps now count distinct directories, not targets. Python is unchanged.

**Also fixed (found while writing the tests):** with a pnpm workspace and no
root `package.json` the Node analyzer did not match the root, so the hybrid
plan added it with all phases and the merge unioned `security` into the
member target -- `npm audit` per member, which 5.50 says never happens.
Node is now skipped in the component pass at member paths.

Tests: `tests/test_nested_packages.py` (11) and one updated test in
`tests/test_node_workspace.py` (it now collects targets per directory and
asserts the member phases). **Not covered:** a project that is not hybrid
(`detect_components` returns None, so a Node root with a standalone nested
package of the same kind is still not run); Go modules listed in a `go.work`
(treated as covered); Maven/Gradle nested builds (the root build is assumed to
cover its modules).

### 5.53 — Package-manager awareness for Node projects (2026-10-07)

Follow-up from the workspace round (5.50), which had recorded "`build system`
still says `npm` for pnpm/Yarn repos". Audited with a pnpm, a Yarn and a
lockfile-less Node fixture against v0.6.14, through `NodeAnalyzer` and
`detect_project`:

1. `build system` was `npm` for all three (every `package.json` maps to
   `npm` in the marker table): wrong in Detected Project, Quick Context, text
   and HTML.
2. **A false security failure.** With `--security`, `npm audit` ran
   unconditionally and exited 1 with `ENOLOCK` ("requires an existing
   lockfile") for all three. It was recorded as a FAILED check, not skipped,
   so it lowered the health score and appeared in Quick Context's Risks, with
   nothing wrong in the project. `npm audit` only reads `package-lock.json` /
   `npm-shrinkwrap.json`.

New `core/node_pm.py`: `node_package_manager(root)` (`packageManager` field
first, then `pnpm-lock.yaml`, `yarn.lock`, `bun.lock`/`bun.lockb`,
`package-lock.json`/`npm-shrinkwrap.json`, then a root `pnpm-workspace.yaml`,
else `npm`); `refine_build_system(detection, root)` corrects only the label,
and only when it says `npm` or (pnpm workspace file present) nothing was
detected -- other build systems and every other field are untouched, and the
same object comes back when nothing changes; `audit_skip_reason(root)` is
`None` when a lockfile `npm audit` understands exists, else a sentence naming
the real reason and the right command (`pnpm audit`, `yarn npm audit` /
`yarn audit`, `npm install`). `NodeAnalyzer.run_security` returns a SKIPPED
`npm audit` result with that reason instead of running (npm-missing is still
reported first); `cli.py` calls `refine_build_system` right after
`refine_detection`. Skipped, not failed, is the honest classification: health
already lists skipped checks and lowers confidence for them.

**Deliberately not changed -- test and lint commands.** Root and members are
still run with `npm test` / `npm run lint`. That works in pnpm and Yarn
repositories (scripts only call binaries in `node_modules/.bin`), while
switching to `pnpm`/`yarn` would turn into a skipped check on every machine
without them. `pnpm audit` / `yarn audit` are not run either (flags differ per
Yarn major; needs the tool and the network).

Tests: `tests/test_node_pm.py` (15) -- detection from every lockfile and from
`packageManager` (which wins, and falls back when unknown or malformed), the
label refinement and its non-effects, the pnpm-only root, every skip message,
the analyzer skipping vs still auditing with a `package-lock.json`, npm-missing
precedence, and a real `cli.main` report showing `Build system: pnpm`.

Not covered: Deno, Bun-specific test runners, `.yarnrc` Plug'n'Play
specifics, a monorepo whose members use a different package manager than the
root.

### 5.54 — Session handoff (2026-10-08)

For whoever (person or assistant) opens this repository in a new session.
Nothing here is new behaviour; it collects what the 5.37 to 5.53 rounds
taught about *how* work on sarand is done.

**Where things stand.** Latest release v0.6.19 (tag on the release commit;
the tag command refuses unless CI is green). It contains the package-manager
round (5.53, `core/node_pm.py`), the nested-package rounds for projects that
are not hybrid (5.55, 5.56), the Node 24 CI actions (5.57), the model of
every workspace of a repository (5.58), the per-package results table (5.59),
the Kubernetes analyzer and raw manifests (5.60), the Maven / Gradle
structure (5.61) and the PyPI publication as `sarand-cli` (5.62 to 5.65).
Nothing is unreleased at the time of writing.
`docs/BACKLOG_STATUS.md` is the authoritative list of what remains and of
what is deliberately out of scope; do not re-audit what it marks done.
`docs/BACKLOG.md` is kept only until the follow-ups in the status file are
finished (its Definition of Done for the monorepo and hybrid items lives
there); then delete both. Versions live in `pyproject.toml`, `Cargo.toml`,
`Cargo.lock` (`sarand_core`) and `pkgs/aur/PKGBUILD`; `scripts/release.py`
and `tests/test_distribution.py` keep them equal.

**Working loop.**
1. Read the real code and, for a bug or gap, reproduce it on a small fixture
   or a real report before changing anything (evidence first). Record what
   was CONFIRMED and what was only suspected; never fix a guess.
2. Smallest scope that closes the gap: detection or representation before
   execution. Write the non-goals into the AGENTS.md section of the round.
3. Deliver one change as: code, tests, an AGENTS.md section, a status-file
   update. When the files touched are shared and may carry local fixes, ship
   an idempotent apply script that edits by anchored replacement and aborts
   without writing anything if an anchor is missing, rather than whole files.
4. Run `ruff check --fix . && ruff format . && ruff format --check . &&
   ruff check . && mypy python && pytest -q` before committing.
5. A claim in the documentation is a claim to verify on a real machine (two
   README statements were wrong until tested).

**Release procedure.** Write the CHANGELOG entry and bump the four version
places (a small release script using `scripts/release.py`'s `bump_texts`, or
`python3 scripts/release.py bump X.Y.Z` once the entry exists), commit
`release: vX.Y.Z`, push, then `python3 scripts/release.py tag && git push
origin vX.Y.Z`. The tag command asks the GitHub CLI and refuses unless every
CI run for `HEAD` succeeded (it fails closed; `--skip-ci-check` overrides).
Never tag a red or unfinished commit: v0.6.10 was tagged on a commit whose
Windows job was red.

**Lint and CI lessons that cost a round each.**
- ruff here flags `TRY004` (do not raise a non-`TypeError` right after
  `if not isinstance(...)`; restructure), `EXE001` (a script with a shebang
  must be executable), `FURB167` (`re.MULTILINE`, not `re.M`), `RUF015`.
  `ruff format` rewraps long lines; run it before `ruff format --check`.
- The py3.10 CI job runs mypy against 3.10: import `tomllib` with
  `if sys.version_info >= (3, 11): ... else: import tomli as tomllib`.
- Report paths are POSIX everywhere (`Path.as_posix()`); the Windows job
  catches backslashes that Linux and macOS never show.
- Anything a local newer Python hides will show up in CI; read the real log.

**Known limits of this working environment** (assistant-side, not product
limits): the assistant's sandbox has no ruff, mypy, pytest, rich, network or
cargo, so lint and type errors surface only on the maintainer's machine or in
CI, and tests there run through a stub runner. A few tests fail in that
sandbox only (`test_analyzers` pinned requirements, `test_new_ecosystems`
skips, some license/lockfile tests); they also failed on the untouched
archive and pass in real CI.

### 5.55 — Follow-up 2, second half: nested packages in non-hybrid projects (2026-10-08)

5.52 closed the gap for hybrid projects and recorded the rest: *a project that
is not hybrid gets no nested runs*, because `detect_components` returns `None`
and `plan_component_runs` had nothing to plan from.

**Audit** (five fixtures, run against v0.6.15 through `detect_components` and
`plan_component_runs`): Node root + standalone `tools/cli`; Node root + two
nested packages; Go root + nested module; Rust root + nested non-member crate;
a root with only a `Makefile`. `detect_components` was `None` and the plan was
EMPTY in all five -- the nested packages were never tested, linted or audited.
CONFIRMED. (A sixth fixture meant as a hybrid control was invalid: it passed
no compose information, so it was not hybrid either; the existing hybrid tests
in `tests/test_nested_packages.py` remain the control.)

**Change** (`core/components.py`, `core/per_component.py`; no model, CLI or
report change): new `nested_application_components(root)` returns the
application components below the root with the same discovery rules as the
component view (depth 3, `_SKIP_DIRS` pruned, so `examples/`, `tests/`,
`fixtures/`, `vendor/` never count). When `plan_component_runs` gets
`components=None` it builds a throw-away `ComponentsInfo` from them and calls
`_component_targets(..., nested_only=True)`, which keeps ONLY the three
non-recursive analyzers (Node.js, Go, Rust) and applies the existing coverage
rules (workspace members, Cargo members, `go.work`, the Node phase rules,
outermost directory wins, cap 8 directories with an omitted note,
`SARAND_NO_COMPONENTS=1`).

**Deliberately not changed.** The report gets no Project Components section
for these projects (it is still emitted only for hybrid ones). No other
analyzer runs in a nested directory: running every analyzer that does not
match the root, as hybrid projects do, would add Dockerfile / JSON / YAML
runs to ordinary projects. Python stays covered by the root `pytest`/`ruff`.

Two existing tests pinned the old behaviour and were updated:
`test_not_hybrid_means_no_nested_runs` (`tests/test_nested_packages.py`, an
empty plan; it now asserts that the nested package is planned) and
`test_non_node_or_missing_workspaces_plan_nothing`
(`tests/test_node_workspace.py`; it injected workspace info that does not
match the packages, which are now planned as standalone packages -- it asserts
that none of them gets member runs, because members never get `security`).

**Observation, not changed.** A repository with both a Cargo and a Node
workspace is always hybrid (the Rust and Node signatures differ), so it goes
through the 5.52 path, where `detect_workspace` reports only Cargo: its Node
members are planned as nested packages with the `security` phase, i.e. a
per-member `npm audit` (5.50 says that never happens; without a lockfile of its
own it is a SKIPPED result since 5.53). This is the already-listed gap "a repo
with both workspaces records only Cargo"; fixing it means modelling both.

Tests: `tests/test_nested_non_hybrid.py` (11) -- the audited Node, Go and Rust
cases, `go.work` and Cargo-member coverage, a Node workspace member planned
once, a root without a marker, fan-out and ESLint phase rules, skipped
directories, Python unchanged, a plain project with an empty plan, the cap and
the escape hatch. **Not covered:** a root without a marker whose nested
packages are Python, Java or any other analyzer (not planned outside hybrid
projects); a repository with both a Cargo and a Node workspace.

### 5.56 — Non-hybrid projects follow the hybrid rule (2026-10-08)

5.55 kept the first scope small: in a project that is not hybrid only the three
non-recursive analyzers (Node.js, Go, Rust) were planned inside nested
packages. It recorded one gap: a root that matches no analyzer whose nested
packages are Python, Java, etc.

**Audit** (v0.6.15 + 5.55, `plan_component_runs`): a root with only a
`Makefile` plus `services/a` and `services/b` (Python); the same with two
Maven modules; a root with only a README plus Python packages `a` and `b`
(a Dockerfile in `a`); and a Python root with a nested Python package as the
control. `detect_components` was `None` and the root matched no analyzer in the
first three, so the plan was EMPTY -- no tests, quality or security for any
service (CONFIRMED). The control was correct: the root `pytest` and `ruff`
recurse. In the first three, Python (and TOML), Java/Kotlin (and XML), and
Python / Dockerfile / TOML matched the nested directories but not the root.

**Change** (`core/per_component.py` only): the `nested_only` restriction of
5.55 is removed. A project that is not hybrid is planned exactly like a hybrid
one: an analyzer that does not match the root runs inside each nested package
(outermost directory wins, cap 8, labelled `<dir>: <check>`), one that does is
never repeated, except the three non-recursive analyzers with their coverage
rules (workspace members, Cargo members, `go.work`, the Node phase rules).

**Trade-off, accepted.** An ordinary project with a nested package (a
`website/` with a `package.json`, say) now also gets the analyzers that match
only that directory (a Dockerfile analyzer when it has a Dockerfile). That is
what a hybrid project already did; the alternative was a list of "language"
analyzers that nothing in the code defines. Bounded by the 8-directory cap,
`SARAND_NO_COMPONENTS=1` turns it off, and `examples/`, `tests/`, `fixtures/`,
`vendor/` never count.

Tests: `tests/test_nested_non_hybrid.py` is now 15 tests (the four new ones
are the audited Python and Maven cases, an analyzer matching only one nested
package, and "a root-matching analyzer is never repeated"; one assertion of the
5.55 test for a root without a marker was relaxed from `== ["Node.js"]` to
`in`; two assertions in `tests/test_node_workspace.py` that required a
Node-only plan were relaxed to "Node.js exactly once per member" and "no Node.js
analyzer in the plan", because a pnpm-only workspace's members now also get the
JSON analyzer, which did not match the root).

**Not covered:** per-package health scores; analyzers that only match a
directory deeper than three levels; a repository with both a Cargo and a Node
workspace (open gap of 5.50).

### 5.57 — CI actions moved to their Node 24 majors (2026-10-08)

Backlog item 8 had recorded that the first-party actions in
`.github/workflows/ci.yml` ran on the deprecated Node 20. Every CI run since
then carried the annotation "Node.js 20 is deprecated ... actions/cache@v4,
actions/checkout@v4, actions/setup-python@v5 ... forced to run on Node.js 24":
GitHub already overrides the runtime, so the jobs passed, but the override is
a transition aid, not a contract (the runner is documented to drop Node 20
altogether), and `upload-artifact@v4` would have followed.

**Evidence for the versions** (release notes read on 2026-10-08, not from
memory): `actions/cache@v5` runs on Node 24 (it also needs runner >= 2.327.1
and invalidates existing cache keys once); `actions/upload-artifact@v6` is the
release that makes Node 24 the default (v7 only adds an ESM bundle and the
`archive` option); `actions/setup-python@v6` and `actions/checkout@v6` are the
Node 24 majors (v7 of both exists; the smallest Node 24 major was chosen so the
change stays a pure runtime bump). `dtolnay/rust-toolchain@stable` is a
composite action and needs no change. GitHub-hosted runners satisfy the
runner version; self-hosted ones would need to be updated first.

**Change.** Four version numbers in `ci.yml`: checkout v4 to v6, setup-python
v5 to v6, cache v4 to v5, upload-artifact v4 to v6. Nothing else in the
workflow or in the code changed.

**Expected, not a regression.** The first run after the change has a cold
cargo cache (new key space), so it is slower once. The annotations about Node
20 should be gone; if one remains, read which action it names.

**Not verifiable locally.** There is no way to run the workflow here: the
check is the next CI run, and `scripts/release.py tag` refuses to tag unless
it is green. Older 5.x text that names `actions/checkout@v4` or
`upload-artifact@v4` (5.4x, the pytest log artifact) describes the workflow as
it was and is left as history; `core/coverage.py` mentions
`actions/checkout@v4` only as an example of a working directory.

### 5.58 — Every workspace of a repository is modelled (2026-10-08)

Backlog status item 1 listed one confirmed gap that 5.56 then measured: a
repository with both a Cargo and a Node workspace recorded only Cargo, because
`detect_workspace` returned the first match (`cargo`, then `npm`). Everything
that consumed a workspace saw one.

**Audit** (v0.6.16, a Cargo workspace `crates/*` with a root package, an npm
workspace `packages/*` with members `a` and `b`, and a standalone
`tools/cli`): `detect_workspace` reported `cargo` with members `.` and
`crates/x`; the planner therefore did not know `packages/a` and `packages/b`
were Node members, planned them as nested Node packages with the phases
`quality`, `security` and `tests` (a per-member `npm audit`, which 5.50 forbids)
and never ran them as members. The report listed only the Cargo workspace.
CONFIRMED. A repository like this is always hybrid (Rust and Node), which is
why it never went through the non-hybrid path.

**Design.** The fix is in the model, not in the planner alone:

- `core/workspace.py`: `detect_workspaces(root) -> list[WorkspaceInfo]`
  (Cargo first, then Node; empty for an ordinary project).
  `detect_workspace(root)` stays and returns the first one, so no existing
  caller or test changes.
- `models/results.py`: `ReportData.extra_workspaces` (every workspace after
  the first, default empty) and the property `all_workspaces`. `workspace`
  stays the first one, so every existing reader keeps working. The new field
  is last, so positional construction is unaffected.
- `core/per_component.py`: `plan_component_runs` takes a `WorkspaceInfo`, a
  list of them or `None` (type `Workspaces`; one tiny normaliser). Member paths
  are collected per kind, so Cargo members are covered by `cargo test --all`
  and Node members are planned as members (phases `tests` and `quality` only,
  never `security`), whichever workspace was found first.
- `renderers/markdown.py`: one `## Workspace` section as before for a single
  workspace; with several, `## Workspace (cargo)` and `## Workspace (npm)`.
- `renderers/json_renderer.py`: `workspace` is unchanged (the first); a
  `workspaces` list (all of them, same shape) appears only when there is more
  than one, so ordinary reports and the golden snapshots are byte-identical.
- `cli.py`: calls `detect_workspaces`, passes the list to the planner and
  stores `workspaces[1:]` as `extra_workspaces`.
- Docs: `docs/WORKSPACES.md` and `.fa.md` (the "not supported" bullet is gone,
  the report and run rules mention both workspaces). The same pass fixed a
  sentence left stale by 5.55 and 5.56: both files still said a project that is
  not hybrid gets no nested runs.

**After** (same fixture): `packages/a` and `packages/b` are planned once each
with the phases `quality` and `tests`; `tools/cli` keeps `quality`, `security`
and `tests` (a standalone package has its own lockfile); `crates/x` is not
planned for Rust. The report and the JSON carry both workspaces.

**Deliberately not changed.** No third workspace kind was added (Gradle,
Maven, Bazel, Nx and Turborepo stay as recorded in `docs/WORKSPACES.md`).
`detect_workspace` is not removed. The root-script and ESLint rules for
members are the 5.50 ones, applied to whichever Node workspace exists.

Tests: `tests/test_multi_workspace.py` (12) -- both detected and ordered, one
or none, `detect_workspace` equals the first, a list and a single workspace
plan identically, the audited phases before/after on the real analyzers,
order independence, cascading root scripts, the Node-only and Cargo-only
cases unchanged, and the markdown and JSON shapes for one and for several
workspaces. **Not covered:** two Node workspaces in one root (npm and pnpm
declarations are already resolved to one by `node_workspace.py`); workspaces
below the root (nested Cargo workspaces are a nested-package question, see
5.55 and 5.56).

### 5.59 — Per-package results, the fence blank line, the filelock range (2026-10-09)

Backlog items 1 ("per-package scores") and 7 ("small items") closed together.

**Per-package results.** *Audit:* with component runs the report already lists
every check labelled `<package>: <kind>`, but there is no view of *which
package passed what*: with eight packages the reader scans the check lists, and
the one health score hides which package pulled it down. The label exists only
inside `CommandResult.kind` (a structured field would add a key to every
result in the JSON through `r.__dict__` and change the golden snapshots).
*Decision:* a per-package **0-100 score** was NOT built. The repository formula
holds parts that belong to no package (git hygiene 10, TODO hygiene 15, tooling
15 of 100); a package score would be a second formula with its own invented
weights. A package gets what it actually ran: passed, failed and skipped
results per phase.

*Change:* `core/package_summary.py` (pure: `summarize_packages(paths, tests,
quality, security) -> list[PackageSummary]`, longest package label first, no
label = root, root row first, empty when no package ran anything).
`ReportData.package_paths` (last field, default empty; the CLI fills it from
the plan's targets). Markdown: `## Package results` with one row per package
and cells like `2/3`, `0/1 failed`, `skipped`, `-`, placed before
`## Test results`. JSON: a `package_results` list, only when there is at least
one package, so ordinary reports and the golden snapshots do not change. The
repository score is untouched.

**Closing fence.** `markdown.py` joined a file's content (which already ends in
a newline) with the fence line, leaving a blank line before the closing
```` ``` ````. It now drops one trailing newline of the content
(`removesuffix`), so a file that ends without a newline or with several keeps its
real shape. Only `tests/golden/hybrid.md` recorded the blank line (three
places); it was regenerated through the golden harness and the diff is exactly
those three lines (5.21: the snapshot records what the renderer emits). The
HTML, JSON, SARIF and text snapshots were unchanged.

**filelock.** *Review:* the pin `filelock==3.32.3` was recorded in 5.44 as a
conflict risk for `pip --user` and distro packaging. The code uses only
`FileLock(path)`, `acquire(blocking=False)`, `Timeout` and `release()` in
`rc/state.py`. *Facts checked on 2026-10-09 (release notes, not memory):* the
3.32 line is current and a 4.x line exists (4.0.8); `blocking` became a
documented first-class option (constructor and property) in 3.14.0. *Change:*
`filelock>=3.14,<4`: every distro and every other package can satisfy it,
while the major that CI exercises stays the one in use. 4.x is NOT verified;
widening to `<5` is a separate, tested step (CI resolves to the newest allowed
version, so the first CI run after this is the proof for 3.32.x).

**Not covered.** The HTML and text renderers do not show the table (they do not
show the Workspace or Project Components sections either; recorded, not fixed
here). A per-package *score*, durations per package, and listing which check
failed inside the table (the detailed sections below it already name it).

Tests: `tests/test_package_results.py` (9).

### 5.60 — Kubernetes, second round: raw manifests and a Kubernetes analyzer (2026-10-09)

Backlog status item 5 ("Kubernetes next phase"). Round one (v0.6.7) detected
Helm charts and Kustomize overlays and nothing else.

**Audit** (fixtures through `detect_kubernetes` and the registry): a repository
with only `deploy/app.yaml` (a Deployment and a Service) gave `None` -- no
Kubernetes section, the manifests invisible; charts and overlays were reported
but no tool ever ran on them (no analyzer, no `--doctor` row). CONFIRMED.

**What was built**

- *Raw manifests* (`core/kubernetes.py`): a `.yaml`/`.yml` file whose documents
  carry `apiVersion` and `kind` (`Kind/name` per resource). Never read: files
  named `kustomization.*`, `Chart.*`, `values.*`, anything inside a chart (its
  templates are not YAML; `crds/` belong to the chart), symlinks, files over
  512 KiB; a `kustomize.config.k8s.io` document is not a resource. Bounded by
  500 files and 8 MiB read, 100 files listed, 50 resources per file; the true
  count is kept in `total_manifest_files` and the report says how many are not
  listed. `KubernetesInfo.manifests` and `.total_manifest_files` are new
  fields; the JSON `kubernetes` object gets `manifests` only when there are
  any. Raw manifests alone do not make a project hybrid (they are not
  components) and a project with only manifests now gets a Kubernetes section.
- *Kubernetes analyzer* (`analyzers/kubernetes_analyzer.py`, the 41st): matches
  when a chart or an overlay exists (detected with `manifests=False`, so
  `matches` stays cheap). `--quality` runs `helm lint <chart>` per chart and
  `kustomize build <overlay> -o <temp file>` per overlay, at most 8 of each
  kind with one skipped note for the rest. It runs no tests and no security
  check, and applies nothing to a cluster.

**Why the rendered output goes to a file.** `kustomize build` prints the
rendered manifests, which can contain `Secret` data; the result type keeps raw
output, so printing it would put secrets in a report. `-o` writes it to a
temporary file that is deleted with its directory; only errors reach the report.

**Skipped, with the reason, instead of failing.** A chart whose `Chart.yaml`
lists dependencies missing from `charts/` (`helm dependency build` first); an
overlay with a remote base (URL, `git@`, `host.tld/org/repo//path`) or a
`helmCharts` generator; a missing `helm` or `kustomize`. A false FAILED here
would repeat the `npm audit` ENOLOCK mistake of 5.53.

**Deliberately not built.** `kubeconform`: its default schema source is the
network, a download failure is indistinguishable from an invalid resource by
exit code, and no real binary was available to verify its output. `helm
template`, `kubectl kustomize` as a fallback, and anything that talks to a
cluster. Hybrid components are unchanged.

**Registration.** `KubernetesAnalyzer` in the registry, two `--doctor` rows
(`helm`, `kustomize`), the `DOCTOR_CATEGORIES` entry, the READMEs (41
analyzers) and `docs/COVERAGE.md` regenerated from the code.

**Verification limit.** The sandbox has no helm or kustomize: the tests replace
the tool runner and check sarand's wiring (what runs, what is skipped and why,
that the rendered file is gone). The behaviour relied on from the tools is
their documented one (a non-zero exit on error; `-o` writes to the file); the
first proof against real binaries is a run of `sarand --quality` on a project
with a chart on a machine that has them.

Tests: `tests/test_kubernetes_phase2.py` (19). **Not covered:** a
manifest outside the 500-file scan window; Helm `values` files that are
rendered with a different `--values`; `kustomize` components with remote URLs
inside nested files (only the overlay's own `resources`, `bases` and
`components` entries are checked).
\n
