"""Health score calculation and recommendation engine."""

from __future__ import annotations

from sarand.constants import (
    FAILURE_DEPENDENCY_POLICY,
    FAILURE_SECURITY_FINDING,
    FAILURE_SECURITY_TOOL,
)
from sarand.core.check_states import (
    STATE_FAILED,
    STATE_PASSED,
    STATE_SKIPPED,
    STATE_UNAVAILABLE,
    check_state,
    has_no_verdict,
    is_executed,
    legacy_inconclusive,
    legacy_ran,
    legacy_skipped,
    unavailable_cause,
)
from sarand.core.execution_coverage import summarize_coverage
from sarand.core.failures import GROUP_SECURITY, classify_result
from sarand.core.finding_identity import (
    KIND_BROKEN_SYMLINKS,
    KIND_SECRETS,
    KIND_TEST_FAILED,
    KIND_TEST_UNAVAILABLE,
    condition_id,
    finding_id,
)
from sarand.core.markers import is_actionable
from sarand.models.results import CommandResult, HealthScore, ReportData, TodoItem


def _is_actionable_todo(item: TodoItem) -> bool:
    """Return whether a marker is a TODO / FIXME written as a task.

    The scanner reports every occurrence of a marker keyword; the health score
    counts only the `actionable` ones (core/markers.py): `TODO: ...`,
    `TODO(owner): ...`, `TODO - ...`, `FIXME: ...`. BUG, SAFETY, HACK and XXX
    markers and a TODO / FIXME that is only mentioned (`TODO-style`, `TODO: ...`)
    are discovered and shown but never scored.

    اسکنر همه‌ی occurrenceها را گزارش می‌کند؛ امتیاز سلامت فقط موارد actionable را
    می‌شمارد.
    """
    return is_actionable(item)


def _unfinished(result: CommandResult) -> bool:
    """True for a check that gave no verdict: skipped, inconclusive, unavailable
    (the runner could not run it) or an unknown record (core/check_states.py).

    چکی که حکمی نداده: رد شده، inconclusive، unavailable یا نامعلوم.
    """
    return has_no_verdict(result)


_MAX_NAMED_TOOLS = 3
_CAUSE_TEXT = {
    "timeout": "timed out",
    "tool_not_found": "tool not found",
    "os_error": "operating-system error",
}


def _names(kinds: list[str]) -> str:
    """Tool names for a message: at most three, then a count."""
    unique = list(dict.fromkeys(kinds))
    if len(unique) <= _MAX_NAMED_TOOLS:
        return ", ".join(unique)
    shown = ", ".join(unique[:_MAX_NAMED_TOOLS])
    return f"{shown} and {len(unique) - _MAX_NAMED_TOOLS} more"


class _Critical:
    """Critical failures with a stable id each (R13-F). `texts` and `ids` stay
    the same length; a condition already added (same id) is not added twice, so
    one underlying problem never counts as two critical failures.
    شکست‌های بحرانی با شناسه‌ی پایدار؛ یک شرط تکراری دوباره اضافه نمی‌شود.
    """

    def __init__(self) -> None:
        self.texts: list[str] = []
        self.ids: list[str] = []

    def add(self, fid: str, text: str) -> None:
        if fid in self.ids:
            return
        self.ids.append(fid)
        self.texts.append(text)


def _security_failure_groups(
    results: list[CommandResult],
) -> tuple[list[str], list[str], list[str]]:
    """Failed security checks split by what the tool reported (core/failures.py):
    (security findings, dependency policy violations, failure without a finding).
    One cargo-deny run can be in both of the first two lists.
    """
    findings: list[str] = []
    policy: list[str] = []
    other: list[str] = []
    for result in results:
        if result.passed:
            continue
        categories = {f.category for f in classify_result(result, GROUP_SECURITY)}
        if FAILURE_SECURITY_FINDING in categories:
            findings.append(result.kind)
        if FAILURE_DEPENDENCY_POLICY in categories:
            policy.append(result.kind)
        if not categories & {FAILURE_SECURITY_FINDING, FAILURE_DEPENDENCY_POLICY}:
            other.append(result.kind)
    return findings, policy, other


