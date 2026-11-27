"""Waivers: findings a project accepts on purpose, with a name, a reason and an end date
(R14-D1, slice F3; contract in docs/FINDINGS_BASELINE.md, "Waivers").

A waiver tells the gate (`--baseline-gate`) not to fail on a finding. It never hides the
finding: the finding stays in every report, listed as waived with its waiver.

The waivers are read from `.sarand.toml`, the file the license policy and the secret
settings already share, as an array of tables:

    [[waivers]]
    id = "dependency_advisory:0123456789ab"     # one exact finding, or
    # rule = "advisories:RUSTSEC-2024-0001"     # a whole rule (needs `covers`)
    # covers = 2                                # the most findings a rule may cover
    reason = "No fixed release; the code path is not reachable (ticket 123)"
    owner = "m.soleimani"
    created = 2026-11-27
    expires = 2027-02-27
    reference = "https://example.org/issues/123"   # optional

Rules (the owner's decisions of 2026-11-24, section 3.2 of `docs/R14D1_PLAN.md`):

- A waiver has a scope: an `id` (one exact finding or condition, the id the report and the
  gate print) or a `rule` (`<class>:<family>`, where the family is the pattern name of a
  secret, the advisory id of an advisory, the category of a failure or the kind of a
  health condition).
- `reason`, `owner`, `created` and `expires` are required, as dates (not strings).
  `created` cannot be in the future and `expires` cannot be more than 366 days after it:
  a waiver is a loan, not a permanent exception.
- An expired waiver (its `expires` date is before today) suppresses nothing. The report
  says that it expired and how many findings it would have covered.
- A broad waiver cannot silently cover a later, different finding: a `rule` waiver must
  declare `covers`, the most findings it may cover. If more findings match it than
  that, it applies to none of them and the report says so.
- Everything wrong in the file (an unknown key, a bad type, a duplicate, invalid TOML) is
  an error, never ignored: an ignored waiver would silently change the gate.

Waivers are evaluated by the gate and only when a gate policy other than `never` is on.

waiver یافته‌ای است که پروژه عمداً می‌پذیرد، با نام، دلیل و تاریخ پایان. gate را از رد کردن
آن یافته بازمی‌دارد ولی هرگز یافته را پنهان نمی‌کند. فایل `.sarand.toml` (همان فایل سیاست
مجوز و تنظیمات secret) آرایه‌ی `[[waivers]]` را نگه می‌دارد. هر چیز نادرست خطاست.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from sarand.core.baseline import CLASSES
from sarand.core.license_policy import POLICY_FILENAME

SCOPE_ID = "id"
SCOPE_RULE = "rule"

# A waiver may live at most this long (from `created` to `expires`).
# یک waiver حداکثر این‌قدر عمر دارد (از `created` تا `expires`).
MAX_LIFETIME_DAYS = 366

_KEYS = frozenset(
    {"id", "rule", "reason", "owner", "created", "expires", "reference", "covers"}
)
_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*:[0-9a-f]{12}$")


class WaiverError(ValueError):
    """The `[[waivers]]` tables of `.sarand.toml` are invalid."""


@dataclass(frozen=True)
class Waiver:
    """One validated waiver. `number` is its 1-based position in the file."""

    number: int
    scope: str  # SCOPE_ID or SCOPE_RULE
    target: str  # the id, or `<class>:<family>`
    reason: str
    owner: str
    created: date
    expires: date
    reference: str | None = None
    covers: int | None = None  # only for a rule

    def summary(self) -> dict[str, Any]:
        """The waiver as the report shows it (dates as ISO text)."""
        return {
            "number": self.number,
            "scope": self.scope,
            "target": self.target,
            "reason": self.reason,
            "owner": self.owner,
            "created": self.created.isoformat(),
            "expires": self.expires.isoformat(),
            "reference": self.reference,
            "covers": self.covers,
        }

    def is_expired(self, today: date) -> bool:
        return self.expires < today

    def matches(self, item: Mapping[str, Any]) -> bool:
        """Whether a failed gate item (`class`, `id`, `family`) is in this waiver's scope."""
        if self.scope == SCOPE_ID:
            return str(item["id"]) == self.target
        return f"{item['class']}:{item['family']}" == self.target


# ------------------------------------------------------------------------ reading


