"""Findings baseline, slice F2: the gate policies on the comparison.

What these tests defend (decisions of 2026-11-24 in `docs/R14D1_PLAN.md`, section 9):
the four policies and only four; what is Critical (a secret that is not a fixture, an
advisory of severity `critical`, a health critical condition and nothing else); that
`fixed`, `unchanged` and `not_checked` never count as new; that missing data is never
assumed Critical and never fails the gate but is always listed as uncertain; and that the
result is deterministic.

gate (قطعه‌ی F2): چهار سیاست و فقط چهار؛ بحرانی یعنی secret غیر-fixture، advisory با
severity `critical` و شرط بحرانی health و بس؛ `fixed` و `unchanged` و `not_checked` هرگز
«جدید» حساب نمی‌شوند؛ داده‌ی ناکافی هرگز بحرانی فرض نمی‌شود و رد نمی‌کند ولی همیشه در
`uncertain` می‌آید؛ نتیجه قطعی (deterministic) است.
"""

from __future__ import annotations

import dataclasses
import json
import random
from typing import Any

import pytest
from sarand.core import baseline as bl
from sarand.core import gate as g
from sarand.core.finding_identity import KIND_SECRETS, finding_id

# Condition ids as the health score builds them (`<kind>:<12 hex>`); the hash part is
# arbitrary here because the gate reads only the kind and compares ids as text.
# شناسه‌ی شرط‌ها مثل health؛ بخش hash اینجا دلخواه است چون gate فقط نوع را می‌خواند.
TEST_A = "test_suite_failed:aaaaaaaaaaaa"
TEST_B = "test_suite_failed:bbbbbbbbbbbb"
POLICY_C = "dependency_policy_failure:cccccccccccc"
TOOL_D = "security_tool_failure:dddddddddddd"
SYMLINKS = "broken_symlinks:eeeeeeeeeeee"
UNAVAILABLE = "test_check_unavailable:ffffffffffff"
SECRET_RESTATED = "hardcoded_secrets:111111111111"
ADVISORY_RESTATED = "security_finding_detected:222222222222"


def _report(
    schema: str = "1.12",
    conditions: list[str] | None = None,
    health: bool = True,
    **over: Any,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema_version": schema,
        "failures": [],
        "advisories": [],
        "secret_findings": [],
        "test_results": [],
        "quality_results": [],
        "security_results": [],
        "included_files": ["conf.py"],
        "skipped_files": [],
        "excluded_secret_files": [],
    }
    if health:
        data["health"] = {"critical_ids": conditions} if conditions else {}
    data.update(over)
    return data


def _check(kind: str, state: str = "passed") -> dict[str, Any]:
    return {
        "kind": kind,
        "returncode": 1 if state == "failed" else 0,
        "summary": "",
        "state": state,
    }


def _failure(
    tool: str = "pytest",
    group: str = "test",
    category: str = "test_failure",
    subject: str = "a",
) -> dict[str, Any]:
    return {
        "tool": tool,
        "group": group,
        "category": category,
        "cause": "exit_code",
        "subject": subject,
        "returncode": 1,
        "signals": [],
    }


def _advisory(
    severity: str | None = "high",
    advisory: str = "RUSTSEC-2024-0001",
    sources: tuple[str, ...] = ("cargo audit",),
) -> dict[str, Any]:
    return {
        "id": advisory,
        "package": "left-pad",
        "version": "1.0.0",
        "severity": severity,
        "fixed_versions": [],
        "sources": list(sources),
    }


def _secret(path: str = "conf.py", name: str = "AWS Access Key ID") -> dict[str, Any]:
    return {"path": path, "line_number": 3, "pattern_name": name}


def _secret_id(path: str = "conf.py", name: str = "AWS Access Key ID") -> str:
    return finding_id(KIND_SECRETS, path, name)


def _run(
    policy: str,
    reference: dict[str, Any],
    current: dict[str, Any],
    fixtures: tuple[str, ...] = (),
) -> dict[str, Any]:
    old = bl.read_report_view(reference)
    new = bl.read_report_view(current)
    if fixtures:
        new = dataclasses.replace(new, fixture_secrets=frozenset(fixtures))
    return g.evaluate_gate(policy, old, new, bl.compare_findings(old, new))


