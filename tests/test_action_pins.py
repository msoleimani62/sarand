"""Action references in the workflows (AGENTS.md 5.72).

`scripts/pin_actions.py` pins every `uses:` to a commit SHA, but it needs the
network, so the maintainer runs it. Until then this test enforces the weaker rule
that holds today: a reference is a tag (`v6`, `v1.2.3`), a branch the action's
authors document for this purpose, or a SHA. After the script has run, set
`ENFORCE_PINNED = True` and the test requires SHAs only.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

_ROOT = Path(__file__).resolve().parent.parent

# Flip to True after `python3 scripts/pin_actions.py --write` (AGENTS.md 5.72).
ENFORCE_PINNED = False

# Branch refs that the action's own documentation tells users to use.
_ALLOWED_BRANCH_REFS = {"stable", "release/v1"}
_TAG = re.compile(r"^v\d+(\.\d+){0,2}$")


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "pin_actions", _ROOT / "scripts" / "pin_actions.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _workflow_texts() -> dict[str, str]:
    folder = _ROOT / ".github" / "workflows"
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(folder.glob("*.y*ml"))
    }


def test_every_reference_is_a_tag_a_documented_branch_or_a_sha() -> None:
    script = _load_script()
    offenders: list[str] = []
    for name, text in _workflow_texts().items():
        for action, ref in script.find_uses(text):
            ok = (
                script.is_pinned(ref)
                or _TAG.fullmatch(ref)
                or ref in _ALLOWED_BRANCH_REFS
            )
            if not ok:
                offenders.append(f"{name}: {action}@{ref}")
    assert offenders == []


def test_pins_are_required_once_enforced() -> None:
    if not ENFORCE_PINNED:
        return
    script = _load_script()
    unpinned = [
        f"{name}: {action}@{ref}"
        for name, text in _workflow_texts().items()
        for action, ref in script.find_uses(text)
        if not script.is_pinned(ref)
    ]
    assert unpinned == []


def test_pin_text_rewrites_unpinned_references_and_keeps_the_rest() -> None:
    script = _load_script()
    sha_a = "a" * 40
    sha_b = "b" * 40
    text = (
        "steps:\n"
        "  - uses: actions/checkout@v6\n"
        f"  - uses: actions/cache@{sha_b} # v5\n"
        "  - uses: ./local-action\n"
        "  - uses: docker://alpine:3\n"
        "  - name: not an action\n"
        "    run: echo uses@v1\n"
        "  - uses: pypa/gh-action-pypi-publish@release/v1\n"
        "    with:\n"
        "      packages-dir: dist\n"
    )
    calls: list[tuple[str, str]] = []

    def resolve(action: str, ref: str) -> str:
        calls.append((action, ref))
        return sha_a

    new_text, changes = script.pin_text(text, resolve)
    assert calls == [
        ("actions/checkout", "v6"),
        ("pypa/gh-action-pypi-publish", "release/v1"),
    ]
    assert f"  - uses: actions/checkout@{sha_a} # v6\n" in new_text
    assert f"  - uses: pypa/gh-action-pypi-publish@{sha_a} # release/v1\n" in new_text
    assert f"actions/cache@{sha_b} # v5" in new_text
    assert "uses: ./local-action" in new_text
    assert "docker://alpine:3" in new_text
    assert "run: echo uses@v1" in new_text
    assert len(changes) == 2
    # Running it again changes nothing: everything is pinned now.
    again, more = script.pin_text(new_text, resolve)
    assert again == new_text
    assert more == []


def test_find_uses_ignores_local_and_docker_actions() -> None:
    script = _load_script()
    text = "- uses: ./a\n- uses: docker://x:1\n- uses: o/r/sub@v2\n"
    assert script.find_uses(text) == [("o/r/sub", "v2")]
