"""Findings baseline, slice F4: SARIF fingerprints and a structural validity check.

What these tests defend (`docs/R14D1_PLAN.md`, section 3.2): a SARIF result carries the
finding id, the same one the findings baseline and the gate print, as
`partialFingerprints`; the id has no line number, so a finding that only moves keeps its
identity; several secrets of one pattern in one file stay distinguishable; rule ids are
stable and declared; level and severity are untouched; and every SARIF log sarand builds
holds the structure of SARIF 2.1.0 that code-scanning tools rely on.

قطعه‌ی F4: نتیجه‌ی SARIF شناسه‌ی یافته (همان که baseline و gate چاپ می‌کنند) را به‌صورت
`partialFingerprints` دارد؛ شناسه شماره‌ی خط ندارد؛ چند secret از یک الگو جدا می‌مانند؛
شناسه‌ی قاعده پایدار و تعریف‌شده است؛ level و severity دست‌نخورده‌اند.
"""

from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from _golden_fixtures import FIXTURES
from sarand.core import baseline as bl
from sarand.core.finding_identity import KIND_SECRETS, finding_id
from sarand.models.results import ReportData, SecretFinding
from sarand.renderers import sarif

_LEVELS = {"none", "note", "warning", "error"}
_KEY = re.compile(r"^[A-Za-z0-9]+/v[0-9]+$")
ID = "sarandFindingId/v1"
OCCURRENCE = "sarandOccurrence/v1"


@contextmanager
def _fixture(name: str) -> Iterator[ReportData]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "p"
        root.mkdir()
        yield FIXTURES[name](root)


def _render(data: ReportData) -> dict[str, Any]:
    return json.loads(sarif.render(data))


def _secret_results(log: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        r
        for r in log["runs"][0]["results"]
        if r["ruleId"].startswith("secret-detection/")
    ]


def _secrets(*items: tuple[str, int, str]) -> list[SecretFinding]:
    return [SecretFinding(path=p, line_number=n, pattern_name=k) for p, n, k in items]


def _by_line(results: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, str]]:
    return {
        (
            r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"],
            r["locations"][0]["physicalLocation"]["region"]["startLine"],
        ): r["partialFingerprints"]
        for r in results
    }


# ----------------------------------------------------------------- the fingerprints


def test_a_secret_result_carries_the_id_the_baseline_and_the_gate_print() -> None:
    with _fixture("hybrid") as data:
        results = _secret_results(_render(data))
        assert results, "the fixture has secret findings"
        view = bl.current_view(
            schema=(1, 12),
            failures=data.failures,
            advisories=data.advisories,
            secret_findings=data.secret_findings,
            test_results=data.test_results,
            quality_results=data.quality_results,
            security_results=data.security_results,
            included_files=[],
            excluded_secret_files=[],
            skipped_files=[],
        )
        got = {r["partialFingerprints"][ID] for r in results}
        assert got == set(view.secrets)
        assert all(i.startswith(f"{KIND_SECRETS}:") for i in got)


def test_the_id_has_no_line_number_so_a_moved_finding_keeps_its_identity() -> None:
    with _fixture("minimal") as data:
        data.secret_findings = _secrets(("src/a.py", 3, "AWS Access Key ID"))
        before = _secret_results(_render(data))[0]["partialFingerprints"]
        data.secret_findings = _secrets(("src/a.py", 97, "AWS Access Key ID"))
        after = _secret_results(_render(data))[0]["partialFingerprints"]
        assert before == after
        assert before[ID] == finding_id(KIND_SECRETS, "src/a.py", "AWS Access Key ID")


def test_another_path_or_another_pattern_is_another_finding() -> None:
    with _fixture("minimal") as data:
        data.secret_findings = _secrets(
            ("a.py", 1, "AWS Access Key ID"),
            ("b.py", 1, "AWS Access Key ID"),
            ("a.py", 1, "GitHub Personal Access Token"),
        )
        ids = [r["partialFingerprints"][ID] for r in _secret_results(_render(data))]
        assert len(ids) == len(set(ids)) == 3


