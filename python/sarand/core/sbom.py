"""syft: generate a Software Bill of Materials (SBOM) for the whole
project -- every dependency across every detected language, in one
pass, rather than sarand trying to enumerate them itself per-language.

This is the P2 "dependency inventory + license policy" layer of
AGENTS.md §5.10 built on top of the P1 "run the tool and show what it
found" version: syft is asked for JSON, and sarand renders (1) a count
per ecosystem, (2) a license histogram, (3) advisory warnings for
copyleft licenses, and (4) the full package table with a license
column. Without a project policy the license check is advisory only
(it never fails the check):
whether a copyleft dependency is a problem depends on this project's own
license and how the dependency is used, which sarand cannot know; a project that does writes `.sarand.toml`
(`license_policy.py`) and the check then enforces it. If
syft's JSON cannot be parsed, the original plain table is used instead,
so this layer can never make the check worse than P1 was.

syft: تولید یک Software Bill of Materials (SBOM) برای کل پروژه -- هر
وابستگی در هر زبان شناسایی‌شده، در یک اجرا، به‌جای این‌که خودِ sarand
سعی کند آن‌ها را تک‌تک به ازای هر زبان برشمارد.

این لایه‌ی P2 «فهرست وابستگی + سیاست لایسنس» از §5.10 AGENTS.md است که
روی نسخه‌ی P1 («ابزار را اجرا کن و چیزی که پیدا کرد را نشان بده») ساخته
شده: از syft خروجی JSON خواسته می‌شود و sarand این‌ها را رندر می‌کند: (۱)
شمارش به تفکیک اکوسیستم، (۲) هیستوگرام لایسنس، (۳) هشدارهای مشورتی برای
لایسنس‌های copyleft، و (۴) جدول کامل پکیج‌ها با ستون لایسنس. بررسی
لایسنس فقط مشورتی است (هرگز چک را شکست نمی‌دهد): اینکه یک وابستگی
copyleft مشکل است یا نه به لایسنس خودِ این پروژه و نحوه‌ی استفاده بستگی
دارد، که sarand نمی‌تواند بداند. اگر JSON خروجی syft parse نشود، همان
جدول ساده‌ی قبلی استفاده می‌شود، پس این لایه هرگز چک را بدتر از P1
نمی‌کند.

اگر پروژه سیاست لایسنس خودش را در `.sarand.toml` بنویسد (`license_policy.py`)،
همین چک آن را اِعمال می‌کند.
"""

from __future__ import annotations

import json
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.core.license_policy import (
    POLICY_FILENAME,
    LicensePolicy,
    PolicyError,
    evaluate,
    load_policy,
)
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("core.sbom")

_KIND = "syft (SBOM)"
_TOP_LICENSES = 8
_MAX_LISTED_WARNINGS = 25

# Levels: 0 = permissive or unrecognized, 1 = weak copyleft, 2 = strong.
# سطح‌ها: ۰ = permissive یا ناشناخته، ۱ = copyleft ضعیف، ۲ = قوی.
_LEVEL_NAMES = {1: "weak-copyleft", 2: "strong-copyleft"}
_STRONG_PREFIXES = ("AGPL", "GPL", "SSPL", "OSL")
_WEAK_PREFIXES = ("LGPL", "MPL", "EPL", "CDDL", "EUPL", "CPL")
_SPDX_OPERATORS = {"AND", "OR", "WITH"}


@dataclass(frozen=True)
class SbomPackage:
    name: str
    version: str
    kind: str
    licenses: tuple[str, ...]


def _token_level(token: str) -> int:
    upper = token.upper()
    if upper.startswith(_WEAK_PREFIXES):
        return 1
    if upper.startswith(_STRONG_PREFIXES):
        return 2
    return 0