def _ids(result: dict[str, Any], key: str = "failed_on") -> set[tuple[str, str]]:
    return {(item["class"], item["id"]) for item in result[key]}


def _reasons(result: dict[str, Any]) -> set[str]:
    return {item["reason"] for item in result["uncertain"]}


# ------------------------------------------------------------------- the policies


def test_there_are_exactly_four_policies_and_the_default_is_never() -> None:
    assert g.POLICIES == ("never", "new", "new-critical", "critical")


def test_an_unknown_policy_is_refused() -> None:
    with pytest.raises(ValueError):
        _run("sometimes", _report(), _report())


def test_never_changes_nothing_even_with_new_and_critical_findings() -> None:
    current = _report(
        secret_findings=[_secret()],
        advisories=[_advisory("critical")],
        failures=[_failure()],
        conditions=[TEST_A],
    )
    result = _run("never", _report(), current)
    assert result == {
        "policy": "never",
        "verdict": "not_gated",
        "failed_on": [],
        "uncertain": [],
    }


def test_the_exit_codes_are_the_decided_ones_and_distinct() -> None:
    codes = (g.EXIT_OK, g.EXIT_ERROR, g.EXIT_GATE_FAILED, g.EXIT_BASELINE_UNUSABLE)
    assert codes == (0, 1, 3, 4)


# --------------------------------------------------------------------- policy: new


def test_new_fails_on_a_new_secret_advisory_and_failure() -> None:
    reference = _report(
        test_results=[_check("pytest")],
        security_results=[_check("cargo audit")],
    )
    current = _report(
        test_results=[_check("pytest", "failed")],
        security_results=[_check("cargo audit", "failed")],
        failures=[_failure()],
        advisories=[_advisory("low")],
        secret_findings=[_secret()],
    )
    result = _run("new", reference, current)
    assert result["verdict"] == "fail"
    assert {c for c, _ in _ids(result)} == {"failures", "advisories", "secrets"}
    assert {i["rule"] for i in result["failed_on"]} == {"new_finding"}
    assert result["uncertain"] == []


def test_new_ignores_fixed_unchanged_and_changed_findings() -> None:
    reference = _report(
        secret_findings=[_secret(name="old one"), _secret(name="kept")],
        advisories=[_advisory("moderate")],
        security_results=[_check("cargo audit", "failed")],
    )
    current = _report(
        secret_findings=[_secret(name="kept"), _secret(name="kept")],  # count 1 -> 2
        advisories=[_advisory("critical")],  # severity changed: not new
        security_results=[_check("cargo audit", "failed")],
    )
    result = _run("new", reference, current)
    assert result["verdict"] == "pass"
    assert result["failed_on"] == [] and result["uncertain"] == []


def test_new_never_counts_a_fixture_secret() -> None:
    current = _report(secret_findings=[_secret(path="tests/t.py")])
    result = _run("new", _report(), current, fixtures=(_secret_id("tests/t.py"),))
    assert result["verdict"] == "pass" and result["uncertain"] == []


def test_new_lists_what_the_reference_could_not_see_as_uncertain_and_passes() -> None:
    # The reference never ran the security check: the advisory cannot be called new.
    # مرجع چک امنیتی را اجرا نکرده: advisory را نمی‌شود «جدید» نامید.
    current = _report(
        advisories=[_advisory("critical")], security_results=[_check("cargo audit")]
    )
    result = _run("new", _report(), current)
    assert result["verdict"] == "pass"
    assert _reasons(result) == {"reference_check_not_run"}


def test_new_with_a_class_the_reference_schema_did_not_record_is_uncertain() -> None:
    current = _report(advisories=[_advisory("high")])
    result = _run("new", _report(schema="1.2", health=False), current)
    assert result["verdict"] == "pass"
    assert _reasons(result) == {"class_not_recorded_in_reference"}