def test_several_secrets_of_one_pattern_in_one_file_are_told_apart_by_line_order() -> (
    None
):
    lines = (40, 7, 22)  # deliberately not in line order in the report
    with _fixture("minimal") as data:
        data.secret_findings = _secrets(*[("k.py", n, "Generic Secret") for n in lines])
        results = _secret_results(_render(data))
        pairs = {
            (r["partialFingerprints"][ID], r["partialFingerprints"][OCCURRENCE])
            for r in results
        }
        assert len(pairs) == 3 and len({i for i, _ in pairs}) == 1
        by_line = {line: fp[OCCURRENCE] for (_, line), fp in _by_line(results).items()}
        assert by_line == {7: "1", 22: "2", 40: "3"}
        # the results keep the order of the report
        assert [
            r["locations"][0]["physicalLocation"]["region"]["startLine"]
            for r in results
        ] == list(lines)


def test_the_fingerprints_do_not_depend_on_the_order_of_the_report() -> None:
    items = [("a.py", 5, "T"), ("a.py", 9, "T"), ("b.py", 2, "U")]
    with _fixture("minimal") as data:
        data.secret_findings = _secrets(*items)
        first = _by_line(_secret_results(_render(data)))
        data.secret_findings = _secrets(*reversed(items))
        second = _by_line(_secret_results(_render(data)))
        assert first == second


def test_rendering_twice_gives_the_same_log() -> None:
    with _fixture("hybrid") as data:
        assert sarif.render(data) == sarif.render(data)


def test_level_and_severity_are_not_touched_by_the_fingerprints() -> None:
    with _fixture("hybrid") as data:
        results = _render(data)["runs"][0]["results"]
        assert {
            r["level"] for r in _secret_results({"runs": [{"results": results}]})
        } == {"error"}
        assert all("severity" not in r for r in results)  # SARIF has `level` only
    with _fixture("advisories") as data:
        advisory = [
            r
            for r in _render(data)["runs"][0]["results"]
            if "package" in r.get("properties", {})
        ]
        assert advisory, "the fixture has advisory results"
        for result in advisory:
            # the upstream severity stays in the property bag and is not folded into level
            assert "severity" in result["properties"]
            assert result["level"] in {"note", "warning"}


# -------------------------------------------------------------- structural validity


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_every_fixture_log_holds_the_sarif_2_1_0_structure(name: str) -> None:
    with _fixture(name) as data:
        log = _render(data)
    assert log["version"] == "2.1.0"
    assert log["$schema"].endswith("sarif-schema-2.1.0.json")
    (run,) = log["runs"]
    driver = run["tool"]["driver"]
    assert driver["name"] == "sarand" and driver["informationUri"].startswith(
        "https://"
    )
    rule_ids = [r["id"] for r in driver["rules"]]
    assert len(rule_ids) == len(set(rule_ids)), "rule ids are unique"
    seen: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
    for result in run["results"]:
        assert result["ruleId"] in rule_ids, "every used rule is declared"
        assert result["level"] in _LEVELS
        assert isinstance(result["message"]["text"], str) and result["message"]["text"]
        for location in result.get("locations", []):
            physical = location["physicalLocation"]
            assert isinstance(physical["artifactLocation"]["uri"], str)
            assert physical["region"]["startLine"] >= 1
        fingerprints = result.get("partialFingerprints")
        if fingerprints is None:
            continue
        for key, value in fingerprints.items():
            assert _KEY.match(key), f"{key!r} should look like name/vN"
            assert isinstance(value, str) and value
        assert ID in fingerprints
        identity = (result["ruleId"], tuple(sorted(fingerprints.items())))
        assert identity not in seen, "a rule and its fingerprints name one result"
        seen.add(identity)


def test_rule_ids_are_derived_from_the_name_and_do_not_depend_on_the_data_order() -> (
    None
):
    with _fixture("minimal") as data:
        data.secret_findings = _secrets(
            ("a.py", 1, "AWS Access Key ID"),
            ("b.py", 2, "GitHub Personal Access Token"),
        )
        wanted = {
            "secret-detection/aws-access-key-id",
            "secret-detection/github-personal-access-token",
        }
        first = {r["id"] for r in _render(data)["runs"][0]["tool"]["driver"]["rules"]}
        data.secret_findings = list(reversed(data.secret_findings))
        second = {r["id"] for r in _render(data)["runs"][0]["tool"]["driver"]["rules"]}
        assert first == second == wanted
    with _fixture("advisories") as data:
        rules = {r["id"] for r in _render(data)["runs"][0]["tool"]["driver"]["rules"]}
        assert {
            a.id for a in data.advisories
        } <= rules  # an advisory's rule is its own id
