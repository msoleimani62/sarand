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
    """Create a file (and parent dirs) with the given content, return the path.

    Written as bytes on purpose: `write_text` translates "\\n" to "\\r\\n" on
    Windows, which made size/byte-exact assertions differ between systems.
    عمداً به‌صورت بایت نوشته می‌شود: `write_text` روی Windows "\\n" را به
    "\\r\\n" تبدیل می‌کند و همین باعث می‌شد assertion های اندازه/بایتی بین
    سیستم‌ها فرق کنند.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
    return path