def test_new_does_not_list_a_not_checked_secret_that_is_a_fixture() -> None:
    reference = _report(skipped_files=[["big.py", 99]])
    current = _report(secret_findings=[_secret(path="big.py")])
    result = _run("new", reference, current, fixtures=(_secret_id("big.py"),))
    assert result["uncertain"] == []


def test_new_lists_a_secret_in_a_file_the_reference_skipped_as_uncertain() -> None:
    reference = _report(skipped_files=[["big.py", 99]])
    current = _report(secret_findings=[_secret(path="big.py")])
    result = _run("new", reference, current)
    assert result["verdict"] == "pass"
    assert _reasons(result) == {"reference_file_skipped"}


# ---------------------------------------------------------------- policy: new-critical


def test_new_critical_fails_on_a_new_valid_secret() -> None:
    result = _run("new-critical", _report(), _report(secret_findings=[_secret()]))
    assert result["verdict"] == "fail"
    assert result["failed_on"][0]["rule"] == "critical_secret"
    assert result["failed_on"][0]["state"] == "new"


def test_new_critical_ignores_a_new_fixture_secret() -> None:
    current = _report(secret_findings=[_secret(path="tests/t.py")])
    result = _run(
        "new-critical", _report(), current, fixtures=(_secret_id("tests/t.py"),)
    )
    assert result["verdict"] == "pass"


def test_new_critical_advisory_severity_decides() -> None:
    reference = _report(security_results=[_check("cargo audit")])
    cases = {
        "critical": "fail",
        "CRITICAL ": "fail",
        "high": "pass",
        "moderate": "pass",
        "low": "pass",
    }
    for severity, verdict in cases.items():
        current = _report(
            security_results=[_check("cargo audit")],
            advisories=[_advisory(severity)],
        )
        assert _run("new-critical", reference, current)["verdict"] == verdict, severity


@pytest.mark.parametrize("severity", [None, "weird", ""])
def test_new_critical_unknown_severity_is_uncertain_never_a_failure(
    severity: str | None,
) -> None:
    reference = _report(security_results=[_check("cargo audit")])
    current = _report(
        security_results=[_check("cargo audit")], advisories=[_advisory(severity)]
    )
    result = _run("new-critical", reference, current)
    assert result["verdict"] == "pass"
    assert _reasons(result) == {"severity_unknown"}


def test_new_critical_a_not_checked_advisory_is_uncertain_only_if_it_could_count() -> (
    None
):
    reference = _report()  # the check did not run there
    current = _report(
        security_results=[_check("cargo audit")],
        advisories=[
            _advisory("critical", "A-1"),
            _advisory("high", "A-2"),
            _advisory(None, "A-3"),
        ],
    )
    result = _run("new-critical", reference, current)
    assert result["verdict"] == "pass"
    labels = {item["label"].split()[0] for item in result["uncertain"]}
    assert labels == {"A-1", "A-3"}  # the high one could never count


def test_new_critical_an_old_critical_advisory_does_not_fail() -> None:
    both = _report(
        security_results=[_check("cargo audit")], advisories=[_advisory("critical")]
    )
    assert _run("new-critical", both, both)["verdict"] == "pass"


def test_new_critical_failure_needs_a_critical_condition_and_a_new_failure() -> None:
    reference = _report(test_results=[_check("pytest")])
    failing: dict[str, Any] = {
        "test_results": [_check("pytest", "failed")],
        "failures": [_failure()],
    }
    # a new failure with the health critical condition: Critical and new
    hit = _run("new-critical", reference, _report(conditions=[TEST_A], **failing))
    assert hit["verdict"] == "fail"
    assert (hit["failed_on"][0]["id"], hit["failed_on"][0]["state"]) == (TEST_A, "new")
    # the same failure with no health condition (an ordinary failure): not Critical
    plain = _run("new-critical", reference, _report(**failing))
    assert plain["verdict"] == "pass" and plain["uncertain"] == []


def test_new_critical_an_ordinary_lint_failure_is_not_critical() -> None:
    reference = _report(quality_results=[_check("ruff")])
    current = _report(
        quality_results=[_check("ruff", "failed")],
        failures=[_failure("ruff", "quality", "lint_failure")],
        conditions=[TEST_A],  # a test condition that has nothing new behind it
    )
    assert _run("new-critical", reference, current)["verdict"] == "pass"