def _scored(result: CommandResult) -> bool:
    """True for a check that counts in a score ratio: it reached a verdict, or the
    runner could not execute it (which earns nothing but is not left out).

    چکی که در نسبت امتیاز می‌آید: یا حکم داده، یا runner نتوانسته اجرایش کند.
    """
    return is_executed(result) or check_state(result) == STATE_UNAVAILABLE


def _could_not_run_text(label: str, results: list[CommandResult]) -> str:
    """One recommendation naming the checks the runner could not execute."""
    reasons = sorted(
        {_CAUSE_TEXT.get(unavailable_cause(r), "did not run") for r in results}
    )
    return (
        f"{label} check could not run ({_names([r.kind for r in results])}: "
        f"{', '.join(reasons)}); it gave no verdict and earns no points, so re-run it."
    )


def _count_actionable_todos(data: ReportData) -> int:
    """Count actionable TODO/FIXME markers for the code-health metric.

    Report / JSON / SARIF continue to show every marker the scanner found.
    Only this count affects the health score.

    فقط markerهای actionable از نوع TODO/FIXME را برای متریک code-health می‌شمارد.
    گزارش / JSON / SARIF همچنان تمام markerهایی که اسکنر پیدا کرده را نشان می‌دهند.
    فقط این عدد روی امتیاز سلامت اثر می‌گذارد.
    """
    return sum(1 for item in data.todos if _is_actionable_todo(item))


