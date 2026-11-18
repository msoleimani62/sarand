"""Entry points of the repository (R14-A2, docs/R14A_PLAN.md section 9).

An entry point is a place execution can start. Each one carries its type, where it is
written, the rule that found it, a confidence and the evidence. Plain functions that
merely *could* be run are **not** entry points.

Found by these rules only:

- `if __name__ == "__main__":` at module level: **definite** (a language rule);
- a `__main__.py` file: **definite** (`python -m package` runs it);
- `[project.scripts]`, `[project.gui-scripts]`, `[tool.poetry.scripts]` and
  `[project.entry-points.<group>]` of a `pyproject.toml`: the target `module:attr` is
  resolved to a repository module or symbol, with the confidence of that resolution
  (definite when it resolves by the rules of `resolve.py`), **unknown** with a note when
  it does not (a target outside the repository, a module found in two roots, a missing
  name);
- `[tool.pytest.ini_options] testpaths`: a `test_root`, definite when an included file
  lies under the path, unknown otherwise;
- framework application objects, **probable** only: a function decorated with
  `click.command` or `click.group` (and `click` declared), a module-level
  `typer.Typer(...)` (and `typer` declared), a module-level `argparse.ArgumentParser(...)`.

A manifest line is not tracked: the location of a manifest entry is the manifest's path
with line 0.

نقطه‌ی ورود جایی است که اجرا می‌تواند شروع شود؛ فقط با قواعد بالا و همراه با شاهد.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Sequence

from sarand.structure.facts import FileFacts
from sarand.structure.imports import pick_module
from sarand.structure.model import (
    CONF_DEFINITE,
    CONF_PROBABLE,
    CONF_UNKNOWN,
    EP_CONSOLE_SCRIPT,
    EP_ENTRY_POINT_GROUP,
    EP_FRAMEWORK_APP,
    EP_MAIN_BLOCK,
    EP_PACKAGE_MAIN,
    EP_TEST_ROOT,
    SYM_CLASS,
    SYM_VARIABLE,
    EntryPoint,
    SourceLocation,
)
from sarand.structure.resolve import Resolver

_EXTRAS = re.compile(r"\s*\[[^\]]*\]\s*$")
_CLICK_DECORATORS = frozenset({"click.command", "click.group"})


def _manifest_location(path: str) -> SourceLocation:
    return SourceLocation(path, 0, 0, 0, 0)


def _table(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _resolve_target(resolver: Resolver, target: str) -> tuple[str, str, str, str]:
    """(resolved, confidence, method, note) of a `module:attr` entry point target."""
    text = _EXTRAS.sub("", target.strip())
    module, _, attrs = text.partition(":")
    module = module.strip()
    if not module:
        return "", CONF_UNKNOWN, "entry-point-target", "the target has no module"
    top = module.split(".", 1)[0]
    if top not in resolver.index.by_name and top not in resolver.index.prefixes:
        return (
            "",
            CONF_UNKNOWN,
            "entry-point-target",
            "the target module is not in the repository",
        )
    entity, how = pick_module(
        resolver.index.by_name.get(module, []), "", only_root=False
    )
    if entity is None:
        note = (
            f"{module} exists in more than one source root"
            if how == "ambiguous"
            else f"{module} is not a module of the repository"
        )
        return "", CONF_UNKNOWN, "entry-point-target", note
    if not attrs.strip():
        return module, CONF_DEFINITE, "entry-point-module", ""
    mfacts = resolver.t.by_path.get(entity.path)
    if mfacts is None:
        return "", CONF_UNKNOWN, "entry-point-target", f"{module} was not analysed"
    names = [part for part in attrs.strip().split(".") if part]
    value = resolver.member_of_module(module, mfacts, names[0], mfacts, 0)
    if names[1:]:
        value = resolver.follow_attributes(value, tuple(names[1:]), mfacts)
    if value.kind == "symbol":
        return value.target, value.confidence, "entry-point-symbol", value.note
    if value.kind == "module":
        return value.target, value.confidence, "entry-point-module", ""
    note = value.note or "the name does not resolve to a definition of the repository"
    return "", CONF_UNKNOWN, "entry-point-target", note


def _from_manifest(
    path: str,
    text: str,
    resolver: Resolver,
    included: Sequence[str],
) -> list[EntryPoint]:
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError):
        return []
    found: list[EntryPoint] = []
    location = _manifest_location(path)
    directory = path.rpartition("/")[0]

    def add_target(kind: str, name: str, target: str) -> None:
        resolved, confidence, method, note = _resolve_target(resolver, target)
        found.append(
            EntryPoint(
                type=kind,
                name=name,
                target=target,
                resolved=resolved,
                confidence=confidence,
                method=method,
                evidence=f'{name} = "{target}"',
                location=location,
                note=note,
            )
        )

    project = _table(data.get("project"))
    for table in ("scripts", "gui-scripts"):
        for name, target in sorted(_table(project.get(table)).items()):
            if isinstance(target, str):
                add_target(EP_CONSOLE_SCRIPT, name, target)
    for group, entries in sorted(_table(project.get("entry-points")).items()):
        for name, target in sorted(_table(entries).items()):
            if isinstance(target, str):
                add_target(EP_ENTRY_POINT_GROUP, f"{group}:{name}", target)
    tool = _table(data.get("tool"))
    poetry = _table(tool.get("poetry"))
    for name, target in sorted(_table(poetry.get("scripts")).items()):
        if isinstance(target, str):
            add_target(EP_CONSOLE_SCRIPT, name, target)
    pytest_options = _table(_table(tool.get("pytest")).get("ini_options"))
    testpaths = pytest_options.get("testpaths")
    if isinstance(testpaths, str):
        testpaths = testpaths.split()
    if isinstance(testpaths, list):
        for raw in testpaths:
            if not isinstance(raw, str) or not raw.strip():
                continue
            relative = raw.strip().strip("/")
            joined = f"{directory}/{relative}" if directory else relative
            exists = any(p == joined or p.startswith(joined + "/") for p in included)
            found.append(
                EntryPoint(
                    type=EP_TEST_ROOT,
                    name=raw.strip(),
                    target=joined,
                    resolved=joined if exists else "",
                    confidence=CONF_DEFINITE if exists else CONF_UNKNOWN,
                    method="pytest-testpaths",
                    evidence=f'testpaths = "{raw.strip()}"',
                    location=location,
                    note="" if exists else "no included file lies under this path",
                )
            )
    return found


def _declared(resolver: Resolver, name: str) -> bool:
    return name in resolver.index.declared


def _from_facts(facts: Sequence[FileFacts], resolver: Resolver) -> list[EntryPoint]:
    found: list[EntryPoint] = []
    for item in facts:
        for block in item.main_blocks:
            found.append(
                EntryPoint(
                    type=EP_MAIN_BLOCK,
                    name="",
                    target=item.label,
                    resolved=item.label,
                    confidence=CONF_DEFINITE,
                    method="main-block",
                    evidence=block.evidence,
                    location=block.location,
                )
            )
        file_name = item.path.rsplit("/", 1)[-1]
        if file_name == "__main__.py" and item.entity is not None:
            package = item.entity.name.rpartition(".")[0]
            found.append(
                EntryPoint(
                    type=EP_PACKAGE_MAIN,
                    name=f"python -m {package}" if package else "python __main__.py",
                    target=item.entity.name,
                    resolved=item.entity.name,
                    confidence=CONF_DEFINITE,
                    method="dunder-main-file",
                    evidence="__main__.py",
                    location=SourceLocation(item.path, 1, 0, 1, 0),
                )
            )
        for info in item.symbols:
            symbol = info.symbol
            if symbol.kind == SYM_VARIABLE and info.value_call and symbol.parent == "":
                called = resolver.resolve_chain(item, info.scope, info.value_call)
                if called.kind != "external":
                    continue
                if called.target == "typer.Typer" and _declared(resolver, "typer"):
                    method = "typer-app"
                elif called.target == "argparse.ArgumentParser":
                    method = "argparse-parser"
                else:
                    continue
                found.append(
                    EntryPoint(
                        type=EP_FRAMEWORK_APP,
                        name=symbol.name,
                        target=f"{item.label}:{symbol.qualname}",
                        resolved=symbol.id,
                        confidence=CONF_PROBABLE,
                        method=method,
                        evidence=f"{symbol.name} = {'.'.join(info.value_call)}(...)",
                        location=symbol.location,
                        note="an application object, not proof that it is run",
                    )
                )
            elif symbol.kind != SYM_CLASS and info.decorator_chains:
                names = resolver.decorator_names(info)
                if any(n in _CLICK_DECORATORS for n in names) and _declared(
                    resolver, "click"
                ):
                    found.append(
                        EntryPoint(
                            type=EP_FRAMEWORK_APP,
                            name=symbol.name,
                            target=f"{item.label}:{symbol.qualname}",
                            resolved=symbol.id,
                            confidence=CONF_PROBABLE,
                            method="click-decorator",
                            evidence=next(
                                d
                                for d, n in zip(symbol.decorators, names, strict=True)
                                if n in _CLICK_DECORATORS
                            ),
                            location=symbol.location,
                            note="a click command, not proof that it is run",
                        )
                    )
    return found


def find_entry_points(
    manifests: Sequence[tuple[str, str]],
    included: Sequence[str],
    facts: Sequence[FileFacts],
    resolver: Resolver,
) -> tuple[EntryPoint, ...]:
    """Every entry point of the project, sorted. `manifests` are the
    `pyproject.toml` files as (relative path, text)."""
    found = _from_facts(facts, resolver)
    for path, text in manifests:
        found.extend(_from_manifest(path, text, resolver, included))
    found.sort(
        key=lambda e: (
            e.type,
            e.name,
            e.target,
            e.location.path,
            e.location.line,
            e.location.col,
            e.method,
        )
    )
    return tuple(found)
