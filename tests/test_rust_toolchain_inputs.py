"""Every dtolnay/rust-toolchain step names its toolchain (audit R8e).

That action reads the toolchain from the ref it is called with (`@stable`,
`@1.88`). Once `scripts/pin_actions.py --write` replaces the ref with a commit
SHA, that information is gone, and a step without the `toolchain` input fails.
This guard keeps every such step safe for SHA pinning.

این اکشن نسخه‌ی toolchain را از ref می‌خواند؛ بعد از پین به SHA باید ورودی
`toolchain` صریح باشد، وگرنه step شکست می‌خورد.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
_ACTION = "dtolnay/rust-toolchain@"


def _rust_toolchain_steps() -> list[tuple[str, dict[str, Any]]]:
    found: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(_WORKFLOWS.glob("*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job_name, job in (data.get("jobs") or {}).items():
            for step in job.get("steps") or []:
                if str(step.get("uses", "")).startswith(_ACTION):
                    found.append((f"{path.name}:{job_name}", step))
    return found


def test_there_are_rust_toolchain_steps_to_guard() -> None:
    assert len(_rust_toolchain_steps()) >= 4


def test_every_rust_toolchain_step_has_an_explicit_toolchain_input() -> None:
    missing = [
        where
        for where, step in _rust_toolchain_steps()
        if not (step.get("with") or {}).get("toolchain")
    ]
    assert missing == []