def compute_health_score(data: ReportData) -> HealthScore:
    """Compute a 0-100 health score with breakdown and recommendations.

    Scoring rules (simplified, transparent):
    - Tests:                    up to 25
    - Quality checks:           up to 20
    - Security checks:          up to 15
    - Git hygiene:              up to 10
    - Code hygiene (TODOs etc): up to 15
    - Tooling availability:     up to 15
    --------------------------------
    Maximum possible score:     100

    قوانین امتیازدهی (ساده و شفاف):
    - تست‌ها:                    حداکثر ۲۵
    - بررسی کیفیت:               حداکثر ۲۰
    - بررسی امنیت:               حداکثر ۱۵
    - وضعیت Git:                 حداکثر ۱۰
    - بهداشت کد (TODO و غیره):   حداکثر ۱۵
    - در دسترس بودن ابزارها:     حداکثر ۱۵
    --------------------------------
    حداکثر امتیاز ممکن:          ۱۰۰
    """
    breakdown: dict[str, float] = {}
    recommendations: list[str] = []
    critical = _Critical()

    # --- Tests ---
    test_results = data.test_results
    if not test_results:
        breakdown["tests"] = 5.0
        recommendations.append(
            "Add automated tests, or make sure your test runner is installed."
        )
    else:
        passed = sum(1 for r in test_results if check_state(r) == STATE_PASSED)
        # A check the runner could not execute (`unavailable`) earns no points: it
        # stays in the denominator, so a timeout never scores better than the
        # same suite failing. It is NOT called a failed suite: it gave no verdict.
        # چکِ unavailable امتیاز نمی‌گیرد (در مخرج می‌ماند) ولی «شکست» خوانده نمی‌شود.
        total = sum(1 for r in test_results if _scored(r))
        failed = sum(1 for r in test_results if check_state(r) == STATE_FAILED)
        t_lost = [r for r in test_results if check_state(r) == STATE_UNAVAILABLE]
        if t_lost:
            recommendations.append(_could_not_run_text("Test", t_lost))
        if total == 0:
            breakdown["tests"] = 10.0
            recommendations.append(
                "Install the relevant test runner(s) so tests can actually run."
            )
        else:
            ratio = passed / total
            breakdown["tests"] = round(25.0 * ratio, 1)
            if failed:
                critical.add(
                    condition_id(
                        KIND_TEST_FAILED,
                        [
                            r.kind
                            for r in test_results
                            if check_state(r) == STATE_FAILED
                        ],
                    ),
                    "One or more test suites failed.",
                )
                recommendations.append("Fix failing tests before release.")
            if t_lost:
                critical.add(
                    condition_id(KIND_TEST_UNAVAILABLE, [r.kind for r in t_lost]),
                    f"Test check could not run ({_names([r.kind for r in t_lost])}); "
                    "it gave no verdict and earns no points.",
                )

    # --- Quality ---
    quality = data.quality_results
    if not quality:
        breakdown["quality"] = 5.0
        recommendations.append("Run quality checks with --quality.")
    else:
        q_passed = sum(1 for r in quality if check_state(r) == STATE_PASSED)
        q_total = sum(1 for r in quality if _scored(r))
        q_failed = sum(1 for r in quality if check_state(r) == STATE_FAILED)
        q_lost = [r for r in quality if check_state(r) == STATE_UNAVAILABLE]
        if q_lost:
            recommendations.append(_could_not_run_text("Quality", q_lost))
        if q_total == 0:
            breakdown["quality"] = 8.0
        else:
            breakdown["quality"] = round(20.0 * (q_passed / q_total), 1)
            if q_failed:
                recommendations.append(
                    "Address lint / format issues reported by quality tools."
                )

    # --- Security ---
    security = data.security_results
    if security:
        # A check the runner could not execute (timeout, tool not found, OS
        # error) gave no verdict: it is not a finding (R13-C), like a skipped one.
        # چکی که runner نتوانست اجرا کند حکمی نداده؛ مثل رد شده «یافته» نیست.
        s_verdict = [r for r in security if is_executed(r)]
        s_failed = sum(1 for r in s_verdict if check_state(r) != STATE_PASSED)
        s_ran = len(s_verdict)
        could_not_run = [r for r in security if check_state(r) == STATE_UNAVAILABLE]
        if could_not_run:
            recommendations.append(_could_not_run_text("Security", could_not_run))
        if s_failed:
            breakdown["security"] = 5.0
            findings, policy, other = _security_failure_groups(s_verdict)
            if findings:
                critical.add(
                    condition_id(FAILURE_SECURITY_FINDING, findings),
                    f"Security finding reported by {_names(findings)} "
                    "(a tool result; exploitability is not assessed).",
                )
                recommendations.append(
                    "Review the reported security advisories: whether this "
                    "project reaches the affected code is not assessed."
                )
            if policy:
                critical.add(
                    condition_id(FAILURE_DEPENDENCY_POLICY, policy),
                    f"Dependency policy violation reported by {_names(policy)} "
                    "(licenses, bans or sources); not a vulnerability.",
                )
                recommendations.append(
                    "Review the dependency policy violations (licenses, bans, sources)."
                )
            if other:
                critical.add(
                    condition_id(FAILURE_SECURITY_TOOL, other),
                    f"Security tool {_names(other)} failed without a recognised finding.",
                )
                recommendations.append(
                    "Check why the security tool failed; its output has no recognised finding."
                )
        elif s_ran == 0:
            # Every security check was skipped (no tool installed): nothing
            # was checked, so this must not earn the "clean" full score.
            # همه‌ی چک‌های امنیتی رد شده‌اند (ابزاری نصب نیست): چیزی بررسی
            # نشده، پس این نباید امتیاز کامل «تمیز» بگیرد.
            breakdown["security"] = 8.0
            if any(check_state(r) == STATE_SKIPPED for r in security):
                recommendations.append(
                    "No security check could run: install the security tools "
                    "(see `sarand --doctor`)."
                )
        elif could_not_run:
            # A security check the runner could not execute proves nothing: no
            # full "clean" score while one of them is unproven, the same 8.0 as
            # when nothing could run. Weights are unchanged.
            # چک امنیتیِ اجرانشده چیزی ثابت نمی‌کند: تا وقتی هست امتیاز کامل ندارد.
            breakdown["security"] = 8.0
        else:
            breakdown["security"] = 15.0
    else:
        breakdown["security"] = 8.0
        recommendations.append("Consider enabling --security for dependency audits.")

    # --- Git hygiene ---
    git = data.git
    git_score = 10.0
    if git.dirty:
        git_score -= 4.0
        recommendations.append("Commit or stash outstanding changes.")
    if git.behind > 10:
        git_score -= 3.0
        recommendations.append("Pull remote changes; branch is significantly behind.")
    if git.untracked and len(git.untracked) > 20:
        git_score -= 2.0
        recommendations.append("Review large number of untracked files.")
    breakdown["git"] = max(0.0, git_score)

    # --- Code health ---
    stats = data.stats
    code_score = 15.0
    todo_count = _count_actionable_todos(data)
    if todo_count > 50:
        code_score -= 5.0
        recommendations.append(
            f"Reduce actionable TODO/FIXME count (currently {todo_count})."
        )
    if stats.broken_symlinks:
        code_score -= 3.0
        critical.add(
            finding_id(KIND_BROKEN_SYMLINKS),
            f"{len(stats.broken_symlinks)} broken symlinks found.",
        )
    if stats.empty_files and len(stats.empty_files) > 10:
        code_score -= 2.0
    if data.secret_findings:
        # BUG FIX: this used to require "fixture" inside pattern_name
        # (e.g. "AWS Access Key ID") on top of a tests/ path, which no
        # actual pattern name ever contains -- so nothing was ever
        # excluded and every real fixture still tanked the score (this is
        # exactly why `code` scored 0.0 in the self-scan report). The
        # scanner now sets is_test_fixture itself (core/secrets.py); read
        # that instead of re-guessing it here from the label text.
        #
        # اصلاح باگ: قبلاً علاوه بر مسیر tests/ نیاز به وجود کلمه
        # "fixture" داخل pattern_name (مثلاً "AWS Access Key ID") هم بود
        # که هیچ‌کدام از نام‌های الگو هرگز آن را ندارند -- پس هیچ‌وقت هیچ
        # چیزی حذف نمی‌شد و هر fixture واقعی همچنان امتیاز را نابود
        # می‌کرد (دقیقاً همان دلیلی که `code` در گزارش خوداسکن 0.0 شد).
        # اسکنر اکنون خودش is_test_fixture را تنظیم می‌کند
        # (core/secrets.py)؛ به‌جای حدس زدن دوباره از متن برچسب، همان را
        # می‌خوانیم.
        # Since 0.6.20 the flag comes from the project's explicit
        # `[secrets] fixture_paths` list (core/secrets.mark_fixture_findings),
        # not from a path guess.
        # از 0.6.20 این پرچم از فهرست صریح `[secrets] fixture_paths` پروژه
        # می‌آید (core/secrets.mark_fixture_findings) نه از حدس مسیر.
        fixture_findings = [
            finding for finding in data.secret_findings if finding.is_test_fixture
        ]
        real_findings = [
            finding
            for finding in data.secret_findings
            if finding not in fixture_findings
        ]

        if real_findings:
            code_score -= 10.0
            critical.add(
                finding_id(KIND_SECRETS),
                f"{len(real_findings)} potential hardcoded secret(s) detected in source files.",
            )
            recommendations.append(
                "Review and rotate any real credentials found; remove them from source control."
            )

        if fixture_findings:
            recommendations.append(
                f"{len(fixture_findings)} secret-pattern match(es) in files listed under "
                "[secrets] fixture_paths (.sarand.toml) were excluded from the health score."
            )
    breakdown["code"] = max(0.0, code_score)

    # --- Tooling availability ---
    # Score is based on the ratio of checks that actually ran for this project,
    # not on how many tools happen to be installed on the machine.
    # امتیاز بر اساس نسبت چک‌هایی است که واقعاً برای این پروژه اجرا شده‌اند،
    # نه بر اساس تعداد ابزارهایی که روی ماشین نصب هستند.
    requested = [*test_results, *quality, *security]
    applicable_checks = len(requested)
    runnable_checks = sum(1 for r in requested if not _unfinished(r))

    if applicable_checks:
        breakdown["tooling"] = round(
            15.0 * runnable_checks / applicable_checks,
            1,
        )
    else:
        breakdown["tooling"] = 0.0

    score = max(0.0, min(100.0, sum(breakdown.values())))

    if score >= 90:
        grade = "A"
    elif score >= 80:
        grade = "B"
    elif score >= 70:
        grade = "C"
    elif score >= 60:
        grade = "D"
    else:
        grade = "F"

    # --- Transparency: how much of this score rests on checks that ran? ---
    # requested is already computed in the tooling block above.
    # متغیر requested بالاتر در بلوک tooling محاسبه شده است.
    checks_run = sum(1 for r in requested if legacy_ran(r))
    checks_skipped = sorted({r.kind for r in requested if legacy_skipped(r)})
    checks_inconclusive = sorted({r.kind for r in requested if legacy_inconclusive(r)})
    missing_tools = sorted(
        {
            r.kind
            for r in requested
            if legacy_skipped(r)
            and (r.returncode == 127 or "not installed" in r.skip_reason.lower())
        }
    )
    unfinished = len(checks_skipped) + len(checks_inconclusive)
    # LEGACY (deprecated since R13-B, schema 1.2): the original arithmetic, kept
    # exactly as it was so the old JSON field keeps its old meaning. It differs
    # from execution coverage in three ways: skipped and inconclusive checks are
    # counted once per distinct kind while ran checks are counted per record, a
    # timed-out or not-found tool counts as ran, and an empty request gives 1.0.
    # Reports show `execution_coverage` (core/execution_coverage.py) instead.
    # قدیمی (منسوخ از R13-B): همان حساب قبلی بدون تغییر؛ گزارش‌ها از
    # `execution_coverage` استفاده می‌کنند.
    confidence = (
        round(checks_run / (checks_run + unfinished), 2)
        if checks_run + unfinished
        else 1.0
    )
    if checks_inconclusive:
        shown = ", ".join(checks_inconclusive[:8])
        more = (
            f" and {len(checks_inconclusive) - 8} more"
            if len(checks_inconclusive) > 8
            else ""
        )
        recommendations.append(
            f"{len(checks_inconclusive)} check(s) could not finish ({shown}{more}), "
            "for example because the network was unreachable; the score does not "
            "reflect them. Re-run with network access."
        )
    if missing_tools:
        shown = ", ".join(missing_tools[:8])
        more = f" and {len(missing_tools) - 8} more" if len(missing_tools) > 8 else ""
        recommendations.append(
            f"{len(missing_tools)} check(s) were skipped because their tool is "
            f"not installed ({shown}{more}); the score does not reflect them. "
            "See `sarand --doctor` for how to install them."
        )

    if not recommendations:
        recommendations.append(
            "Project looks healthy. Keep tests and quality checks green."
        )

    coverage = summarize_coverage(test_results, quality, security)

    return HealthScore(
        score=round(score, 1),
        max_score=100.0,
        grade=grade,
        breakdown=breakdown,
        recommendations=recommendations,
        critical_failures=critical.texts,
        critical_ids=critical.ids,
        checks_run=checks_run,
        checks_skipped=missing_tools,
        confidence=confidence,
        checks_inconclusive=checks_inconclusive,
        execution_coverage=coverage.coverage,
        checks_requested=coverage.requested,
        checks_executed=coverage.executed,
        coverage_by_group=coverage.by_group,
        coverage_gaps=list(coverage.gaps),
    )
