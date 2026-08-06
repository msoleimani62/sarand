"""Detect known high-level problem signatures in combined tool output."""

from __future__ import annotations

from sarand.constants import KNOWN_ISSUE_PATTERNS
from sarand.models.results import CommandResult


def detect_known_issues(results: list[CommandResult]) -> list[str]:
    combined = "\n".join(r.raw_output for r in results if r.raw_output)
    lower = combined.lower()
    return [note for pattern, note in KNOWN_ISSUE_PATTERNS if pattern.lower() in lower]
