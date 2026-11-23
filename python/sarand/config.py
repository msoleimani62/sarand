"""Runtime configuration for sarand."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Any

from sarand.constants import (
    DEFAULT_OUTPUT_DIR,
    MAX_FILE_SIZE,
    MAX_TREE_DEPTH,
    MAX_TREE_ENTRIES,
)
from sarand.userconfig import load_persisted_config
from sarand.utils.fs import default_output_name


def _optional_path(value: Any) -> Path | None:
    """An optional path from the command line: absolute, symlinks left as they are.
    مسیر اختیاری خط فرمان: مطلق؛ symlinkها دست‌نخورده می‌مانند.
    """
    return Path(str(value)).expanduser().absolute() if value else None


def resolve_project_path(value: str | Path | None) -> Path:
    """Explicit value wins, otherwise the current working directory."""
    if value:
        return Path(value).expanduser().resolve()
    return Path.cwd().resolve()


def resolve_output_dir(cli_value: str | None) -> Path:
    """Priority: --output-dir > SARAND_OUTPUT_DIR > persisted config > ~/Downloads."""
    if cli_value:
        return Path(cli_value).expanduser().resolve()

    env_value = os.environ.get("SARAND_OUTPUT_DIR")
    if env_value:
        return Path(env_value).expanduser().resolve()

    persisted = load_persisted_config().get("output_dir")
    if persisted:
        return Path(persisted).expanduser().resolve()

    return DEFAULT_OUTPUT_DIR


def validate_output_name(value: str) -> None:
    """Require a portable, non-empty filename component, never a path.

    The name is joined to the output directory, so a separator, a drive or an
    absolute path would let the join leave that directory. The Windows rules
    (device names, a trailing dot or space, `:` and friends) keep the same
    report name valid on every platform.
    نام به دایرکتوری خروجی چسبانده می‌شود؛ جداکننده، درایو یا مسیر مطلق می‌گذارد
    این چسباندن از دایرکتوری بیرون برود. قواعد Windows (نام دستگاه‌ها، نقطه یا
    فاصله‌ی آخر، `:` و مانند آن) همان نام را روی همه‌ی پلتفرم‌ها معتبر نگه می‌دارد.
    """
    if not isinstance(value, str) or not value:
        raise ValueError("output_name must be a non-empty filename")
    if value in {".", ".."}:
        raise ValueError("output_name must not be '.' or '..'")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("output_name must not contain control characters")
    if "/" in value or "\\" in value:
        raise ValueError("output_name must be a filename, not a path")
    if any(char in value for char in '<>:"|?*') or value.endswith((" ", ".")):
        raise ValueError("output_name contains a non-portable filename character")
    windows_path = PureWindowsPath(value)
    reserved_stem = windows_path.name.split(".", 1)[0].rstrip(" .").upper()
    reserved_names = {"CON", "PRN", "AUX", "NUL"}
    if reserved_stem in reserved_names or (
        len(reserved_stem) == 4
        and reserved_stem[:3] in {"COM", "LPT"}
        and reserved_stem[3] in "123456789¹²³"
    ):
        raise ValueError("output_name uses a reserved Windows device name")
    if windows_path.is_absolute() or windows_path.drive:
        raise ValueError("output_name must not be an absolute or drive-qualified path")
    if Path(value).name != value:
        raise ValueError("output_name must be a single filename component")


def resolve_report_path(output_dir: Path, output_name: str) -> Path:
    """Resolve a report destination and reject symlink escapes from output_dir.

    Both the report and its `.sha256` companion must stay inside the resolved
    output directory and neither may be a symlink. This is a path check, not a
    sandbox against a process that renames parent directories concurrently.
    گزارش و فایل `.sha256` همراهش باید داخل دایرکتوری خروجیِ resolveشده بمانند و
    هیچ‌کدام symlink نباشند. این یک بررسی مسیر است، نه sandbox در برابر فرایندی که
    هم‌زمان دایرکتوری‌های والد را تغییر نام می‌دهد.
    """
    validate_output_name(output_name)
    resolved_dir = output_dir.resolve()
    report_path = resolved_dir / output_name
    checksum_path = report_path.with_suffix(report_path.suffix + ".sha256")
    for candidate in (report_path, checksum_path):
        if candidate.is_symlink():
            raise ValueError(
                f"report destination must not be a symlink: {candidate.name}"
            )
        candidate.resolve(strict=False).relative_to(resolved_dir)
    return report_path


@dataclass
class SarandConfig:
    """Runtime configuration for one sarand run."""

    project_root: Path = field(default_factory=Path.cwd)
    output_dir: Path = field(default_factory=lambda: DEFAULT_OUTPUT_DIR)
    output_name: str = ""
    skip_tests: bool = False
    # None: decided by SARAND_JOBS or the machine (core/concurrency.py).
    # None: با SARAND_JOBS یا از روی دستگاه تعیین می‌شود.
    jobs: int | None = None
    run_quality: bool = False
    run_security: bool = False
    skip_audit: bool = False
    verbose: bool = False
    debug: bool = False
    output_format: str = "markdown"
    max_tree_depth: int = MAX_TREE_DEPTH
    max_tree_entries: int = MAX_TREE_ENTRIES
    max_file_size: int = MAX_FILE_SIZE
    include_source: bool = True
    health_score: bool = True
    use_cache: bool = False
    full: bool = False
    # L4 (core/relevant_source.py): None means off, the default.
    # L4: برابر None یعنی خاموش (پیش‌فرض).
    relevant_source_tokens: int | None = None
    focus: str = ""
    # R14-A: build the repository structure (imports, cycles); off by default.
    # R14-A: ساخت ساختار مخزن؛ به‌طور پیش‌فرض خاموش.
    structure: bool = False
    # R14-D1 (S2): compare the structure with a reference snapshot / write a snapshot.
    # Both need `structure`; replacing an existing snapshot needs the explicit flag.
    # R14-D1 (S2): مقایسه‌ی ساختار با snapshot مرجع / نوشتن snapshot. هر دو به `structure`
    # نیاز دارند؛ جایگزینی snapshot موجود پرچم صریح می‌خواهد.
    structure_baseline: Path | None = None
    structure_snapshot: Path | None = None
    replace_structure_snapshot: bool = False

    def __post_init__(self) -> None:
        # A config built directly (not from CLI args) still gets the default name.
        # پیکربندیِ ساخته‌شده مستقیم (نه از آرگومان‌های CLI) هم نام پیش‌فرض می‌گیرد.
        if not self.output_name:
            self.output_name = default_output_name(
                self.project_root, self.output_format
            )

    @classmethod
    def from_args(cls, args: Any) -> SarandConfig:
        project = resolve_project_path(getattr(args, "project", None))
        output_format = str(getattr(args, "format", "markdown")).lower()
        out_dir = resolve_output_dir(getattr(args, "output_dir", None))
        explicit_name = getattr(args, "output_name", None)
        if explicit_name is None:
            output_name = default_output_name(project, output_format)
        else:
            output_name = str(explicit_name)
            validate_output_name(output_name)

        def _int_or(value: Any, default: int) -> int:
            return default if value is None else int(value)

        # --full: maximum-completeness report. Only changes what the
        # "no explicit value given" default resolves to for each limit
        # -- an explicit --max-depth/--max-entries still wins over
        # --full, same as any other explicit flag beats a convenience
        # default (matches AGENTS.md §4.13's spirit: explicit user
        # intent is never silently overridden by a convenience flag).
        # --full: گزارش با حداکثر کامل‌بودن. فقط تغییر می‌دهد که «مقدار
        # صریح داده نشده» برای هر محدودیت به چه چیزی resolve می‌شود --
        # یک --max-depth/--max-entries صریح همچنان بر --full غالب است.
        full = bool(getattr(args, "full", False))
        unlimited_tree_depth = 10_000
        unlimited_tree_entries = 1_000_000
        unlimited_file_size = (
            10 * 1024 * 1024 * 1024
        )  # 10 GiB -- no real source file exceeds this

        return cls(
            project_root=project,
            output_dir=out_dir,
            output_name=output_name,
            skip_tests=bool(getattr(args, "skip_tests", False)),
            jobs=getattr(args, "jobs", None),
            run_quality=full or bool(getattr(args, "quality", False)),
            run_security=full or bool(getattr(args, "security", False)),
            skip_audit=bool(getattr(args, "skip_audit", False)),
            verbose=bool(getattr(args, "verbose", False)),
            debug=bool(getattr(args, "debug", False)),
            output_format=output_format,
            max_tree_depth=_int_or(
                getattr(args, "max_depth", None),
                unlimited_tree_depth if full else MAX_TREE_DEPTH,
            ),
            max_tree_entries=_int_or(
                getattr(args, "max_entries", None),
                unlimited_tree_entries if full else MAX_TREE_ENTRIES,
            ),
            max_file_size=_int_or(
                getattr(args, "max_file_size", None),
                unlimited_file_size if full else MAX_FILE_SIZE,
            ),
            include_source=not bool(getattr(args, "no_source", False)),
            health_score=not bool(getattr(args, "no_health", False)),
            use_cache=bool(getattr(args, "cache", False)),
            relevant_source_tokens=getattr(args, "relevant_source", None),
            focus=str(getattr(args, "focus", None) or ""),
            structure=bool(getattr(args, "structure", False)),
            structure_baseline=_optional_path(
                getattr(args, "structure_baseline", None)
            ),
            structure_snapshot=_optional_path(
                getattr(args, "structure_snapshot", None)
            ),
            replace_structure_snapshot=bool(
                getattr(args, "replace_structure_snapshot", False)
            ),
            # Stored (not just used locally above) because renderers need
            # it too: --full's "nothing is skipped or cut short" promise
            # (its own --help text) has to reach the *rendering* layer,
            # not just file-collection limits -- otherwise a passing
            # tool's full output and a >500-row issue list still get cut
            # to a tail/head regardless of --full. See renderers/*.py's
            # `full_output` parameter.
            #
            # ذخیره می‌شود (نه فقط بالا مصرف محلی) چون رندرکننده‌ها هم
            # بهش نیاز دارند: وعده‌ی --full («چیزی رد یا کوتاه نمی‌شود» -
            # متن --help خودش) باید به لایه‌ی رندر هم برسد، نه فقط
            # محدودیت‌های جمع‌آوری فایل -- وگرنه خروجی کامل یک ابزار
            # موفق و یک لیست issue با بیش از ۵۰۰ ردیف همچنان صرف‌نظر از
            # --full به تِیل/سر کوتاه می‌شوند. پارامتر `full_output` در
            # renderers/*.py را ببینید.
            full=full,
        )

    def validate(self) -> None:
        validate_output_name(self.output_name)
        if not self.project_root.is_dir():
            raise ValueError(
                f"Project root does not exist or is not a directory: {self.project_root}"
            )
        allowed = {"markdown", "json", "text", "html", "pdf", "sarif"}
        if self.output_format not in allowed:
            raise ValueError(
                f"Unsupported output format: {self.output_format}. Allowed: {allowed}"
            )
        if self.max_tree_depth < 1:
            raise ValueError("max_tree_depth must be >= 1")
        if self.max_tree_entries < 1:
            raise ValueError("max_tree_entries must be >= 1")
        if self.max_file_size < 1024:
            raise ValueError("max_file_size must be >= 1024 bytes")
        if not self.structure:
            for flag, value in (
                ("--structure-baseline", self.structure_baseline),
                ("--structure-snapshot", self.structure_snapshot),
                (
                    "--replace-structure-snapshot",
                    self.replace_structure_snapshot or None,
                ),
            ):
                if value is not None:
                    raise ValueError(f"{flag} needs --structure")
        if self.replace_structure_snapshot and self.structure_snapshot is None:
            raise ValueError("--replace-structure-snapshot needs --structure-snapshot")
