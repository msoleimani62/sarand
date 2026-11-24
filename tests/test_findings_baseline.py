"""Findings baseline, slice F1: the comparison of two reports by finding identity.

What these tests defend (the acceptance criteria of `docs/R14D1_PLAN.md`, section 5):
every state (new, fixed, unchanged, changed, not_checked); the key rule (a finding is
`fixed` only when the check that reports it ran to a verdict in the current run, and
`new` only when the reference could have seen it); identity that does not depend on
wording, order or line numbers; a report schema that did not record a class; an unusable
reference; and independence from the structure package.

باز‌شناسی یافته‌ها (قطعه‌ی F1): همه‌ی حالت‌ها؛ قاعده‌ی کلیدی (fixed فقط وقتی که چکِ منبع در
اجرای فعلی به حکم رسیده)؛ هویتِ مستقل از متن، ترتیب و شماره خط؛ دسته‌ی ثبت‌نشده؛ مرجع نامعتبر.
"""

from __future__ import annotations

import copy
import json
import random
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest
from _golden_fixtures import FIXTURES
from sarand.core import baseline as bl
from sarand.core.advisories import collect_advisories
from sarand.core.failures import classify_failures
from sarand.models.results import CommandResult
from sarand.renderers import json_renderer
from sarand.utils.command import make_command_result

_DATA = Path(__file__).parent / "data" / "ramz_v0_3_2"
_AUDIT = (_DATA / "cargo_audit.txt").read_text(encoding="utf-8")


def _report(schema: str = "1.12", **over: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema_version": schema,
        "failures": [],
        "advisories": [],
        "secret_findings": [],
        "test_results": [],
        "quality_results": [],
        "security_results": [],
        "included_files": [],
        "skipped_files": [],
        "excluded_secret_files": [],
    }
    data.update(over)
    return data


def _check(kind: str, state: str) -> dict[str, Any]:
    returncode = 1 if state == "failed" else 0
    return {"kind": kind, "returncode": returncode, "summary": "", "state": state}


def _failure(
    subject: str = "a", returncode: int = 1, tool: str = "pytest"
) -> dict[str, Any]:
    return {
        "tool": tool,
        "group": "test",
        "category": "test_failure",
        "cause": "exit_code",
        "subject": subject,
        "returncode": returncode,
        "signals": [],
    }


def _advisory(
    severity: str | None = "high",
    sources: tuple[str, ...] = ("cargo audit",),
    fixed: tuple[str, ...] = ("1.2.3",),
    advisory: str = "RUSTSEC-2024-0001",
) -> dict[str, Any]:
    return {
        "id": advisory,
        "package": "left-pad",
        "version": "1.0.0",
        "severity": severity,
        "fixed_versions": list(fixed),
        "sources": list(sources),
    }


def _secret(
    path: str = "conf.py", line: int = 1, name: str = "AWS Access Key ID"
) -> dict[str, Any]:
    return {"path": path, "line_number": line, "pattern_name": name}


