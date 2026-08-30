"""Tests for sarand.core.issues (detect_known_issues).

Both tests below are regression tests for two separate false-positive
bugs found during a self-scan review, both of which made
`detect_known_issues` report "Compilation or lint errors were
detected." even though every tool had actually passed.

هر دو تست زیر، تست ریگرسیون برای دو باگ جدا از نوع false-positive
هستند که در طول یک بررسی خوداسکن پیدا شدند و باعث می‌شدند
`detect_known_issues` عبارت «Compilation or lint errors were detected.»
را گزارش کند، حتی وقتی همه‌ی ابزارها واقعاً موفق (PASS) بودند.
"""

from __future__ import annotations

from sarand.core.issues import detect_known_issues
from sarand.models.results import CommandResult


def _result(kind: str, raw_output: str, returncode: int = 0) -> CommandResult:
    return CommandResult(kind=kind, returncode=returncode, summary="ok", raw_output=raw_output)


def test_ignores_oserror_inside_bandit_context_line() -> None:
    # Round 1 regression: a naive substring check on "error:" used to
    # match inside "OSError:" too.
    result = _result("bandit", "91\t        except OSError:\nNo issues identified.")

    assert detect_known_issues([result]) == []


def test_ignores_error_colon_inside_a_quoted_bandit_context_line() -> None:
    # Round 2 regression: a source-code string literal quoted verbatim
    # by bandit as context -- `assert result.raw_output == "error: test
    # failed"` -- still matched "error:" after a real word boundary
    # (the quote character). Bandit context lines always look like
    # "<lineno>\t<code>" and are reproduced source, not a genuine
    # diagnostic, so they must be excluded from the scan entirely.
    result = _result(
        "bandit",
        '288\t    assert result.raw_output == "error: test failed"\nNo issues identified.',
    )

    assert detect_known_issues([result]) == []


def test_still_detects_a_genuine_compiler_error() -> None:
    result = _result(
        "cargo",
        "error: unresolved import `foo`\n --> src/lib.rs:1:5",
        returncode=1,
    )

    assert detect_known_issues([result]) == ["Compilation or lint errors were detected."]


def test_still_detects_a_genuine_missing_dependency() -> None:
    result = _result(
        "pytest",
        "E   ModuleNotFoundError: No module named 'sarand'",
        returncode=1,
    )

    assert detect_known_issues([result]) == ["A required Python dependency is missing."]


def test_combines_findings_across_multiple_command_results() -> None:
    results = [
        _result("cargo", "error: unresolved import `foo`", returncode=1),
        _result("pytest", "E   ModuleNotFoundError: No module named 'sarand'", returncode=1),
    ]

    issues = detect_known_issues(results)

    assert "Compilation or lint errors were detected." in issues
    assert "A required Python dependency is missing." in issues
