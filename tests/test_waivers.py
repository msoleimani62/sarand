"""Findings baseline, slice F3: the waivers.

What these tests defend (decisions of 2026-11-24, `docs/R14D1_PLAN.md` section 3.2):
a waiver has a scope, a reason, an owner, a creation date and an end date and is invalid
without them; an expired waiver suppresses nothing; a broad (`rule`) waiver cannot
silently cover a later, different finding; every applied waiver stays visible; and
anything wrong in the file is an error, never ignored.

waiverها (قطعه‌ی F3): هر waiver دامنه، دلیل، مالک، تاریخ ایجاد و پایان دارد؛ waiver منقضی
هیچ چیزی را مهار نمی‌کند؛ waiver گسترده (`rule`) نمی‌تواند بی‌صدا یافته‌ی بعدیِ متفاوت را
بپوشاند؛ هر waiver اعمال‌شده دیده می‌شود؛ هر چیز نادرست در فایل خطاست.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sarand.core import baseline as bl
from sarand.core import gate as g
from sarand.core import waivers as w
from sarand.core.finding_identity import KIND_SECRETS, finding_id

TODAY = date(2026, 11, 27)
ID_A = "dependency_advisory:0123456789ab"
# Built at run time: gitleaks flags a literal named like a secret that holds an
# id-shaped value (the id is a hash, not a credential).
# در زمان اجرا ساخته می‌شود: gitleaks literal با نام شبیه secret و مقدار شبیه شناسه را
# پرچم می‌زند (شناسه hash است، نه credential).


def _cat(*parts: str) -> str:
    return "".join(parts)


ID_B = _cat("hardcoded_secrets:", "ba9876543210")


def _toml(*tables: str) -> str:
    return "\n".join(tables)


def _waiver_toml(**fields: str) -> str:
    base = {
        "id": f'"{ID_A}"',
        "reason": '"not reachable from our code"',
        "owner": '"alice"',
        "created": "2026-11-01",
        "expires": "2026-12-31",
    }
    base.update(fields)
    base = {k: v for k, v in base.items() if v != ""}
    return "[[waivers]]\n" + "\n".join(f"{k} = {v}" for k, v in base.items()) + "\n"


def _parse(text: str, today: date = TODAY) -> tuple[w.Waiver, ...]:
    return w.parse_waivers(text, today)


# ---------------------------------------------------------------------- reading


def test_a_valid_id_waiver_and_a_valid_rule_waiver_are_read() -> None:
    text = _toml(
        _waiver_toml(reference='"https://example.org/1"'),
        _waiver_toml(
            id="",
            rule='"advisories:RUSTSEC-2024-0001"',
            covers="2",
        ),
    )
    first, second = _parse(text)
    assert (first.number, first.scope, first.target) == (1, "id", ID_A)
    assert first.owner == "alice" and first.reference == "https://example.org/1"
    assert first.created == date(2026, 11, 1) and first.expires == date(2026, 12, 31)
    assert first.covers is None
    assert (second.number, second.scope, second.covers) == (2, "rule", 2)
    assert second.target == "advisories:RUSTSEC-2024-0001"
    assert second.reference is None
    assert first.summary()["expires"] == "2026-12-31"


def test_no_file_or_no_waivers_table_means_no_waivers(tmp_path: Path) -> None:
    assert w.load_waivers(tmp_path, TODAY) == ()
    (tmp_path / ".sarand.toml").write_text('[secrets]\nfixture_paths = ["a"]\n')
    assert w.load_waivers(tmp_path, TODAY) == ()


def test_other_tables_of_the_shared_file_do_not_disturb_the_waivers(
    tmp_path: Path,
) -> None:
    (tmp_path / ".sarand.toml").write_text(
        '[secrets]\nfixture_paths = ["a"]\n\n' + _waiver_toml(), encoding="utf-8"
    )
    assert [x.target for x in w.load_waivers(tmp_path, TODAY)] == [ID_A]


def test_load_names_the_file_in_an_error(tmp_path: Path) -> None:
    (tmp_path / ".sarand.toml").write_text("[[waivers]]\nbad = 1\n", encoding="utf-8")
    with pytest.raises(w.WaiverError, match=r"\.sarand\.toml: \[\[waivers\]\] #1"):
        w.load_waivers(tmp_path, TODAY)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (_waiver_toml(rule='"secrets:x"', covers="1"), "exactly one of"),
        (_waiver_toml(id=""), "exactly one of"),
        (_waiver_toml(id='"nonsense"'), "not a finding id"),
        (_waiver_toml(id="", rule='"nothing"', covers="1"), "<class>:<family>"),
        (_waiver_toml(id="", rule='"bogus:x"', covers="1"), "<class>:<family>"),
        (_waiver_toml(id="", rule='"secrets:"', covers="1"), "<class>:<family>"),
        (_waiver_toml(id="", rule='"secrets:x"'), "must declare `covers`"),
        (_waiver_toml(covers="1"), "only for a `rule`"),
        (_waiver_toml(id="", rule='"secrets:x"', covers="0"), "at least 1"),
        (_waiver_toml(id="", rule='"secrets:x"', covers="true"), "at least 1"),
        (_waiver_toml(id="", rule='"secrets:x"', covers='"2"'), "at least 1"),
        (_waiver_toml(reason='""'), "`reason` must be"),
        (_waiver_toml(reason=""), "`reason` must be"),
        (_waiver_toml(owner='"  "'), "`owner` must be"),
        (_waiver_toml(owner=""), "`owner` must be"),
        (_waiver_toml(created='"2026-11-01"'), "must be a date"),
        (_waiver_toml(created="2026-11-01T10:00:00"), "must be a date"),
        (_waiver_toml(expires=""), "`expires` is required"),
        (_waiver_toml(created="2026-12-01"), "is in the future"),
        (_waiver_toml(expires="2026-10-31"), "before `created`"),
        (_waiver_toml(created="2025-11-01", expires="2026-11-03"), "at most 366"),
        (_waiver_toml(reference='""'), "`reference` must be"),
        (_waiver_toml(extra="1"), "unknown key"),
        ("waivers = 3\n", "array of tables"),
        ("waivers = [1]\n", "must be a table"),
        ("[[waivers]\n", "invalid TOML"),
    ],
)
def test_everything_wrong_in_the_file_is_an_error(text: str, message: str) -> None:
    with pytest.raises(w.WaiverError, match=message):
        _parse(text)


def test_lifetime_and_date_boundaries_are_inclusive() -> None:
    same = _waiver_toml(created="2026-11-27", expires="2026-11-27")
    assert _parse(same)[0].expires == TODAY  # created today, expires today
    longest = _waiver_toml(created="2025-11-27", expires="2026-11-28")
    assert _parse(longest)  # exactly 366 days


def test_the_same_scope_twice_is_ambiguous() -> None:
    twice = _waiver_toml() + _waiver_toml(owner='"bob"')
    with pytest.raises(w.WaiverError, match="already waived by #1"):
        _parse(twice)


# --------------------------------------------------------------------- applying


def _item(
    name: str = "secrets", fid: str = ID_B, family: str = "AWS Access Key ID"
) -> dict[str, Any]:
    return {
        "class": name,
        "id": fid,
        "state": "new",
        "rule": "new_finding",
        "label": f"{name} {family}",
        "family": family,
    }


def _make(
    number: int = 1,
    scope: str = "id",
    target: str = ID_B,
    expires: date = date(2026, 12, 31),
    covers: int | None = None,
) -> w.Waiver:
    return w.Waiver(
        number=number,
        scope=scope,
        target=target,
        reason="because",
        owner="alice",
        created=date(2026, 11, 1),
        expires=expires,
        covers=covers,
    )


def test_an_id_waiver_covers_exactly_that_finding_and_keeps_it_visible() -> None:
    kept, covered = _item(fid="hardcoded_secrets:000000000001"), _item()
    out = w.apply_waivers([kept, covered], [_make()], TODAY)
    assert out.remaining == [kept]
    assert len(out.waived) == 1 and out.waived[0]["id"] == ID_B
    assert out.waived[0]["waiver"]["owner"] == "alice"
    assert out.expired == out.unused == out.exceeded == []


def test_an_expired_waiver_suppresses_nothing_and_says_how_much_it_would_have() -> None:
    out = w.apply_waivers([_item()], [_make(expires=date(2026, 11, 26))], TODAY)
    assert out.waived == [] and len(out.remaining) == 1
    assert [(e["number"], e["matches"]) for e in out.expired] == [(1, 1)]
    assert out.unused == []  # it is expired, not merely unused


def test_the_expiry_day_itself_is_still_active() -> None:
    out = w.apply_waivers([_item()], [_make(expires=TODAY)], TODAY)
    assert len(out.waived) == 1 and out.expired == []


def test_a_rule_waiver_covers_up_to_its_declared_number() -> None:
    items = [_item(fid=f"hardcoded_secrets:00000000000{i}") for i in (1, 2)]
    exact = _make(scope="rule", target="secrets:AWS Access Key ID", covers=2)
    out = w.apply_waivers(items, [exact], TODAY)
    assert out.remaining == [] and len(out.waived) == 2


def test_a_rule_waiver_with_more_matches_than_declared_covers_none() -> None:
    # The later, different finding must not be swallowed by the old waiver.
    # یافته‌ی بعدیِ متفاوت نباید توسط waiver قدیمی بلعیده شود.
    items = [_item(fid=f"hardcoded_secrets:00000000000{i}") for i in (1, 2)]
    broad = _make(scope="rule", target="secrets:AWS Access Key ID", covers=1)
    out = w.apply_waivers(items, [broad], TODAY)
    assert out.waived == [] and len(out.remaining) == 2
    assert [(e["matches"], e["covers"]) for e in out.exceeded] == [(2, 1)]


def test_a_rule_names_the_class_as_well_as_the_family() -> None:
    advisory = _item("advisories", "dependency_advisory:00000000000a", "X-1")
    other = _make(scope="rule", target="secrets:X-1", covers=1)
    assert w.apply_waivers([advisory], [other], TODAY).waived == []
    right = _make(scope="rule", target="advisories:X-1", covers=1)
    assert len(w.apply_waivers([advisory], [right], TODAY).waived) == 1


def test_a_waiver_that_matches_nothing_is_reported_as_unused() -> None:
    out = w.apply_waivers([_item()], [_make(target=ID_A)], TODAY)
    assert [u["number"] for u in out.unused] == [1] and len(out.remaining) == 1


def test_the_first_waiver_in_the_file_wins_and_the_second_is_unused() -> None:
    first = _make(1, "id", ID_B)
    second = _make(2, "rule", "secrets:AWS Access Key ID", covers=1)
    out = w.apply_waivers([_item()], [first, second], TODAY)
    assert [x["waiver"]["number"] for x in out.waived] == [1]
    assert [u["number"] for u in out.unused] == [2]


def test_applying_waivers_does_not_change_its_input() -> None:
    items = [_item()]
    before = json.dumps(items, sort_keys=True)
    w.apply_waivers(items, [_make()], TODAY)
    assert json.dumps(items, sort_keys=True) == before


# ------------------------------------------------------------- through the gate


def _report(**over: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema_version": "1.12",
        "failures": [],
        "advisories": [],
        "secret_findings": [],
        "test_results": [],
        "quality_results": [],
        "security_results": [],
        "included_files": ["a.py", "b.py", "conf.py", "other.py"],
        "skipped_files": [],
        "excluded_secret_files": [],
        "health": {},
    }
    data.update(over)
    return data


def _secret(path: str = "conf.py") -> dict[str, Any]:
    return {"path": path, "line_number": 3, "pattern_name": "AWS Access Key ID"}


def _gate(
    policy: str,
    current: dict[str, Any],
    waivers: tuple[w.Waiver, ...] = (),
    reference: dict[str, Any] | None = None,
) -> dict[str, Any]:
    old = bl.read_report_view(reference or _report())
    new = bl.read_report_view(current)
    return g.evaluate_gate(
        policy, old, new, bl.compare_findings(old, new), waivers, TODAY
    )


def _secret_id(path: str = "conf.py") -> str:
    return finding_id(KIND_SECRETS, path, "AWS Access Key ID")


def test_a_waived_failure_passes_the_gate_and_stays_listed() -> None:
    waiver = _make(target=_secret_id())
    result = _gate("new", _report(secret_findings=[_secret()]), (waiver,))
    assert result["verdict"] == "pass" and result["failed_on"] == []
    assert [i["id"] for i in result["waived"]] == [_secret_id()]
    assert result["waived"][0]["waiver"]["number"] == 1


def test_a_waiver_for_one_finding_does_not_pass_another() -> None:
    waiver = _make(target=_secret_id("conf.py"))
    current = _report(secret_findings=[_secret("conf.py"), _secret("other.py")])
    result = _gate("new", current, (waiver,))
    assert result["verdict"] == "fail"
    assert [i["id"] for i in result["failed_on"]] == [_secret_id("other.py")]


def test_the_core_scenario_a_later_finding_breaks_a_one_finding_rule_waiver() -> None:
    rule = _make(scope="rule", target="secrets:AWS Access Key ID", covers=1)
    first = _gate("new", _report(secret_findings=[_secret("a.py")]), (rule,))
    assert first["verdict"] == "pass"
    later = _report(secret_findings=[_secret("a.py"), _secret("b.py")])
    second = _gate("new", later, (rule,))
    assert second["verdict"] == "fail" and len(second["failed_on"]) == 2
    assert second["waivers"]["exceeded"][0]["number"] == 1


def test_an_expired_waiver_makes_the_gate_fail_again() -> None:
    expired = _make(target=_secret_id(), expires=date(2026, 11, 20))
    result = _gate("new", _report(secret_findings=[_secret()]), (expired,))
    assert result["verdict"] == "fail"
    assert result["waivers"]["expired"][0]["matches"] == 1


def test_uncertain_findings_are_never_waived_and_never_fail() -> None:
    # A finding the reference could not see is uncertain; a waiver aimed at it is unused.
    # یافته‌ای که مرجع نمی‌دید uncertain است؛ waiver برای آن بی‌استفاده می‌ماند.
    reference = _report(skipped_files=[["big.py", 99]])
    current = _report(secret_findings=[_secret("big.py")])
    waiver = _make(target=_secret_id("big.py"))
    result = _gate("new", current, (waiver,), reference)
    assert result["verdict"] == "pass" and result["waived"] == []
    assert len(result["uncertain"]) == 1
    assert [u["number"] for u in result["waivers"]["unused"]] == [1]


def test_waivers_work_under_critical_for_an_old_finding() -> None:
    both = _report(secret_findings=[_secret()])
    waiver = _make(target=_secret_id())
    result = _gate("critical", both, (waiver,), reference=both)
    assert result["verdict"] == "pass" and len(result["waived"]) == 1


def test_never_ignores_waivers_and_reports_the_date() -> None:
    result = _gate("never", _report(), (_make(),))
    assert result["verdict"] == "not_gated" and result["waived"] == []
    assert result["waivers"]["as_of"] == "2026-11-27"


def test_the_date_is_an_input_when_there_are_waivers() -> None:
    old = bl.read_report_view(_report())
    with pytest.raises(ValueError, match="today"):
        g.evaluate_gate("new", old, old, bl.compare_findings(old, old), (_make(),))


def test_the_family_of_every_class_is_what_a_rule_names() -> None:
    reference = _report(
        test_results=[
            {"kind": "pytest", "returncode": 0, "summary": "", "state": "passed"}
        ],
        security_results=[
            {"kind": "cargo audit", "returncode": 0, "summary": "", "state": "passed"}
        ],
    )
    current = _report(
        secret_findings=[_secret()],
        advisories=[
            {
                "id": "RUSTSEC-2024-0001",
                "package": "p",
                "version": "1",
                "severity": "critical",
                "fixed_versions": [],
                "sources": ["cargo audit"],
            }
        ],
        security_results=[
            {"kind": "cargo audit", "returncode": 0, "summary": "", "state": "passed"}
        ],
    )
    result = _gate("new", current, reference=reference)
    families = {(i["class"], i["family"]) for i in result["failed_on"]}
    assert families == {
        ("secrets", "AWS Access Key ID"),
        ("advisories", "RUSTSEC-2024-0001"),
    }


def test_a_condition_family_is_its_kind() -> None:
    both = _report(health={"critical_ids": ["broken_symlinks:eeeeeeeeeeee"]})
    result = _gate("critical", both, reference=both)
    assert [(i["class"], i["family"]) for i in result["failed_on"]] == [
        ("failures", "broken_symlinks")
    ]
    rule = _make(scope="rule", target="failures:broken_symlinks", covers=1)
    waived = _gate("critical", both, (rule,), reference=both)
    assert waived["verdict"] == "pass" and len(waived["waived"]) == 1
