"""Per-project license policy, read from `.sarand.toml` in the project root.

Whether a dependency's license is acceptable depends on the project that
uses it -- a GPL library is fine in a GPL project and a blocker in a
proprietary one -- so sarand's built-in copyleft advisory (see `sbom.py`)
can only warn. A project that knows its own rules writes them down here
and `--security` enforces them against the SBOM that `syft` produces.

The file lives in the project root (not in `pyproject.toml`) because sarand
audits every ecosystem and most of them have no `pyproject.toml`; it sits
next to `.gitleaks.toml` and `deny.toml`, the other per-project scanner
configs. Example:

    [licenses]
    allow   = ["MIT", "Apache-2.0", "BSD-*", "ISC", "PSF-2.0"]
    deny    = ["AGPL-*", "GPL-*", "SSPL-*"]
    warn    = ["MPL-2.0", "LGPL-*"]
    unknown = "allow"          # packages with no license reported

    [[licenses.exceptions]]
    package = "somelib"
    reason  = "GPL-3.0, used only as a build tool and never shipped"

Semantics (deliberately close to `cargo-deny`):

- Patterns are case-insensitive and support `*`; `GPL-*` does not match
  `LGPL-2.1`.
- `deny` wins over everything, then "not in `allow`" (when `allow` is set),
  then `warn`. A `warn` license is acceptable but reported.
- `A OR B` lets the consumer choose, so the package is judged by its best
  alternative; `A AND B` needs every part to pass. Several license entries
  on one package are treated as alternatives (the lenient reading).
- Non-SPDX strings that ecosystems actually report ("Apache 2.0", "PSFL",
  "MIT License") are mapped to their SPDX id first; any other unrecognised
  string is treated as one opaque license name and must be listed in
  `allow` verbatim.
- `exceptions` need a written `reason` and may pin a `version`.

Anything the file gets wrong -- an unknown key, a bad type, invalid TOML --
is an error, never silently ignored: a typo such as `alow = [...]` would
otherwise turn the whole policy into a no-op.

سیاست لایسنس هر پروژه، از `.sarand.toml` در ریشه‌ی پروژه خوانده می‌شود.

قابل‌قبول‌بودن لایسنس یک وابستگی به پروژه‌ای بستگی دارد که از آن استفاده
می‌کند -- کتابخانه‌ی GPL در پروژه‌ی GPL مشکلی ندارد ولی برای پروژه‌ی
اختصاصی مانع است -- پس هشدار مشورتیِ داخلیِ sarand (`sbom.py`) فقط می‌تواند
هشدار بدهد. پروژه‌ای که قوانین خودش را می‌داند اینجا می‌نویسد و `--security`
آن را روی SBOM تولیدشده‌ی `syft` اِعمال می‌کند.

فایل در ریشه‌ی پروژه است (نه در `pyproject.toml`) چون sarand هر اکوسیستمی
را بررسی می‌کند و بیشترشان `pyproject.toml` ندارند؛ کنار `.gitleaks.toml` و
`deny.toml` می‌نشیند که کانفیگ‌های اسکنرِ هر پروژه‌اند.

هر چیزی که فایل غلط داشته باشد -- کلید ناشناخته، نوع اشتباه، TOML نامعتبر --
خطاست و هرگز بی‌صدا نادیده گرفته نمی‌شود: یک غلط املایی مثل `alow = [...]`
وگرنه کل سیاست را بی‌اثر می‌کند.
"""

from __future__ import annotations

import fnmatch
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10: same parser, packaged separately
    import tomli as tomllib

POLICY_FILENAME = ".sarand.toml"
_UNKNOWN_MODES = ("allow", "warn", "deny")
_LICENSE_KEYS = {"allow", "deny", "warn", "unknown", "exceptions"}
_LIST_KEYS = ("allow", "deny", "warn")
_SPDX_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+-]*$")