def test_new_critical_a_fixed_suite_changes_the_condition_id_but_is_not_new() -> None:
    # Two suites failed; one was fixed. The condition id hashes the tool SET, so it
    # changes, yet nothing new happened and the gate must not fail.
    # دو suite شکست خورده بود؛ یکی رفع شد. شناسه عوض می‌شود ولی چیز جدیدی نیست.
    reference = _report(
        conditions=[TEST_A],
        test_results=[_check("pytest", "failed"), _check("mypy", "failed")],
        failures=[_failure("pytest"), _failure("mypy")],
    )
    current = _report(
        conditions=[TEST_B],
        test_results=[_check("pytest", "failed"), _check("mypy")],
        failures=[_failure("pytest")],
    )
    result = _run("new-critical", reference, current)
    assert result["verdict"] == "pass" and result["uncertain"] == []


def test_new_critical_a_failure_the_reference_could_not_see_is_uncertain() -> None:
    reference = _report(conditions=None)  # no test check ran there
    current = _report(
        conditions=[TEST_A],
        test_results=[_check("pytest", "failed")],
        failures=[_failure()],
    )
    result = _run("new-critical", reference, current)
    assert result["verdict"] == "pass"
    assert _reasons(result) == {"reference_check_not_run"}


def test_new_critical_each_backed_kind_counts_through_its_own_failures() -> None:
    reference = _report(security_results=[_check("cargo deny"), _check("pip-audit")])
    current = _report(
        conditions=[POLICY_C, TOOL_D],
        security_results=[
            _check("cargo deny", "failed"),
            _check("pip-audit", "failed"),
        ],
        failures=[
            _failure("cargo deny", "security", "dependency_policy_failure"),
            _failure("pip-audit", "security", "security_tool_failure"),
        ],
    )
    result = _run("new-critical", reference, current)
    assert {i["id"] for i in result["failed_on"]} == {POLICY_C, TOOL_D}


def test_new_critical_an_unbacked_condition_is_compared_by_id() -> None:
    base: dict[str, Any] = {"conditions": [SYMLINKS]}
    assert _run("new-critical", _report(**base), _report(**base))["verdict"] == "pass"
    new = _run("new-critical", _report(), _report(**base))
    assert new["verdict"] == "fail" and new["failed_on"][0]["id"] == SYMLINKS


def test_new_critical_an_unbacked_condition_without_reference_ids_is_uncertain() -> (
    None
):
    reference = _report(schema="1.4", health=False)
    result = _run("new-critical", reference, _report(conditions=[SYMLINKS]))
    assert result["verdict"] == "pass"
    assert _reasons(result) == {"reference_has_no_critical_ids"}


def test_new_critical_without_a_current_health_is_uncertain_not_a_pass_in_silence() -> (
    None
):
    result = _run("new-critical", _report(), _report(health=False))
    assert result["verdict"] == "pass"
    assert _reasons(result) == {"health_not_computed"}


def test_new_critical_restated_condition_kinds_are_left_to_their_own_classes() -> None:
    current = _report(conditions=[SECRET_RESTATED, ADVISORY_RESTATED])
    result = _run("new-critical", _report(), current)
    assert result["verdict"] == "pass" and result["uncertain"] == []


def test_new_critical_a_high_advisory_is_not_critical_through_its_condition() -> None:
    # The health score marks a failed audit critical; the owner's rule says only the
    # severity `critical` is Critical for an advisory.
    # health شکست audit را بحرانی می‌داند؛ قاعده‌ی مالک: برای advisory فقط severity
    # `critical` بحرانی است.
    reference = _report(security_results=[_check("cargo audit")])
    current = _report(
        security_results=[_check("cargo audit", "failed")],
        advisories=[_advisory("high")],
        failures=[_failure("cargo audit", "security", "security_finding_detected")],
        conditions=[ADVISORY_RESTATED],
    )
    assert _run("new-critical", reference, current)["verdict"] == "pass"


