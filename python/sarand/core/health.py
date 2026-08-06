"""Health score calculation and recommendation engine."""

from __future__ import annotations

from sarand.models.results import HealthScore, ReportData


def compute_health_score(data: ReportData) -> HealthScore:
    """Compute a 0-100 health score with breakdown and recommendations.

    Scoring rules (simplified, transparent):
    - Tests pass: +25
    - No critical errors in quality/security: +20
    - Clean git (not dirty, not far behind): +10
    - Reasonable TODO count & code hygiene: +15
    - Presence of tests & quality tooling: +15
    - Security tooling run and clean: +15
    """
    breakdown: dict[str, float] = {}
    recommendations: list[str] = []
    critical: list[str] = []

    # --- Tests ---
    test_results = data.test_results
    if not test_results:
        breakdown["tests"] = 5.0
        recommendations.append("Add automated tests, or make sure your test runner is installed.")
    else:
        passed = sum(1 for r in test_results if r.passed and not r.skipped)
        total = sum(1 for r in test_results if not r.skipped)
        if total == 0:
            breakdown["tests"] = 10.0
            recommendations.append("Install the relevant test runner(s) so tests can actually run.")
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
                recommendations.append("Address lint / format issues reported by quality tools.")

    # --- Security ---
    security = data.security_results
    if security:
        s_failed = sum(1 for r in security if not r.passed and not r.skipped)
        if s_failed:
            breakdown["security"] = 5.0
            critical.append("Security tool reported issues.")
            recommendations.append("Review the security tool findings.")
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
    todo_count = len(data.todos)
    if todo_count > 50:
        code_score -= 5.0
        recommendations.append(f"Reduce TODO/FIXME count (currently {todo_count}).")
    if stats.broken_symlinks:
        code_score -= 3.0
        critical.append(f"{len(stats.broken_symlinks)} broken symlinks found.")
    if stats.empty_files and len(stats.empty_files) > 10:
        code_score -= 2.0
    breakdown["code"] = max(0.0, code_score)

    # --- Tooling presence ---
    tooling = 0.0
    if data.environment.tool_versions:
        tooling += min(10.0, 2.0 * len(data.environment.tool_versions))
    breakdown["tooling"] = tooling

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

    if not recommendations:
        recommendations.append("Project looks healthy. Keep tests and quality checks green.")

    return HealthScore(
        score=round(score, 1),
        max_score=100.0,
        grade=grade,
        breakdown=breakdown,
        recommendations=recommendations,
        critical_failures=critical,
    )
