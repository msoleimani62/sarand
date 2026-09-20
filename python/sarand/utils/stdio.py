"""Make writing to stdout/stderr never raise `UnicodeEncodeError`.

sarand prints arrows, check marks and (from a scanned project's path or
file names) arbitrary Unicode. When the output stream is not UTF-8 --
Windows with redirected output or a legacy code page (cp437/cp1252),
a C/POSIX locale in a container or over SSH -- Python's default
`errors="strict"` turns the first such character into a crash before
any report is written. Switching the stream's error handler to
`replace` keeps its encoding and prints `?` for what cannot be encoded.

sarand فلش، تیک و (از مسیر یا نام فایل‌های پروژه‌ی اسکن‌شده) هر
Unicode دلخواهی چاپ می‌کند. وقتی جریان خروجی UTF-8 نباشد -- Windows با
خروجی redirect شده یا code page قدیمی (cp437/cp1252)، locale سیِ/POSIX
در container یا روی SSH -- مقدار پیش‌فرض `errors="strict"` پایتون اولین
چنین نویسه‌ای را قبل از نوشته‌شدن هر گزارشی به crash تبدیل می‌کند. تغییر
error handler جریان به `replace` انکودینگش را نگه می‌دارد و برای چیزی که
انکود نمی‌شود `?` چاپ می‌کند.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from typing import Any


def harden_stdio(streams: Iterable[Any] | None = None) -> None:
    """Set `errors="replace"` on each stream that supports `reconfigure`.

    Streams without `reconfigure` (pytest capture objects, custom
    wrappers) and closed/detached ones are left untouched.
    """
    targets = (sys.stdout, sys.stderr) if streams is None else streams
    for stream in targets:
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(errors="replace")
        except (ValueError, OSError, TypeError):
            continue