def _compare(reference: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    return bl.compare_findings(
        bl.read_report_view(reference), bl.read_report_view(current)
    )


def _only(result: dict[str, Any], name: str) -> dict[str, Any]:
    (entry,) = result["findings"][name]
    return entry


def _counts(result: dict[str, Any], name: str) -> dict[str, int]:
    return {k: v for k, v in result["summary"][name].items() if v}


# ------------------------------------------------------------------ the states


def test_identical_reports_are_unchanged_everywhere() -> None:
    report = _report(
        failures=[_failure()],
        advisories=[_advisory()],
        secret_findings=[_secret()],
        test_results=[_check("pytest", "failed")],
        security_results=[_check("cargo audit", "failed")],
        excluded_secret_files=["conf.py"],
    )
    result = _compare(report, report)
    assert all(entries == [] for entries in result["findings"].values())
    assert _counts(result, "failures") == {"unchanged": 1}
    assert _counts(result, "advisories") == {"unchanged": 1}
    assert _counts(result, "secrets") == {"unchanged": 1}
    assert result["reference"]["classes_not_recorded"] == []


def test_a_new_failure_is_new_when_the_reference_ran_that_check() -> None:
    reference = _report(test_results=[_check("pytest", "passed")])
    current = _report(failures=[_failure()], test_results=[_check("pytest", "failed")])
    entry = _only(_compare(reference, current), "failures")
    assert entry["state"] == "new" and entry["tool"] == "pytest"
    assert entry["old"] is None and entry["new"]["subject"] == "a"


@pytest.mark.parametrize(
    ("state", "reason"),
    [
        ("skipped", "reference_check_skipped"),
        ("inconclusive", "reference_check_inconclusive"),
        ("unavailable", "reference_check_unavailable"),
        ("missing", "reference_check_not_run"),
    ],
)
def test_a_failure_is_not_new_when_the_reference_could_not_have_seen_it(
    state: str, reason: str
) -> None:
    results = [] if state == "missing" else [_check("pytest", state)]
    reference = _report(test_results=results)
    current = _report(failures=[_failure()], test_results=[_check("pytest", "failed")])
    entry = _only(_compare(reference, current), "failures")
    assert (entry["state"], entry["reason"]) == ("not_checked", reason)


def test_a_failure_is_fixed_only_when_its_check_ran_in_the_current_run() -> None:
    reference = _report(
        failures=[_failure()], test_results=[_check("pytest", "failed")]
    )
    fixed = _only(
        _compare(reference, _report(test_results=[_check("pytest", "passed")])),
        "failures",
    )
    assert fixed["state"] == "fixed"
    still_failing_elsewhere = _report(test_results=[_check("pytest", "failed")])
    assert (
        _only(_compare(reference, still_failing_elsewhere), "failures")["state"]
        == "fixed"
    )


@pytest.mark.parametrize(
    ("state", "reason"),
    [
        ("skipped", "check_skipped"),
        ("inconclusive", "check_inconclusive"),
        ("unavailable", "check_unavailable"),
        ("missing", "check_not_run"),
    ],
)
def test_a_failure_whose_check_gave_no_verdict_is_never_fixed(
    state: str, reason: str
) -> None:
    reference = _report(
        failures=[_failure()], test_results=[_check("pytest", "failed")]
    )
    results = [] if state == "missing" else [_check("pytest", state)]
    entry = _only(_compare(reference, _report(test_results=results)), "failures")
    assert (entry["state"], entry["reason"]) == ("not_checked", reason)


def test_a_changed_failure_and_the_wording_that_is_not_a_change() -> None:
    reference = _report(
        failures=[_failure(returncode=1)], test_results=[_check("pytest", "failed")]
    )
    current = _report(
        failures=[_failure(returncode=2)], test_results=[_check("pytest", "failed")]
    )
    entry = _only(_compare(reference, current), "failures")
    assert (entry["state"], entry["direction"]) == ("changed", "neutral")
    worded = copy.deepcopy(reference)
    worded["failures"][0]["summary"] = "completely different words"
    assert _compare(reference, worded)["findings"]["failures"] == []


def test_a_failure_keeps_its_identity_when_only_the_order_changes() -> None:
    first = [_failure("a"), _failure("b")]
    result = _compare(
        _report(failures=first, test_results=[_check("pytest", "failed")]),
        _report(
            failures=list(reversed(first)), test_results=[_check("pytest", "failed")]
        ),
    )
    assert _counts(result, "failures") == {"unchanged": 2}


# --------------------------------------------------------------------- advisories


def test_an_advisory_is_fixed_only_when_every_source_check_ran() -> None:
    reference = _report(
        advisories=[_advisory(sources=("cargo audit", "cargo deny"))],
        security_results=[
            _check("cargo audit", "failed"),
            _check("cargo deny", "failed"),
        ],
    )
    both = _report(
        security_results=[
            _check("cargo audit", "passed"),
            _check("cargo deny", "passed"),
        ]
    )
    assert _only(_compare(reference, both), "advisories")["state"] == "fixed"
    one = _report(
        security_results=[
            _check("cargo audit", "passed"),
            _check("cargo deny", "skipped"),
        ]
    )
    entry = _only(_compare(reference, one), "advisories")
    assert (entry["state"], entry["reason"]) == ("not_checked", "check_skipped")
    none = _only(_compare(reference, _report()), "advisories")
    assert none["reason"] == "check_not_run"


def test_an_advisory_without_a_recorded_source_is_never_fixed() -> None:
    reference = _report(advisories=[_advisory(sources=())])
    entry = _only(
        _compare(
            reference, _report(security_results=[_check("cargo audit", "passed")])
        ),
        "advisories",
    )
    assert (entry["state"], entry["reason"]) == ("not_checked", "no_source_recorded")


def test_a_new_advisory_needs_a_reference_that_ran_its_checks() -> None:
    current = _report(
        advisories=[_advisory()], security_results=[_check("cargo audit", "failed")]
    )
    seen = _report(security_results=[_check("cargo audit", "passed")])
    assert _only(_compare(seen, current), "advisories")["state"] == "new"
    blind = _report(security_results=[_check("cargo audit", "skipped")])
    entry = _only(_compare(blind, current), "advisories")
    assert (entry["state"], entry["reason"]) == (
        "not_checked",
        "reference_check_skipped",
    )


@pytest.mark.parametrize(
    ("before", "after", "direction"),
    [
        ("high", "critical", "worse"),
        ("critical", "low", "better"),
        ("medium", "moderate", None),
        (None, "high", "neutral"),
        ("high", None, "neutral"),
    ],
)
def test_the_direction_of_an_advisory_change(
    before: str | None, after: str | None, direction: str | None
) -> None:
    checks = [_check("cargo audit", "failed")]
    result = _compare(
        _report(advisories=[_advisory(before)], security_results=checks),
        _report(advisories=[_advisory(after)], security_results=checks),
    )
    if direction is None:
        assert result["findings"]["advisories"] == []
    else:
        assert _only(result, "advisories")["direction"] == direction


def test_other_fixed_versions_are_a_neutral_change() -> None:
    checks = [_check("cargo audit", "failed")]
    result = _compare(
        _report(advisories=[_advisory(fixed=("1.2.3",))], security_results=checks),
        _report(advisories=[_advisory(fixed=("1.2.4",))], security_results=checks),
    )
    assert _only(result, "advisories")["direction"] == "neutral"


def test_a_class_the_reference_schema_did_not_record_is_not_checked() -> None:
    current = _report(
        failures=[_failure()],
        advisories=[_advisory()],
        test_results=[_check("pytest", "failed")],
        security_results=[_check("cargo audit", "failed")],
    )
    result = _compare(_report("1.2"), current)
    assert result["reference"]["classes_not_recorded"] == ["failures", "advisories"]
    for name in ("failures", "advisories"):
        entry = _only(result, name)
        assert (entry["state"], entry["reason"]) == (
            "not_checked",
            "class_not_recorded_in_reference",
        )
    four = _compare(_report("1.4"), current)
    assert four["reference"]["classes_not_recorded"] == ["failures"]
    # advisories are recorded by 1.4, but that report ran no security check
    entry = _only(four, "advisories")
    assert (entry["state"], entry["reason"]) == (
        "not_checked",
        "reference_check_not_run",
    )


# ----------------------------------------------------------------------- secrets


def test_a_secret_is_fixed_only_when_its_file_was_scanned_again() -> None:
    reference = _report(secret_findings=[_secret()], excluded_secret_files=["conf.py"])
    clean = _report(included_files=["conf.py"])
    assert _only(_compare(reference, clean), "secrets")["state"] == "fixed"
    skipped = _report(skipped_files=[["conf.py", 99999999]])
    entry = _only(_compare(reference, skipped), "secrets")
    assert (entry["state"], entry["reason"]) == ("not_checked", "file_skipped")
    absent = _only(_compare(reference, _report()), "secrets")
    assert (absent["state"], absent["reason"]) == ("not_checked", "file_not_scanned")


def test_a_new_secret_and_one_the_reference_could_not_scan() -> None:
    current = _report(secret_findings=[_secret()], excluded_secret_files=["conf.py"])
    assert (
        _only(_compare(_report(included_files=["conf.py"]), current), "secrets")[
            "state"
        ]
        == "new"
    )
    assert _only(_compare(_report(), current), "secrets")["state"] == "new"
    blind = _report(skipped_files=[["conf.py", 1]])
    entry = _only(_compare(blind, current), "secrets")
    assert (entry["state"], entry["reason"]) == (
        "not_checked",
        "reference_file_skipped",
    )


def test_a_line_number_is_never_identity_and_a_changed_count_is() -> None:
    reference = _report(
        secret_findings=[_secret(line=1)], excluded_secret_files=["conf.py"]
    )
    moved = _report(
        secret_findings=[_secret(line=40)], excluded_secret_files=["conf.py"]
    )
    assert _compare(reference, moved)["findings"]["secrets"] == []
    two = _report(
        secret_findings=[_secret(line=1), _secret(line=9)],
        excluded_secret_files=["conf.py"],
    )
    assert _only(_compare(reference, two), "secrets")["direction"] == "worse"
    assert _only(_compare(two, reference), "secrets")["direction"] == "better"


# ------------------------------------------------------ determinism, references


def test_the_output_does_not_depend_on_the_order_of_the_input() -> None:
    reference = _report(
        failures=[_failure("a"), _failure("b"), _failure("c")],
        advisories=[_advisory(advisory=f"RUSTSEC-2024-000{i}") for i in range(1, 4)],
        secret_findings=[_secret("a.py"), _secret("b.py"), _secret("c.py")],
        test_results=[_check("pytest", "failed")],
        security_results=[_check("cargo audit", "failed")],
    )
    current = _report(
        failures=[_failure("b", returncode=3), _failure("d")],
        advisories=[_advisory("critical", advisory="RUSTSEC-2024-0002")],
        secret_findings=[_secret("a.py"), _secret("z.py")],
        test_results=[_check("pytest", "passed")],
        security_results=[_check("cargo audit", "passed")],
        included_files=["b.py", "c.py"],
    )
    expected = json.dumps(_compare(reference, current), sort_keys=True)
    rng = random.Random(7)
    for _ in range(5):
        a, b = copy.deepcopy(reference), copy.deepcopy(current)
        for report in (a, b):
            for key in ("failures", "advisories", "secret_findings"):
                rng.shuffle(report[key])
        assert json.dumps(_compare(a, b), sort_keys=True) == expected


def test_unusable_references_are_reported_with_a_kind(tmp_path: Path) -> None:
    for data, kind in (
        ([], "invalid"),
        ({}, "invalid"),
        ({"schema_version": "x"}, "invalid"),
        ({"schema_version": "2.0"}, "incompatible"),
        (_report(failures="nope"), "invalid"),
        (_report(failures=[{"group": "test"}]), "invalid"),
        (_report(secret_findings=[{"path": "a"}]), "invalid"),
        (_report(test_results=[7]), "invalid"),
    ):
        with pytest.raises(bl.BaselineReferenceError) as excinfo:
            bl.read_report_view(data)
        assert excinfo.value.kind == kind, data


def test_reading_a_reference_file_raises_only_the_documented_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "text.json").write_text("not json", encoding="utf-8")
    (tmp_path / "binary.json").write_bytes(b"\xff\xfe\x00")
    (tmp_path / "dir").mkdir()
    good = tmp_path / "good.json"
    good.write_text(json.dumps(_report()), encoding="utf-8")
    for name in ("text.json", "binary.json", "dir", "absent.json"):
        with pytest.raises(bl.BaselineReferenceError):
            bl.read_baseline_file(tmp_path / name)
    assert bl.read_baseline_file(good).schema == (1, 12)
    monkeypatch.setattr(bl, "MAX_REFERENCE_BYTES", 10)
    with pytest.raises(bl.BaselineReferenceError) as excinfo:
        bl.read_baseline_file(good)
    assert "larger than" in str(excinfo.value)