# Non-SPDX names that ecosystems really report, mapped to SPDX ids. Kept
# small on purpose: an unlisted string is not guessed at, it is reported
# verbatim so the user can allow it explicitly.
# نام‌های غیر-SPDX که اکوسیستم‌ها واقعاً گزارش می‌کنند، با نگاشت به SPDX.
# عمداً کوچک نگه داشته شده: رشته‌ی ناشناخته حدس زده نمی‌شود، عیناً گزارش
# می‌شود تا کاربر صریحاً allow کند.
_ALIASES = {
    "apache 2.0": "Apache-2.0",
    "apache-2": "Apache-2.0",
    "apache software license": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "mit license": "MIT",
    "psfl": "PSF-2.0",
    "python software foundation license": "PSF-2.0",
    "isc license (iscl)": "ISC",
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    "gnu general public license v2 (gplv2)": "GPL-2.0-only",
    "gnu general public license v3 (gplv3)": "GPL-3.0-only",
    "gnu lesser general public license v2 or later (lgplv2+)": "LGPL-2.1-or-later",
    "gnu lesser general public license v3 (lgplv3)": "LGPL-3.0-only",
    "gnu affero general public license v3": "AGPL-3.0-only",
}


class PolicyError(ValueError):
    """The policy file exists but is not valid."""


class _PackageLike(Protocol):
    # Read-only properties, so a frozen dataclass (SbomPackage) satisfies it.
    # ویژگی‌های فقط‌خواندنی، تا یک dataclass فریز‌شده (SbomPackage) آن را برآورده کند.
    @property
    def name(self) -> str: ...
    @property
    def version(self) -> str: ...
    @property
    def kind(self) -> str: ...
    @property
    def licenses(self) -> tuple[str, ...]: ...


@dataclass(frozen=True)
class PolicyException:
    package: str
    reason: str
    version: str | None = None


@dataclass(frozen=True)
class LicensePolicy:
    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()
    warn: tuple[str, ...] = ()
    unknown: str = "allow"
    exceptions: tuple[PolicyException, ...] = ()


@dataclass(frozen=True)
class Violation:
    package: str
    version: str
    kind: str
    level: int  # 2 = problem (fails the check), 1 = warning
    message: str


def _string_list(table: dict[str, object], key: str) -> tuple[str, ...]:
    value = table.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise PolicyError(f"[licenses] {key} must be a list of strings")
    return tuple(v.strip() for v in value if v.strip())


def _parse_exceptions(raw: object) -> tuple[PolicyException, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(e, dict) for e in raw):
        raise PolicyError("[[licenses.exceptions]] must be a list of tables")
    found: list[PolicyException] = []
    for index, entry in enumerate(raw, start=1):
        unknown = set(entry) - {"package", "version", "reason"}
        if unknown:
            raise PolicyError(
                f"[[licenses.exceptions]] #{index}: unknown key(s) "
                f"{', '.join(sorted(unknown))}"
            )
        package, reason = entry.get("package"), entry.get("reason")
        version = entry.get("version")
        if not isinstance(package, str) or not package.strip():
            raise PolicyError(
                f"[[licenses.exceptions]] #{index}: `package` is required"
            )
        if not isinstance(reason, str) or not reason.strip():
            raise PolicyError(
                f"[[licenses.exceptions]] #{index} ({package}): "
                "a written `reason` is required"
            )
        if version is not None and not isinstance(version, str):
            raise PolicyError(
                f"[[licenses.exceptions]] #{index}: `version` must be a string"
            )
        found.append(PolicyException(package.strip(), reason.strip(), version))
    return tuple(found)


