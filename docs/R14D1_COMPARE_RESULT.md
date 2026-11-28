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

## On the phone

The owner's device, run of 2026-11-28 (the commit of the `compare` mode, `0368816`):
Python 3.14.6 (CPython), Linux 4.14.186 aarch64, **8 CPUs**, hash seed 0, the **compiled
core in use**, the real `rich`; five measured runs after one warm-up. Inputs are made from
the tracked files of the checkout (`git archive`): `small` = `scripts` (a dozen files),
`medium` = `python/sarand`, `large` = the whole checkout. They are not the sandbox inputs, so
only the shape of the results is comparable with the section above, not the seconds.

### Seconds of the whole command

| input | configuration | median | min | max | P95 | RSS KB (median) | structure package loaded |
|---|---|---|---|---|---|---|---|
| small | plain | 3.6838 | 3.5752 | 3.7992 | 3.7992* | 69120 | False |
| small | findings-baseline | 3.7747 | 3.6864 | 4.7591 | 4.7591* | 69428 | False |
| small | findings-gate | 3.7712 | 3.6839 | 4.517 | 4.517* | 69192 | False |
| small | structure | 4.2636 | 4.1724 | 5.6585 | 5.6585* | 69388 | True |
| small | structure-baseline | 4.818 | 4.4299 | 5.4909 | 5.4909* | 69388 | True |
| medium | plain | 5.4372 | 5.0538 | 5.6018 | 5.6018* | 69484 | False |
| medium | findings-baseline | 5.501 | 5.1929 | 6.4202 | 6.4202* | 69472 | False |
| medium | findings-gate | 5.3148 | 5.2022 | 6.1211 | 6.1211* | 69488 | False |
| medium | structure | 10.2383 | 9.5385 | 10.6691 | 10.6691* | 88824 | True |
| medium | structure-baseline | 10.883 | 10.0387 | 11.7477 | 11.7477* | 99392 | True |
| large | plain | 9.1318 | 7.7151 | 10.7591 | 10.7591* | 69336 | False |
| large | findings-baseline | 8.7652 | 8.237 | 9.31 | 9.31* | 69156 | False |
| large | findings-gate | 8.1651 | 7.9778 | 10.0579 | 10.0579* | 69264 | False |
| large | structure | 19.6742 | 18.0937 | 19.9121 | 19.9121* | 151056 | True |
| large | structure-baseline | 19.8366 | 19.5266 | 21.3012 | 21.3012* | 203288 | True |

### What each option adds to its base

| input | option | base | added seconds (median) | change | ranges overlap | added RSS KB |
|---|---|---|---|---|---|---|
| small | findings-baseline | plain | 0.0909 | 2.5% | yes | 308 |
| small | findings-gate | findings-baseline | -0.0035 | -0.1% | yes | -236 |
| small | structure-baseline | structure | 0.5544 | 13.0% | yes | 0 |
| medium | findings-baseline | plain | 0.0638 | 1.2% | yes | -12 |
| medium | findings-gate | findings-baseline | -0.1862 | -3.4% | yes | 16 |
| medium | structure-baseline | structure | 0.6447 | 6.3% | yes | 10568 |
| large | findings-baseline | plain | -0.3666 | -4.0% | yes | -180 |
| large | findings-gate | findings-baseline | -0.6001 | -6.8% | yes | 108 |
| large | structure-baseline | structure | 0.1624 | 0.8% | yes | 52232 |

### Reading the phone run

- **Same conclusion as the sandbox: the findings path costs nothing measurable.** All six
  findings rows (`--baseline` and the gate, three inputs) have overlapping ranges and
  differences of −6.8 % to +2.5 %; on the large input they are negative, which is the
  noise of a phone (the plain runs themselves range from 7.7 s to 10.8 s). The structure
  package was not loaded in any of them.
- **The structural baseline is visible only as a trend:** +0.55 s on small (13 %), +0.64 s
  on medium (6.3 %) and +0.16 s on large (0.8 %), all with overlapping ranges, so a cost
  of this size cannot be told from the noise of this device with five runs. The sandbox
  (+0.68 s on the large input, ranges apart) and the phone agree on the order of magnitude:
  well below a second.
- **What the phone shows clearly is that `--structure` itself is the expensive part:** on
  the large input the run goes from 9.1 s to 19.7 s and from 69 MB to 151 MB (203 MB with the
  baseline). Even the smallest input takes 3.7 s plain, so the start-up of the interpreter
  and the imports weigh more than the scan there.
- **No optimization was made on this evidence either:** it contains no cost that a
  comparison adds and that is clear of the noise.

## Running it again

On the phone, from a checkout with the environment active, with any three projects of
increasing size:

```text
python scripts/structure_bench.py compare --out /tmp/cmp \
    --input small=PATH --input medium=PATH --input large=PATH \
    --code NOW=$PWD/python --rounds 5 --warmup 1
```

`/tmp/cmp/compare.md` is the report and `/tmp/cmp/compare.json` the full record.