def test_a_report_is_read_with_the_state_it_carries_or_derives_it() -> None:
    carried = bl.read_report_view(
        _report(test_results=[{"kind": "pytest", "returncode": 0, "state": "skipped"}])
    )
    assert carried.check_states == {"test/pytest": "skipped"}
    derived = bl.read_report_view(
        _report(
            "1.5", test_results=[{"kind": "pytest", "returncode": 1, "summary": "x"}]
        )
    )
    assert derived.check_states == {"test/pytest": "failed"}


# --------------------------------------------------- real data, independence


def _real_data(security: list[CommandResult]) -> Any:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "p"
        root.mkdir()
        data = FIXTURES["minimal"](root)
    data.test_results = []
    data.quality_results = []
    data.security_results = security
    data.failures = classify_failures([], [], security)
    data.advisories = collect_advisories(security)
    return data


def _current(data: Any) -> bl.FindingsView:
    return bl.current_view(
        schema=bl.parse_schema(json_renderer.JSON_SCHEMA_VERSION),
        failures=data.failures,
        advisories=data.advisories,
        secret_findings=data.secret_findings,
        test_results=data.test_results,
        quality_results=data.quality_results,
        security_results=data.security_results,
        included_files=[p.as_posix() for p in data.included_files],
        excluded_secret_files=[p.as_posix() for p in data.excluded_secret_files],
        skipped_files=[p.as_posix() for p, _ in data.skipped_files],
    )


