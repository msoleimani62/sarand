"""Gate: turn the findings comparison into a pass or a fail for a pipeline
(R14-D1, slice F2; contract in docs/FINDINGS_BASELINE.md, "Gate and exit codes").

The comparison (`core/baseline.py`) says what is new, fixed, unchanged, changed or not
checked. The gate adds one decision on top of it, chosen by `--baseline-gate`:

- `never`         the default: a baseline changes no exit code (`not_gated`);
- `new`           a new valid finding fails the gate;
- `new-critical`  a new Critical finding fails the gate;
- `critical`      any Critical finding, new or old, fails the gate.

**What is Critical** (one definition for `new-critical` and `critical`; explicit, never
guessed from a summary, a message or a tool name):

- a secret finding is Critical when it is *valid*, that is not a test fixture (the flag
  comes from the project's explicit `[secrets] fixture_paths`);
- an advisory is Critical only when its severity is `critical`;
- a failure is Critical only through a health critical condition (`health.critical_ids`):
  an ordinary tool failure is not. Two kinds of condition only restate the classes above
  (`hardcoded_secrets`, `security_finding_detected`) and are left to their own rules; a
  check that could not run (`test_check_unavailable`) gave no verdict and is reported as
  uncertain, not as a failure.

**What the gate never does:** it never counts `fixed`, `unchanged` or `not_checked` as
new, and it never assumes Critical when the data to decide is missing. Such cases are
listed in `uncertain` with the reason. They do not fail the gate (no false failure) and
they are never hidden (no silent pass).

The result is a plain dict stored as `baseline.gate`. This module reads views and the
comparison payload only; it never imports `sarand.structure`.

gate: نتیجه‌ی مقایسه‌ی یافته‌ها را به «قبول» یا «رد» برای pipeline تبدیل می‌کند. بحرانی بودن
صریح است و هرگز حدس زده نمی‌شود؛ داده‌ی ناکافی در `uncertain` می‌آید، نه رد می‌کند و نه پنهان
می‌ماند.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from sarand.constants import FAILURE_DEPENDENCY_POLICY, FAILURE_SECURITY_TOOL
from sarand.core.baseline import (
    CLASS_ADVISORIES,
    CLASS_FAILURES,
    CLASS_SECRETS,
    CLASSES,
    SEVERITY_CRITICAL,
    SEVERITY_OTHER,
    SEVERITY_UNKNOWN,
    STATE_NEW,
    STATE_NOT_CHECKED,
    STATE_UNCHANGED,
    FindingsView,
    severity_class,
)
from sarand.core.failures import GROUP_TEST
from sarand.core.finding_identity import KIND_SECRETS, KIND_TEST_UNAVAILABLE

# Exit codes of the command (the owner's decision of 2026-11-24). Other paths keep
# theirs; a baseline error is never confused with a gate failure.
# کدهای خروج فرمان (تصمیم مالک، ۲۰۲۶-۱۱-۲۴). خطای baseline هرگز با شکست gate اشتباه نمی‌شود.
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_GATE_FAILED = 3
EXIT_BASELINE_UNUSABLE = 4

POLICY_NEVER = "never"
POLICY_NEW = "new"
POLICY_NEW_CRITICAL = "new-critical"
POLICY_CRITICAL = "critical"
POLICIES: tuple[str, ...] = (
    POLICY_NEVER,
    POLICY_NEW,
    POLICY_NEW_CRITICAL,
    POLICY_CRITICAL,
)

VERDICT_NOT_GATED = "not_gated"
VERDICT_OK = "pass"
VERDICT_FAIL = "fail"

# Rules (why a finding failed the gate) and reasons (why it is uncertain).
# قاعده‌ها (چرا یافته gate را رد کرد) و دلیل‌ها (چرا نامعلوم است).
RULE_NEW_FINDING = "new_finding"
RULE_CRITICAL_LEAK = "critical_secret"
RULE_CRITICAL_ADVISORY = "critical_advisory"
RULE_CRITICAL_CONDITION = "critical_condition"
REASON_SEVERITY_UNKNOWN = "severity_unknown"
REASON_HEALTH_NOT_COMPUTED = "health_not_computed"
REASON_NO_CRITICAL_IDS_IN_REFERENCE = "reference_has_no_critical_ids"
REASON_CHECK_NO_VERDICT = "check_unavailable_no_verdict"
REASON_NOT_CHECKED_FALLBACK = "not_checked"

STATE_EXISTING = "existing"

# Condition kinds that only restate another class (see the module text). The kind is
# the part of a condition id before the colon.
# انواع شرطی که فقط دسته‌ی دیگری را تکرار می‌کنند؛ نوع بخشِ پیش از «:» در شناسه است.
RESTATED_KINDS: frozenset[str] = frozenset({KIND_SECRETS, "security_finding_detected"})

# A condition id hashes a SET of tools, so it changes when that set changes (a suite that
# was fixed leaves a smaller set, which is a different id and not a new problem). For the
# kinds below a new condition therefore counts only when a failure of the matching kind
# is `new` in the comparison, which already requires that the reference ran the check.
# شناسه‌ی شرط روی یک مجموعه ابزار ساخته می‌شود و با تغییر آن مجموعه عوض می‌شود (رفع یک suite
# مجموعه‌ی کوچک‌تر و شناسه‌ی دیگری می‌دهد، نه مشکل جدید). پس برای انواع زیر شرط جدید فقط وقتی
# حساب می‌شود که شکستی از نوع متناظر در مقایسه `new` باشد (که خودش اجرای چک در مرجع را می‌طلبد).
_BACKING: dict[str, Callable[[Mapping[str, Any]], bool]] = {
    "test_suite_failed": lambda e: e.get("group") == GROUP_TEST,
    FAILURE_DEPENDENCY_POLICY: lambda e: e.get("category") == FAILURE_DEPENDENCY_POLICY,
    FAILURE_SECURITY_TOOL: lambda e: e.get("category") == FAILURE_SECURITY_TOOL,
}


def condition_kind(condition_id: str) -> str:
    """The kind of a health condition id (`<kind>:<12 hex>`)."""
    return condition_id.partition(":")[0]


def _label(name: str, item: Mapping[str, Any]) -> str:
    if name == CLASS_FAILURES:
        return f"{item['tool']} {item['category']} {item['subject']}".strip()
    if name == CLASS_ADVISORIES:
        return f"{item['advisory_id']} {item['package']} {item['version']}".strip()
    return f"{item['path']} ({item['pattern_name']})"


def _condition_label(condition_id: str) -> str:
    return f"health critical condition {condition_id}"


def _failed(name: str, fid: str, state: str, rule: str, label: str) -> dict[str, Any]:
    return {"class": name, "id": fid, "state": state, "rule": rule, "label": label}


def _uncertain(name: str, fid: str, reason: str, label: str) -> dict[str, Any]:
    return {"class": name, "id": fid, "reason": reason, "label": label}


class _Gate:
    """The state of one evaluation (the lists it fills and the data it reads)."""

    def __init__(
        self,
        policy: str,
        reference: FindingsView,
        current: FindingsView,
        comparison: Mapping[str, Any],
    ) -> None:
        self.policy = policy
        self.reference = reference
        self.current = current
        self.entries: dict[str, dict[str, Mapping[str, Any]]] = {
            name: {str(e["id"]): e for e in comparison["findings"].get(name, [])}
            for name in CLASSES
        }
        self.failed: list[dict[str, Any]] = []
        self.uncertain: list[dict[str, Any]] = []

    def state(self, name: str, fid: str) -> tuple[str, str]:
        """The comparison state of a finding of the current run and its reason."""
        entry = self.entries[name].get(fid)
        if entry is None:
            return STATE_UNCHANGED, ""
        return str(entry["state"]), str(entry.get("reason", ""))

    # ----------------------------------------------------------------- secrets

    def secrets(self) -> None:
        for fid, item in sorted(self.current.secrets.items()):
            if fid in self.current.fixture_secrets:
                continue  # a fixture is never valid, so never Critical
            state, reason = self.state(CLASS_SECRETS, fid)
            label = _label(CLASS_SECRETS, item)
            if self.policy == POLICY_CRITICAL:
                self.failed.append(
                    _failed(CLASS_SECRETS, fid, state, RULE_CRITICAL_LEAK, label)
                )
            elif state == STATE_NEW:
                # Under `new-critical` the finding fails because it is Critical, under
                # `new` because it is new.
                # زیر `new-critical` چون بحرانی است، زیر `new` چون جدید است.
                rule = (
                    RULE_NEW_FINDING
                    if self.policy == POLICY_NEW
                    else RULE_CRITICAL_LEAK
                )
                self.failed.append(_failed(CLASS_SECRETS, fid, state, rule, label))
            elif state == STATE_NOT_CHECKED:
                self.uncertain.append(
                    _uncertain(
                        CLASS_SECRETS, fid, reason or REASON_NOT_CHECKED_FALLBACK, label
                    )
                )

    # -------------------------------------------------------------- advisories

    def advisories(self) -> None:
        for fid, item in sorted(self.current.advisories.items()):
            state, reason = self.state(CLASS_ADVISORIES, fid)
            label = _label(CLASS_ADVISORIES, item)
            level = severity_class(item["severity"])
            if self.policy == POLICY_NEW:
                if state == STATE_NEW:
                    self.failed.append(
                        _failed(CLASS_ADVISORIES, fid, state, RULE_NEW_FINDING, label)
                    )
                elif state == STATE_NOT_CHECKED:
                    self.uncertain.append(
                        _uncertain(
                            CLASS_ADVISORIES,
                            fid,
                            reason or REASON_NOT_CHECKED_FALLBACK,
                            label,
                        )
                    )
            elif self.policy == POLICY_CRITICAL:
                if level == SEVERITY_CRITICAL:
                    self.failed.append(
                        _failed(
                            CLASS_ADVISORIES, fid, state, RULE_CRITICAL_ADVISORY, label
                        )
                    )
                elif level == SEVERITY_UNKNOWN:
                    self.uncertain.append(
                        _uncertain(
                            CLASS_ADVISORIES, fid, REASON_SEVERITY_UNKNOWN, label
                        )
                    )
            else:  # new-critical
                self._new_critical_advisory(fid, state, reason, label, level)

    def _new_critical_advisory(
        self, fid: str, state: str, reason: str, label: str, level: str
    ) -> None:
        if state == STATE_NEW:
            if level == SEVERITY_CRITICAL:
                self.failed.append(
                    _failed(CLASS_ADVISORIES, fid, state, RULE_CRITICAL_ADVISORY, label)
                )
            elif level == SEVERITY_UNKNOWN:
                self.uncertain.append(
                    _uncertain(CLASS_ADVISORIES, fid, REASON_SEVERITY_UNKNOWN, label)
                )
        elif state == STATE_NOT_CHECKED and level != SEVERITY_OTHER:
            # It would count if it were new, and the comparison cannot say.
            # اگر جدید بود حساب می‌شد و مقایسه نمی‌تواند بگوید.
            self.uncertain.append(
                _uncertain(
                    CLASS_ADVISORIES, fid, reason or REASON_NOT_CHECKED_FALLBACK, label
                )
            )

    # ---------------------------------------------------------------- failures

    def failures(self) -> None:
        if self.policy == POLICY_NEW:
            self._new_failures()
        else:
            self._critical_conditions()

    def _new_failures(self) -> None:
        for fid, entry in sorted(self.entries[CLASS_FAILURES].items()):
            if entry["state"] == STATE_NEW:
                self.failed.append(
                    _failed(
                        CLASS_FAILURES,
                        fid,
                        STATE_NEW,
                        RULE_NEW_FINDING,
                        _label(CLASS_FAILURES, entry),
                    )
                )
            elif entry["state"] == STATE_NOT_CHECKED and entry.get("new") is not None:
                self.uncertain.append(
                    _uncertain(
                        CLASS_FAILURES,
                        fid,
                        str(entry.get("reason") or REASON_NOT_CHECKED_FALLBACK),
                        _label(CLASS_FAILURES, entry),
                    )
                )

    def _backing(self, kind: str, state: str) -> list[Mapping[str, Any]]:
        match = _BACKING[kind]
        return [
            e
            for e in self.entries[CLASS_FAILURES].values()
            if e["state"] == state and e.get("new") is not None and match(e)
        ]

    def _critical_conditions(self) -> None:
        conditions = self.current.conditions
        if conditions is None:
            self.uncertain.append(
                _uncertain(
                    CLASS_FAILURES,
                    "",
                    REASON_HEALTH_NOT_COMPUTED,
                    "health critical conditions",
                )
            )
            return
        known = self.reference.conditions
        every = self.policy == POLICY_CRITICAL
        for cid in sorted(conditions):
            kind = condition_kind(cid)
            if kind in RESTATED_KINDS:
                continue
            if kind == KIND_TEST_UNAVAILABLE:
                if every or known is None or cid not in known:
                    self.uncertain.append(
                        _uncertain(
                            CLASS_FAILURES,
                            cid,
                            REASON_CHECK_NO_VERDICT,
                            _condition_label(cid),
                        )
                    )
                continue
            if kind in _BACKING:
                self._backed_condition(cid, kind, every)
            else:
                self._unbacked_condition(cid, every, known)

    def _backed_condition(self, cid: str, kind: str, every: bool) -> None:
        fresh = self._backing(kind, STATE_NEW)
        if every or fresh:
            self.failed.append(
                _failed(
                    CLASS_FAILURES,
                    cid,
                    STATE_NEW if fresh else STATE_EXISTING,
                    RULE_CRITICAL_CONDITION,
                    _condition_label(cid),
                )
            )
            return
        for entry in self._backing(kind, STATE_NOT_CHECKED):
            self.uncertain.append(
                _uncertain(
                    CLASS_FAILURES,
                    str(entry["id"]),
                    str(entry.get("reason") or REASON_NOT_CHECKED_FALLBACK),
                    _label(CLASS_FAILURES, entry),
                )
            )

    def _unbacked_condition(
        self, cid: str, every: bool, known: frozenset[str] | None
    ) -> None:
        if every:
            self.failed.append(
                _failed(
                    CLASS_FAILURES,
                    cid,
                    STATE_EXISTING,
                    RULE_CRITICAL_CONDITION,
                    _condition_label(cid),
                )
            )
        elif known is None:
            self.uncertain.append(
                _uncertain(
                    CLASS_FAILURES,
                    cid,
                    REASON_NO_CRITICAL_IDS_IN_REFERENCE,
                    _condition_label(cid),
                )
            )
        elif cid not in known:
            self.failed.append(
                _failed(
                    CLASS_FAILURES,
                    cid,
                    STATE_NEW,
                    RULE_CRITICAL_CONDITION,
                    _condition_label(cid),
                )
            )


def _order(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    return sorted(items, key=lambda i: (i["class"], i["id"], str(i[key])))


def evaluate_gate(
    policy: str,
    reference: FindingsView,
    current: FindingsView,
    comparison: Mapping[str, Any],
) -> dict[str, Any]:
    """The gate result for `policy`: `{policy, verdict, failed_on, uncertain}`.

    Pure and deterministic. `comparison` is the payload of
    `baseline.compare_findings(reference, current)`. Raises `ValueError` for a policy
    that is not one of `POLICIES`.
    """
    if policy not in POLICIES:
        raise ValueError(
            f"unknown gate policy {policy!r} (one of {', '.join(POLICIES)})"
        )
    if policy == POLICY_NEVER:
        return {
            "policy": policy,
            "verdict": VERDICT_NOT_GATED,
            "failed_on": [],
            "uncertain": [],
        }
    gate = _Gate(policy, reference, current, comparison)
    gate.secrets()
    gate.advisories()
    gate.failures()
    return {
        "policy": policy,
        "verdict": VERDICT_FAIL if gate.failed else VERDICT_OK,
        "failed_on": _order(gate.failed, "rule"),
        "uncertain": _order(gate.uncertain, "reason"),
    }


def gate_failed(gate: Mapping[str, Any] | None) -> bool:
    """Whether a gate result says `fail`."""
    return gate is not None and gate.get("verdict") == VERDICT_FAIL


__all__ = [
    "EXIT_BASELINE_UNUSABLE",
    "EXIT_ERROR",
    "EXIT_GATE_FAILED",
    "EXIT_OK",
    "POLICIES",
    "POLICY_CRITICAL",
    "POLICY_NEVER",
    "POLICY_NEW",
    "POLICY_NEW_CRITICAL",
    "VERDICT_FAIL",
    "VERDICT_NOT_GATED",
    "VERDICT_OK",
    "condition_kind",
    "evaluate_gate",
    "gate_failed",
]
