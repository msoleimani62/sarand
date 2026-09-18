"""JSON report renderer."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sarand.models.results import ReportData
from sarand.progress import status


def render(
    data: ReportData, *, include_source: bool = True, full_output: bool = False
) -> str:
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
        "excluded_secret_files": [str(p) for p in data.excluded_secret_files],
        "secret_findings": [f.__dict__ for f in data.secret_findings],
    }

    # BUG FIX: `include_source` was accepted in the signature (interface
    # parity with every other renderer) but never actually read in this
    # function body -- so JSON output never contained a single byte of
    # source code, regardless of --no-source/--full, even though
    # `included_files` (just the *paths*) was right there implying
    # completeness. For an AI-facing structured format this is the one
    # gap that matters most, since it's the format most likely to be fed
    # straight into another model's context. Mirrors the same per-file
    # embed markdown.py/html.py already do.
    #
    # اصلاح باگ: `include_source` در امضای تابع پذیرفته می‌شد (برای
    # هم‌شکلی رابط با بقیه‌ی رندرکننده‌ها) ولی هرگز در بدنه‌ی تابع خوانده
    # نمی‌شد -- پس خروجی JSON صرف‌نظر از --no-source/--full حتی یک بایت
    # کد منبع هم نداشت، با اینکه `included_files` (فقط *مسیرها*) درست
    # همان‌جا بود و القای کامل‌بودن می‌کرد. برای یک فرمت ساخت‌یافته‌ی
    # رو-به-AI، این دقیقاً همان خلأیی است که بیشترین اهمیت را دارد، چون
    # محتمل‌ترین فرمت برای تغذیه‌ی مستقیم context یک مدل دیگر است. همان
    # embed تک‌فایلی که markdown.py/html.py از قبل دارند اینجا هم تکرار
    # می‌شود.
    if include_source:
        source_files: list[dict[str, Any]] = []
        for rel in data.included_files:
            full = data.project_root / rel
            try:
                content = full.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                content = f"(error reading file: {exc})"
            try:
                size = full.stat().st_size
            except OSError:
                size = 0
            source_files.append({"path": str(rel), "size": size, "content": content})
        payload["source_files"] = source_files

    return json.dumps(payload, indent=2, default=default, ensure_ascii=False)