def classify_license(expression: str) -> int:
    """Copyleft level of one SPDX-style license string.

    `A OR B` means the consumer may choose, so the package gets the most
    permissive alternative; `A AND B` binds to the strictest term. Parentheses
    are flattened -- good enough for an advisory, not a legal parser.

    `A OR B` یعنی مصرف‌کننده انتخاب می‌کند، پس پکیج سطح راحت‌ترین گزینه را
    می‌گیرد؛ `A AND B` به سخت‌ترین شرط می‌بندد. پرانتزها flatten می‌شوند --
    برای یک هشدار مشورتی کافی است، نه یک parser حقوقی.
    """
    flat = expression.replace("(", " ").replace(")", " ")
    levels: list[int] = []
    for alternative in re.split(r"\s+OR\s+", flat, flags=re.IGNORECASE):
        tokens = [
            token
            for token in re.findall(r"[A-Za-z0-9.+-]+", alternative)
            if token.upper() not in _SPDX_OPERATORS
        ]
        levels.append(max((_token_level(t) for t in tokens), default=0))
    return min(levels) if levels else 0


def parse_packages(json_text: str) -> list[SbomPackage] | None:
    """Parse `syft -o json` output; None if it is not the expected shape."""
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        # Tolerate stray non-JSON lines around the document.
        # خطوط غیر-JSON اضافه دور سند را تحمل می‌کند.
        start, end = json_text.find("{"), json_text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(json_text[start : end + 1])
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict) or not isinstance(data.get("artifacts"), list):
        return None

    merged: dict[tuple[str, str, str], list[str]] = {}
    for artifact in data["artifacts"]:
        if not isinstance(artifact, dict) or not isinstance(artifact.get("name"), str):
            continue
        key = (
            artifact["name"],
            str(artifact.get("version") or ""),
            str(artifact.get("type") or "unknown"),
        )
        found = merged.setdefault(key, [])
        for lic in artifact.get("licenses") or []:
            if not isinstance(lic, dict):
                continue
            text = str(lic.get("spdxExpression") or lic.get("value") or "").strip()
            if text and text not in found:
                found.append(text)
    return [
        SbomPackage(name, version, kind, tuple(lics))
        for (name, version, kind), lics in sorted(merged.items())
    ]


def _policy_lines(
    packages: list[SbomPackage], policy: LicensePolicy
) -> tuple[list[str], int]:
    """Policy verdict lines and the number of violations that fail the check."""
    violations, applied = evaluate(packages, policy)
    problems = [v for v in violations if v.level == 2]
    warnings = [v for v in violations if v.level == 1]
    lines = [
        (
            f"License policy ({POLICY_FILENAME}): {len(problems)} violation(s), "
            f"{len(warnings)} warning(s), {len(applied)} exception(s) applied"
        )
    ]
    for prefix, group in (("problem", problems), ("warning", warnings)):
        for violation in group[:_MAX_LISTED_WARNINGS]:
            lines.append(
                f"{prefix}: license policy: {violation.message} -- "
                f"{violation.package} {violation.version} ({violation.kind})"
            )
        if len(group) > _MAX_LISTED_WARNINGS:
            lines.append(
                f"{prefix}: license policy: +{len(group) - _MAX_LISTED_WARNINGS} "
                "more not listed"
            )
    lines.extend(
        f"note: exception for {label}: {exception.reason}"
        for label, exception in applied
    )
    return lines, len(problems)


def _advisory_lines(packages: list[SbomPackage]) -> list[str]:
    """The built-in copyleft advisory, used when the project has no policy."""
    lines: list[str] = []
    for level in (2, 1):
        flagged = [
            (p, lic)
            for p in packages
            for lic in p.licenses
            if classify_license(lic) == level
        ]
        for pkg, lic in flagged[:_MAX_LISTED_WARNINGS]:
            lines.append(
                f"warning: {_LEVEL_NAMES[level]} license {lic} -- {pkg.name} "
                f"{pkg.version} ({pkg.kind}); review against this project's license"
            )
        if len(flagged) > _MAX_LISTED_WARNINGS:
            lines.append(
                f"warning: +{len(flagged) - _MAX_LISTED_WARNINGS} more "
                f"{_LEVEL_NAMES[level]} package(s) not listed"
            )
    return lines


