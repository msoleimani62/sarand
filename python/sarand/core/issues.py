"""Detect known high-level problem signatures in combined tool output."""

from __future__ import annotations

import re

from sarand.constants import KNOWN_ISSUE_PATTERNS
from sarand.models.results import CommandResult

# BUG FIX (round 1): a plain substring check on "error:" also matched
# inside unrelated words such as "OSError:" -- fixed with a \b word
# boundary so "OSError:" no longer matches "error:".
#
# BUG FIX (round 2): the word-boundary fix above still isn't enough,
# because bandit prints the literal source line around every finding as
# context, in the form "<lineno>\t<code>". One such context line was
# `288\t    assert result.raw_output == "error: test failed"` -- a
# string literal from this project's OWN test suite (testing an
# unrelated function), quoted verbatim by bandit. The `"` right before
# "error:" is a real word boundary too, so round 1's fix didn't help
# here. These bandit context lines are reproduced source code, never
# genuine tool diagnostics, so they are stripped out before any pattern
# search runs -- the fingerprint `^<digits>\t` is specific to bandit's
# context format and doesn't appear in real compiler/linter/pytest
# output.
#
# اصلاح باگ (دور اول): تطبیق ساده‌ی substring روی "error:" داخل کلماتی
# مثل "OSError:" هم مچ می‌شد -- با یک مرز کلمه (\b) درست شد.
#
# اصلاح باگ (دور دوم): فیکس دور اول هم کافی نبود، چون bandit خط سورس
# دور‌وبر هر finding را به‌عنوان context عیناً چاپ می‌کند، با فرمت
# «شماره‌خط<TAB>کد». یکی از این خطوط context این بود:
# `288\t    assert result.raw_output == "error: test failed"` -- یک
# رشته‌ی literal از تست‌های خودِ همین پروژه (برای تست یک تابع بی‌ربط)
# که bandit عیناً نقل‌قول کرده. علامت `"` درست قبل از "error:" هم یک
# مرز کلمه‌ی واقعی است، پس فیکس دور اول اینجا کمکی نکرد. این خطوط
# context خودِ بندیت، سورس‌کد بازتولیدشده هستند، نه diagnostic واقعیِ
# ابزار، پس قبل از هر جستجوی الگو حذف می‌شوند -- امضای `^<رقم‌ها>\t`
# مخصوص فرمت context بندیت است و در خروجی واقعی کامپایلر/linter/pytest
# دیده نمی‌شود.
_BANDIT_CONTEXT_LINE = re.compile(r"^\d+\t")

_PATTERN_CACHE: dict[str, re.Pattern[str]] = {
    pattern: re.compile(r"\b" + re.escape(pattern.lower()))
    for pattern, _note in KNOWN_ISSUE_PATTERNS
}


def detect_known_issues(results: list[CommandResult]) -> list[str]:
    combined = "\n".join(r.raw_output for r in results if r.raw_output)
    real_lines = (
        line for line in combined.splitlines() if not _BANDIT_CONTEXT_LINE.match(line)
    )
    lower = "\n".join(real_lines).lower()
    return [
        note
        for pattern, note in KNOWN_ISSUE_PATTERNS
        if _PATTERN_CACHE[pattern].search(lower)
    ]
