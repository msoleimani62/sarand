"""Secret detection: never let a credential end up inside a generated
report. Two independent layers, per AGENTS.md §4.10:

1. Filename-based exclusion -- a file that merely *looks* like a
   credential (id_rsa, .env, a service-account JSON, ...) is dropped
   from the report entirely, regardless of extension, before its
   contents are ever read for embedding.
2. Content-based scanning -- a lightweight, dependency-free regex scan
   over files that *were* included, catching a hardcoded secret sitting
   inside an otherwise ordinary source file (e.g. an AWS key pasted
   into a .py config module). Findings report the location and pattern
   name only -- never the matched value itself, so the finding can't
   leak the very thing it's warning about.

Both layers run unconditionally (not gated behind --security) because
this is a safety rule, not an optional quality check -- see AGENTS.md
§7, priority 1.
"""

from __future__ import annotations

import re
from pathlib import Path

from sarand.constants import SECRET_FILENAME_PATTERNS
from sarand.models.results import SecretFinding
from sarand.utils.logging import get_logger

logger = get_logger("secrets")

_FILENAME_RE = [re.compile(p, re.IGNORECASE) for p in SECRET_FILENAME_PATTERNS]

# (pattern name, compiled regex). Content is never captured in the
# finding -- only the fact that *something* matched, at this location.
# (نام الگو، regex کامپایل‌شده). محتوا هرگز در یافته ذخیره نمی‌شود --
# فقط این واقعیت که *چیزی* در این مکان مطابقت داشته است.
_CONTENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("AWS Access Key ID", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "Private Key Block",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----"),
    ),
    ("Slack Token", re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}")),
    ("GitHub Token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    (
        "Generic API Key Assignment",
        re.compile(
            r"(?i)(?:api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*[\"'][A-Za-z0-9_\-]{16,}[\"']"
        ),
    ),
]


def looks_like_secret_filename(name: str) -> bool:
    """Return True if a bare filename (not full path) looks credential-shaped."""
    return any(pattern.search(name) for pattern in _FILENAME_RE)


def content_pattern_names() -> list[str]:
    """Public accessor for the content-scan pattern names.

    Exists so other modules (core/cache.py's rules fingerprint) don't
    reach into the private `_CONTENT_PATTERNS` list directly.
    """
    return [name for name, _ in _CONTENT_PATTERNS]


def scan_for_secrets(root: Path, included_files: list[Path]) -> list[SecretFinding]:
    """Scan already-included files' content for hardcoded-secret patterns.

    Args:
        root: Project root.
        included_files: Relative paths of files that passed the
            filename-exclusion layer and will be embedded in the report.

    Returns:
        Findings with location + pattern name only, never the matched value.
    """
    findings: list[SecretFinding] = []
    for rel in included_files:
        path = root / rel
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                for lineno, line in enumerate(fh, start=1):
                    for pattern_name, pattern in _CONTENT_PATTERNS:
                        if pattern.search(line):
                            findings.append(
                                SecretFinding(
                                    path=str(rel),
                                    line_number=lineno,
                                    pattern_name=pattern_name,
                                )
                            )
        except OSError:
            continue

    if findings:
        logger.warning("Found %d potential secret(s) in included files", len(findings))
    return findings


def exclude_flagged_files(
    included: list[Path],
    excluded: list[Path],
    findings: list[SecretFinding],
) -> tuple[list[Path], list[Path]]:
    """Move any file with a content-level finding out of `included`.

    A finding on its own is just a warning; this is the step that turns
    it into an actual guarantee. A file whose content matched a secret
    pattern must never have its full source embedded in the report --
    otherwise the "finding" would flag the exact secret sitting three
    sections below it in the same document.

    یک finding به‌تنهایی فقط یک هشدار است؛ این تابع همان مرحله‌ای است که
    آن را به یک تضمین واقعی تبدیل می‌کند. فایلی که محتوایش با یک الگوی
    secret مطابقت داشته هرگز نباید سورس کاملش در گزارش embed شود --
    وگرنه همان "finding" دقیقاً همان secretای را که چند بخش پایین‌تر در
    همان سند نشسته، پرچم‌گذاری کرده بود.

    Args:
        included: Files currently slated for full-source embedding.
        excluded: Files already excluded (filename-based, §4.10).
        findings: Result of scan_for_secrets() over `included`.

    Returns:
        (new_included, new_excluded) with flagged files moved across.
    """
    flagged = {Path(f.path) for f in findings}
    if not flagged:
        return included, excluded

    new_included = [p for p in included if p not in flagged]
    new_excluded = sorted(set(excluded) | flagged)
    return new_included, new_excluded
