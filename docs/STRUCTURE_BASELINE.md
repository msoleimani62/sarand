# Structural baseline: comparing two structure snapshots

Status: the library and the command line (slices S1 and S2 of R14-D1,
`docs/R14D1_PLAN.md`). This page is the contract: what a snapshot is, what a comparison
may claim, what it refuses to claim, and how the command line uses it.

The structural baseline is **independent of the findings baseline**. It compares what a
project is made of (files, symbols, relations, imports, cycles, entry points); it never
creates or changes a finding, and no findings code imports it.

## The question and the two sides

`compare_structures(old, new)` compares a reference (`old`) with the current state
(`new`). Each side is a `Reference` that `read_reference` builds from parsed JSON:

- a **snapshot**: the `structure` object of a report in a small envelope (below), or
- a **JSON report** that has a `structure` key.

`read_reference` never raises on bad input. It returns a reference that says why it is
unusable, so that a comparison can say so instead of comparing nothing and calling the
result "unchanged".

## The snapshot envelope

| Key | Meaning |
|---|---|
| `kind` | `sarand-structure-snapshot` |
| `snapshot_format` | `1` |
| `structure_schema`, `language` | copied from the structure and checked against it |
| `fingerprint_basis` | for example `fp1/python-3.14`; checked against the structure |
| `settings` | `excluded_secret_files` (sorted paths) and `max_file_size`: what changes the content of a snapshot |
| `structure` | the `structure` payload of the report |
| `digest` | `sha256:` of everything above in canonical JSON |

A snapshot has no time and no machine name: the same project and the same code always
write the same bytes (`snapshot_text`). A changed byte anywhere makes the digest fail and
the reference `invalid`.

## Verdicts

The verdict is the first field of the answer. The first that applies wins; the facts
behind the lower ones stay in `reasons`, `fingerprints_comparable` and `uncertain_paths`.

| Verdict | When | What is compared |
|---|---|---|
| `invalid` | a side is not a usable snapshot: not an object, no `structure` key, digest mismatch, a missing part, an envelope that disagrees with its structure | nothing |
| `incompatible` | a side is well formed but of a structure schema, snapshot format or language this version does not compare (`SUPPORTED_SCHEMAS` is `4`), or the two differ | nothing |
| `partial` | at least one uncertain path, or two known file size limits that differ | everything; what depends on an uncertain path is `uncertain` |
| `ids_only` | the fingerprint bases differ or are missing (another Python minor) | symbols by id only; no `content_changed` is claimed |
| `comparable` | none of the above | everything |

A structure schema that the builder starts to write must be added to `SUPPORTED_SCHEMAS`
together with the comparison; until then it is `incompatible`, and a test ties the
supported list to the schema that the builder writes today.

## Absence is not removal

A path is **uncertain** when a change that involves it cannot be read as a real change:

- the file is not `full` in one of the snapshots (`partial`, `failed`, `skipped_size`);
- the path is in the secret exclusion of one snapshot and not of the other.

Every added, removed or changed item that depends on an uncertain path is reported with
the status `uncertain` and a reason, never as added or removed. External packages that
are no longer imported are `uncertain` too while any uncertain path exists, because the
import that used them may simply not have been read.

## What is compared and how it is identified

| Part | Identity | Statuses |
|---|---|---|
| Files | path | `added`, `removed`, `changed` (fields `content`, `completeness`, `language`), `uncertain` |
| Modules | name and root | `added`, `removed`, `changed` (`path`, `is_package`, `is_namespace`), `uncertain` |
| Symbols | the match classes of `identity.py` | `content_changed`, `content_unknown`, `moved`, `ambiguous`, `added`, `removed`, `uncertain` |
| Relations | kind, matched source, matched target | `added`, `removed`, `changed`, `uncertain` |
| Import edges | kind, importing module, requested name | `added`, `removed`, `changed`, `uncertain` |
| Cycles | the sorted set of modules | `added`, `removed`, `changed` (eager flag), `uncertain` |
| Entry points | type, name, target | `added`, `removed`, `changed`, `uncertain` |
| External packages | name | `added`, `removed`, `changed`, `uncertain` |

Unchanged items are counted, not listed. Source lines and columns are evidence and are
never part of an identity.

