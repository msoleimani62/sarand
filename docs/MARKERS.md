# Source markers

sarand finds the keywords `TODO`, `FIXME`, `BUG`, `HACK`, `SAFETY` and `XXX` in
your source and lists them. Finding a keyword and counting it as technical debt
are two different things, and the report keeps them apart.

## Discovery is wide, scoring is narrow

The scanner reports **every occurrence** of a keyword on a line, in any
non-binary file that is not excluded, case-insensitively. A line such as
`# TODO: a  # BUG: b` gives two markers. It cannot tell a comment from a string,
a docstring or a variable name, so it also finds the word in prose
(`the TODO scanner`) and in code (`todo.kind`).

Each occurrence then gets one **category**:

| Category | What it is | Scored? |
|---|---|---|
| `actionable` | `TODO` or `FIXME` written as a task: `TODO: x`, `TODO(owner): x`, `TODO - x` | yes |
| `historical` | `BUG`: usually a defect that was already fixed ("BUG FIX: ...") or a known limitation | no |
| `safety` | `SAFETY`: a justification of an invariant (Rust's `// SAFETY:`) or a safety note | no, but shown for review |
| `development` | `HACK` or `XXX`: a workaround or a place that needs attention | no |
| `mention` | `TODO` or `FIXME` that is not a task: prose, a name, `TODO/FIXME`, `TODO: ...`, `TODO-style` | no |

A task needs the keyword, an optional `(owner)`, then `:` or a spaced dash, then
text that starts like a sentence (a letter, a digit, a quote, a backtick or a
bracket). That is why `TODO-CLUSTER`, `TODO-style markers` and a placeholder
`TODO: ...` are mentions. A `BUG` marker is never a task by itself: write a task
as `TODO` or `FIXME`.

## What each category changes

- **Health score:** only `actionable` markers count; more than 50 of them lowers
  the code-hygiene points, as before.
- **Risk `TODO-CLUSTER`:** counts `actionable` markers per file and fires when one
  file has 10 or more (the threshold is unchanged). A file that only mentions the
  words is not a hot spot.
- **Reports:** the Markdown table has a `Category` column and a summary line with
  the five counts; JSON has `category` on every marker and `todo_categories`;
  SARIF carries `properties.category`. `safety` markers stay in the list, so a
  reviewer can still find them.

## Where markers are not looked for

Directories named `golden`, `fixtures`, `snapshots` or `__snapshots__` and
Markdown / reStructuredText files are excluded by default, and `[todo]
exclude_globs` in `.sarand.toml` adds more; the report says how many markers were
suppressed. Vendored dependencies, build output and similar directories are
already left out by the file scan itself. Generated source is not recognised
automatically: list it in `exclude_globs`.

A task written inside a string literal of a test (`write(f, "# TODO: x")`) looks
like a real task. Exclude such files with `exclude_globs`.

## What changed in R13-E

- The scanner reported only the first marker on a line; it now reports all of
  them, so some counts rise. The cached marker results of older runs are
  discarded once.
- The health contract accepted `TODO-style` and `TODO-CLUSTER` as tasks (a hyphen
  with no space was enough), and `TODO: ...` in documentation. Those are
  mentions now. Measured on sarand's own report (149 markers): 19 matched the old
  contract; none was a task in the project's own code (17 were prose such as
  `TODO-style` and `TODO-CLUSTER`, 2 were fixture strings in tests).
- `TODO(owner): x` is now accepted as a task.
