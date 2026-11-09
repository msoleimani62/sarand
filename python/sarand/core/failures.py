"""Failure classification (R13-A): WHAT kind of failure a check is, and nothing more.

A failed check is a result that exited non-zero, was not skipped and is not
inconclusive. Each one is classified from the tool that ran and from strong,
explicit evidence in its output; the result is a structured `Failure` record plus
neutral, accurate sentences for `known_issues`.

Rules (docs/R13_* record the evidence behind each):

- The tool decides first (`TOOL_FAILURE_CLASSES`): a linter that fails is a
  `lint_failure`, a test runner a `test_failure`. A bare `error:` line never
  decides a category: on a real report the old catch-all produced "Compilation or
  lint errors were detected." from cargo audit and cargo deny.
- Strong signatures override the tool default: a rustc error code (`error[E0425]:`)
  is a `compilation_failure` even when it appears under `cargo test` or
  `cargo clippy`; a Python `ModuleNotFoundError` is a `configuration_failure`.
- Execution failures (the runner could not run the tool: timeout, tool not found,
  OS error) are recognised by the runner's own sentinel line and exit code, never
  by the exit code alone. They are never findings: for a security tool they are a
  `security_tool_failure`, for any other tool an `unknown_tool_failure` whose
  `cause` says what happened.
- A security tool that exited non-zero is a `security_tool_failure` until a
  findings signature proves it completed and reported findings
  (`security_finding_detected`). cargo deny is read by diagnostic code: advisory
  codes are findings, every other `error[...]` code is a
  `dependency_policy_failure` (a license violation is not a vulnerability).
- Nothing here claims exploitability or reachability; that is R13-C.
- An unrecognised tool or an unrecognised failure stays `unknown_tool_failure`.

Pure and deterministic: the same results give the same failures in the same
order. No clock, no environment, no I/O.

طبقه‌بندی شکست (R13-A): فقط «چه نوع شکستی»، نه بیشتر. ابتدا خود ابزار تعیین‌کننده
است، بعد امضای قوی؛ خطای اجرای runner هرگز «یافته» نیست؛ نقض لایسنس آسیب‌پذیری
نیست؛ ناشناخته ناشناخته می‌ماند. خروجی خالص و قطعی است.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from sarand.constants import (
    CARGO_DENY_ADVISORY_CODES,
    CARGO_DENY_ERROR_PATTERN,
    CAUSE_EXIT_CODE,
    COMPILE_SIGNATURES,
    EXECUTION_SENTINELS,
    FAILURE_CATEGORIES,
    FAILURE_COMPILATION,
    FAILURE_CONFIGURATION,
    FAILURE_DEPENDENCY_POLICY,
    FAILURE_LINT,
    FAILURE_SECURITY_FINDING,
    FAILURE_SECURITY_TOOL,
    FAILURE_TEST,
    FAILURE_UNKNOWN_TOOL,
    KNOWN_ISSUE_MISSING_MODULE,
    KNOWN_ISSUE_SYNTAX,
    MISSING_MODULE_PATTERN,
    SECURITY_FINDING_SIGNATURES,
    SIGNAL_PYTHON_MISSING_MODULE,
    SIGNAL_PYTHON_SYNTAX,
    TOOL_FAILURE_CLASSES,
    TOOL_FAILURE_PREFIXES,
)
from sarand.core.finding_identity import (
    KIND_PYTHON_MISSING_MODULE,
    KIND_PYTHON_SYNTAX,
    condition_id,
)
from sarand.models.results import CommandResult, Failure

GROUP_TEST = "test"
GROUP_QUALITY = "quality"
GROUP_SECURITY = "security"

# bandit prints the offending source line after each issue; those lines can look
# like diagnostics, so they are dropped before any signature is searched.
# bandit خطِ مشکل‌دار را هم چاپ می‌کند؛ پیش از جست‌وجوی امضا حذف می‌شود.
_BANDIT_CONTEXT_LINE = re.compile(r"^\d+\t")

_COMPILE = tuple((re.compile(rx), sig, subj) for rx, sig, subj in COMPILE_SIGNATURES)
_MISSING_MODULE = re.compile(MISSING_MODULE_PATTERN)
_FINDINGS = tuple(
    (marker, re.compile(rx), sig) for marker, rx, sig in SECURITY_FINDING_SIGNATURES
)
_DENY_CODE = re.compile(CARGO_DENY_ERROR_PATTERN)

_MAX_TOOLS_IN_SENTENCE = 6


def _is_failure(result: CommandResult) -> bool:
    """Exited non-zero, was not skipped, and is not inconclusive (which only
    exists for exit code 0)."""
    return result.returncode != 0 and not result.skipped and not result.inconclusive


def _clean(output: str) -> str:
    return "\n".join(
        line for line in output.splitlines() if not _BANDIT_CONTEXT_LINE.match(line)
    )


def _tool_class(kind: str) -> tuple[str, str] | None:
    key = kind.strip().lower()
    hit = TOOL_FAILURE_CLASSES.get(key)
    if hit is not None:
        return hit
    for prefix, category, subject in TOOL_FAILURE_PREFIXES:
        if key.startswith(prefix):
            return category, subject
    return None


def execution_cause(result: CommandResult) -> str:
    """Why the runner could not run the tool, or "" when it ran and exited.

    Recognised only by the runner's own sentinel line together with its exit
    code (utils/command.py), so a tool that really exits with 124 or 127 is not
    reported as a timeout or a missing tool.
    """
    out = result.raw_output.strip()
    for code, sentinel, cause in EXECUTION_SENTINELS:
        if result.returncode != code:
            continue
        if cause == "timeout":
            if out.endswith(sentinel):
                return cause
        elif out.startswith(sentinel):
            return cause
    return ""


def _is_security(result: CommandResult, group: str) -> bool:
    known = _tool_class(result.kind)
    if known is not None:
        return known[0] in (FAILURE_SECURITY_TOOL, FAILURE_SECURITY_FINDING)
    return group == GROUP_SECURITY


def _summary(category: str, tool: str, subject: str, cause: str, code: int) -> str:
    """A neutral sentence naming the tool, never a verdict about the project."""
    what = f" ({subject})" if subject else ""
    if cause != CAUSE_EXIT_CODE:
        reason = {
            "timeout": "did not finish: it timed out",
            "tool_not_found": "could not run: the tool was not found",
            "os_error": "could not run: the operating system refused to start it",
        }[cause]
        return f"{tool}{what} {reason}."
    if category == FAILURE_COMPILATION:
        return f"{tool}{what} reported compilation or syntax errors."
    if category == FAILURE_TEST:
        return f"{tool}{what} reported failing tests (exit code {code})."
    if category == FAILURE_LINT:
        return f"{tool}{what} reported lint or validation problems."
    if category == FAILURE_SECURITY_FINDING:
        return (
            f"{tool}{what} reported security findings; this is a tool result, "
            "not proof that the project is exploitable."
        )
    if category == FAILURE_SECURITY_TOOL:
        return (
            f"{tool}{what} exited with code {code} without a recognised findings "
            "report; treated as a tool failure, not as a finding."
        )
    if category == FAILURE_DEPENDENCY_POLICY:
        return (
            f"{tool}{what} reported dependency policy violations (licenses, bans "
            "or sources); this is not a vulnerability."
        )
    if category == FAILURE_CONFIGURATION:
        return f"{tool}{what} reported a configuration or environment problem."
    return f"{tool}{what} exited with code {code}; the cause was not classified."


def _failure(
    result: CommandResult,
    group: str,
    category: str,
    subject: str,
    cause: str,
    signals: Iterable[str],
) -> Failure:
    return Failure(
        tool=result.kind,
        group=group,
        category=category,
        cause=cause,
        subject=subject,
        returncode=result.returncode,
        summary=_summary(category, result.kind, subject, cause, result.returncode),
        signals=tuple(sorted(set(signals))),
    )


def _classify_deny(result: CommandResult, group: str, text: str) -> list[Failure]:
    codes = _DENY_CODE.findall(text)
    advisory = sorted({c for c in codes if c in CARGO_DENY_ADVISORY_CODES})
    policy = sorted({c for c in codes if c not in CARGO_DENY_ADVISORY_CODES})
    out: list[Failure] = []
    if advisory:
        out.append(
            _failure(
                result,
                group,
                FAILURE_SECURITY_FINDING,
                "dependency advisories",
                CAUSE_EXIT_CODE,
                (f"cargo-deny:{c}" for c in advisory),
            )
        )
    if policy:
        out.append(
            _failure(
                result,
                group,
                FAILURE_DEPENDENCY_POLICY,
                "dependency licenses, bans and sources",
                CAUSE_EXIT_CODE,
                (f"cargo-deny:{c}" for c in policy),
            )
        )
    return out


def classify_result(result: CommandResult, group: str = "") -> list[Failure]:
    """Classify one check result; an empty list when it did not fail."""
    if not _is_failure(result):
        return []
    known = _tool_class(result.kind)
    default_category, subject = known if known is not None else ("", "")
    security = _is_security(result, group)

    cause = execution_cause(result)
    if cause:
        category = FAILURE_SECURITY_TOOL if security else FAILURE_UNKNOWN_TOOL
        return [_failure(result, group, category, subject, cause, (cause,))]

    text = _clean(result.raw_output)
    key = result.kind.strip().lower()

    if key.startswith("cargo deny"):
        found = _classify_deny(result, group, text)
        if found:
            return found

    if security:
        for marker, pattern, signal in _FINDINGS:
            if marker in key and pattern.search(text):
                return [
                    _failure(
                        result,
                        group,
                        FAILURE_SECURITY_FINDING,
                        subject,
                        CAUSE_EXIT_CODE,
                        (signal,),
                    )
                ]
        return [
            _failure(result, group, FAILURE_SECURITY_TOOL, subject, CAUSE_EXIT_CODE, ())
        ]

    failures: list[Failure] = []
    compile_signals: dict[str, str] = {}
    for pattern, signal, compile_subject in _COMPILE:
        if pattern.search(text):
            compile_signals.setdefault(signal, compile_subject)
    if compile_signals:
        failures.append(
            _failure(
                result,
                group,
                FAILURE_COMPILATION,
                " and ".join(sorted(set(compile_signals.values()))),
                CAUSE_EXIT_CODE,
                compile_signals,
            )
        )
    if _MISSING_MODULE.search(text):
        failures.append(
            _failure(
                result,
                group,
                FAILURE_CONFIGURATION,
                "Python environment",
                CAUSE_EXIT_CODE,
                (SIGNAL_PYTHON_MISSING_MODULE,),
            )
        )
    if failures:
        return failures

    if default_category:
        return [_failure(result, group, default_category, subject, CAUSE_EXIT_CODE, ())]
    if group == GROUP_TEST:
        return [_failure(result, group, FAILURE_TEST, "", CAUSE_EXIT_CODE, ())]
    return [_failure(result, group, FAILURE_UNKNOWN_TOOL, "", CAUSE_EXIT_CODE, ())]


def classify_failures(
    test_results: Iterable[CommandResult],
    quality_results: Iterable[CommandResult],
    security_results: Iterable[CommandResult],
) -> list[Failure]:
    """Every failure of every check, in the order of the groups and results."""
    out: list[Failure] = []
    for group, results in (
        (GROUP_TEST, test_results),
        (GROUP_QUALITY, quality_results),
        (GROUP_SECURITY, security_results),
    ):
        for result in results:
            out.extend(classify_result(result, group))
    return out


def _tools(failures: list[Failure]) -> str:
    names = sorted({f.tool for f in failures})
    shown = ", ".join(names[:_MAX_TOOLS_IN_SENTENCE])
    extra = len(names) - _MAX_TOOLS_IN_SENTENCE
    return shown + (f" (+{extra} more)" if extra > 0 else "")


# What each category says in `known_issues`. lint_failure and test_failure give no
# known issue: they stay in the check sections and in `failures`; a known issue is
# a high-level problem signature (compilation, environment, security, policy, an
# unclassified failure), and listing every failing linter there would inflate it.
# lint و test در known_issues نمی‌آیند؛ آن‌ها در بخش چک‌ها و `failures` هستند.
_KNOWN_ISSUE_TEMPLATES: dict[str, str] = {
    FAILURE_COMPILATION: "Compilation errors were reported by: {tools}.",
    FAILURE_SECURITY_TOOL: (
        "A security tool did not complete or reported no recognised findings: "
        "{tools}. This is a tool failure, not a vulnerability."
    ),
    FAILURE_SECURITY_FINDING: (
        "Security findings were reported by: {tools}. These are tool results, "
        "not proof that the project is exploitable."
    ),
    FAILURE_DEPENDENCY_POLICY: (
        "Dependency policy checks failed in: {tools} (licenses, bans or "
        "sources). This is not a vulnerability."
    ),
    FAILURE_CONFIGURATION: "Configuration or environment problems were reported by: {tools}.",
    FAILURE_UNKNOWN_TOOL: (
        "A tool failed for a reason that was not classified: {tools}."
    ),
}


def known_issue_entries(failures: list[Failure]) -> list[tuple[str, str]]:
    """(id, sentence) of every known issue, in a fixed order (R13-F).

    The two historical sentences are kept word for word when their evidence is
    present: a Python syntax error, and a missing Python dependency. Every other
    sentence names the tools that failed and the category they failed in; its id
    is the condition id of that category and tool set, the same id the health
    score gives the same condition, so the two can be tied together.
    """
    issues: list[tuple[str, str]] = []
    syntax = [f for f in failures if SIGNAL_PYTHON_SYNTAX in f.signals]
    missing = [f for f in failures if SIGNAL_PYTHON_MISSING_MODULE in f.signals]
    if syntax:
        issues.append(
            (
                condition_id(KIND_PYTHON_SYNTAX, (f.tool for f in syntax)),
                KNOWN_ISSUE_SYNTAX,
            )
        )
    if missing:
        issues.append(
            (
                condition_id(KIND_PYTHON_MISSING_MODULE, (f.tool for f in missing)),
                KNOWN_ISSUE_MISSING_MODULE,
            )
        )
    for category in FAILURE_CATEGORIES:
        template = _KNOWN_ISSUE_TEMPLATES.get(category)
        if template is None:
            continue
        group = [
            f
            for f in failures
            if f.category == category
            and not (
                category == FAILURE_COMPILATION and f.signals == (SIGNAL_PYTHON_SYNTAX,)
            )
            and not (
                category == FAILURE_CONFIGURATION
                and f.signals == (SIGNAL_PYTHON_MISSING_MODULE,)
            )
        ]
        if group:
            issues.append(
                (
                    condition_id(category, (f.tool for f in group)),
                    template.format(tools=_tools(group)),
                )
            )
    return issues


def known_issues_from_failures(failures: list[Failure]) -> list[str]:
    """Neutral known-issue sentences, in a fixed order (see `known_issue_entries`)."""
    return [text for _, text in known_issue_entries(failures)]


def detect_known_issues(results: list[CommandResult]) -> list[str]:
    """Known issues for a flat list of results (kept for callers that do not
    track the test, quality and security groups). The group is unknown, so a
    tool is classified by name and by evidence only."""
    failures: list[Failure] = []
    for result in results:
        failures.extend(classify_result(result, ""))
    return known_issues_from_failures(failures)
