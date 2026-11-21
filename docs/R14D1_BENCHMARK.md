# R14-D1: repeatable benchmark of the structure build

This is the measurement method that the owner's acceptance of R14-A3 asks D1 to put in
place (`docs/R14A_GATE_ACCEPTANCE.md`, "Duties for D1"). The tool is
`scripts/structure_bench.py`. It measures; it changes nothing in the package and it does
not justify an optimization by itself. No change to A3 code comes with it.

## What each duty becomes

| Duty of the acceptance | What the tool does |
|---|---|
| 1. A repeatable benchmark, fixed input, same environment | Every measurement is one worker in a fresh interpreter; the file list, the size limit and the hash seed are the same for every version; the environment is written to the result |
| 2. Same Python minor, settings, cache state | One interpreter runs everything; the Python version is recorded per result and the comparison says whether the minor versions are equal; a fresh process means no cache or allocator state is carried over |
| 3. Spread, minimum, maximum and P95 beside the median | `summarize`: n, median, mean, standard deviation, min, max, P95 (nearest rank) and the spread in percent. With fewer than 20 runs P95 is the maximum, and the report marks it with `*` |
| 4. Time the phases and the fingerprint separately | A second, instrumented run inside the same worker times declarations, imports and AST, symbol facts, fingerprints, cycles, resolution, entry points and `other`. The headline seconds never include that instrumentation |
| 5. Small, medium and large inputs | `--input LABEL=PATH` can be given several times; every input is measured with every code version |
| 6. Optimize only after profiling | The phase table says where the time goes; a change must be argued from it and measured again with the same method |
| 7. Compare the CLI of A2 and A3 | `--cli` times the whole `sarand --structure` command (wall time and the peak RSS of that process) for every version and input; the report warns when one version has a compiled core and the other has not |

## How the comparison is made fair

- The code versions run **interleaved**, round by round, and the order flips every round
  (A B, B A, A B ...). A slow minute on a busy phone hits all versions alike.
- Warm-up rounds run and are dropped; only the measured rounds are summarized.
- Each worker prints the file its `sarand` was imported from. The script stops if that
  is not the requested directory, so a version cannot silently be the wrong one.
- The output of every run is hashed. Runs of one version on one input must give one
  hash; otherwise the script exits with an error. Two versions may differ (a schema
  changed between A2 and A3); the report says so.
- The load average is logged before and after every round, where the platform shows it.
- Give the same code twice under two labels (an A/A control). The difference between
  the two is the noise of the machine, and a difference between versions smaller than
  that is not a finding.

## How to read the result

`results.json` is the full record; `results.md` is the same for reading. For a pair of
versions the report gives the change of the median, of P95 and of the peak RSS, and says
whether the [min, max] ranges overlap. Overlap means the difference cannot be told from
noise with this many runs. Five runs are not a statistical test; they are an estimate
with its spread shown.

## Limits

- The phase numbers come from a separate instrumented run; they show proportions, not an
  exact split of the clean run. Fingerprints are inside the facts phase, so the phases
  overlap by design and `other` is what is left of the instrumented run.
- The load average cannot be read on every platform, for example inside some proot
  environments; the record then holds `null`.
- The CLI timing includes starting the interpreter, reading the project and the other
  parts of the report; the report is not parsed and its content is not checked.
- Peak RSS is that of the process (or of the child process for `--cli`), not of the
  structure alone.

## Usage

```text
python scripts/structure_bench.py run --out DIR \
    --input small=PATH --input medium=PATH --input large=PATH \
    --code A2=DIR/python --code A3=DIR/python --code A3-control=DIR/python \
    [--rounds 5] [--warmup 1] [--hashseed 0] [--cli]
```

`--code` takes the `python/` directory of a checkout or of a `git worktree`. For the
comparison of two commits, use one worktree for each, so that both either have a
compiled core or have none.