def test_new_critical_an_unavailable_check_is_uncertain_when_it_is_new() -> None:
    result = _run("new-critical", _report(), _report(conditions=[UNAVAILABLE]))
    assert result["verdict"] == "pass"
    assert _reasons(result) == {"check_unavailable_no_verdict"}
    same = _run(
        "new-critical",
        _report(conditions=[UNAVAILABLE]),
        _report(conditions=[UNAVAILABLE]),
    )
    assert same["uncertain"] == []  # an old one is not repeated as news


# ------------------------------------------------------------------ policy: critical


def test_critical_fails_on_an_old_valid_secret_and_a_fixture_does_not() -> None:
    both = _report(secret_findings=[_secret(), _secret(path="tests/t.py", name="x")])
    result = _run("critical", both, both, fixtures=(_secret_id("tests/t.py", "x"),))
    assert result["verdict"] == "fail"
    assert [i["id"] for i in result["failed_on"]] == [_secret_id()]
    assert result["failed_on"][0]["state"] == "unchanged"


def test_critical_fails_on_a_critical_advisory_old_or_new_not_on_a_high_one() -> None:
    old = _report(
        security_results=[_check("cargo audit")], advisories=[_advisory("critical")]
    )
    assert _run("critical", old, old)["verdict"] == "fail"
    high = _report(
        security_results=[_check("cargo audit")], advisories=[_advisory("high")]
    )
    assert _run("critical", high, high)["verdict"] == "pass"


def test_critical_a_not_checked_critical_finding_is_still_a_present_finding() -> None:
    # Not being comparable does not make a present Critical secret go away.
    # قابل‌مقایسه نبودن، secret بحرانیِ موجود را از بین نمی‌برد.
    reference = _report(skipped_files=[["conf.py", 99]])
    current = _report(secret_findings=[_secret()])
    assert _run("critical", reference, current)["verdict"] == "fail"


def test_critical_unknown_severity_is_uncertain_in_every_state() -> None:
    both = _report(
        security_results=[_check("cargo audit")], advisories=[_advisory(None)]
    )
    result = _run("critical", both, both)
    assert result["verdict"] == "pass"
    assert _reasons(result) == {"severity_unknown"}


def test_critical_fails_on_an_existing_critical_condition_and_says_it_is_old() -> None:
    both = _report(
        conditions=[TEST_A, SYMLINKS],
        test_results=[_check("pytest", "failed")],
        failures=[_failure()],
    )
    result = _run("critical", both, both)
    assert result["verdict"] == "fail"
    assert {(i["id"], i["state"]) for i in result["failed_on"]} == {
        (TEST_A, "existing"),
        (SYMLINKS, "existing"),
    }


def test_critical_marks_a_condition_with_a_new_failure_as_new() -> None:
    reference = _report(test_results=[_check("pytest")])
    current = _report(
        conditions=[TEST_A],
        test_results=[_check("pytest", "failed")],
        failures=[_failure()],
    )
    result = _run("critical", reference, current)
    assert [(i["id"], i["state"]) for i in result["failed_on"]] == [(TEST_A, "new")]


def test_critical_passes_when_nothing_is_critical() -> None:
    clean = _report(
        security_results=[_check("cargo audit")],
        advisories=[_advisory("moderate")],
        failures=[_failure("ruff", "quality", "lint_failure")],
        quality_results=[_check("ruff", "failed")],
    )
    result = _run("critical", clean, clean)
    assert result["verdict"] == "pass" and result["failed_on"] == []


def test_critical_without_a_current_health_is_uncertain_but_secrets_still_count() -> (
    None
):
    current = _report(health=False, secret_findings=[_secret()])
    result = _run("critical", _report(), current)
    assert result["verdict"] == "fail"
    assert _reasons(result) == {"health_not_computed"}


def test_critical_an_unavailable_check_is_always_listed() -> None:
    both = _report(conditions=[UNAVAILABLE])
    result = _run("critical", both, both)
    assert result["verdict"] == "pass"
    assert _reasons(result) == {"check_unavailable_no_verdict"}


# -------------------------------------------------------------------- reading views


def test_a_report_with_health_but_no_critical_ids_has_no_critical_condition() -> None:
    view = bl.read_report_view(_report())
    assert view.conditions == frozenset()


