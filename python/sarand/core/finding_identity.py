"""R13-F: stable finding identity (docs/FINDINGS.md).

One underlying problem can be told in several places of a report: a failed
check, a health critical failure, a known issue, a risk, a Quick Context line.
This module gives such a problem ONE identity built from structured fields, never
from the rendered sentence, so that the places can be tied together without
guessing from similar words.

An id looks like ``<kind>:<12 hex digits>``. The kind stays readable (a category
such as ``security_finding_detected``); the digits are the first 12 of a SHA-256
over the kind and the identifying parts, joined by a separator that cannot occur
in them. The parts are normalised (stripped, case kept) and a set of tools is
sorted, so the id does not depend on the order the checks ran in.

Roles of a finding in a report (a finding is never dropped, only classified):

- ``primary``  the section that owns the finding and shows all its evidence;
- ``summary``  a section that counts or restates it (a risk, Quick Context);
- ``related``  another section that tells the same problem in other words (a
  known issue beside the health critical failure of the same condition).

Two findings with similar text but different structured fields keep different
ids: ``cargo audit`` and ``cargo deny`` failing in the same category are two
conditions only when their tool sets differ.

شناسه‌ی پایدار یافته؛ از فیلدهای ساختاریافته ساخته می‌شود نه از متن نمایش‌داده‌شده.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from sarand.models.results import Advisory, Failure

ROLE_PRIMARY = "primary"
ROLE_SUMMARY = "summary"
ROLE_RELATED = "related"
ROLES: tuple[str, ...] = (ROLE_PRIMARY, ROLE_SUMMARY, ROLE_RELATED)

# Kinds that are not a failure category (core/failures.py owns those).
# انواعی که دسته‌ی شکست نیستند.
KIND_TEST_FAILED = "test_suite_failed"
KIND_TEST_UNAVAILABLE = "test_check_unavailable"
KIND_BROKEN_SYMLINKS = "broken_symlinks"
KIND_SECRETS = "hardcoded_secrets"
KIND_ADVISORY = "dependency_advisory"
KIND_PYTHON_SYNTAX = "python_syntax_error"
KIND_PYTHON_MISSING_MODULE = "python_missing_module"

_SEP = "\x1f"
_DIGITS = 12


def finding_id(kind: str, *parts: str) -> str:
    """The id of a finding from its kind and identifying parts (in this order)."""
    material = _SEP.join([kind, *(str(p).strip() for p in parts)])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"{kind}:{digest[:_DIGITS]}"


def condition_id(kind: str, tools: Iterable[str]) -> str:
    """The id of one condition seen in a set of tools (order and repeats do not
    matter). Health critical failures and known issues of the same category and
    tool set get the same id, which is how they are tied together."""
    return finding_id(kind, *sorted({str(t).strip() for t in tools}))


def failure_id(failure: Failure) -> str:
    """The id of one classified failure: tool, group, category, cause, subject.

    The return code and the summary are NOT part of it: they are evidence of the
    finding, not what makes it that finding.
    """
    return finding_id(
        failure.category,
        failure.tool,
        failure.group,
        failure.cause,
        failure.subject,
    )


def advisory_finding_id(advisory: Advisory) -> str:
    """The id of one advisory: its advisory id, package and version. The checks
    that reported it, the severity and the title are evidence, not identity."""
    return finding_id(KIND_ADVISORY, advisory.id, advisory.package, advisory.version)


def kind_of(fid: str) -> str:
    """The readable kind of an id ('' for an empty or malformed id)."""
    head, sep, tail = fid.partition(":")
    return head if sep and tail else ""


def unique_ids(ids: Iterable[str]) -> list[str]:
    """Distinct non-empty ids in first-seen order (deterministic)."""
    return list(dict.fromkeys(i for i in ids if i))
