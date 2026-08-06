"""JSON report renderer."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sarand.models.results import ReportData
from sarand.progress import status


def render(data: ReportData, *, include_source: bool = True) -> str:
    status("Rendering JSON report...")

    def default(obj: Any) -> Any:
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, "__dataclass_fields__"):
            return {k: getattr(obj, k) for k in obj.__dataclass_fields__}
        return str(obj)

    payload = {
        "project_root": str(data.project_root),
        "generated_at": data.generated_at.isoformat(),
        "used_rust_core": data.used_rust_core,
        "detection": data.detection.__dict__,
        "environment": data.environment.__dict__,
        "git": data.git.__dict__,
        "stats": data.stats.__dict__,
        "todos": [t.__dict__ for t in data.todos],
        "test_results": [r.__dict__ for r in data.test_results],
        "quality_results": [r.__dict__ for r in data.quality_results],
        "security_results": [r.__dict__ for r in data.security_results],
        "health": data.health.__dict__ if data.health else None,
        "known_issues": data.known_issues,
        "ai_summary": data.ai_summary,
        "suggested_reading_order": data.suggested_reading_order,
        "included_files": [str(p) for p in data.included_files],
        "skipped_files": [(str(p), s) for p, s in data.skipped_files],
    }
    return json.dumps(payload, indent=2, default=default, ensure_ascii=False)