def parse_policy(text: str) -> LicensePolicy | None:
    """Parse the file's text. None when it has no `[licenses]` table."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise PolicyError(f"invalid TOML: {exc}") from exc
    table = data.get("licenses")
    if table is None:
        return None
    if not isinstance(table, dict):
        raise PolicyError("`licenses` must be a table")
    unknown_keys = set(table) - _LICENSE_KEYS
    if unknown_keys:
        raise PolicyError(
            f"[licenses] unknown key(s): {', '.join(sorted(unknown_keys))} "
            f"(expected: {', '.join(sorted(_LICENSE_KEYS))})"
        )
    unknown_mode = table.get("unknown", "allow")
    if unknown_mode not in _UNKNOWN_MODES:
        raise PolicyError(
            f"[licenses] unknown must be one of {', '.join(_UNKNOWN_MODES)}"
        )
    lists = {key: _string_list(table, key) for key in _LIST_KEYS}
    return LicensePolicy(
        allow=lists["allow"],
        deny=lists["deny"],
        warn=lists["warn"],
        unknown=unknown_mode,
        exceptions=_parse_exceptions(table.get("exceptions")),
    )


def load_policy(root: Path) -> LicensePolicy | None:
    """The project's policy, or None when there is no (usable) file section.

    Raises PolicyError when the file exists but is invalid.
    """
    path = root / POLICY_FILENAME
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PolicyError(f"cannot read {POLICY_FILENAME}: {exc}") from exc
    try:
        return parse_policy(text)
    except PolicyError as exc:
        raise PolicyError(f"{POLICY_FILENAME}: {exc}") from exc


def license_alternatives(expression: str) -> list[list[str]]:
    """Split a license string into OR-alternatives of AND-ed SPDX ids.

    A string that is not a valid SPDX expression ("Some Vendor License")
    comes back as one opaque alternative holding the whole string.
    """
    text = expression.strip()
    alias = _ALIASES.get(text.lower())
    if alias:
        return [[alias]]
    flat = text.replace("(", " ").replace(")", " ").strip()
    alternatives: list[list[str]] = []
    for alternative in re.split(r"\s+OR\s+", flat, flags=re.IGNORECASE):
        ids: list[str] = []
        for term in re.split(r"\s+AND\s+", alternative.strip(), flags=re.IGNORECASE):
            license_id = re.split(r"\s+WITH\s+", term.strip(), flags=re.IGNORECASE)[0]
            license_id = license_id.strip()
            if not _SPDX_ID.match(license_id):
                return [[text]]
            ids.append(_ALIASES.get(license_id.lower(), license_id))
        alternatives.append(ids)
    return alternatives


def _matches(patterns: Iterable[str], value: str) -> bool:
    lowered = value.lower()
    return any(fnmatch.fnmatchcase(lowered, pattern.lower()) for pattern in patterns)


def _judge_alternative(ids: list[str], policy: LicensePolicy) -> tuple[int, str]:
    """(level, reason) for one AND-ed group; level 0 ok, 1 warn, 2 problem."""
    for license_id in ids:
        if _matches(policy.deny, license_id):
            return 2, f"{license_id} is denied by the policy"
    if policy.allow:
        acceptable = (*policy.allow, *policy.warn)
        for license_id in ids:
            if not _matches(acceptable, license_id):
                return 2, f"{license_id} is not in the allow list"
    for license_id in ids:
        if _matches(policy.warn, license_id):
            return 1, f"{license_id} needs review (policy `warn`)"
    return 0, ""


def _is_excepted(
    package: _PackageLike, policy: LicensePolicy
) -> PolicyException | None:
    def normal(name: str) -> str:
        return name.lower().replace("_", "-")

    for exception in policy.exceptions:
        if normal(exception.package) != normal(package.name):
            continue
        if exception.version is None or exception.version == package.version:
            return exception
    return None


def evaluate(
    packages: Iterable[_PackageLike], policy: LicensePolicy
) -> tuple[list[Violation], list[tuple[str, PolicyException]]]:
    """Judge every package. Returns (violations, applied exceptions)."""
    violations: list[Violation] = []
    applied: list[tuple[str, PolicyException]] = []
    for package in packages:
        exception = _is_excepted(package, policy)
        if exception is not None:
            applied.append((f"{package.name} {package.version}", exception))
            continue
        if not package.licenses:
            if policy.unknown != "allow":
                level = 2 if policy.unknown == "deny" else 1
                violations.append(
                    Violation(
                        package.name,
                        package.version,
                        package.kind,
                        level,
                        "no license reported",
                    )
                )
            continue
        verdicts = [
            _judge_alternative(ids, policy)
            for entry in package.licenses
            for ids in license_alternatives(entry)
        ]
        level, reason = min(verdicts, key=lambda verdict: verdict[0])
        if level:
            violations.append(
                Violation(package.name, package.version, package.kind, level, reason)
            )
    return violations, applied
