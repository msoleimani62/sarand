# R14-D1 comparison paths: measured cost

Slice P of `docs/R14D1_PLAN.md`: what the findings comparison, the gate and the structural
comparison cost, each measured separately. Method: the `compare` mode of
`scripts/structure_bench.py` (`docs/R14D1_BENCHMARK.md`).

## Conditions of this run

- Sandbox container: Python 3.12.3 (CPython), Linux x86_64, **1 CPU**, hash seed 0, the
  pure-Python engine (no compiled core), the checkout after the F4 delivery (commit `4fa459d`, the zip carries no git record).
- The terminal library `rich` was replaced by an empty stub (it is not installed there), so
  the cost of drawing the console summary is absent from every configuration alike.
- Inputs: `small` = the `json` package of the standard library (a handful of files),
  `medium` = the `email` package of the standard library (23 entries), `large` = the sarand
  checkout itself (603 files).
- Five measured runs after one warm-up; one fresh interpreter each; the whole command
  with `--skip-tests`.
- These numbers are from one container, not from the phone. The phone run (the owner's
  device) is the command at the end of this file; its numbers go to the closing report of
  slice C.

## Seconds of the whole command

| input | configuration | median | min | max | P95 | RSS KB (median) | structure package loaded |
|---|---|---|---|---|---|---|---|
| small | plain | 0.2979 | 0.2432 | 0.3463 | 0.3463* | 57548 | False |
| small | findings-baseline | 0.2891 | 0.2665 | 0.3416 | 0.3416* | 57464 | False |
| small | findings-gate | 0.2904 | 0.2508 | 0.3477 | 0.3477* | 57536 | False |
| small | structure | 0.3519 | 0.2978 | 0.3744 | 0.3744* | 57484 | True |
| small | structure-baseline | 0.3352 | 0.3229 | 0.3911 | 0.3911* | 57524 | True |
| medium | plain | 0.3396 | 0.3139 | 0.3771 | 0.3771* | 57512 | False |
| medium | findings-baseline | 0.3306 | 0.2792 | 0.4134 | 0.4134* | 57488 | False |
| medium | findings-gate | 0.3039 | 0.2653 | 0.3123 | 0.3123* | 57480 | False |
| medium | structure | 0.7577 | 0.6997 | 0.7824 | 0.7824* | 57528 | True |
| medium | structure-baseline | 0.8857 | 0.7786 | 1.0156 | 1.0156* | 57516 | True |
| large | plain | 0.6996 | 0.5652 | 0.7681 | 0.7681* | 57476 | False |
| large | findings-baseline | 0.7024 | 0.593 | 0.7973 | 0.7973* | 59272 | False |
| large | findings-gate | 0.6964 | 0.6081 | 0.7315 | 0.7315* | 59288 | False |
| large | structure | 4.6507 | 4.1464 | 4.8736 | 4.8736* | 174388 | True |
| large | structure-baseline | 5.327 | 5.1747 | 5.7851 | 5.7851* | 231352 | True |

## What each option adds to its base

| input | option | base | added seconds (median) | change | ranges overlap | added RSS KB |
|---|---|---|---|---|---|---|
| small | findings-baseline | plain | -0.0088 | -3.0% | yes | -84 |
| small | findings-gate | findings-baseline | 0.0013 | 0.4% | yes | 72 |
| small | structure-baseline | structure | -0.0167 | -4.7% | yes | 40 |
| medium | findings-baseline | plain | -0.009 | -2.7% | yes | -24 |
| medium | findings-gate | findings-baseline | -0.0267 | -8.1% | yes | -8 |
| medium | structure-baseline | structure | 0.128 | 16.9% | yes | -12 |
| large | findings-baseline | plain | 0.0028 | 0.4% | yes | 1796 |
| large | findings-gate | findings-baseline | -0.006 | -0.9% | yes | 16 |
| large | structure-baseline | structure | 0.6763 | 14.5% | no | 56964 |

## Reading

- **The findings comparison and the gate cost nothing measurable.** On the large input
  `--baseline` adds 0.003 s (0.4 %) and the gate adds nothing (−0.006 s); on every input the
  [min, max] ranges overlap, so the differences are noise. The work is a comparison of two
  lists of findings, small next to reading and scanning the project (about 0.7 s here).
- **The findings path does not load the structure package** in any of its configurations:
  the probe saw `sarand.structure` imported only in `structure` and `structure-baseline`.
  A findings-only run keeps the memory of a plain run (57 MB here, 59 MB with a large
  reference).
- **The structural comparison is the one with a visible cost, and it is the structure.**
  `--structure` itself takes the run from 0.7 s to 4.7 s on the large input (and 175 MB).
  `--structure-baseline` adds 0.68 s (14.5 %, ranges do not overlap) and 57 MB on top of
  that: it reads and checks the snapshot, then compares it with the new one. On the medium
  input the difference is 0.13 s but the ranges overlap; on the small one it is noise.
- **No optimization was made.** The plan allows one only after a profile shows the
  bottleneck. The structure baseline costs one seventh of the structure run itself and
  never touches a run that does not ask for it; if the phone run shows a cost that
  matters, profile `compare_structures` and the snapshot read first (the snapshot read
  validates every record).

## Running it again

On the phone, from a checkout with the environment active, with any three projects of
increasing size:

```text
python scripts/structure_bench.py compare --out /tmp/cmp \
    --input small=PATH --input medium=PATH --input large=PATH \
    --code NOW=$PWD/python --rounds 5 --warmup 1
```

`/tmp/cmp/compare.md` is the report and `/tmp/cmp/compare.json` the full record.
