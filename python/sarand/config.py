"""Runtime configuration for sarand."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sarand.constants import DEFAULT_OUTPUT_DIR, MAX_FILE_SIZE, MAX_TREE_DEPTH, MAX_TREE_ENTRIES
from sarand.userconfig import load_persisted_config
from sarand.utils.fs import default_output_name


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


@dataclass
class SarandConfig:
    """Runtime configuration for one sarand run."""

    project_root: Path = field(default_factory=Path.cwd)
    output_dir: Path = field(default_factory=lambda: DEFAULT_OUTPUT_DIR)
    output_name: str = ""
    skip_tests: bool = False
    run_quality: bool = False
    run_security: bool = False
    verbose: bool = False
    debug: bool = False
    output_format: str = "markdown"
    max_tree_depth: int = MAX_TREE_DEPTH
    max_tree_entries: int = MAX_TREE_ENTRIES
    max_file_size: int = MAX_FILE_SIZE
    include_source: bool = True
    health_score: bool = True

    @classmethod
    def from_args(cls, args: Any) -> "SarandConfig":
        project = resolve_project_path(getattr(args, "project", None))
        output_format = str(getattr(args, "format", "markdown")).lower()
        out_dir = resolve_output_dir(getattr(args, "output_dir", None))
        explicit_name = getattr(args, "output_name", None)
        output_name = explicit_name or default_output_name(project, output_format)

        def _int_or(value: Any, default: int) -> int:
            return default if value is None else int(value)

        return cls(
            project_root=project,
            output_dir=out_dir,
            output_name=output_name,
            skip_tests=bool(getattr(args, "skip_tests", False)),
            run_quality=bool(getattr(args, "quality", False)),
            run_security=bool(getattr(args, "security", False)),
            verbose=bool(getattr(args, "verbose", False)),
            debug=bool(getattr(args, "debug", False)),
            output_format=output_format,
            max_tree_depth=_int_or(getattr(args, "max_depth", None), MAX_TREE_DEPTH),
            max_tree_entries=_int_or(getattr(args, "max_entries", None), MAX_TREE_ENTRIES),
            max_file_size=_int_or(getattr(args, "max_file_size", None), MAX_FILE_SIZE),
            include_source=not bool(getattr(args, "no_source", False)),
            health_score=not bool(getattr(args, "no_health", False)),
        )

    def validate(self) -> None:
        if not self.project_root.is_dir():
            raise ValueError(f"Project root does not exist or is not a directory: {self.project_root}")
        allowed = {"markdown", "json", "text"}
        if self.output_format not in allowed:
            raise ValueError(f"Unsupported output format: {self.output_format}. Allowed: {allowed}")
        if self.max_tree_depth < 1:
            raise ValueError("max_tree_depth must be >= 1")
        if self.max_tree_entries < 1:
            raise ValueError("max_tree_entries must be >= 1")
        if self.max_file_size < 1024:
            raise ValueError("max_file_size must be >= 1024 bytes")
