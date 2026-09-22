"""Health score calculation and recommendation engine."""

from __future__ import annotations

import re

from sarand.models.results import HealthScore, ReportData, TodoItem

# Only markers written with explicit task syntax count as technical debt.
# فقط markerهایی که با syntax صریح task نوشته شده‌اند به‌عنوان بدهی فنی حساب می‌شوند.
# Accepted forms: TODO: ..., TODO - ..., FIXME: ..., FIXME - ...
_ACTIONABLE_TODO_RE = re.compile(
    r"\b(?:TODO|FIXME)\b\s*(?::|-)\s*\S",
    re.IGNORECASE,
)


def _is_actionable_todo(item: TodoItem) -> bool:
    """Return whether a TODO/FIXME uses explicit task-marker syntax.

    The TODO scanner intentionally reports every marker occurrence.
    Health scoring uses a stricter contract: only TODO/FIXME markers
    written as ``TODO: ...``, ``TODO - ...``, ``FIXME: ...``, or
    ``FIXME - ...`` count toward technical-debt scoring.

    اسکنر عمداً همه occurrenceها را گزارش می‌کند.
    امتیازدهی سلامت قرارداد سخت‌گیرانه‌تری دارد: فقط markerهای TODO/FIXME
    که به شکل ``TODO: ...``، ``TODO - ...``، ``FIXME: ...`` یا
    ``FIXME - ...`` نوشته شده‌اند به‌عنوان بدهی فنی حساب می‌شوند.
    """
    if (item.kind or "").upper() not in {"TODO", "FIXME"}:
        return False

    return bool(_ACTIONABLE_TODO_RE.search((item.content or "").strip()))


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
    critical: list[str] = []

    # --- Tests ---
    test_results = data.test_results
    if not test_results:
        breakdown["tests"] = 5.0
        recommendations.append(
            "Add automated tests, or make sure your test runner is installed."
        )
    else:
        passed = sum(1 for r in test_results if r.passed and not r.skipped)
        total = sum(1 for r in test_results if not r.skipped)
        if total == 0:
            breakdown["tests"] = 10.0
            recommendations.append(
                "Install the relevant test runner(s) so tests can actually run."
            )
        else:
            ratio = passed / total
            breakdown["tests"] = round(25.0 * ratio, 1)
            if ratio < 1.0:
                critical.append("One or more test suites failed.")
                recommendations.append("Fix failing tests before release.")

    # --- Quality ---
    quality = data.quality_results
    if not quality:
        breakdown["quality"] = 5.0
        recommendations.append("Run quality checks with --quality.")
    else:
        q_passed = sum(1 for r in quality if r.passed and not r.skipped)
        q_total = sum(1 for r in quality if not r.skipped)
        if q_total == 0:
            breakdown["quality"] = 8.0
        else:
            breakdown["quality"] = round(20.0 * (q_passed / q_total), 1)
            if q_passed < q_total:
                recommendations.append(
                    "Address lint / format issues reported by quality tools."
                )

    # --- Security ---
    security = data.security_results
    if security:
        s_failed = sum(1 for r in security if not r.passed and not r.skipped)
        s_ran = sum(1 for r in security if not r.skipped)
        if s_failed:
            breakdown["security"] = 5.0
            critical.append("Security tool reported issues.")
            recommendations.append("Review the security tool findings.")
        elif s_ran == 0:
            # Every security check was skipped (no tool installed): nothing
            # was checked, so this must not earn the "clean" full score.
            # همه‌ی چک‌های امنیتی رد شده‌اند (ابزاری نصب نیست): چیزی بررسی
            # نشده، پس این نباید امتیاز کامل «تمیز» بگیرد.
            breakdown["security"] = 8.0
            recommendations.append(
                "No security check could run: install the security tools "
                "(see `sarand --doctor`)."
            )
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
        recommendations.append(f"Reduce actionable TODO/FIXME count (currently {todo_count}).")
    if stats.broken_symlinks:
        code_score -= 3.0
        critical.append(f"{len(stats.broken_symlinks)} broken symlinks found.")
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
            critical.append(
                f"{len(real_findings)} potential hardcoded secret(s) detected in source files."
            )
            recommendations.append(
                "Review and rotate any real credentials found; remove them from source control."
            )

        if fixture_findings:
            recommendations.append(
                f"{len(fixture_findings)} secret-pattern match(es) explicitly identified "
                "as test fixtures were excluded from the health score."
            )
    breakdown["code"] = max(0.0, code_score)

    # --- Tooling availability ---
    # Score is based on the ratio of checks that actually ran for this project,
    # not on how many tools happen to be installed on the machine.
    # امتیاز بر اساس نسبت چک‌هایی است که واقعاً برای این پروژه اجرا شده‌اند،
    # نه بر اساس تعداد ابزارهایی که روی ماشین نصب هستند.
    requested = [*test_results, *quality, *security]
    applicable_checks = len(requested)
    runnable_checks = sum(1 for r in requested if not r.skipped)

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
    checks_run = sum(1 for r in requested if not r.skipped)
    checks_skipped = sorted(
        {
            r.kind
            for r in requested
            if r.skipped
        }
    )
    missing_tools = sorted(
        {
            r.kind
            for r in requested
            if r.skipped
            and (
                r.returncode == 127
                or "not installed" in r.skip_reason.lower()
            )
        }
    )
    confidence = (
        round(checks_run / (checks_run + len(checks_skipped)), 2)
        if checks_run + len(checks_skipped)
        else 1.0
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

    return HealthScore(
        score=round(score, 1),
        max_score=100.0,
        grade=grade,
        breakdown=breakdown,
        recommendations=recommendations,
        critical_failures=critical,
        checks_run=checks_run,
        checks_skipped=missing_tools,
        confidence=confidence,
    )