def test_a_report_without_health_or_before_schema_1_5_has_unknown_conditions() -> None:
    assert bl.read_report_view(_report(health=False)).conditions is None
    old = _report(schema="1.4")
    old["health"] = {"critical_ids": [TEST_A]}
    assert bl.read_report_view(old).conditions is None


def test_critical_ids_that_are_not_a_list_make_the_reference_invalid() -> None:
    bad = _report()
    bad["health"] = {"critical_ids": "oops"}
    with pytest.raises(bl.BaselineReferenceError) as caught:
        bl.read_report_view(bad)
    assert caught.value.kind == "invalid"


@dataclasses.dataclass
class _Secret:
    path: str
    pattern_name: str
    is_test_fixture: bool


def _current(secrets: list[_Secret], critical_ids: list[str] | None) -> bl.FindingsView:
    return bl.current_view(
        schema=(1, 12),
        failures=[],
        advisories=[],
        secret_findings=secrets,
        test_results=[],
        quality_results=[],
        security_results=[],
        included_files=[],
        excluded_secret_files=[],
        skipped_files=[],
        critical_ids=critical_ids,
    )


def test_the_current_view_knows_fixtures_and_conditions() -> None:
    view = _current(
        [
            _Secret("tests/t.py", "k", True),
            _Secret("src/a.py", "k", False),
            _Secret("mixed.py", "k", True),
            _Secret("mixed.py", "k", False),
        ],
        [TEST_A],
    )
    assert view.conditions == frozenset({TEST_A})
    assert view.fixture_secrets == {_secret_id("tests/t.py", "k")}  # mixed is not one
    assert _current([], None).conditions is None


# ------------------------------------------------------------------ result and shape


def test_the_result_is_deterministic_whatever_the_input_order() -> None:
    secrets = [_secret(path=f"f{i}.py") for i in range(6)]
    advisories = [_advisory("critical", f"A-{i}") for i in range(4)]
    rendered = set()
    for seed in range(5):
        shuffled = list(secrets), list(advisories)
        random.Random(seed).shuffle(shuffled[0])
        random.Random(seed).shuffle(shuffled[1])
        current = _report(
            secret_findings=shuffled[0],
            advisories=shuffled[1],
            security_results=[_check("cargo audit")],
        )
        rendered.add(json.dumps(_run("critical", _report(), current), sort_keys=True))
    assert len(rendered) == 1


def test_a_failed_item_and_an_uncertain_item_carry_the_documented_fields() -> None:
    current = _report(
        secret_findings=[_secret()],
        advisories=[_advisory(None)],
        security_results=[_check("cargo audit")],
    )
    result = _run("critical", _report(), current)
    assert set(result) == {"policy", "verdict", "failed_on", "uncertain"}
    assert set(result["failed_on"][0]) == {"class", "id", "state", "rule", "label"}
    assert set(result["uncertain"][0]) == {"class", "id", "reason", "label"}


def test_condition_kind_is_the_part_before_the_colon() -> None:
    assert g.condition_kind(TEST_A) == "test_suite_failed"
    assert g.condition_kind("no_colon") == "no_colon"


def test_severity_class_never_guesses() -> None:
    assert bl.severity_class("Critical") == "critical"
    assert bl.severity_class(" moderate ") == "other"
    assert bl.severity_class("informational") == "other"
    assert bl.severity_class(None) == "unknown"
    assert bl.severity_class("catastrophic") == "unknown"


def test_gate_failed_reads_only_the_verdict() -> None:
    assert g.gate_failed({"verdict": "fail"})
    assert not g.gate_failed({"verdict": "pass"})
    assert not g.gate_failed({"verdict": "not_gated"})
    assert not g.gate_failed(None)


def test_the_gate_module_does_not_load_the_structure_package() -> None:
    import subprocess  # nosec B404
    import sys

    code = (
        "import sys; import sarand.core.gate; print('sarand.structure' in sys.modules)"
    )
    done = subprocess.run(  # nosec B603
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert done.stdout.strip() == "False", done.stderr
