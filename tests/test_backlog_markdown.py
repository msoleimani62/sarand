"""docs/BACKLOG.md is real Markdown and is linted (audit R8d).

The backlog refers to its sections by number ("items 8 and 11"), so the numbers
must survive the conversion of the section titles into headings.

بک‌لاگ به بخش‌ها با شماره ارجاع می‌دهد؛ شماره‌ها باید بعد از تبدیل عنوان‌ها به
heading سالم بمانند.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_BACKLOG = _ROOT / "docs" / "BACKLOG.md"


def test_the_backlog_is_no_longer_excluded_from_markdownlint() -> None:
    lines = (_ROOT / ".markdownlintignore").read_text(encoding="utf-8").splitlines()
    assert "docs/BACKLOG.md" not in [line.strip() for line in lines]


def test_the_backlog_has_one_title_and_sections_zero_to_twenty_three_in_order() -> None:
    lines = _BACKLOG.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("# ")
    numbers = [
        int(match.group(1))
        for line in lines
        if (match := re.match(r"^## (\d+)\. ", line))
    ]
    assert numbers == list(range(24))


def test_the_backlog_keeps_its_item_template_and_score_table_as_code() -> None:
    text = _BACKLOG.read_text(encoding="utf-8")
    assert text.count("```text") == 2
    assert text.count("```") == 4
    assert "Tests       25" in text
    assert "## [ID] Title" in text
