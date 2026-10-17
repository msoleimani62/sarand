"""Tests for AGENTS.md 5.68: line-shaped diagnostics, errors only from failed
commands, known issues only from failed checks, and the INCONCLUSIVE state of
audit-style checks that exited 0 without finishing.

The sample strings are the real ones from sarand's own self-report.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC

from sarand.core.health import compute_health_score
from sarand.core.issues import detect_known_issues
from sarand.core.package_summary import summarize_packages
from sarand.core.quick_context import build_quick_context
from sarand.models.results import (
    CommandResult,
    EnvironmentInfo,
    GitSnapshot,
    ProjectStats,
    ReportData,
)
from sarand.renderers import html, json_renderer, markdown
from sarand.utils.command import (
    detect_inconclusive,
    make_command_result,
    scan_for_issues,
)

_SYFT_LICENSE_LINE = (
    "License policy (.sarand.toml): 0 violation(s), 0 warning(s), "
    "0 exception(s) applied"
)
_CARGO_AUDIT_TIMEOUT = (
    "Warning: couldn't check if the package is yanked: request or response "
    "body error: operation timed out"
)


def _report(**overrides: object) -> ReportData:
    from datetime import datetime
    from pathlib import Path

    defaults: dict[str, object] = {
        "project_root": Path("fixture-project"),
        "generated_at": datetime(2026, 1, 1, tzinfo=UTC),
        "environment": EnvironmentInfo(),
        "git": GitSnapshot(),
        "stats": ProjectStats(),
    }
    defaults.update(overrides)
    return ReportData(**defaults)  # type: ignore[arg-type]


# --- A6: line shape, not substring ------------------------------------------


def test_the_syft_license_line_is_neither_a_warning_nor_an_error() -> None:
    warnings, errors = scan_for_issues("syft", _SYFT_LICENSE_LINE)
    assert warnings == []
    assert errors == []


def test_real_error_shapes_are_errors() -> None:
    lines = [
        "error[E0308]: mismatched types",
        "error: could not compile `sarand`",
        "src/a.py:3: error: Incompatible types in assignment",
        "src/a.c:3:5: error: expected ';' before 'return'",
        "Traceback (most recent call last):",
        "ValueError: bad value",
        "ModuleNotFoundError: No module named 'x'",
        "thread 'main' panicked at src/lib.rs:1:1:",
        "FAILED tests/test_x.py::test_y - assert 1 == 2",
        "ERROR tests/test_x.py - ImportError",
        "npm ERR! code E404",
        "--- FAIL: TestSomething (0.00s)",
        "FAIL\tgithub.com/x/y\t0.01s",
        "test result: FAILED. 1 passed; 1 failed; 0 ignored",
        "=== 2 failed, 10 passed in 0.12s ===",
    ]
    for line in lines:
        _warnings, errors = scan_for_issues("tool", line)
        assert len(errors) == 1, line


def test_lookalikes_are_not_errors() -> None:
    lines = [
        _SYFT_LICENSE_LINE,
        "OSError handling is described in the docs",
        'assert result.raw_output == "error: boom"',
        "this sentence has the word exception in it",
        "the task failed successfully",
        "test result: ok. 21 passed; 0 failed; 0 ignored",
        "    raise ValueError(message)",
        "0 failed, 12 passed",
    ]
    for line in lines:
        _warnings, errors = scan_for_issues("tool", line)
        assert errors == [], line


def test_warning_shapes_are_warnings_and_bare_words_are_not() -> None:
    for line in (
        "warning: unused variable: `x`",
        "warning[W0001]: something",
        "src/a.c:3:5: warning: unused parameter 'x'",
        "DeprecationWarning: use new_api instead",
    ):
        warnings, _errors = scan_for_issues("tool", line)
        assert len(warnings) == 1, line
    for line in (
        "this API is deprecated in favour of another",
        "F401 `os` imported but unused",
        "0 warning(s)",
    ):
        warnings, _errors = scan_for_issues("tool", line)
        assert warnings == [], line


def test_a_command_that_exited_zero_reports_no_errors_but_keeps_warnings() -> None:
    output = "error: this is a quoted log line\nwarning: unused variable: `x`"
    ok = make_command_result("cargo build", 0, output, 0.1)
    assert ok.errors == []
    assert len(ok.warnings) == 1
    failed = make_command_result("cargo build", 101, output, 0.1)
    assert len(failed.errors) == 1


# --- known issues only from failed checks -----------------------------------


def test_known_issues_ignore_every_passing_tool() -> None:
    passing = CommandResult(
        kind="ruff check",
        returncode=0,
        summary="ok",
        raw_output="error: Failed to parse a quoted example\nAll checks passed!",
    )
    assert detect_known_issues([passing]) == []


def test_known_issues_come_from_failed_checks_only() -> None:
    failed = CommandResult(
        kind="cargo",
        returncode=101,
        summary="x",
        raw_output="error[E0432]: unresolved import `foo`",
    )
    passing = CommandResult(
        kind="ruff", returncode=0, summary="ok", raw_output="ModuleNotFoundError: x"
    )
    assert detect_known_issues([failed, passing]) == [
        "Compilation or lint errors were detected."
    ]


def test_an_inconclusive_check_does_not_feed_known_issues() -> None:
    result = make_command_result("cargo audit", 0, _CARGO_AUDIT_TIMEOUT, 1.0)
    assert result.inconclusive
    assert detect_known_issues([result]) == []


# --- A7: the inconclusive state --------------------------------------------


def test_cargo_audit_that_could_not_finish_is_inconclusive_not_pass() -> None:
    result = make_command_result("cargo audit", 0, _CARGO_AUDIT_TIMEOUT, 1.0)
    assert result.inconclusive is True
    assert "yanked" in result.inconclusive_reason
    assert result.passed is False
    assert result.skipped is False


def test_a_failing_exit_is_never_downgraded_to_inconclusive() -> None:
    result = make_command_result("cargo audit", 1, _CARGO_AUDIT_TIMEOUT, 1.0)
    assert result.inconclusive is False
    assert result.passed is False


def test_only_audit_style_kinds_can_be_inconclusive() -> None:
    assert detect_inconclusive("pytest", 0, _CARGO_AUDIT_TIMEOUT) == ""
    assert detect_inconclusive("ruff check", 0, "Max retries exceeded with url") == ""
    for kind in ("pip-audit", "npm audit", "govulncheck", "web: cargo audit"):
        assert detect_inconclusive(kind, 0, "Max retries exceeded with url: /x"), kind


def test_a_clean_audit_and_a_skipped_audit_are_not_inconclusive() -> None:
    clean = make_command_result("cargo audit", 0, "No vulnerabilities found", 1.0)
    assert clean.inconclusive is False
    assert clean.passed is True
    skipped = make_command_result(
        "cargo audit", 0, _CARGO_AUDIT_TIMEOUT, 0.0, skipped=True, skip_reason="x"
    )
    assert skipped.inconclusive is False


def test_relabelling_keeps_the_inconclusive_reason() -> None:
    result = make_command_result("cargo audit", 0, _CARGO_AUDIT_TIMEOUT, 1.0)
    assert replace(result, kind="web: cargo audit").inconclusive


def test_health_treats_inconclusive_like_not_run_and_says_why() -> None:
    inconclusive = make_command_result("cargo audit", 0, _CARGO_AUDIT_TIMEOUT, 1.0)
    clean_tests = [CommandResult(kind="pytest", returncode=0, summary="ok")]
    health = compute_health_score(
        _report(test_results=clean_tests, security_results=[inconclusive])
    )
    # Not a failure: no critical finding and no security penalty.
    assert health.breakdown["security"] == 8.0
    assert "Security tool reported issues." not in health.critical_failures
    assert health.checks_inconclusive == ["cargo audit"]
    assert health.checks_run == 1
    assert health.confidence == 0.5
    assert any("could not finish" in r for r in health.recommendations)
    assert not any("install the security tools" in r for r in health.recommendations)


def test_health_still_fails_a_real_security_failure_next_to_an_inconclusive() -> None:
    inconclusive = make_command_result("cargo audit", 0, _CARGO_AUDIT_TIMEOUT, 1.0)
    failing = make_command_result("pip-audit", 1, "Found 2 known vulnerabilities", 1.0)
    health = compute_health_score(_report(security_results=[inconclusive, failing]))
    assert health.breakdown["security"] == 5.0
    assert "Security tool reported issues." in health.critical_failures


def test_renderers_label_the_state_and_the_json_key_appears_only_when_set() -> None:
    inconclusive = make_command_result("cargo audit", 0, _CARGO_AUDIT_TIMEOUT, 1.0)
    clean = make_command_result("pip-audit", 0, "No known vulnerabilities", 1.0)
    data = _report(security_results=[inconclusive, clean])
    output = markdown.render(data, include_source=False)
    assert "### cargo audit [INCONCLUSIVE]" in output
    assert "*Inconclusive:*" in output
    assert "### pip-audit [PASS]" in output
    assert "INCONCLUSIVE" in html.render(data, include_source=False)
    import json

    payload = json.loads(json_renderer.render(data, include_source=False))
    first, second = payload["security_results"]
    assert "yanked" in first["inconclusive_reason"]
    assert "inconclusive_reason" not in second


def test_quick_context_and_package_counts_do_not_call_it_passed_or_failed() -> None:
    inconclusive = make_command_result("cargo audit", 0, _CARGO_AUDIT_TIMEOUT, 1.0)
    data = _report(security_results=[inconclusive])
    context = build_quick_context(data)
    assert any("could not finish" in risk for risk in context.risks)
    labelled = make_command_result("web: cargo audit", 0, _CARGO_AUDIT_TIMEOUT, 1.0)
    summaries = summarize_packages(["web"], [], [], [labelled])
    web = next(s for s in summaries if s.package == "web")
    assert (web.security.passed, web.security.failed, web.security.skipped) == (0, 0, 1)
