"""Shared test helpers. Deliberately dependency-free (no `import pytest`)
so these files remain runnable under real pytest, plain unittest, or any
minimal test collector -- see AGENTS.md section 3.8 on verification.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any


def assert_raises(
    exc_type: type[BaseException], fn: Callable[..., Any], *args: Any, **kwargs: Any
) -> None:
    """Assert that calling fn(*args, **kwargs) raises exc_type."""
    try:
        fn(*args, **kwargs)
    except exc_type:
        return
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(
            f"Expected {exc_type.__name__}, got {type(exc).__name__}: {exc}"
        )
    raise AssertionError(f"Expected {exc_type.__name__}, but nothing was raised")


def write(path: Path, content: str = "") -> Path:
    """Create a file (and parent dirs) with the given content, return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
