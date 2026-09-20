"""Regression tests for report noise found in real `sarand --security` runs:
lines that are not diagnostics were being listed as warnings/errors, bandit
scanned test code, and repo-level tool configs must not silently disable
their own scanner."""

from __future__ import annotations

from pathlib import Path

from sarand.analyzers.python_analyzer import _BANDIT_EXCLUDE_ARG
from sarand.utils.command import scan_for_issues

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_zero_failed_in_a_success_summary_is_not_an_error() -> None:
    line = "test result: ok. 21 passed; 0 failed; 0 ignored; 0 measured"

    warnings, errors = scan_for_issues("cargo test", line)

    assert warnings == []
    assert errors == []


def test_nonzero_failed_is_still_an_error() -> None:
    for line in ("test result: FAILED. 1 passed; 1 failed", "10 failed, 2 passed"):
        _warnings, errors = scan_for_issues("pytest", line)
        assert len(errors) == 1, line


def test_bandit_context_and_internal_log_lines_are_not_issues() -> None:
    lines = [
        '88\t    assert "warning: more than one lockfile" in text',
        '288\t    assert result.raw_output == "error: test failed"',
        "[tester]\tWARNING\tnosec encountered (B108), but no failed test on file x.py:1",
        "[main]\tINFO\tprofile exclude tests: None",
    ]
    output = "\n".join(lines)

    warnings, errors = scan_for_issues("bandit", output)

    assert warnings == []
    assert errors == []


def test_a_real_error_line_from_a_tool_log_is_kept() -> None:
    _warnings, errors = scan_for_issues(
        "bandit", "[manager]\tERROR\tcould not parse file: error: bad token"
    )

    assert len(errors) == 1


def test_bandit_skips_test_directories() -> None:
    excluded = _BANDIT_EXCLUDE_ARG.split(",")

    assert "./tests" in excluded
    assert "./test" in excluded
    assert "tests" not in excluded  # must stay "./"-prefixed (bandit#975)


def test_gitleaks_config_extends_the_default_rules() -> None:
    """A custom .gitleaks.toml REPLACES gitleaks' built-in rules unless it
    extends them -- forgetting `useDefault` would silently turn the whole
    scanner into a no-op that always reports zero leaks."""
    config = _REPO_ROOT / ".gitleaks.toml"
    if not config.is_file():
        return  # e.g. tests run from an sdist that does not ship dotfiles

    text = config.read_text(encoding="utf-8")

    assert "useDefault = true" in text