def test_a_rendered_report_reads_back_to_the_findings_of_the_run() -> None:
    audit = make_command_result("cargo audit", 1, _AUDIT, 1.0)
    data = _real_data([audit])
    assert data.failures and data.advisories
    reference = bl.read_report_view(json.loads(json_renderer.render(data)))
    current = _current(data)
    assert set(reference.failures) == set(current.failures)
    assert set(reference.advisories) == set(current.advisories)
    assert reference.check_states == current.check_states
    result = bl.compare_findings(reference, current)
    assert all(entries == [] for entries in result["findings"].values())
    total = len(data.failures) + len(data.advisories)
    assert sum(c["unchanged"] for c in result["summary"].values()) >= total


def test_the_real_findings_are_not_fixed_when_the_security_check_is_skipped() -> None:
    audit = make_command_result("cargo audit", 1, _AUDIT, 1.0)
    reference = bl.read_report_view(
        json.loads(json_renderer.render(_real_data([audit])))
    )
    skipped = CommandResult(
        kind="cargo audit", returncode=0, summary="", skipped=True, skip_reason="user"
    )
    result = bl.compare_findings(reference, _current(_real_data([skipped])))
    for name in ("failures", "advisories"):
        assert result["findings"][name]
        assert {e["state"] for e in result["findings"][name]} == {"not_checked"}
        assert result["summary"][name]["fixed"] == 0


def test_the_comparison_does_not_load_the_structure_package() -> None:
    code = (
        "import sys, sarand.cli, sarand.core.baseline, sarand.renderers.json_renderer;"
        "import sarand.renderers.markdown, sarand.renderers.html, sarand.renderers.text;"
        "print([m for m in sys.modules if m.startswith('sarand.structure')])"
    )
    done = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )  # nosec B603
    assert done.stdout.strip() == "[]"
