"""Tests for sarand.core.issues (detect_known_issues).

The bandit tests below are regression tests for two separate false-positive
bugs found during a self-scan review, both of which made
`detect_known_issues` report "Compilation or lint errors were
detected." even though every tool had actually passed. Since R13-A that
sentence no longer exists: classification lives in core/failures.py (see
tests/test_failures.py) and the tests below assert the new, stricter behavior.

هر دو تست زیر، تست ریگرسیون برای دو باگ جدا از نوع false-positive
هستند که در طول یک بررسی خوداسکن پیدا شدند و باعث می‌شدند
`detect_known_issues` عبارت «Compilation or lint errors were detected.»
را گزارش کند، حتی وقتی همه‌ی ابزارها واقعاً موفق (PASS) بودند.
"""

from __future__ import annotations

from sarand.core.issues import detect_known_issues
from sarand.models.results import CommandResult


def _result(kind: str, raw_output: str, returncode: int = 0) -> CommandResult:
    return CommandResult(
        kind=kind, returncode=returncode, summary="ok", raw_output=raw_output
    )


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


def test_a_rustc_error_code_is_a_compilation_failure() -> None:
    result = _result(
        "cargo test",
        "error[E0432]: unresolved import `foo`\n --> src/lib.rs:1:5",
        returncode=1,
    )

    assert detect_known_issues([result]) == [
        "Compilation errors were reported by: cargo test."
    ]


def test_a_bare_error_line_from_an_unknown_tool_stays_unclassified() -> None:
    """R13-A: the old catch-all claimed "Compilation or lint errors were
    detected." for any `error:` line. A bare line proves neither; it is reported
    as an unclassified failure of the named tool."""
    result = _result(
        "cargo",
        "error: unresolved import `foo`\n --> src/lib.rs:1:5",
        returncode=1,
    )

    assert detect_known_issues([result]) == [
        "A tool failed for a reason that was not classified: cargo."
    ]


def test_still_detects_a_genuine_missing_dependency() -> None:
    result = _result(
        "pytest",
        "E   ModuleNotFoundError: No module named 'sarand'",
        returncode=1,
    )

    assert detect_known_issues([result]) == ["A required Python dependency is missing."]


def test_combines_findings_across_multiple_command_results() -> None:
    results = [
        _result("cargo test", "error[E0432]: unresolved import `foo`", returncode=1),
        _result(
            "pytest", "E   ModuleNotFoundError: No module named 'sarand'", returncode=1
        ),
    ]

    issues = detect_known_issues(results)

    assert issues == [
        "A required Python dependency is missing.",
        "Compilation errors were reported by: cargo test.",
    ]


def test_the_generic_message_is_never_produced() -> None:
    for kind in ("cargo audit", "cargo deny check", "yamllint", "unknown-tool"):
        issues = detect_known_issues(
            [_result(kind, "error: something went wrong", returncode=1)]
        )
        assert all("Compilation or lint errors" not in i for i in issues), kind
