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
class HealthScore:
    """Computed project health score and breakdown."""

    score: float = 0.0
    max_score: float = 100.0
    grade: str = "F"
    breakdown: dict[str, float] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    critical_failures: list[str] = field(default_factory=list)


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
    health: HealthScore | None = None
    known_issues: list[str] = field(default_factory=list)
    ai_summary: str = ""
    suggested_reading_order: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