def _text(entry: Mapping[str, Any], key: str, where: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise WaiverError(f"{where}: `{key}` must be a non-empty string")
    return value.strip()


def _date(entry: Mapping[str, Any], key: str, where: str) -> date:
    value = entry.get(key)
    if value is None:
        raise WaiverError(f"{where}: `{key}` is required")
    # tomllib gives a datetime for a value with a time; only a plain date is accepted.
    # tomllib برای مقدار دارای ساعت datetime می‌دهد؛ فقط تاریخ ساده پذیرفته می‌شود.
    if isinstance(value, datetime) or not isinstance(value, date):
        raise WaiverError(
            f"{where}: `{key}` must be a date such as 2026-12-31 (not a string)"
        )
    return value


def _scope(entry: Mapping[str, Any], where: str) -> tuple[str, str]:
    has_id, has_rule = "id" in entry, "rule" in entry
    if has_id == has_rule:
        raise WaiverError(f"{where}: give exactly one of `id` and `rule`")
    if has_id:
        target = _text(entry, "id", where)
        if not _ID_PATTERN.match(target):
            raise WaiverError(
                f"{where}: `id` {target!r} is not a finding id "
                "(`<kind>:<12 hex digits>`, as printed by the report and the gate)"
            )
        return SCOPE_ID, target
    target = _text(entry, "rule", where)
    name, _, family = target.partition(":")
    if name not in CLASSES or not family.strip():
        raise WaiverError(
            f"{where}: `rule` {target!r} must be `<class>:<family>` with the class "
            f"one of {', '.join(CLASSES)}"
        )
    return SCOPE_RULE, f"{name}:{family.strip()}"


def _covers(entry: Mapping[str, Any], scope: str, where: str) -> int | None:
    value = entry.get("covers")
    if scope == SCOPE_ID:
        if value is not None:
            raise WaiverError(f"{where}: `covers` is only for a `rule` waiver")
        return None
    if value is None:
        raise WaiverError(
            f"{where}: a `rule` waiver must declare `covers`, the most findings it may "
            "cover (a broad waiver must not silently cover a later finding)"
        )
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise WaiverError(f"{where}: `covers` must be an integer of at least 1")
    return value


def _parse_entry(raw: Any, number: int, today: date) -> Waiver:
    where = f"[[waivers]] #{number}"
    if not isinstance(raw, dict):
        raise WaiverError(f"{where}: must be a table")
    unknown = set(raw) - _KEYS
    if unknown:
        raise WaiverError(
            f"{where}: unknown key(s) {', '.join(sorted(unknown))} "
            f"(expected: {', '.join(sorted(_KEYS))})"
        )
    scope, target = _scope(raw, where)
    created = _date(raw, "created", where)
    expires = _date(raw, "expires", where)
    if created > today:
        raise WaiverError(f"{where}: `created` {created} is in the future")
    if expires < created:
        raise WaiverError(f"{where}: `expires` is before `created`")
    if expires - created > timedelta(days=MAX_LIFETIME_DAYS):
        raise WaiverError(
            f"{where}: a waiver may last at most {MAX_LIFETIME_DAYS} days "
            "from `created` to `expires`"
        )
    reference = _text(raw, "reference", where) if "reference" in raw else None
    return Waiver(
        number=number,
        scope=scope,
        target=target,
        reason=_text(raw, "reason", where),
        owner=_text(raw, "owner", where),
        created=created,
        expires=expires,
        reference=reference,
        covers=_covers(raw, scope, where),
    )


def parse_waivers(text: str, today: date) -> tuple[Waiver, ...]:
    """Parse the file's text. Empty tuple when it has no `[[waivers]]`."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise WaiverError(f"invalid TOML: {exc}") from exc
    table = data.get("waivers")
    if table is None:
        return ()
    if not isinstance(table, list):
        raise WaiverError("`waivers` must be an array of tables ([[waivers]])")
    waivers = tuple(_parse_entry(raw, i, today) for i, raw in enumerate(table, 1))
    seen: dict[tuple[str, str], int] = {}
    for waiver in waivers:
        key = (waiver.scope, waiver.target)
        if key in seen:
            raise WaiverError(
                f"[[waivers]] #{waiver.number}: the same {waiver.scope} "
                f"{waiver.target!r} is already waived by #{seen[key]}"
            )
        seen[key] = waiver.number
    return waivers


def load_waivers(root: Path, today: date) -> tuple[Waiver, ...]:
    """The project's waivers (empty when there is no file or no `[[waivers]]`).

    Raises WaiverError when the file exists but is invalid.
    """
    path = root / POLICY_FILENAME
    if not path.is_file():
        return ()
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise WaiverError(f"cannot read {POLICY_FILENAME}: {exc}") from exc
    try:
        return parse_waivers(text, today)
    except WaiverError as exc:
        raise WaiverError(f"{POLICY_FILENAME}: {exc}") from exc


# ---------------------------------------------------------------------- applying


@dataclass(frozen=True)
class WaiverOutcome:
    """What the waivers did to the findings the gate would fail on."""

    remaining: list[dict[str, Any]]  # still failing
    waived: list[dict[str, Any]]  # each failing item plus its `waiver` summary
    expired: list[dict[str, Any]]  # waiver summary + `matches`
    unused: list[dict[str, Any]]  # active waivers that matched nothing
    exceeded: list[dict[str, Any]]  # rule waivers with more matches than `covers`


def apply_waivers(
    failed: Sequence[Mapping[str, Any]], waivers: Sequence[Waiver], today: date
) -> WaiverOutcome:
    """Split `failed` into what stays failing and what a waiver covers.

    Pure and deterministic (the file order decides when two waivers cover one finding).
    An expired waiver covers nothing; a rule waiver with more matches than `covers`
    covers nothing; an active waiver that covers nothing is reported as unused.
    """
    waived: list[dict[str, Any]] = []
    expired: list[dict[str, Any]] = []
    unused: list[dict[str, Any]] = []
    exceeded: list[dict[str, Any]] = []
    covered: set[int] = set()  # indexes into `failed`
    for waiver in waivers:
        hits = [i for i, item in enumerate(failed) if waiver.matches(item)]
        if waiver.is_expired(today):
            expired.append({**waiver.summary(), "matches": len(hits)})
            continue
        if waiver.covers is not None and len(hits) > waiver.covers:
            exceeded.append({**waiver.summary(), "matches": len(hits)})
            continue
        fresh = [i for i in hits if i not in covered]
        if not fresh:
            unused.append(waiver.summary())
            continue
        for i in fresh:
            covered.add(i)
            waived.append({**failed[i], "waiver": waiver.summary()})
    remaining = [dict(item) for i, item in enumerate(failed) if i not in covered]
    return WaiverOutcome(remaining, waived, expired, unused, exceeded)


__all__ = [
    "MAX_LIFETIME_DAYS",
    "SCOPE_ID",
    "SCOPE_RULE",
    "Waiver",
    "WaiverError",
    "WaiverOutcome",
    "apply_waivers",
    "load_waivers",
    "parse_waivers",
]
