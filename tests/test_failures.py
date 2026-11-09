"""R13-A: failure classification (core/failures.py) and its use in the report.

Evidence behind the tests: the real Ramz v0.3.2 tool outputs frozen in
tests/data/ramz_v0_3_2 (a report of 2026-11-01 whose "Compilation or lint errors
were detected." came from cargo audit and cargo deny, not from a compiler or a
linter). Every rule has a positive and a negative case. Dependency-free like the
other tests (no `import pytest`).
R13-A: تست طبقه‌بندی شکست؛ شواهد واقعی در tests/data/ramz_v0_3_2 منجمد شده‌اند.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from _golden_fixtures import FIXTURES
from sarand.constants import (
    CAUSE_EXIT_CODE,
    FAILURE_CATEGORIES,
    FAILURE_COMPILATION,
    FAILURE_CONFIGURATION,
    FAILURE_DEPENDENCY_POLICY,
    FAILURE_LINT,
    FAILURE_SECURITY_FINDING,
    FAILURE_SECURITY_TOOL,
    FAILURE_TEST,
    FAILURE_UNKNOWN_TOOL,
    SENTINEL_NOT_FOUND,
    SENTINEL_OS_ERROR,
    SENTINEL_TIMEOUT,
)
from sarand.core.failures import (
    classify_failures,
    classify_result,
    detect_known_issues,
    execution_cause,
    known_issues_from_failures,
)
from sarand.models.results import CommandResult, Failure, ReportData
from sarand.renderers import json_renderer, markdown
from sarand.utils.command import run_cmd

_DATA = Path(__file__).resolve().parent / "data" / "ramz_v0_3_2"
_GENERIC = "Compilation or lint errors were detected"


def _real(name: str) -> str:
    return (_DATA / name).read_text(encoding="utf-8")


def _r(
    kind: str,
    out: str = "",
    rc: int = 1,
    *,
    skipped: bool = False,
    skip_reason: str = "",
    inconclusive_reason: str = "",
) -> CommandResult:
    return CommandResult(
        kind=kind,
        returncode=rc,
        summary="",
        raw_output=out,
        skipped=skipped,
        skip_reason=skip_reason,
        inconclusive_reason=inconclusive_reason,
    )


def _one(kind: str, out: str, group: str = "", rc: int = 1) -> Failure:
    found = classify_result(_r(kind, out, rc), group)
    assert len(found) == 1, found
    return found[0]


def _ramz() -> tuple[list[CommandResult], list[CommandResult], list[CommandResult]]:
    quality = [
        _r("actionlint", _real("actionlint.txt")),
        _r("yamllint", _real("yamllint.txt")),
        _r("markdownlint", _real("markdownlint_excerpt.txt")),
    ]
    security = [
        _r("cargo audit", _real("cargo_audit.txt")),
        _r("cargo deny check", _real("cargo_deny_excerpt.txt"), rc=5),
    ]
    return [], quality, security


def test_the_vocabulary_is_the_eight_required_categories_plus_security_findings() -> (
    None
):
    assert len(FAILURE_CATEGORIES) == len(set(FAILURE_CATEGORIES)) == 9
    assert set(FAILURE_CATEGORIES) >= {
        "compilation_failure",
        "test_failure",
        "lint_failure",
        "security_tool_failure",
        "configuration_failure",
        "dependency_policy_failure",
        "report_generation_failure",
        "unknown_tool_failure",
    }
    assert "security_finding_detected" in FAILURE_CATEGORIES


# --- the real Ramz evidence ------------------------------------------------


def test_real_cargo_audit_output_is_a_security_finding_not_a_compile_or_lint_error() -> (
    None
):
    f = _one("cargo audit", _real("cargo_audit.txt"), "security")
    assert (f.category, f.cause, f.group) == (
        FAILURE_SECURITY_FINDING,
        CAUSE_EXIT_CODE,
        "security",
    )
    assert f.signals == ("advisory-reported",) and f.returncode == 1
    assert "not proof" in f.summary


def test_real_cargo_deny_output_splits_advisories_from_license_policy() -> None:
    found = classify_result(
        _r("cargo deny check", _real("cargo_deny_excerpt.txt"), 5), "security"
    )
    assert [f.category for f in found] == [
        FAILURE_SECURITY_FINDING,
        FAILURE_DEPENDENCY_POLICY,
    ]
    assert found[0].signals == ("cargo-deny:unmaintained", "cargo-deny:vulnerability")
    assert found[1].signals == ("cargo-deny:rejected",)
    assert "not a vulnerability" in found[1].summary


def test_real_actionlint_yamllint_and_markdownlint_are_lint_failures_with_their_subject() -> (
    None
):
    expect = {
        "actionlint": "GitHub Actions workflow files",
        "yamllint": "YAML files",
        "markdownlint": "Markdown documentation",
    }
    _, quality, _ = _ramz()
    for result in quality:
        (f,) = classify_result(result, "quality")
        assert (f.category, f.subject) == (FAILURE_LINT, expect[result.kind])
        assert f.signals == ()


def test_the_ramz_report_no_longer_claims_a_compilation_or_lint_error() -> None:
    tests, quality, security = _ramz()
    issues = known_issues_from_failures(classify_failures(tests, quality, security))
    assert issues == [
        (
            "Security findings were reported by: cargo audit, cargo deny check. "
            "These are tool results, not proof that the project is exploitable."
        ),
        (
            "Dependency policy checks failed in: cargo deny check (licenses, bans "
            "or sources). This is not a vulnerability."
        ),
    ]
    assert all(_GENERIC not in i for i in issues)


def test_when_only_lint_tools_fail_there_is_no_known_issue_at_all() -> None:
    _, quality, _ = _ramz()
    failures = classify_failures([], quality, [])
    assert {f.category for f in failures} == {FAILURE_LINT}
    assert known_issues_from_failures(failures) == []


def test_skipping_the_security_tools_removes_their_failures_and_nothing_else() -> None:
    """The no-tools Ramz run: security tools skipped, yamllint and markdownlint
    still failed. Nothing is invented for the skipped tools."""
    skipped = [_r("cargo audit", "", 0, skipped=True, skip_reason="not installed")]
    failures = classify_failures([], _ramz()[1][1:], skipped)
    assert [f.tool for f in failures] == ["yamllint", "markdownlint"]


# --- compilation -----------------------------------------------------------


def test_a_rustc_error_code_is_a_compilation_failure_under_any_tool() -> None:
    for kind in ("cargo test", "cargo clippy", "cargo build", "cargo"):
        f = _one(kind, "error[E0425]: cannot find value `x` in this scope")
        assert f.category == FAILURE_COMPILATION, kind
        assert f.signals == ("rust-error-code",) and f.subject == "Rust compilation"


def test_clippy_lints_promoted_to_errors_are_lint_failures_not_compilation() -> None:
    out = (
        "error: this `if` has identical blocks\n"
        "error: could not compile `ramz-core` (lib) due to 1 previous error"
    )
    f = _one("cargo clippy", out)
    assert f.category == FAILURE_LINT and f.signals == ()


def test_a_python_syntax_error_is_a_compilation_failure_with_the_legacy_sentence() -> (
    None
):
    for out in (
        "error: Failed to parse a.py:3:1: Expected an indented block",
        '  File "a.py", line 1\nSyntaxError: invalid syntax',
    ):
        failures = classify_result(_r("ruff", out), "quality")
        assert [f.category for f in failures] == [FAILURE_COMPILATION]
        assert known_issues_from_failures(failures) == [
            "One or more source files contain syntax errors."
        ]


def test_other_compilers_have_strong_signatures_too() -> None:
    cases = {
        (
            "tsc --noEmit",
            "src/a.ts(1,1): error TS2304: Cannot find name 'x'.",
        ): "typescript-error-code",
        ("go test", "FAIL\tgithub.com/x/y [build failed]"): "go-build-failed",
        ("mvn test", "[ERROR] COMPILATION ERROR :"): "java-compilation-error",
        (
            "dotnet test",
            "Program.cs(1,1): error CS0103: The name 'x' does not exist",
        ): "dotnet-error-code",
    }
    for (kind, out), signal in cases.items():
        f = _one(kind, out)
        assert f.category == FAILURE_COMPILATION and signal in f.signals, kind


def test_a_bare_error_line_never_decides_a_category() -> None:
    for kind in ("ruff", "pytest", "yamllint", "cargo audit", "mystery-tool"):
        found = classify_result(_r(kind, "error: something failed"), "")
        assert all(f.category != FAILURE_COMPILATION for f in found), kind


def test_a_missing_python_module_is_a_configuration_failure_with_the_legacy_sentence() -> (
    None
):
    failures = classify_result(
        _r("pytest", "E   ModuleNotFoundError: No module named 'x'"), "test"
    )
    assert [f.category for f in failures] == [FAILURE_CONFIGURATION]
    assert known_issues_from_failures(failures) == [
        "A required Python dependency is missing."
    ]


def test_one_result_can_carry_two_independent_causes() -> None:
    out = "error[E0432]: unresolved import\nModuleNotFoundError: No module named 'y'"
    failures = classify_result(_r("pytest", out), "test")
    assert [f.category for f in failures] == [
        FAILURE_COMPILATION,
        FAILURE_CONFIGURATION,
    ]


# --- execution failures ----------------------------------------------------


def test_execution_failures_are_recognised_by_the_runner_sentinel_and_exit_code() -> (
    None
):
    cases = [
        (124, f"partial output\n{SENTINEL_TIMEOUT}", "timeout"),
        (124, SENTINEL_TIMEOUT, "timeout"),
        (127, f"{SENTINEL_NOT_FOUND} cargo", "tool_not_found"),
        (1, f"{SENTINEL_OS_ERROR} [Errno 13] Permission denied", "os_error"),
    ]
    for rc, out, cause in cases:
        assert execution_cause(_r("x", out, rc)) == cause


def test_a_tool_that_really_exits_124_or_127_is_not_a_timeout_or_a_missing_tool() -> (
    None
):
    assert execution_cause(_r("cargo audit", "audit says no", 124)) == ""
    assert execution_cause(_r("cargo audit", "audit says no", 127)) == ""
    assert (
        execution_cause(
            _r("cargo audit", f"{SENTINEL_TIMEOUT} is a log line\nmore", 124)
        )
        == ""
    )
    assert execution_cause(_r("cargo audit", f"{SENTINEL_TIMEOUT}", 1)) == ""


def test_a_security_tool_that_could_not_run_is_a_tool_failure_never_a_finding() -> None:
    for rc, out, cause in (
        (124, SENTINEL_TIMEOUT, "timeout"),
        (127, f"{SENTINEL_NOT_FOUND} cargo-audit", "tool_not_found"),
    ):
        f = _one("cargo audit", out, "security", rc)
        assert (f.category, f.cause) == (FAILURE_SECURITY_TOOL, cause)
        assert f.signals == (cause,)
        assert "finding" in f.summary or "not" in f.summary


def test_a_non_security_tool_that_could_not_run_is_unclassified_with_its_cause() -> (
    None
):
    f = _one("pytest", SENTINEL_TIMEOUT, "test", 124)
    assert (f.category, f.cause) == (FAILURE_UNKNOWN_TOOL, "timeout")
    assert f.summary == "pytest (Python tests) did not finish: it timed out."


def test_the_real_runner_marks_a_timeout_and_a_missing_tool_end_to_end() -> None:
    cwd = Path(tempfile.gettempdir())
    rc, out, _ = run_cmd(
        [
            sys.executable,
            "-c",
            "import time; print('start', flush=True); time.sleep(30)",
        ],
        cwd,
        timeout=1,
    )
    assert rc == 124 and out.rstrip().endswith(SENTINEL_TIMEOUT) and "start" in out
    assert execution_cause(_r("cargo audit", out, rc)) == "timeout"
    rc, out, _ = run_cmd(["definitely-not-a-command-r13"], cwd)
    assert rc == 127 and out.startswith(SENTINEL_NOT_FOUND)
    assert execution_cause(_r("cargo audit", out, rc)) == "tool_not_found"


# --- security tools --------------------------------------------------------


def test_a_security_tool_without_a_findings_report_is_a_tool_failure() -> None:
    f = _one("cargo audit", "error: couldn't fetch advisory database", "security")
    assert f.category == FAILURE_SECURITY_TOOL and f.cause == CAUSE_EXIT_CODE
    assert "tool failure, not as a finding" in f.summary


def test_findings_signatures_for_the_other_security_tools() -> None:
    cases = {
        "pip-audit": "Found 2 known vulnerabilities in 1 package",
        "npm audit": "found 3 vulnerabilities (1 low, 2 high)",
        "govulncheck": "Vulnerability #1: GO-2024-0001",
        "bundler-audit": "Vulnerabilities found!",
        "composer audit": "Found 1 security vulnerability advisory",
        "bandit": ">> Issue: [B105:hardcoded_password_string] x",
        "gitleaks": "WRN leaks found: 2",
    }
    for kind, out in cases.items():
        assert _one(kind, out, "security").category == FAILURE_SECURITY_FINDING, kind


def test_zero_vulnerabilities_with_a_failing_exit_is_not_a_finding() -> None:
    assert (
        _one("npm audit", "found 0 vulnerabilities", "security").category
        == FAILURE_SECURITY_TOOL
    )
    assert (
        _one("gitleaks", "INF no leaks found", "security").category
        == FAILURE_SECURITY_TOOL
    )


def test_bandit_context_lines_cannot_fake_a_compile_error_or_a_finding() -> None:
    out = "91\t        except SyntaxError:\n>> Issue: [B101:assert_used] Use of assert"
    f = _one("bandit", out, "security")
    assert f.category == FAILURE_SECURITY_FINDING and f.signals == (
        "static-finding-reported",
    )
    assert (
        _one(
            "bandit",
            "91\t        except SyntaxError:\nSome unrelated failure",
            "security",
        ).category
        == FAILURE_SECURITY_TOOL
    )


def test_cargo_deny_warnings_alone_are_not_findings_or_policy_failures() -> None:
    out = "warning[duplicate]: found 2 duplicate entries for crate 'x'\nwarning[license-not-encountered]: license was not encountered"
    f = _one("cargo deny check", out, "security", 1)
    assert f.category == FAILURE_SECURITY_TOOL and f.signals == ()


def test_every_cargo_deny_advisory_code_is_a_finding_and_other_error_codes_are_policy() -> (
    None
):
    for code in ("vulnerability", "unmaintained", "unsound", "yanked", "notice"):
        (f,) = classify_result(_r("cargo deny check", f"error[{code}]: x"), "security")
        assert f.category == FAILURE_SECURITY_FINDING, code
    for code in ("rejected", "banned", "not-allowed", "source-not-allowed", "wildcard"):
        (f,) = classify_result(_r("cargo deny check", f"error[{code}]: x"), "security")
        assert f.category == FAILURE_DEPENDENCY_POLICY, code


# --- defaults and fallbacks ------------------------------------------------


def test_test_runners_default_to_test_failure_and_unknown_tools_stay_unknown() -> None:
    assert _one("cargo test", "test a ... FAILED", "test").category == FAILURE_TEST
    assert _one("pytest", "1 failed, 3 passed", "test").category == FAILURE_TEST
    assert _one("mystery-tool", "boom", "quality").category == FAILURE_UNKNOWN_TOOL
    assert _one("mystery-tool", "boom", "security").category == FAILURE_SECURITY_TOOL
    assert _one("mystery-tool", "boom", "test").category == FAILURE_TEST
    assert _one("mystery-tool", "boom", "").category == FAILURE_UNKNOWN_TOOL


def test_kinds_with_a_target_in_their_name_match_by_prefix() -> None:
    assert (
        _one("docker compose config deploy/compose.yaml", "bad").category
        == FAILURE_CONFIGURATION
    )
    assert _one("helm lint charts/app", "bad").category == FAILURE_LINT
    assert _one("gradle someTask", "bad").category == FAILURE_UNKNOWN_TOOL


def test_a_failing_check_with_no_output_is_still_a_failure() -> None:
    assert _one("cargo fmt --check", "", "quality").category == FAILURE_LINT


def test_passed_skipped_and_inconclusive_checks_are_not_failures() -> None:
    results = [
        _r("ruff", "error: Failed to parse", 0),
        _r("cargo audit", "", 0, skipped=True, skip_reason="not installed"),
        _r(
            "cargo audit",
            "x",
            0,
            inconclusive_reason="the advisory database was unreachable",
        ),
    ]
    assert classify_failures(results, [], []) == []
    assert detect_known_issues(results) == []


# --- determinism, purity, wording -------------------------------------------


def test_classification_is_deterministic_and_does_not_mutate_its_input() -> None:
    tests, quality, security = _ramz()
    snapshot = [(r.kind, r.returncode, r.raw_output) for r in quality + security]
    first = classify_failures(tests, quality, security)
    assert first == classify_failures(tests, quality, security)
    assert snapshot == [
        (r.kind, r.returncode, r.raw_output) for r in quality + security
    ]
    assert [f.tool for f in first] == [
        "actionlint",
        "yamllint",
        "markdownlint",
        "cargo audit",
        "cargo deny check",
        "cargo deny check",
    ]


def test_the_known_issue_tool_list_is_capped() -> None:
    failures = [
        Failure(tool=f"tool{i}", group="security", category=FAILURE_SECURITY_FINDING)
        for i in range(9)
    ]
    (line,) = known_issues_from_failures(failures)
    assert "tool0, tool1, tool2, tool3, tool4, tool5 (+3 more)" in line


def test_no_summary_asserts_a_vulnerability_or_exploitability() -> None:
    tests, quality, security = _ramz()
    for f in classify_failures(tests, quality, security):
        text = f.summary.lower()
        assert "exploitable" not in text.replace(
            "not proof that the project is exploitable", ""
        )
        assert "confirmed" not in text


# --- the report ---------------------------------------------------------------


def _data(name: str) -> ReportData:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "p"
        root.mkdir()
        return FIXTURES[name](root)


def test_the_hybrid_fixture_matches_what_the_classifier_produces() -> None:
    data = _data("hybrid")
    got = classify_failures(
        data.test_results, data.quality_results, data.security_results
    )
    assert data.failures == got
    assert data.known_issues == known_issues_from_failures(got)


def test_json_carries_the_failures_and_omits_the_key_when_nothing_failed() -> None:
    payload = json.loads(json_renderer.render(_data("hybrid"), include_source=False))
    assert [f["category"] for f in payload["failures"]] == [
        FAILURE_TEST,
        FAILURE_LINT,
        FAILURE_SECURITY_FINDING,
    ]
    assert set(payload["failures"][2]) == {
        "tool",
        "group",
        "category",
        "cause",
        "subject",
        "returncode",
        "summary",
        "signals",
        "id",
    }
    assert payload["failures"][2]["signals"] == ["leak-reported"]
    assert "failures" not in json.loads(
        json_renderer.render(_data("minimal"), include_source=False)
    )


def test_markdown_and_json_agree_on_the_failures() -> None:
    data = _data("hybrid")
    md = markdown.render(data, include_source=False)
    rows = md.split("## Failure classification")[1].split("\n\n")[1].splitlines()[2:]
    assert len(rows) == len(data.failures) == 3
    for f, row in zip(data.failures, rows, strict=True):
        assert f"`{f.category}`" in row and f.tool in row
    assert "## Failure classification" not in markdown.render(
        _data("minimal"), include_source=False
    )


def test_the_report_never_contains_the_retired_generic_sentence() -> None:
    for name in FIXTURES:
        data = _data(name)
        assert _GENERIC not in markdown.render(data, include_source=False)
        assert _GENERIC not in json_renderer.render(data, include_source=False)
