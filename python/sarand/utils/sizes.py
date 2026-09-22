"""Parsing of human-written sizes such as `512K`, `2M` or `1.5G`.

Used by `--max-file-size`. Kept in its own module (not `utils/fs.py`) so the
public `sarand.utils` API is unchanged.

تجزیه‌ی اندازه‌هایی که آدم می‌نویسد، مثل `512K`، `2M` یا `1.5G`. برای
`--max-file-size` استفاده می‌شود. عمداً در ماژول جدا است (نه `utils/fs.py`) تا
API عمومی `sarand.utils` تغییر نکند.
"""

from __future__ import annotations

import argparse
import re

_UNITS = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3}
_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([kmg]?)(?:i?b)?\s*$", re.IGNORECASE)


def parse_size(text: str) -> int:
    """Bytes for `text`: a plain number of bytes, or a number with K/M/G
    (powers of 1024; an optional trailing `B`/`iB` is accepted).

    Raises `ValueError` for anything else.
    """
    match = _PATTERN.match(text)
    if match is None:
        raise ValueError(f"not a size: {text!r} (examples: 500000, 512K, 2M, 1.5G)")
    number, unit = match.groups()
    return int(float(number) * _UNITS[unit.lower()])


def size_argument(text: str) -> int:
    """`argparse` type: like `parse_size`, but errors are reported by argparse."""
    try:
        return parse_size(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