def render_with_policy(
    packages: list[SbomPackage], policy: LicensePolicy | None = None
) -> tuple[str, int]:
    """Full package table first, then the summary and license verdicts.

    Returns (text, number of policy violations that fail the check).

    The summary goes LAST on purpose: a passing tool's output is shown as
    its last 80 lines unless `--full` is given, and with the summary first
    a real run showed only the table's tail. Ending with the summary keeps
    the counts and license verdicts in that default view.

    جدول کامل پکیج‌ها اول، بعد خلاصه و حکم لایسنس‌ها. خلاصه عمداً آخر
    است: خروجی یک ابزارِ موفق بدون `--full` فقط ۸۰ خط آخر نشان داده
    می‌شود، و با خلاصه‌ی اول یک اجرای واقعی فقط انتهای جدول را نشان داد.
    """
    rows = [(p.name, p.version, p.kind, ", ".join(p.licenses) or "-") for p in packages]
    header = ("NAME", "VERSION", "TYPE", "LICENSES")
    widths = [max(len(r[i]) for r in [header, *rows]) for i in range(3)]
    lines: list[str] = []
    for row in [header, *rows]:
        lines.append(
            "  ".join(row[i].ljust(widths[i]) for i in range(3)) + "  " + row[3]
        )
    lines.append("")

    by_type = Counter(p.kind for p in packages)
    breakdown = ", ".join(f"{k}: {n}" for k, n in by_type.most_common())
    lines.append(f"SBOM: {len(packages)} package(s) -- {breakdown or 'none'}")

    histogram = Counter(lic for p in packages for lic in p.licenses)
    unknown = sum(1 for p in packages if not p.licenses)
    top = histogram.most_common(_TOP_LICENSES)
    parts = [f"{lic}: {n}" for lic, n in top]
    if len(histogram) > len(top):
        parts.append(f"+{len(histogram) - len(top)} more")
    if unknown:
        parts.append(f"no license reported: {unknown}")
    if parts:
        lines.append("Licenses: " + ", ".join(parts))

    violations = 0
    if policy is None:
        lines.extend(_advisory_lines(packages))
    else:
        policy_lines, violations = _policy_lines(packages, policy)
        lines.extend(policy_lines)
    return "\n".join(lines) + "\n", violations


def render_sbom(packages: list[SbomPackage]) -> str:
    """The report text with the built-in advisory (no project policy)."""
    return render_with_policy(packages)[0]


async def run_syft(root: Path) -> CommandResult:
    """Generate an SBOM for `root` with syft.

    syft's own exit code is 0 whether it finds 0 or 500 components, so the
    inventory by itself is informational. The check fails only on a
    license-policy violation (see `license_policy.py`) or an invalid
    `.sarand.toml` -- never merely because a dependency is copyleft.

    کد خروج خودِ syft چه ۰ چه ۵۰۰ مؤلفه پیدا کند ۰ است، پس فهرست به‌تنهایی
    اطلاعاتی است. چک فقط با نقض سیاست لایسنس (`license_policy.py`) یا
    `.sarand.toml` نامعتبر fail می‌شود -- نه صرفاً چون یک وابستگی copyleft است.
    """
    if shutil.which("syft") is None:
        return make_command_result(
            _KIND,
            127,
            "",
            0.0,
            skipped=True,
            skip_reason="syft not installed (see https://github.com/anchore/syft)",
        )

    rc, out, dur = await run_cmd_async(
        ["syft", "dir:.", "-o", "json", "--quiet"], root, LONG_CMD_TIMEOUT
    )
    if rc == 0:
        packages = parse_packages(out)
        if packages is not None:
            policy_error = ""
            try:
                policy = load_policy(root)
            except PolicyError as exc:
                policy, policy_error = None, str(exc)
            text, violations = render_with_policy(packages, policy)
            if policy_error:
                text += f"problem: license policy: {policy_error}\n"
            failed = violations > 0 or bool(policy_error)
            return make_command_result(_KIND, 1 if failed else 0, text, dur)
        logger.warning("could not parse syft JSON output; falling back to table")

    rc2, out2, dur2 = await run_cmd_async(
        ["syft", "dir:.", "-o", "table", "--quiet"], root, LONG_CMD_TIMEOUT
    )
    return make_command_result(_KIND, rc2, out2, dur + dur2)
