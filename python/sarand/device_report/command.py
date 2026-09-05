"""CLI entry point for the device-report subsystem.

Invoked exactly like the RC subsystem -- `python3 -m
sarand.device_report.command` -- not registered as its own
[project.scripts] entry, matching README's existing documented
convention for `sarand.rc.command`.

نقطه‌ورود CLI زیرسیستم device-report.

دقیقاً مثل زیرسیستم RC فراخوانی می‌شود -- `python3 -m
sarand.device_report.command` -- و به‌عنوان یک entry جدا در
[project.scripts] ثبت نشده، مطابق قرارداد مستندشده‌ی README برای
`sarand.rc.command`.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sarand.device_report.config import build_parser, resolve_config
from sarand.device_report.report import generate_report


def _fail_write(output_file: Path, exc: OSError) -> int:
    print(f"Error: cannot write to output path: {output_file} ({exc})", file=sys.stderr)
    return 2


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        config = resolve_config(args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        config.output_file.write_text("")
    except OSError as exc:
        return _fail_write(config.output_file, exc)

    report_text = generate_report(config)

    try:
        config.output_file.write_text(report_text)
    except OSError as exc:
        return _fail_write(config.output_file, exc)

    print(f"Report written to: {config.output_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
