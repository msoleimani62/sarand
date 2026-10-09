"""Per-package result summary for reports that ran checks inside packages.

When a project has component runs (a hybrid project, workspace members or
nested packages), every result of a package is labelled ``"<package>: <kind>"``
by `core/per_component.py`, and the repository still has ONE health score.
This module answers a different question: *which package passed what*. It
counts passed, failed and skipped results per package and phase. It does not
invent a per-package 0-100 score: the repository formula also contains
repository-level parts (git hygiene, TODOs, tooling) that belong to no package
(AGENTS.md section 5.59).

خلاصه‌ی نتایج هر بسته برای گزارش‌هایی که چک‌ها را داخل بسته‌ها اجرا کرده‌اند.
امتیاز سلامت مخزن یکی می‌ماند؛ این ماژول فقط می‌شمارد هر بسته چه چیزی را
پاس یا رد کرده، و امتیاز ۰ تا ۱۰۰ جدا برای بسته نمی‌سازد.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sarand.models.results import CommandResult

ROOT_PACKAGE = "."


@dataclass(frozen=True)
class PhaseCount:
    """Results of one phase (tests, quality or security) of one package."""

    passed: int = 0
    failed: int = 0
    skipped: int = 0

    @property
    def ran(self) -> int:
        return self.passed + self.failed


@dataclass(frozen=True)
class PackageSummary:
    """What one package passed, failed and skipped, phase by phase."""

    package: str
    tests: PhaseCount
    quality: PhaseCount
    security: PhaseCount

    @property
    def failed(self) -> int:
        return self.tests.failed + self.quality.failed + self.security.failed


def _package_of(kind: str, longest_first: Sequence[str]) -> str:
    # The label is `"<package>: "` in front of the kind. Longest package
    # first, so `packages/a/b` is never taken for `packages/a`; anything
    # that carries no known label belongs to the root.
    # برچسب `"<package>: "` جلوی kind است؛ بدون برچسب معتبر = ریشه.
    for package in longest_first:
        if kind.startswith(f"{package}: "):
            return package
    return ROOT_PACKAGE


def _count(
    results: Sequence[CommandResult], longest_first: Sequence[str]
) -> dict[str, PhaseCount]:
    counts: dict[str, list[int]] = {}
    for result in results:
        slot = counts.setdefault(_package_of(result.kind, longest_first), [0, 0, 0])
        if result.skipped:
            slot[2] += 1
        elif result.passed:
            slot[0] += 1
        else:
            slot[1] += 1
    return {name: PhaseCount(*slot) for name, slot in counts.items()}


def summarize_packages(
    packages: Sequence[str],
    test_results: Sequence[CommandResult],
    quality_results: Sequence[CommandResult],
    security_results: Sequence[CommandResult],
) -> list[PackageSummary]:
    """One summary per package, the root first, then in the order given.

    Empty when no package ran anything (`packages` empty), so an ordinary
    project gets no summary at all.
    """
    names = [p for p in dict.fromkeys(packages) if p != ROOT_PACKAGE]
    if not names:
        return []
    longest_first = sorted(names, key=len, reverse=True)
    tests = _count(test_results, longest_first)
    quality = _count(quality_results, longest_first)
    security = _count(security_results, longest_first)
    empty = PhaseCount()
    return [
        PackageSummary(
            package=name,
            tests=tests.get(name, empty),
            quality=quality.get(name, empty),
            security=security.get(name, empty),
        )
        for name in (ROOT_PACKAGE, *names)
    ]
