"""Pins the claims of the README "Trust model" section to the code
(AGENTS.md 5.70): a claim in the documentation is a claim to verify.

- sarand never installs dependencies, never runs `make`, never uses a shell;
- the only project scripts it starts are npm's `test` and `lint`;
- the trust model is documented in both READMEs and announced by `--help`;
- SECURITY.md and CONTRIBUTING.md exist and are linked with absolute URLs.
"""

from __future__ import annotations

import ast
from pathlib import Path

from sarand import cli

_ROOT = Path(__file__).resolve().parent.parent
_PACKAGE = _ROOT / "python" / "sarand"
_ABSOLUTE = "https://github.com/msoleimani62/sarand/blob/main/"


def _trees() -> list[tuple[Path, ast.AST]]:
    return [
        (path, ast.parse(path.read_text(encoding="utf-8")))
        for path in sorted(_PACKAGE.rglob("*.py"))
    ]


def _string_lists() -> list[tuple[Path, int, list[str]]]:
    """Every list literal whose items are all plain strings (argv-shaped)."""
    found: list[tuple[Path, int, list[str]]] = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if not isinstance(node, ast.List) or not node.elts:
                continue
            items = [
                elt.value
                for elt in node.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            ]
            if len(items) == len(node.elts):
                found.append((path, node.lineno, items))
    return found


def test_sarand_never_starts_a_shell() -> None:
    offenders: list[str] = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if not isinstance(node, ast.keyword) or node.arg != "shell":
                continue
            value = node.value
            if isinstance(value, ast.Constant) and value.value is True:
                offenders.append(f"{path.relative_to(_ROOT)}:{value.lineno}")
    assert offenders == []


def test_sarand_never_runs_make_or_installs_dependencies() -> None:
    forbidden_first = {"make", "gmake"}
    offenders: list[str] = []
    for path, line, items in _string_lists():
        if items[0] in forbidden_first or "install" in items[1:3]:
            offenders.append(f"{path.relative_to(_ROOT)}:{line} {items[:3]}")
    assert offenders == []


def test_the_only_npm_project_scripts_started_are_test_and_lint() -> None:
    commands = [items for _path, _line, items in _string_lists() if items[0] == "npm"]
    assert commands, "the node analyzer should start npm"
    for items in commands:
        assert items[1] in {"test", "run", "audit"}, items
        if items[1] == "run":
            assert items[2] == "lint", items


def test_help_announces_the_trust_model() -> None:
    epilog = cli.build_parser().epilog or ""
    assert "Trust" in epilog
    assert "--skip-tests" in epilog


def test_both_readmes_document_the_trust_model() -> None:
    english = (_ROOT / "README.md").read_text(encoding="utf-8")
    persian = (_ROOT / "README.fa.md").read_text(encoding="utf-8")
    assert "### Trust model: scanning runs project code" in english
    assert '<a id="trust-model"></a>' in persian
    for text in (english, persian):
        assert "--skip-tests" in text
        assert "--no-source" in text
        assert "SECURITY.md" in text


def test_security_and_contributing_files_exist_and_are_linked_absolutely() -> None:
    assert (_ROOT / "SECURITY.md").is_file()
    assert (_ROOT / "CONTRIBUTING.md").is_file()
    english = (_ROOT / "README.md").read_text(encoding="utf-8")
    assert f"({_ABSOLUTE}SECURITY.md)" in english
    assert f"({_ABSOLUTE}CONTRIBUTING.md)" in english


def test_the_contributing_check_chain_matches_ci() -> None:
    contributing = (_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    ci = (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for command in (
        "cargo clippy --all-targets --all-features -- -D warnings",
        "mypy .",
    ):
        assert command in contributing
        assert command in ci
