"""R13-C: dependency advisories keep their identity (core/advisories.py) and a
security check that could not run is not a finding.

Evidence behind the tests: the real Ramz v0.3.2 outputs frozen in
tests/data/ramz_v0_3_2 (cargo audit: 5 vulnerabilities and 13 warnings, none with
a severity; cargo deny: a license violation and advisory diagnostics). Every rule
has a positive and a negative case. Dependency-free like the other tests.
R13-C: هویت advisoryها حفظ می‌شود و چکی که اجرا نشده «یافته» نیست.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from _golden_fixtures import FIXTURES
from sarand.constants import (
    APPLICABILITY_UNKNOWN,
    SARAND_INFO_URI,
    SENTINEL_NOT_FOUND,
    SENTINEL_TIMEOUT,
)
from sarand.core.advisories import (
    collect_advisories,
    parse_cargo_audit,
    parse_cargo_deny,
)
from sarand.core.health import compute_health_score
from sarand.core.risks import evaluate_risks
from sarand.models.results import CommandResult, ReportData
from sarand.renderers import json_renderer, markdown, sarif
from sarand.utils.command import make_command_result

_DATA = Path(__file__).parent / "data" / "ramz_v0_3_2"
_AUDIT = (_DATA / "cargo_audit.txt").read_text(encoding="utf-8")
_DENY = (_DATA / "cargo_deny_excerpt.txt").read_text(encoding="utf-8")


def _audit(rc: int = 1, out: str = _AUDIT, kind: str = "cargo audit") -> CommandResult:
    return make_command_result(kind, rc, out, 1.0)


def _deny(rc: int = 5, out: str = _DENY) -> CommandResult:
    return make_command_result("cargo deny check", rc, out, 1.0)


def _data(security: list[CommandResult], *, advisories: bool = True) -> ReportData:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "p"
        root.mkdir()
        data = FIXTURES["minimal"](root)
    data.test_results = []
    data.quality_results = []
    data.security_results = security
    if advisories:
        data.advisories = collect_advisories(security)
    data.health = compute_health_score(data)
    return data


_BLOCK = (
    "Crate:     demo\nVersion:   1.2.3\nTitle:     A demo flaw\nDate:      2026-01-01\n"
    "ID:        RUSTSEC-2099-0001\nURL:       https://rustsec.org/advisories/RUSTSEC-2099-0001\n"
    "Severity:  7.5 (high)\nSolution:  Upgrade to ^1.2.4, >=2.0.0\n"
)


# --- parsing the real Ramz output ---------------------------------------------


def test_the_real_cargo_audit_output_gives_eighteen_advisories() -> None:
    found = parse_cargo_audit(_AUDIT)
    kinds = [a.kind for a in found]
    assert len(found) == 18
    assert kinds.count("vulnerability") == 5
    assert kinds.count("unsound") == 10
    assert kinds.count("unmaintained") == 3


def test_identity_fields_come_from_the_tool_output() -> None:
    by_id = {a.id: a for a in parse_cargo_audit(_AUDIT)}
    ctutils = by_id["RUSTSEC-2026-0385"]
    assert (ctutils.package, ctutils.version) == ("ctutils", "0.4.2")
    assert ctutils.fixed_versions == (">=0.4.4",)
    assert ctutils.url == "https://github.com/RustCrypto/utils/pull/1569"
    assert by_id["RUSTSEC-2026-0410"].version == "2.0.16+zstd.1.5.7"
    assert by_id["RUSTSEC-2026-0403"].fixed_versions == (">=8.2.0",)


def test_severity_is_none_when_the_tool_printed_none_and_never_guessed() -> None:
    assert all(a.severity is None for a in parse_cargo_audit(_AUDIT))


def test_severity_is_kept_when_the_tool_printed_it() -> None:
    (found,) = parse_cargo_audit(_BLOCK)
    assert found.severity == "7.5 (high)"
    assert found.fixed_versions == ("^1.2.4", ">=2.0.0")
    assert found.kind == "vulnerability"


def test_no_safe_upgrade_means_no_fixed_versions() -> None:
    for advisory in parse_cargo_audit(_AUDIT):
        if advisory.kind != "vulnerability":
            assert advisory.fixed_versions == ()


def test_applicability_is_unknown_for_every_advisory() -> None:
    for advisory in collect_advisories([_audit(), _deny()]):
        assert advisory.applicability == APPLICABILITY_UNKNOWN == "unknown"


def test_the_database_is_named_without_a_local_path() -> None:
    (first, *_) = parse_cargo_audit(_AUDIT)
    assert "RustSec/advisory-db" in first.database
    assert "1395 advisories loaded" in first.database
    assert "/home/" not in first.database


def test_cargo_deny_advisories_are_read_and_license_errors_are_not() -> None:
    found = parse_cargo_deny(_DENY)
    assert {(a.id, a.package, a.kind) for a in found} == {
        ("RUSTSEC-2026-0374", "basic-toml", "unmaintained"),
        ("RUSTSEC-2026-0385", "ctutils", "vulnerability"),
    }
    assert all("licen" not in a.title for a in found)


def test_the_same_advisory_from_two_tools_is_one_entry_with_both_sources() -> None:
    merged = collect_advisories([_audit(), _deny()])
    assert len(merged) == 18
    ctutils = next(a for a in merged if a.id == "RUSTSEC-2026-0385")
    assert ctutils.sources == ("cargo audit", "cargo deny check")
    assert ctutils.fixed_versions == (">=0.4.4",)


def test_two_advisories_of_one_crate_stay_two_entries() -> None:
    ids = [a.id for a in collect_advisories([_audit()]) if a.package == "zstd-safe"]
    assert len(ids) == len(set(ids)) == 12


def test_the_list_is_sorted_and_independent_of_the_input_order() -> None:
    forward = collect_advisories([_audit(), _deny()])
    backward = collect_advisories([_deny(), _audit()])
    assert [a.id for a in forward] == [a.id for a in backward]
    ranks = [
        ("vulnerability", "unsound", "unmaintained").index(a.kind) for a in forward
    ]
    assert ranks == sorted(ranks)


# --- what is NOT an advisory ----------------------------------------------------


def test_a_clean_run_reports_no_advisory() -> None:
    clean = _audit(
        0, "    Scanning Cargo.lock for vulnerabilities (46 crate dependencies)\n"
    )
    assert collect_advisories([clean]) == []


def test_a_check_the_runner_could_not_execute_contributes_nothing() -> None:
    timed_out = _audit(124, _AUDIT + SENTINEL_TIMEOUT)
    missing = _audit(127, f"{SENTINEL_NOT_FOUND} cargo-audit")
    assert collect_advisories([timed_out, missing]) == []


def test_a_skipped_check_contributes_nothing() -> None:
    skipped = CommandResult(
        kind="cargo audit", returncode=0, summary="", raw_output=_AUDIT, skipped=True
    )
    assert collect_advisories([skipped]) == []


def test_a_component_relabelled_cargo_audit_is_still_read() -> None:
    assert len(collect_advisories([_audit(kind="web: cargo audit")])) == 18


def test_another_tool_is_not_parsed_as_cargo_audit() -> None:
    assert collect_advisories([_audit(kind="pip-audit")]) == []


# --- health: findings, policy violations and tool failures are different --------


def test_cargo_audit_advisories_are_a_finding_not_a_vulnerability_claim() -> None:
    health = compute_health_score(_data([_audit()]))
    assert health.breakdown["security"] == 5.0
    (message,) = health.critical_failures
    assert "Security finding reported by cargo audit" in message
    assert "exploitability is not assessed" in message
    assert "Security tool reported issues." not in health.critical_failures


def test_a_license_only_cargo_deny_failure_is_a_policy_violation() -> None:
    licenses = (
        "error[rejected]: failed to satisfy license requirements\n"
        "   ┌─ Cargo.lock:3:1\n"
    )
    health = compute_health_score(_data([_deny(4, licenses)]))
    (message,) = health.critical_failures
    assert "Dependency policy violation reported by cargo deny check" in message
    assert "not a vulnerability" in message
    assert "finding" not in message


def test_a_failure_without_a_recognised_finding_says_so() -> None:
    health = compute_health_score(
        _data([_audit(2, "error: could not parse Cargo.lock\n")])
    )
    (message,) = health.critical_failures
    assert "failed without a recognised finding" in message
    assert "finding reported" not in message


def test_a_timeout_is_not_a_security_finding() -> None:
    timed_out = _audit(124, SENTINEL_TIMEOUT)
    health = compute_health_score(_data([timed_out]))
    assert health.critical_failures == []
    assert health.breakdown["security"] == 8.0
    assert any(
        "could not run" in r and "timed out" in r for r in health.recommendations
    )


def test_a_missing_binary_is_not_a_security_finding() -> None:
    missing = _audit(127, f"{SENTINEL_NOT_FOUND} cargo-audit")
    health = compute_health_score(_data([missing, _audit(0, "ok\n", "pip-audit")]))
    assert health.critical_failures == []
    assert any("tool not found" in r for r in health.recommendations)


def test_a_real_finding_next_to_a_timeout_still_fails_the_security_category() -> None:
    timed_out = _audit(124, SENTINEL_TIMEOUT, kind="pip-audit")
    health = compute_health_score(_data([timed_out, _audit()]))
    assert health.breakdown["security"] == 5.0
    assert len(health.critical_failures) == 1


def test_the_security_weights_are_unchanged() -> None:
    clean = compute_health_score(_data([_audit(0, "ok\n")]))
    assert clean.breakdown["security"] == 15.0
    assert compute_health_score(_data([_audit()])).breakdown["security"] == 5.0


# --- risks ------------------------------------------------------------------------


def _ids(data: ReportData) -> set[str]:
    return {risk.rule_id for risk in evaluate_risks(data).risks}


def test_the_security_risk_does_not_fire_for_a_timeout_alone() -> None:
    assert "SEC-CHECK-FAILED" not in _ids(_data([_audit(124, SENTINEL_TIMEOUT)]))


def test_the_security_risk_fires_for_a_real_failure() -> None:
    assert "SEC-CHECK-FAILED" in _ids(_data([_audit()]))


# --- renderers: JSON, SARIF, Markdown ------------------------------------------------


def test_json_carries_the_advisories_at_schema_1_3() -> None:
    payload = json.loads(json_renderer.render(_data([_audit(), _deny()])))
    assert payload["schema_version"] == "1.3"
    assert len(payload["advisories"]) == 18
    first = payload["advisories"][0]
    assert first["severity"] is None
    assert first["applicability"] == "unknown"
    assert first["sources"] == ["cargo audit", "cargo deny check"]


def test_json_has_no_advisories_key_when_none_was_reported() -> None:
    payload = json.loads(json_renderer.render(_data([_audit(0, "ok\n")])))
    assert "advisories" not in payload


def _sarif(data: ReportData) -> dict:
    return json.loads(sarif.render(data))["runs"][0]


def test_sarif_has_one_result_per_advisory_with_its_id_as_rule() -> None:
    run = _sarif(_data([_audit(), _deny()]))
    advisory_results = [r for r in run["results"] if r["ruleId"].startswith("RUSTSEC-")]
    assert len(advisory_results) == 18
    assert len({r["ruleId"] for r in advisory_results}) == 18
    sample = next(r for r in advisory_results if r["ruleId"] == "RUSTSEC-2026-0391")
    props = sample["properties"]
    assert (props["package"], props["version"]) == ("zstd", "0.13.3")
    assert props["fixedVersions"] == [">=0.14.3"]
    assert props["severity"] is None
    assert props["applicability"] == "unknown"
    rule = next(
        r for r in run["tool"]["driver"]["rules"] if r["id"] == "RUSTSEC-2026-0391"
    )
    assert rule["helpUri"] == "https://rustsec.org/advisories/RUSTSEC-2026-0391"


def test_sarif_no_longer_repeats_the_anonymous_warning_lines() -> None:
    texts = [r["message"]["text"] for r in _sarif(_data([_audit()]))["results"]]
    assert not [t for t in texts if t.startswith("Warning:")]
    assert "error: 5 vulnerabilities found!" in texts


def test_sarif_keeps_the_warning_lines_when_nothing_was_parsed() -> None:
    data = _data([_audit()], advisories=False)
    texts = [r["message"]["text"] for r in _sarif(data)["results"]]
    assert len([t for t in texts if t.startswith("Warning:")]) == 13


def test_sarif_points_at_the_real_repository() -> None:
    driver = _sarif(_data([_audit(0, "ok\n")]))["tool"]["driver"]
    assert driver["informationUri"] == SARAND_INFO_URI
    assert "example" not in driver["informationUri"]


def test_sarif_levels_do_not_hide_unknown_severity() -> None:
    results = {r["ruleId"]: r for r in _sarif(_data([_audit()]))["results"]}
    assert results["RUSTSEC-2026-0391"]["level"] == "warning"
    assert results["RUSTSEC-2026-0374"]["level"] == "note"


def test_markdown_lists_every_advisory_with_the_caveat() -> None:
    output = markdown.render(_data([_audit(), _deny()]), include_source=False)
    assert "## Dependency advisories" in output
    assert "18 advisory(ies) reported" in output
    assert "not proof that this project is exploitable" in output
    assert (
        "| RUSTSEC-2026-0385 | ctutils | 0.4.2 | vulnerability | - | >=0.4.4 |"
        in output
    )
    assert output.count("| unknown |") == 18


def test_markdown_lists_advisories_even_when_the_check_passed() -> None:
    warnings_only = _BLOCK.replace(
        "Severity:  7.5 (high)\n", "Warning:   unmaintained\n"
    )
    output = markdown.render(_data([_audit(0, warnings_only)]), include_source=False)
    assert "## Dependency advisories" in output
    assert "| RUSTSEC-2099-0001 | demo | 1.2.3 | unmaintained |" in output


def test_markdown_has_no_section_without_advisories() -> None:
    output = markdown.render(_data([_audit(0, "ok\n")]), include_source=False)
    assert "## Dependency advisories" not in output
