# ADR: structural identity and content fingerprints (R14-A3)

Status: accepted. The owner accepted the R14-A3 gate on 2026-11-21 (see
`docs/R14A_GATE_ACCEPTANCE.md`). Implemented and tested in R14-A3; not yet used by a
baseline. Date: 2026-11-19. Accepted: 2026-11-21.

## Context

R14-D will compare two runs of `--structure` (a baseline and the current state) and
needs to say which symbol of the new state is which symbol of the old one, and whether
its content changed. Two different questions are involved: *which* symbol it is, and
*did it change*. A single identifier cannot answer both, because an identifier that
changes with the content cannot link a symbol across an edit, and one that ignores the
content cannot see the edit.

## Decision

1. **Identity is the symbol `id`** (R14-A2): `sym:` plus 12 hex digits over language,
   kind, repository-relative path, qualified name and a `#n` ordinal for a duplicated
   name. It holds no line number and no content.
2. **Content is a separate `fingerprint`**, `fp1:` plus 12 hex digits: SHA-256 of a
   canonical walk of the definition's syntax tree (positions, whitespace, parentheses,
   quote style, trailing commas, comments and docstrings ignored; statements,
   expressions, nested definitions, decorators, defaults and annotations included).
   A variable is fingerprinted from its annotation and value only. The walk is
   iterative, in the sandbox about 15 percent of the structure build.
3. **A basis travels with every output**: `meta.fingerprint_basis`
   (`fp1/python-<minor>`). Fingerprints are compared only under equal bases.
4. **Four match classes** between two states, in `structure/identity.py`: `exact`
   (same id, unambiguous), `probable` (same kind, qualified name and fingerprint at a
   different path, one candidate each side), `ambiguous` (several candidates; all are
   listed, none is chosen), `unmatched` (`removed` or `added`). Every symbol appears in
   exactly one row; the result does not depend on input order.
5. **Renames are not guessed.** A renamed symbol is an unmatched pair.
6. **A fingerprint never decides alone.** It can only make a match `probable`; an
   `exact` match needs the same id.
7. **A duplicated qualified name is never silently paired.** Duplicates pair exactly
   only when their content is equal; otherwise they are `ambiguous`.
8. Schema: structure schema 3, report schema 1.9, both additive (a default report
   changes only its version number).

## Alternatives considered

- **One content-derived id.** Rejected: every edit would look like a removal plus an
  addition.
- **Id from path and name only, with no fingerprint.** Rejected: it cannot see a change
  and cannot propose a move.
- **Hashing the source text.** Rejected: formatting, comments and docstrings would
  change it; it would make baselines noisy.
- **`ast.dump` as the canonical form.** Rejected: its output differs between Python
  versions even for the same code, and it includes the docstring and cannot skip
  fields; a small own walker is cheaper to reason about and to version.
- **Guessing renames by similarity.** Rejected for R14-A: no evidence base for a
  threshold; a wrong guess would be presented as a match.
- **Automatic resolution of ambiguity** (pick the first, or the closest path).
  Rejected: it turns doubt into a claim.

## Consequences

- A baseline can report, for each symbol, unchanged, changed, moved, ambiguous, added
  or removed, with the reason, and an ambiguous symbol is visible instead of hidden.
- A move combined with an edit has no counterpart (removed plus added). Accepted.
- A method moved with its class is matched per symbol. Accepted.
- Output built with different Python minor versions matches by id only. R14-D has to
  build and compare on one interpreter, or report the limit.
- Changing the algorithm means a new version (`fp2`) and a new basis; old and new
  outputs are then compared by id only.
- Relations and entry points are not matched yet; that is R14-D's decision.

## Evidence

31 tests in `tests/test_structure_identity.py` (harmless edits keep identity; real
edits change fingerprints; a moved file is `probable`; a renamed symbol is unmatched;
duplicates and equal-quality move candidates are `ambiguous`; different bases match by
id only; order independence; stored JSON payloads; deep nesting without recursion
errors) and the evaluation in `docs/R14A_GATE_REPORT.md`.

## Acceptance

Accepted on 2026-11-21 together with the R14-A3 gate. The acceptance fixes the current
decision. It does not forbid a review later if new evidence shows that a change is
needed. The cost of the fingerprints is measured again in D1 and in later changes.
