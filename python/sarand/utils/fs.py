"""Pure filesystem helper functions (no dependency on the rest of sarand)."""

from __future__ import annotations

import re
from pathlib import Path

FORMAT_EXTENSIONS: dict[str, str] = {
    "markdown": "md",
    "json": "json",
    "text": "txt",
    "html": "html",
    "pdf": "pdf",
    "sarif": "sarif",
}


def human_size(size: int) -> str:
    """Convert byte count to human-readable string."""
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    value = float(size)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{size} B"


def is_binary(path: Path, sample_size: int = 8192) -> bool:
    """Heuristically detect whether a file is binary (NUL-byte sniff).

    This is the pure-Python fallback used when the compiled Rust core
    is unavailable; the Rust walker uses the identical heuristic.

    این نسخه‌ی پایتونیِ fallback است، برای وقتی هسته‌ی کامپایل‌شده‌ی
    Rust در دسترس نیست؛ واکر Rust از همین هیوریستیک استفاده می‌کند.
    """
    try:
        with path.open("rb") as fh:
            chunk = fh.read(sample_size)
        return b"\0" in chunk
    except OSError:
        return True


def safe_relative(path: Path, root: Path) -> Path:
    """Return path relative to root, falling back to absolute on error."""
    try:
        return path.relative_to(root)
    except ValueError:
        return path


def slugify_project_name(name: str) -> str:
    """Turn a project directory name into a safe, portable filename slug."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip())
    slug = re.sub(r"-{2,}", "-", slug).strip("-.")
    return slug.lower() or "project"


def default_output_name(project_root: Path, output_format: str) -> str:
    """Build the default report filename for a project + format.

    e.g. ``sarand-my-project-report.md``. Two different projects can
    never silently overwrite each other's report in the same output
    directory, and the extension always matches ``--format``.
    """
    slug = slugify_project_name(project_root.name)
    ext = FORMAT_EXTENSIONS.get(output_format, "md")
    return f"sarand-{slug}-report.{ext}"
