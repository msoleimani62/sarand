"""Assembly analyzer: detects assembly sources and names their dialects.

There is no universal assembler or test runner for "assembly" -- the right
tool depends on the architecture and syntax (NASM, GNU as, MASM, FASM, an
ARM or RISC-V toolchain, ...) and is almost always driven by the project's
own Makefile or build script. So this analyzer deliberately runs nothing:
its job is *identification*. It matches when the project has assembly
sources in the root or a conventional first-level directory, reports the
files that declare an entry symbol, and the dialect of every file appears
in the report's "Detected project" section (see
`sarand.discovery.assembly` for the classifier).

Never executes or assembles project code. Detection is shallow and
deterministic, so vendored or nested files cannot turn a project into an
assembly project.

تحلیل‌گر اسمبلی: سورس‌های اسمبلی را شناسایی می‌کند و گویششان را نام می‌برد.

برای «اسمبلی» هیچ اسمبلر یا test runner جهانی وجود ندارد -- ابزار درست به
معماری و سینتکس بستگی دارد (NASM، GNU as، MASM، FASM، زنجیره‌ابزار ARM یا
RISC-V، ...) و تقریباً همیشه با Makefile یا اسکریپت build خودِ پروژه اجرا
می‌شود. پس این آنالایزر عمداً چیزی اجرا نمی‌کند: کارش *شناسایی* است. وقتی
پروژه در ریشه یا یک پوشه‌ی قراردادی سطح اول سورس اسمبلی داشته باشد match
می‌شود، فایل‌هایی را که نماد ورود تعریف می‌کنند گزارش می‌کند و گویش هر فایل
در بخش «Detected project» گزارش می‌آید (طبقه‌بند در
`sarand.discovery.assembly` است).

هرگز کد پروژه را اجرا یا اسمبل نمی‌کند. تشخیص سطحی و قطعی است، پس فایل‌های
vendored یا تو در تو نمی‌توانند پروژه را «پروژه‌ی اسمبلی» کنند.
"""

from __future__ import annotations

from pathlib import Path

from sarand.discovery.assembly import assembly_entry_points, has_assembly_sources
from sarand.models.results import CommandResult


class AssemblyAnalyzer:
    name = "Assembly"

    def matches(self, root: Path) -> bool:
        return has_assembly_sources(root)

    def entry_points(self, root: Path) -> list[str]:
        return assembly_entry_points(root)

    async def run_tests(self, root: Path) -> CommandResult | None:
        return None

    async def run_quality(self, root: Path) -> list[CommandResult]:
        return []

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
