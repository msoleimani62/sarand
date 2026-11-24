# R14-D1: benchmark result of the structure build (A2 against A3)

Recorded on 2026-11-21 with `scripts/structure_bench.py` (commit `ad5f44f`, method in
`docs/R14D1_BENCHMARK.md`). This file is evidence; it changes nothing in the code and it
does not reopen the acceptance of R14-A3 (`docs/R14A_GATE_ACCEPTANCE.md`).

## Conditions

- Device: Redmi Note 8 Pro, 8 cores, Linux 4.14.186 aarch64 in a Kali NetHunter proot,
  Python 3.14.6 (CPython), hash seed 0. The load average cannot be read in the proot, so
  it was not logged; the A/A control (A3 run twice under two labels) is the only noise
  indicator.
- Code: `A2` is `31a038d` and `A3` is `2118c89`, each in its own `git worktree`
  (`/tmp/sarand-r14a2`, `/tmp/sarand-r14a3`). Neither has a compiled core, so the whole
  command measured below runs the pure-Python scan path in both.
- Method: 1 warm-up round and 5 measured rounds, one fresh interpreter per measurement,
  the code versions interleaved with the order flipped every round, every run hashed
  (every run of a version on an input gave one hash). P95 equals the maximum with 5 runs.
- Inputs: `small` is open-downloader-cli (76 files, 534 symbols, 742 relations), `click`
  is click (179 files, 91 of them Python, 2,546 symbols, 4,347 relations), `bimarz` has
  565 files but only 753 symbols (mostly not Python), `sarand` is the A3 worktree (439
  files, 5,078 symbols, 9,496 relations). The two inputs with at least 2,000 symbols are
  the ones that describe a real project.

## `build_structure`, seconds (median, min to max)

| Input | A2 | A3 | A3-control | A3 against A2 | Control against A3 | Ranges A2 and A3 |
|---|---|---|---|---|---|---|
| small | 0.6064 (0.5612 to 0.6264) | 0.7468 (0.6304 to 0.9867) | 0.6722 (0.6497 to 0.7674) | +23.2% | -10.0% | do not overlap |
| click | 2.5714 (2.3776 to 2.7697) | 2.9945 (2.908 to 3.1875) | 2.9687 (2.8926 to 3.3999) | +16.5% | -0.9% | do not overlap |
| bimarz | 0.8603 (0.8223 to 0.8787) | 0.922 (0.8749 to 0.9528) | 0.9336 (0.8034 to 1.0889) | +7.2% | +1.3% | overlap |
| sarand | 6.7448 (5.836 to 6.8676) | 7.2602 (6.8944 to 7.8127) | 7.435 (7.2115 to 8.3639) | +7.6% | +2.4% | do not overlap |

An earlier run of the same method without `--cli` (3 inputs, A2 and A3 only in the
comparison) gave sarand 6.4381 to 7.0784 (+9.9%, A/A -1.0%), bimarz 0.823 to 0.9404
(+14.3%, A/A 0.0%) and small 0.5975 to 0.6961 (+16.5%, A/A +5.4%). The A2 median of
sarand moved by 4.8% between the two sessions, so differences of about 5% between runs
made hours apart are noise, and the percentages above are estimates, not constants.

## Where the time goes (instrumented run, median seconds)

| Input | `facts` A2 | `facts` A3 | growth | `fingerprint` (inside `facts`) | share of the growth | `parse_imports` A2 | `parse_imports` A3 |
|---|---|---|---|---|---|---|---|
| small | 0.1577 | 0.2486 | 0.0909 | 0.0873 | 96% | 0.3045 | 0.305 |
| click | 0.7626 | 1.2854 | 0.5228 | 0.4744 | 91% | 1.2615 | 1.2782 |
| bimarz | 0.1983 | 0.3358 | 0.1375 | 0.131 | 95% | 0.4153 | 0.3978 |
| sarand | 1.7292 | 2.7742 | 1.045 | 0.9321 | 89% | 3.3529 | 3.4304 |

- The growth of the facts phase between A2 and A3 is, for nine tenths or more, the cost of
  the fingerprints; the fingerprint is about 12% to 16% of the A3 structure build. No
  other phase moved by more than its own spread (`declarations`, new in A3, is 0.002 to
  0.016 s).
- The largest phase, `parse_imports`, is the same in A2 and A3 (about 45% of the build
  on sarand). Phase numbers come from a separate instrumented run and show proportions,
  not an exact split.

## Memory

| Input | Peak RSS A2 / A3 (KiB) | `tracemalloc` peak A2 / A3 (KiB) |
|---|---|---|
| small | 34,964 / 34,940 | 5,170 / 5,199 |
| click | 54,580 / 54,932 | 23,877 / 23,997 |
| bimarz | 35,580 / 36,384 | 5,362 / 5,411 |
| sarand | 77,488 / 78,376 | 44,832 / 45,159 |

The increase is between 0.6% and 2.3% of the process peak and under 1% of the
`tracemalloc` peak.

## The whole `sarand --structure` command, seconds (median; spread of the 5 runs)

| Input | A2 | A3 | A3-control | A3 against A2 | Control against A3 |
|---|---|---|---|---|---|
| small | 6.1276 (41%) | 6.0311 (80%) | 5.5511 (40%) | -1.6% | -8.0% |
| click | 8.7685 (10%) | 8.7477 (24%) | 8.8457 (29%) | -0.2% | +1.1% |
| bimarz | 9.5532 (22%) | 10.4279 (35%) | 10.0401 (5%) | +9.2% | -3.7% |
| sarand | 14.9744 (34%) | 16.6271 (19%) | 16.7424 (31%) | +11.0% | +0.7% |

Every run exited with 0. Peak RSS of the process: click 94,956 / 96,236 KiB, sarand
129,872 / 130,832 KiB, bimarz 69,448 / 69,464 KiB, small 69,292 / 69,384 KiB. Every run
of an input wrote the same number of bytes to standard error in both versions (for
example 2,685 for small); the content of that output was not inspected.

## What the data shows and what it does not

- The structure build of A3 costs about 7% to 23% more than A2 on the four inputs; on the
  two inputs that are real projects, 7.6% (sarand) and 16.5% (click). The earlier
  accepted figure of about 9.8% is inside that range. The cost is the fingerprint.
- The whole command shows no difference on small and click, and about +9% to +11% on
  bimarz and sarand with spreads of 19% to 35%, which are as large as the differences.
  The command is dominated by other work (6 to 17 s), so the cost of the fingerprints
  is not visible in it with 5 runs.
- Not shown: any difference between machines or Python versions (only 3.14.6 on one
  phone was measured), the effect of a compiled core on the whole command, and any
  effect of load (it could not be logged).
- Per the acceptance rule, no optimization follows from this: the profile names the
  fingerprint and `parse_imports` as the largest costs, and neither is changed. The
  measurement is repeated, with the same method, when the code of D1 is in place.

## Standard error of the command

Checked on 2026-11-23 on click, with the A2 and A3 worktrees: both runs exit with 0 and
write the same 575 bytes to standard error, identical except for the time stamp of one
line. The content is the normal progress of the command (the detected ecosystem, the scan
engine `pure-Python fallback`, the collection steps, "Building the repository
structure...", "Rendering JSON report...", "Report completed") and one warning,
`sarand.git: Not a git repository`, because the extracted click archive is not a git
checkout. No error and no difference between A2 and A3. The earlier larger byte counts
of the benchmark's whole-command runs (for example 2,875 for click) were not inspected
line by line; they come from the same kind of progress output.
