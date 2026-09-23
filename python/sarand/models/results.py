"""Typed data models for scan results and reports.

This module is the base layer of sarand: it must never import from
any other sarand module (discovery, utils, analyzers, ...). Every
other module is free to import from here without risk of a cycle.

این ماژول لایه‌ی پایه‌ی sarand است: هرگز نباید از هیچ ماژول دیگر sarand
(discovery، utils، analyzers، ...) ایمپورت کند. هر ماژول دیگری آزاد است
بدون خطر ایجاد چرخه از اینجا ایمپورت کند.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class ProjectDetection:
    """Result of scanning a directory for project/language markers."""

    languages: list[str] = field(default_factory=list)
    primary_language: str = "Unknown"
    project_type: str = "unknown"
    build_system: str = "unknown"
    markers_found: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    # Extra "label -> text" facts about the project, shown under "Detected
    # project" (today: the dialect breakdown of its assembly files).
    # حقایق اضافه به شکل «برچسب -> متن» درباره‌ی پروژه، زیر «Detected
    # project» (فعلاً: تفکیک گویش فایل‌های اسمبلیِ آن).
    details: dict[str, str] = field(default_factory=dict)

    @property
    def is_recognized(self) -> bool:
        return bool(self.markers_found)


@dataclass(frozen=True)
class Issue:
    """A single warning or error extracted from tool output."""

    source: str
    message: str
    severity: str = "warning"  # warning | error


@dataclass
class CommandResult:
    """Result of running an external command (test/quality/security check)."""

    kind: str
    returncode: int
    summary: str
    raw_output: str = ""
    warnings: list[Issue] = field(default_factory=list)
    errors: list[Issue] = field(default_factory=list)
    duration_seconds: float = 0.0
    skipped: bool = False
    skip_reason: str = ""

    @property
    def passed(self) -> bool:
        return self.returncode == 0 and not self.skipped


@dataclass
class EnvironmentInfo:
    """Collected host and toolchain information."""

    python: str = "(unavailable)"
    rust_core: str = "(unavailable)"
    os_name: str = "(unknown)"
    architecture: str = "(unknown)"
    cpu_summary: str = "(unknown)"
    memory_summary: str = "(unknown)"
    disk_free: str = "(unknown)"
    hostname: str = "(unknown)"
    tool_versions: dict[str, str] = field(default_factory=dict)


@dataclass
class GitSnapshot:
    """Snapshot of Git repository state."""

    branch: str = "(unavailable)"
    commit: str = "(unavailable)"
    status: str = ""
    log: str = ""
    diff: str = ""
    dirty: bool = False
    ahead: int = 0
    behind: int = 0
    tags: str = ""
    stashes: str = ""
    untracked: list[str] = field(default_factory=list)


@dataclass
class ProjectStats:
    """Aggregate project statistics, aggregated from the flat scan records."""

    total_files: int = 0
    total_loc: int = 0
    code_lines: int = 0
    comment_lines: int = 0
    blank_lines: int = 0
    files_by_extension: dict[str, int] = field(default_factory=dict)
    largest_directories: list[tuple[str, int]] = field(default_factory=list)
    largest_files: list[tuple[str, int]] = field(default_factory=list)
    duplicate_files: list[tuple[str, list[str]]] = field(default_factory=list)
    broken_symlinks: list[str] = field(default_factory=list)
    temporary_files: list[str] = field(default_factory=list)
    unused_cache_files: list[str] = field(default_factory=list)
    empty_files: list[str] = field(default_factory=list)
    executable_scripts: list[str] = field(default_factory=list)
    hidden_files: int = 0
    binary_files: int = 0


@dataclass
class TodoItem:
    """A TODO / FIXME / BUG marker found in source."""

    path: str
    line_number: int
    kind: str
    content: str


@dataclass
class SecretFinding:
    """A location where a hardcoded-secret-shaped pattern was found.

    Deliberately holds no `value`/`matched_text` field -- only enough to
    locate and classify the finding, so the finding itself can never leak
    the secret it's warning about (AGENTS.md §4.10).
    """

    path: str
    line_number: int
    pattern_name: str
    # Set by the scanner (the only layer that actually knows the file's
    # location) when the match sits under tests/. health.py used to try to
    # infer this from pattern_name text, which never worked -- see the fix
    # in core/health.py and core/secrets.py.
    #
    # توسط اسکنر (تنها لایه‌ای که واقعاً مسیر فایل را می‌داند) هنگامی که
    # مورد مطابقت‌یافته زیر tests/ باشد تنظیم می‌شود. health.py قبلاً سعی
    # می‌کرد این را از متن pattern_name استنتاج کند که هرگز کار نمی‌کرد --
    # اصلاح مربوطه را در core/health.py و core/secrets.py ببینید.
    is_test_fixture: bool = False


@dataclass
class HealthScore:
    """Computed project health score and breakdown."""

    score: float = 0.0
    max_score: float = 100.0
    grade: str = "F"
    breakdown: dict[str, float] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    critical_failures: list[str] = field(default_factory=list)
    # How much of the score rests on checks that really ran. A check whose
    # tool is not installed is skipped, and a skipped check proves nothing:
    # `checks_skipped` names them, `confidence` is ran / (ran + skipped).
    # چه مقدار از امتیاز روی چک‌هایی است که واقعاً اجرا شده‌اند. چکی که ابزارش
    # نصب نیست رد می‌شود و چک ردشده چیزی ثابت نمی‌کند: `checks_skipped` اسم
    # آن‌ها را می‌آورد و `confidence` برابر ran / (ran + skipped) است.
    checks_run: int = 0
    checks_skipped: list[str] = field(default_factory=list)
    confidence: float = 1.0


@dataclass
class WorkspaceMember:
    """One member package/crate of a detected workspace. Populated by
    `core/workspace.py` -- see that module for detection logic and
    which workspace models are (and are not yet) supported.
    """

    # POSIX-style, relative to the project root ("." for the root
    # itself when the root manifest carries both a workspace table
    # and its own package -- a common, valid layout, e.g. Cargo).
    # به‌سبک POSIX، نسبت به ریشه‌ی پروژه (ریشه‌ی خودش وقتی مانیفست
    # ریشه هم جدول workspace دارد هم بسته‌ی خودش را -- چیدمانی رایج
    # و معتبر، مثلاً در Cargo).
    path: str
    # The member's own package name, read from its manifest. Falls
    # back to the directory name when that manifest could not be read
    # or names no package (a nested virtual manifest).
    # نام بسته‌ی خودِ عضو، از مانیفست خودش خوانده می‌شود. اگر آن
    # مانیفست خوانده نشود یا نامی نداشته باشد (یک مانیفست مجازیِ
    # تودرتو)، به نام دایرکتوری برمی‌گردد.
    name: str


@dataclass
class WorkspaceInfo:
    """A detected monorepo/workspace structure at the project root.

    Detection only -- which analyzer(s) actually run, and how their
    results roll up, is unchanged by this: `core/workspace.py`'s own
    docstring notes that the underlying tools (e.g. `cargo test
    --all`) are already workspace-aware for every ecosystem audited so
    far, so this is purely extra structure shown in the report, not a
    change to what gets executed.
    """

    # Which detector found this ("cargo" today; "npm"/"pnpm"/"yarn"/
    # "gradle"/"maven" are the documented next candidates, not yet
    # implemented -- see core/workspace.py's module docstring audit).
    kind: str
    members: list[WorkspaceMember] = field(default_factory=list)
    # Raw, unresolved exclude patterns from the workspace manifest
    # (e.g. Cargo's `[workspace] exclude = [...]`), kept for the
    # report to show verbatim.
    # الگوهای exclude خام و حل‌نشده از مانیفست workspace (مثلاً
    # `exclude` خودِ `[workspace]` در Cargo)، برای نمایش عیناً در
    # گزارش نگه داشته می‌شوند.
    exclude_patterns: list[str] = field(default_factory=list)


@dataclass
class ReportData:
    """Complete data package used to render any report format."""

    project_root: Path
    generated_at: datetime
    environment: EnvironmentInfo
    git: GitSnapshot
    stats: ProjectStats
    detection: ProjectDetection = field(default_factory=ProjectDetection)
    used_rust_core: bool = False
    todos: list[TodoItem] = field(default_factory=list)
    test_results: list[CommandResult] = field(default_factory=list)
    quality_results: list[CommandResult] = field(default_factory=list)
    security_results: list[CommandResult] = field(default_factory=list)
    tree_text: str = ""
    included_files: list[Path] = field(default_factory=list)
    skipped_files: list[tuple[Path, int]] = field(default_factory=list)
    excluded_secret_files: list[Path] = field(default_factory=list)
    secret_findings: list[SecretFinding] = field(default_factory=list)
    health: HealthScore | None = None
    known_issues: list[str] = field(default_factory=list)
    ai_summary: str = ""
    suggested_reading_order: list[str] = field(default_factory=list)
    workspace: WorkspaceInfo | None = None
    extra: dict[str, Any] = field(default_factory=dict)
