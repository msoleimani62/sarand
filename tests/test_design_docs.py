"""The Quick Context design record exists and still names its decisions.

The design (L2 completion, L3, L4) is recorded in one file and the backlog status
points at it; this keeps the two from drifting apart.

سند طراحی Quick Context وجود دارد و تصمیم‌هایش را نام می‌برد.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DESIGN = _ROOT / "docs" / "QUICK_CONTEXT_DESIGN.md"


def test_the_design_record_names_every_accepted_decision() -> None:
    text = _DESIGN.read_text(encoding="utf-8")
    for decision in (f"D-QC{n}" for n in range(1, 8)):
        assert decision in text, decision


def test_the_design_record_lists_the_nine_risk_rules() -> None:
    text = _DESIGN.read_text(encoding="utf-8")
    rules = (
        "SEC-CHECK-FAILED",
        "HEALTH-CRITICAL",
        "SECRET-PATTERNS",
        "CHECKS-SKIPPED",
        "GIT-STATE",
        "HEALTH-LOW-CONFIDENCE",
        "TODO-CLUSTER",
        "LARGE-FILE",
        "DUPLICATE-FILES",
    )
    for rule in rules:
        assert f"`{rule}`" in text, rule


def test_the_backlog_status_points_at_the_design_record() -> None:
    status = _ROOT / "docs" / "BACKLOG_STATUS.md"
    if not status.is_file():
        return
    assert "docs/QUICK_CONTEXT_DESIGN.md" in status.read_text(encoding="utf-8")
