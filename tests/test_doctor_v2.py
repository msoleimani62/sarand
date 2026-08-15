"""Tests for the redesigned sarand.core.doctor -- categorized tool checks."""

from __future__ import annotations

from sarand.core.doctor import _CATEGORY_ORDER, collect_checks


def test_every_language_tool_check_has_a_category_from_the_defined_order() -> None:
    checks = collect_checks()
    for check in checks:
        if check.category == "Core":
            continue
        assert check.category in _CATEGORY_ORDER


def test_android_and_java_share_the_gradle_and_maven_checks() -> None:
    """No separate Android-specific tool row -- gradle/mvn serve both
    JavaAnalyzer and AndroidAnalyzer, so a duplicate row would be
    misleading (as if a different tool were needed for each)."""
    checks = collect_checks()
    android_category_tools = {
        c.name for c in checks if c.category == "Java / Kotlin / Android"
    }
    assert android_category_tools == {"mvn", "gradle"}


def test_every_tool_check_declares_what_it_is_used_for() -> None:
    checks = collect_checks()
    for check in checks:
        if check.category == "Core":
            continue
        assert check.used_for, f"{check.name} has no 'used_for' explanation"


def test_gradle_check_mentions_the_wrapper_fallback() -> None:
    checks = collect_checks()
    gradle_check = next(c for c in checks if c.name == "gradle")
    assert "gradlew" in gradle_check.used_for
