"""Renderer contract -- one file per output format, all interchangeable.

Adding PDF/HTML-dashboard/SARIF later means adding a new file here
that implements ``render(data) -> str``, plus one line in
``renderers/registry.py``. Nothing else changes.
"""

from __future__ import annotations

from typing import Protocol

from sarand.models.results import ReportData


class Renderer(Protocol):
    """A report renderer: ReportData in, formatted text out."""

    def render(self, data: ReportData, *, include_source: bool = True) -> str: ...
