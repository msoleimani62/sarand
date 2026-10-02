# Writing a sarand plugin

A plugin teaches sarand about one more language or tool. It is a normal
Python package that registers one class under the `sarand.analyzers`
entry-point group. sarand finds it, wraps it so it cannot crash a scan, and
runs it next to the built-in analyzers.

[Persian / فارسی](PLUGINS.fa.md) · a complete working example lives in
[`examples/sarand-plugin-justfile`](../examples/sarand-plugin-justfile).

## The contract

`PLUGIN_API_VERSION` is **1**. Your class must provide:

| Member | Required | Meaning |
|---|---|---|
| `name: str` | yes | Non-empty, unique display name, e.g. `"Zig"`. |
| `matches(root: Path) -> bool` | yes | `True` when your tool applies to the project at `root`. Check for a real marker file; never run a tool here. |
| `entry_points(root: Path) -> list[str]` | yes | Existing entry-point files under `root` (may be empty). |
| `async run_tests(root: Path) -> CommandResult \| None` | yes | Run the test suite, or return `None` if there is nothing to run. |
| `async run_quality(root: Path) -> list[CommandResult]` | yes | Lint and format checks. Empty list if none. |
| `async run_security(root: Path) -> list[CommandResult]` | no | Dependency or vulnerability checks. Leave it out if you have none. |
| `api_version: int` | no | The plugin API you were written for. Defaults to 1. |

Rules that keep your plugin well behaved:

- sarand calls `run_*` only after `matches(root)` returned `True`.
- If your external tool is missing, return a *skipped* result
  (`make_command_result(kind, 127, "", 0.0, skipped=True, skip_reason="x not found in PATH")`)
  instead of failing. A missing tool is information, not a broken project.
- All `run_*` methods are `async` and may run concurrently with other
  analyzers. Use `run_cmd_async` for subprocesses: it has a timeout and
  cleans up the process group.
- Do not write into the project directory.

### The public surface

Import only these from sarand; everything else may change without notice:

- `sarand.analyzers.base.LanguageAnalyzer` and `PLUGIN_API_VERSION`
- `sarand.models.results.CommandResult` and `Issue`
- `sarand.utils.command.make_command_result` and `run_cmd_async`

`make_command_result(kind, returncode, output, duration, *, skipped=False, skip_reason="")`
builds a result and extracts warnings and errors from the tool output.
`run_cmd_async(cmd, cwd, timeout)` returns `(returncode, output, seconds)`.

## What sarand does for you (and to you)

**Lifecycle.** Each scan creates one instance with `YourClass()` (no
arguments), calls the methods above, and drops it. Keep `__init__` cheap and
keep no state between scans.

**Failure isolation.** Every plugin is wrapped. If it raises, returns the
wrong type, or returns invalid list items, sarand logs a warning and
substitutes one skipped result that names your plugin, the phase and the
error. The scan, and every other analyzer, carries on. A plugin failure is
never counted as a failing test of the user's project. A plugin that cannot
be imported or constructed is skipped with a warning.

**Rejected plugins.** A plugin is skipped, with the reason logged, when it
has no usable `name`, lacks a required method, or declares an `api_version`
newer than the running sarand supports.

**Name clashes.** If your `name` equals a built-in analyzer or an earlier
plugin (case-insensitive), your plugin is skipped. First one wins; pick a
distinct name.

**Order.** Plugins load sorted by entry-point name, so results are
reproducible.

Not provided: sandboxing, and a timeout for work that is not a subprocess.
A plugin that awaits something forever will hang the scan.

## Version compatibility

`PLUGIN_API_VERSION` changes only when the contract changes in a way old
plugins cannot handle. Adding optional members (as `run_security` was) does
not bump it. Policy:

- A plugin with no `api_version` is treated as version 1.
- A plugin declaring a version **higher** than sarand supports is skipped
  with a message telling the user to upgrade sarand or the plugin.
- A plugin declaring a lower version keeps working for as long as sarand
  supports that version; removals are announced in the changelog first.
- Pin a lower bound on sarand in your `pyproject.toml`
  (`dependencies = ["sarand>=0.6.11"]`).

## Author workflow

1. **Start from the example.** Copy `examples/sarand-plugin-justfile`, then
   rename the package, the class and the entry-point key.
2. **Implement the contract** above. Keep `matches` fast and side-effect free.
3. **Register it** in your `pyproject.toml`:

   ```toml
   [project.entry-points."sarand.analyzers"]
   zig = "my_zig_plugin:ZigAnalyzer"
   ```

4. **Install it into the environment sarand runs from.** With a pipx install
   of sarand:

   ```bash
   pipx inject sarand ./my-plugin
   ```

   With a plain virtual environment, `pip install ./my-plugin` in the same
   environment. A plugin installed into a different environment is invisible.
5. **Check that it is discovered**, using the Python of sarand's environment:

   ```bash
   python -c "from sarand.analyzers.registry import discover_analyzers; print([a.name for a in discover_analyzers()])"
   ```

   For pipx, use the Python inside sarand's own environment
   (`pipx environment` prints where those live). Your `name` should be in the
   list. Alternatively run `sarand --verbose` on any project: it logs
   `Loaded plugin analyzer: ...` for every plugin it accepted. A plugin that
   was skipped is always logged as a warning, with the reason, even without
   `--verbose`.
6. **Test it** like any package. `asyncio.run(YourAnalyzer().run_tests(path))`
   against a temporary project directory is enough for most plugins.
7. **Run sarand on a real project** that has your marker file and look for
   your results, labelled with your `kind` strings.

There is deliberately no plugin registry or marketplace: the API has to be
stable first.
