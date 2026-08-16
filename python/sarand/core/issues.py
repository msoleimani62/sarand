"""Detect known high-level problem signatures in combined tool output."""

from __future__ import annotations

import re

from sarand.constants import KNOWN_ISSUE_PATTERNS
from sarand.models.results import CommandResult

# BUG FIX: a plain substring check on "error:" also matches inside unrelated
# words such as "OSError:" (bandit's own source-context lines quote
# "except OSError:"), which falsely raised "Compilation or lint errors were
# detected" even when every tool actually passed. \b requires a real word
# boundary before the pattern, so "OSError:" no longer matches "error:".
#
# اصلاح باگ: تطبیق ساده‌ی substring روی "error:" داخل کلمات نامرتبطی مثل
# "OSError:" هم مچ می‌شد (خطوط context خودِ bandit عبارت "except OSError:" را
# نمایش می‌دهند) و باعث اعلام غلط «Compilation or lint errors were detected»
# می‌شد، حتی وقتی همه‌ی ابزارها واقعاً PASS بودند. \b یک مرز واقعی کلمه قبل از
# الگو الزامی می‌کند، پس "OSError:" دیگر با "error:" مچ نمی‌شود.
_PATTERN_CACHE: dict[str, re.Pattern[str]] = {
    pattern: re.compile(r"\b" + re.escape(pattern.lower()))
    for pattern, _note in KNOWN_ISSUE_PATTERNS
}


def detect_known_issues(results: list[CommandResult]) -> list[str]:
    combined = "\n".join(r.raw_output for r in results if r.raw_output)
    lower = combined.lower()
    return [
        note
        for pattern, note in KNOWN_ISSUE_PATTERNS
        if _PATTERN_CACHE[pattern].search(lower)
    ]