- **Content is not identity.** A symbol with the same id and another fingerprint is
  `content_changed`; it is never reported as removed plus added. A moved symbol is
  `moved` (a `probable` match); a renamed symbol is an unmatched pair, as in
  `docs/R14A_ADR_STRUCTURAL_IDENTITY.md`. A formatting-only change moves the file hash
  and no symbol.
- **Relations follow their symbols.** A relation whose source or target symbol was
  removed or added is counted in `removed_with_symbol` or `added_with_symbol` and is not
  listed again. A relation that touches an `ambiguous` symbol or one in an uncertain
  file is listed `uncertain` with the reason, because no key can be trusted for it.
  Relations between matched symbols are compared by kind and the matched ids; a changed
  confidence, resolution method, flag or number of sites is `changed`.

## Determinism and safety

The same two references give the same bytes (`to_json`) whatever the order of the items
inside them. A comparison changes neither input. `compare_structures` reads only the
two references: no file, no network, no clock.

## Command line

Both options need `--structure` (without it the run is refused).

| Option | What it does |
|---|---|
| `--structure-baseline PATH` | Compare the structure of this run with the reference in `PATH` (a snapshot, or a JSON report that has a `structure`) and add what changed to the report. |
| `--structure-snapshot PATH` | Write the structure of this run to `PATH` as a snapshot. |
| `--replace-structure-snapshot` | Allow `--structure-snapshot` to replace an existing file. |

- **Fail fast.** A baseline that is missing, unreadable, not a snapshot or report, of
  another snapshot format or structure schema, or with a wrong digest is an error that
  names the file and the reason, and so is a snapshot target that is a directory, a
  symbolic link, in a missing directory, or an existing file without
  `--replace-structure-snapshot`. This is checked before any work: no scan, no report.
  The exit code is 1.
- **Order.** The comparison uses the reference as it was before the run. The snapshot is
  written last, only after the report succeeded; with a failed PDF (exit 1) no snapshot
  is written. The same path may be given to both options: the run compares with the old
  file, then replaces it (keeping the old one as `PATH.prev`).
- **Safe writing.** The snapshot is staged in a temporary file next to the target,
  flushed, read back and verified (it must parse as a usable snapshot with the digest
  that was meant), then renamed into place. A failure leaves the target as it was and no
  temporary file behind. A replacement keeps one previous generation as `PATH.prev`; to
  restore it, rename it back. The permission bits of an existing file are kept, otherwise
  the umask default applies.
- **Where the result goes.** JSON: the `structure_comparison` object (report schema 1.11,
  `docs/JSON_SCHEMA.md`). Markdown and HTML: a "Structure changes" section (verdict,
  reasons, counts per part, uncertain paths, up to 40 listed changes). Text: one line.
  SARIF: nothing. The comparison is information only: it never changes the exit code and
  never creates a finding.

```text
sarand --structure --structure-snapshot structure.json          # first run: write the reference
sarand --structure --structure-baseline structure.json          # later: what changed?
sarand --structure --structure-baseline structure.json \
       --structure-snapshot structure.json --replace-structure-snapshot   # compare, then update
```

## Limits

- A relation whose target could not be resolved has no stable target name in the
  payload, so several unresolved targets of one source and kind are one key.
- A renamed module is a removed plus an added module; its imports follow.
- With `ids_only` the report cannot tell a content change from no change; such symbols
  are `content_unknown`.
- A snapshot is the whole structure payload: about 11.6 MB for sarand (5,078 symbols).
  In the sandbox (x86, Python 3.12) one comparison of two such snapshots took 0.3 to
  0.6 s. Phone numbers are measured in slice P.
- Only Python is compared. Another language is `incompatible`.

## Use (library)

```python
from sarand.structure.snapshot import make_snapshot, read_reference
from sarand.structure.compare import compare_structures

old = read_reference(make_snapshot(old_structure_payload))
new = read_reference(make_snapshot(new_structure_payload))
result = compare_structures(old, new)
print(result.verdict)
print(result.to_json())
```

## Tests

`tests/test_structure_compare.py` covers identical snapshots, every status, every verdict
and every way a snapshot can be unusable, the digest and the absence of a time, the
independence of the output from input order, and the fact that nothing in the inputs is
changed. `tests/test_structure_baseline_cli.py` covers the snapshot files (all or nothing,
never over a file unasked, the previous generation, permissions, reading that never
raises) and the command (the refusals, the JSON schema and the other formats, a run
without the options).
