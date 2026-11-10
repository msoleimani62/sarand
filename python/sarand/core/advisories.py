"""Dependency advisories read from cargo audit and cargo deny output (R13-C).

A security tool that exits non-zero can mean four different things: it could not
run, it found an advisory, a dependency violates a configured policy, or the
application is really exploitable. `core/failures.py` already tells the first
three apart; this module keeps the *identity* of each advisory (id, package,
version, fixed versions, severity when the tool printed one) so a report can
list them one by one instead of repeating one sentence.

Rules this module follows, on purpose:

- It parses what the tool printed and nothing else. Severity stays `None` when
  the tool printed none: the RustSec text output carries a severity line only
  when the advisory has a CVSS score, and none is invented.
- It never decides reachability. `Advisory.applicability` is "unknown" for every
  advisory: whether the project calls the affected API, enables the affected
  feature or builds for the affected target needs evidence this module does not
  gather. A dependency in Cargo.lock is not evidence of exploitability.
- It does not refresh anything. The database line names the database and how many
  advisories the tool loaded; whether the tool fetched a fresh copy is not
  claimed.

Pure and deterministic: no I/O, the same results give the same list.

ماژول فقط آنچه ابزار چاپ کرده را می‌خواند. severity نیست مگر ابزار چاپ کرده
باشد؛ reachability هرگز تصمیم‌گیری نمی‌شود (همیشه unknown)؛ چیزی refresh نمی‌شود.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from sarand.constants import (
    ADVISORY_KINDS,
    APPLICABILITY_UNKNOWN,
    CARGO_DENY_ADVISORY_CODES,
)
from sarand.core.failures import execution_cause
from sarand.models.results import Advisory, CommandResult, Issue

_AUDIT_FIELD = re.compile(
    r"^(Crate|Version|Warning|Title|ID|URL|Severity|Solution):[ \t]+(\S.*?)[ \t]*$"
)
_AUDIT_DB_URL = re.compile(r"Fetching advisory database from `([^`]+)`")
_AUDIT_DB_COUNT = re.compile(r"Loaded (\d+) security advisories")
_DENY_HEAD = re.compile(r"(?m)^(?:error|warning)\[([a-z0-9-]+)\]: (.*)$")
# The generic line `cargo audit` prints per advisory ("Warning:   unsound"), and the
# head of a `cargo deny` diagnostic ("error[unmaintained]: ...").
# خط عمومی cargo audit برای هر advisory، و سر diagnostic در cargo deny.
_AUDIT_KIND_LINE = re.compile(r"^Warning:\s+\w+$")
_DENY_ISSUE = re.compile(r"^(?:error|warning)\[([a-z0-9-]+)\]:")
_DENY_ID = re.compile(r"(?m)^\s*├ ID:[ \t]*(\S+)")
_DENY_URL = re.compile(r"(?m)^\s*├ Advisory:[ \t]*(\S+)")
_DENY_SOLUTION = re.compile(r"(?m)^\s*├ Solution:[ \t]*(.+?)[ \t]*$")
_DENY_PACKAGE = re.compile(
    r"(?m)^\s*\d+\s*│\s+(\S+)\s+(\d\S*)\s+(?:registry|git|path|sparse)"
)
_UPGRADE_SPLIT = re.compile(r"\s*(?:,|\bOR\b)\s*")

_TOOL_AUDIT = "cargo audit"
_TOOL_DENY = "cargo deny"


def _tool_name(kind: str) -> str:
    """`web: cargo audit` (a per-component result) and `cargo audit` are one tool."""
    return kind.strip().lower().rsplit(": ", 1)[-1]


def _fixed_versions(solution: str) -> tuple[str, ...]:
    """`Upgrade to >=0.4.4` -> (">=0.4.4",); "No safe upgrade" -> ()."""
    head = "upgrade to"
    if not solution.lower().startswith(head):
        return ()
    rest = solution[len(head) :].strip()
    return tuple(v for v in _UPGRADE_SPLIT.split(rest) if v)


def _database(text: str) -> str:
    """Which database the tool says it used; no local path is kept."""
    url = _AUDIT_DB_URL.search(text)
    count = _AUDIT_DB_COUNT.search(text)
    if url and count:
        return f"{url.group(1)} ({count.group(1)} advisories loaded)"
    if url:
        return url.group(1)
    if count:
        return f"{count.group(1)} advisories loaded"
    return ""


def parse_cargo_audit(output: str, source: str = _TOOL_AUDIT) -> list[Advisory]:
    """Advisories in the text output of `cargo audit` (one block per advisory)."""
    database = _database(output)
    blocks: list[dict[str, str]] = []
    for line in output.splitlines():
        match = _AUDIT_FIELD.match(line)
        if match is None:
            continue
        name, value = match.group(1), match.group(2)
        if name == "Crate":
            blocks.append({})
        if blocks:
            blocks[-1].setdefault(name, value)
    found: list[Advisory] = []
    for block in blocks:
        advisory_id = block.get("ID", "")
        package = block.get("Crate", "")
        if not advisory_id or not package:
            continue
        found.append(
            Advisory(
                id=advisory_id,
                package=package,
                version=block.get("Version", ""),
                kind=block.get("Warning", "vulnerability").lower(),
                title=block.get("Title", ""),
                severity=block.get("Severity"),
                fixed_versions=_fixed_versions(block.get("Solution", "")),
                url=block.get("URL", ""),
                sources=(source,),
                database=database,
                applicability=APPLICABILITY_UNKNOWN,
            )
        )
    return found


def parse_cargo_deny(output: str, source: str = _TOOL_DENY) -> list[Advisory]:
    """Advisory diagnostics of `cargo deny check` (license / ban / source ones
    are policy diagnostics, not advisories, and are skipped)."""
    heads = list(_DENY_HEAD.finditer(output))
    found: list[Advisory] = []
    for index, head in enumerate(heads):
        code = head.group(1)
        if code not in CARGO_DENY_ADVISORY_CODES:
            continue
        end = heads[index + 1].start() if index + 1 < len(heads) else len(output)
        block = output[head.end() : end]
        advisory_id = _DENY_ID.search(block)
        package = _DENY_PACKAGE.search(block)
        if advisory_id is None or package is None:
            continue
        url = _DENY_URL.search(block)
        solution = _DENY_SOLUTION.search(block)
        found.append(
            Advisory(
                id=advisory_id.group(1),
                package=package.group(1),
                version=package.group(2),
                kind=code,
                title=head.group(2).strip(),
                severity=None,
                fixed_versions=_fixed_versions(solution.group(1)) if solution else (),
                url=url.group(1) if url else "",
                sources=(source,),
                database="",
                applicability=APPLICABILITY_UNKNOWN,
            )
        )
    return found


def _merge(first: Advisory, other: Advisory) -> Advisory:
    """The same advisory reported twice: keep every fact either tool printed."""
    sources = tuple(dict.fromkeys((*first.sources, *other.sources)))
    return Advisory(
        id=first.id,
        package=first.package,
        version=first.version,
        kind=first.kind,
        title=first.title or other.title,
        severity=first.severity if first.severity is not None else other.severity,
        fixed_versions=first.fixed_versions or other.fixed_versions,
        url=first.url or other.url,
        sources=sources,
        database=first.database or other.database,
        applicability=first.applicability,
    )


def _kind_rank(kind: str) -> int:
    return ADVISORY_KINDS.index(kind) if kind in ADVISORY_KINDS else len(ADVISORY_KINDS)


def collect_advisories(results: Iterable[CommandResult]) -> list[Advisory]:
    """Every advisory the security results report, one per (id, package, version).

    A skipped or inconclusive check, or one the runner could not execute,
    contributes nothing: its output is not a verdict.
    """
    merged: dict[tuple[str, str, str], Advisory] = {}
    for result in results:
        if result.skipped or result.inconclusive or execution_cause(result):
            continue
        tool = _tool_name(result.kind)
        if tool == _TOOL_AUDIT:
            parsed = parse_cargo_audit(result.raw_output, result.kind)
        elif tool.startswith(_TOOL_DENY):
            parsed = parse_cargo_deny(result.raw_output, result.kind)
        else:
            continue
        for advisory in parsed:
            key = (advisory.id, advisory.package, advisory.version)
            known = merged.get(key)
            merged[key] = advisory if known is None else _merge(known, advisory)
    return sorted(
        merged.values(),
        key=lambda a: (_kind_rank(a.kind), a.id, a.package, a.version),
    )


def is_advisory_line(issue: Issue, advisories: Iterable[Advisory]) -> bool:
    """True for a tool-output line that one of the parsed advisories already
    represents (R13-G): the anonymous `Warning:   unsound` line of cargo audit, or
    a cargo deny `error[vulnerability]` / `warning[unmaintained]` head.

    The line must come from a check that produced at least one advisory, so an
    advisory-shaped line is never dropped when nothing was parsed from its tool.
    Other lines of the same tool (`error: 5 vulnerabilities found!`, a license
    violation, a duplicate crate) are not advisory lines and stay.
    خطی که یکی از advisoryهای پارس‌شده همان را نمایندگی می‌کند؛ بقیه‌ی خطوط می‌مانند.
    """
    if not any(issue.source in a.sources for a in advisories):
        return False
    tool = _tool_name(issue.source)
    if tool == _TOOL_AUDIT:
        return bool(_AUDIT_KIND_LINE.match(issue.message))
    if tool.startswith(_TOOL_DENY):
        match = _DENY_ISSUE.match(issue.message)
        return bool(match and match.group(1) in CARGO_DENY_ADVISORY_CODES)
    return False
