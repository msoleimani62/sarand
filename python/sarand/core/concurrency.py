"""How many external tools sarand starts at once (AGENTS.md 5.73).

Every analyzer, every component of a hybrid project and every workspace member used
to start its tools all at once: `cargo test`, `pytest`, `npm test` and the audits
together. On the owner's 6 GB phone and 2 GB laptop that can exhaust memory. A single
process-wide limit now applies to every external command (`utils/command.py`); this
module only decides what that limit is.

Precedence: `--jobs N` on the command line, then the `SARAND_JOBS` environment
variable, then a default that follows the machine: one tool per CPU and per GiB of
*free* memory (measured when the scan starts, so a busy machine gets fewer), at most
DEFAULT_MAX_JOBS. A 2 GB laptop therefore runs one tool at a time and a 16-core
workstation with plenty of memory runs eight.

تعداد ابزارهای بیرونی که sarand هم‌زمان اجرا می‌کند. قبلاً همه‌ی آن‌ها با هم شروع
می‌شدند و روی گوشی ۶ گیگ و لپ‌تاپ ۲ گیگ می‌توانست حافظه را تمام کند. حالا یک سقف
سراسری روی هر دستور بیرونی اعمال می‌شود؛ این ماژول فقط تصمیم می‌گیرد سقف چقدر باشد.
اولویت: `--jobs N`، بعد متغیر `SARAND_JOBS`، بعد پیش‌فرضی که از دستگاه می‌آید.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping

from sarand.constants import DEFAULT_MAX_JOBS, MAX_JOBS_LIMIT, MEMORY_PER_JOB_MIB

ENV_VARIABLE = "SARAND_JOBS"


def default_jobs(cpus: int | None, available_bytes: int | None) -> int:
    """The limit to use when nothing was asked for.

    One per CPU, one per MEMORY_PER_JOB_MIB of free memory, at most DEFAULT_MAX_JOBS,
    never less than one. `available_bytes` is None when the system does not report
    free memory; the limit then follows the CPU count only.
    """
    jobs = max(1, min(DEFAULT_MAX_JOBS, cpus or 1))
    if available_bytes is not None:
        by_memory = max(1, available_bytes // (MEMORY_PER_JOB_MIB * 1024 * 1024))
        jobs = min(jobs, by_memory)
    return jobs


def parse_jobs(text: str, source: str) -> int:
    """A whole number from 1 to MAX_JOBS_LIMIT, or ValueError naming `source`."""
    try:
        value = int(text.strip())
    except ValueError:
        raise ValueError(f"{source} must be a whole number, got {text!r}") from None
    if not 1 <= value <= MAX_JOBS_LIMIT:
        raise ValueError(
            f"{source} must be between 1 and {MAX_JOBS_LIMIT}, got {value}"
        )
    return value


def jobs_argument(text: str) -> int:
    """argparse `type=` for `--jobs`."""
    try:
        return parse_jobs(text, "--jobs")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def resolve_jobs(
    cli_value: int | None,
    environ: Mapping[str, str],
    cpus: int | None,
    available_bytes: int | None,
) -> int:
    """`--jobs`, else `SARAND_JOBS`, else the machine default.

    Raises ValueError when `SARAND_JOBS` is set to something invalid; the caller warns
    and falls back to `default_jobs` (a bad environment must not stop a scan).
    """
    if cli_value is not None:
        return cli_value
    raw = environ.get(ENV_VARIABLE)
    if raw is not None and raw.strip():
        return parse_jobs(raw, ENV_VARIABLE)
    return default_jobs(cpus, available_bytes)
