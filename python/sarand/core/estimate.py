"""A cheap size estimate made *before* the report is rendered.

`--full` deliberately means "everything": no file-size, depth or entry
limits. That is the right default for a complete report, but on a small
device (a 2 GB laptop, a phone) a medium project can produce a report that
is slow to build or runs out of memory, and until now the first sign of it
was the crash. The included files and their sizes are already known after
the scan, so sarand can say up front how much source it is about to embed and
warn when that looks too big for this machine -- without changing what
`--full` means or asking questions (sarand runs unattended in CI).

یک تخمین ارزان از حجم، *قبل* از رندر گزارش. `--full` عمداً یعنی «همه‌چیز»:
بدون محدودیت اندازه‌ی فایل، عمق و تعداد ورودی. برای یک گزارش کامل این پیش‌فرض
درست است، ولی روی دستگاه کوچک (لپ‌تاپ ۲ گیگابایتی، گوشی) یک پروژه‌ی متوسط
می‌تواند گزارشی بسازد که ساختنش کند است یا حافظه تمام می‌کند، و تا حالا
اولین نشانه‌اش خودِ crash بود. فایل‌های واردشده و اندازه‌شان بعد از اسکن
معلوم است، پس sarand می‌تواند از همان اول بگوید چقدر سورس embed می‌کند و
وقتی برای این ماشین زیاد به نظر برسد هشدار بدهد -- بدون تغییر معنی `--full`
و بدون پرسیدن سؤال (sarand در CI بدون مراقبت اجرا می‌شود).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from sarand.utils.fs import human_size

LARGE_REPORT_BYTES = 50 * 1024 * 1024
# Warn when the embedded source alone exceeds this share of free memory: the
# report text, the tool output and the renderer's own copy come on top of it.
# وقتی فقط سورسِ embed‌شده از این سهم حافظه‌ی آزاد بیشتر شود هشدار بده: متن
# گزارش، خروجی ابزارها و نسخه‌ی خودِ رندرر هم روی آن اضافه می‌شوند.
MEMORY_FRACTION = 0.25


def estimate_source_bytes(
    records: Sequence[Mapping[str, Any]], included: Iterable[Path]
) -> int:
    """Total size of the files that will be embedded in the report."""
    sizes = {
        Path(str(record["rel_path"])).as_posix(): int(record["size"])
        for record in records
    }
    return sum(sizes.get(path.as_posix(), 0) for path in included)


def size_advice(estimated: int, available: int | None) -> str | None:
    """A warning when `estimated` looks too large, or None when it is fine."""
    too_big = estimated >= LARGE_REPORT_BYTES
    tight = (
        available is not None
        and available > 0
        and estimated > available * MEMORY_FRACTION
    )
    if not (too_big or tight):
        return None
    message = f"The report will embed about {human_size(estimated)} of source"
    if available:
        message += f" (about {human_size(available)} of memory is free)"
    return (
        message + ". Large reports can be slow, or run out of memory on a small "
        "device. Consider --no-source, a lower --max-file-size (the default is "
        "2M; --full removes the limit) or running without --full."
    )
