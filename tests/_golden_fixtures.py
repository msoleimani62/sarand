"""Deterministic ``ReportData`` fixtures for the golden-report regression
suite (see ``test_golden_reports.py`` and ``golden/README.md``).

Deliberately dependency-free (no ``import pytest``), mirroring
``_helpers.py`` -- these are plain data builders, not tests.

مولدهای فیکسچر قطعی ``ReportData`` برای مجموعه‌تست رگرسیون golden-report
(به ``test_golden_reports.py`` و ``golden/README.md`` نگاه کنید).

عمداً بدون وابستگی (بدون ``import pytest``)، هم‌راستا با ``_helpers.py`` --
این‌ها سازنده‌ی داده‌ی ساده هستند، نه تست.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from _helpers import write
from sarand.models.results import (
    CommandResult,
    EnvironmentInfo,
    GitSnapshot,
    HealthScore,
    Issue,
    ProjectDetection,
    ProjectStats,
    ReportData,
    SecretFinding,
    TodoItem,
)

# Fixed instant so every render is byte-identical across machines/timezones.
# لحظه‌ی ثابت تا هر رندر روی هر ماشین/منطقه‌زمانی بایت‌به‌بایت یکسان باشد.
GENERATED_AT = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def build_hybrid_fixture(root: Path) -> ReportData:
    """A dense, multi-language project touching nearly every renderer
    branch: truncation limits, skipped checks, secrets, mixed
    pass/fail/skip results, untracked files, etc.

    پروژه‌ای چندزبانه و پرمحتوا که تقریباً هر شاخه‌ی رندرکننده را لمس
    می‌کند: سقف‌های truncation، چک‌های ردشده، اسرار، نتایج ترکیبی
    pass/fail/skip، فایل‌های untracked و غیره.
    """
    # Double-quoted print() content: ruff format also formats Python
    # embedded in markdown code fences, and this exact string ends up
    # inside a ```python fence in hybrid.md's report -- single quotes
    # here would make `ruff format --check .` want to rewrite the
    # golden snapshot on every run.
    # محتوای print() با نقل‌قول دوتایی: ruff format، پایتونِ جاسازی‌شده
    # در fenceهای کد مارک‌داون را هم فرمت می‌کند، و این رشته‌ی دقیق داخل
    # یک fence با نوع ```python در گزارش hybrid.md قرار می‌گیرد -- نقل‌قول
    # تکی اینجا باعث می‌شد `ruff format --check .` بخواهد هر بار اسنپ‌شات
    # golden را بازنویسی کند.
    write(root / "src" / "main.py", 'def main():\n    print("hi")\n')
    write(
        root / "src" / "lib.rs", "pub fn add(a: i32, b: i32) -> i32 {\n    a + b\n}\n"
    )
    write(root / "README.md", "# Hybrid demo\n")

    detection = ProjectDetection(
        languages=["Python", "Rust", "Go"],
        primary_language="Python",
        project_type="workspace",
        build_system="pip + cargo + go mod",
        markers_found=["pyproject.toml", "Cargo.toml", "go.mod"],
        entry_points=["src/main.py", "src/lib.rs", "cmd/server/main.go"],
        details={"Assembly dialects": "x86 (NASM): 2 file(s), ARM: 1 file(s)"},
    )

    environment = EnvironmentInfo(
        python="Python 3.14.6",
        rust_core="compiled and loaded",
        os_name="Linux",
        architecture="aarch64",
        cpu_summary="8-core",
        memory_summary="6.0 GiB total / 2.1 GiB free",
        disk_free="41.2 GiB free",
        hostname="kali",
        tool_versions={"ruff": "0.8.0", "cargo": "1.83.0", "go": "1.23.0"},
    )

    git = GitSnapshot(
        branch="main",
        commit="1e99b0ce56c28c2472531bf4683ca8d93899b1f9",
        status="M src/main.py\n?? scratch.py",
        log="1e99b0c style: format health module\nbd88701 fix health tooling score",
        diff="",
        dirty=True,
        ahead=1,
        behind=0,
        tags="v0.6.2",
        stashes="",
        # 52 entries so the ``[:50]`` slice in markdown.py is exercised.
        # ۵۲ مورد تا برش ``[:50]`` در markdown.py هم آزموده شود.
        untracked=[f"scratch/untracked-{i}.tmp" for i in range(52)],
    )

    stats = ProjectStats(
        total_files=196,
        total_loc=12000,
        code_lines=9800,
        comment_lines=1500,
        blank_lines=700,
        # 12 extensions so the ``[:10]`` slice in markdown.py is exercised.
        # ۱۲ پسوند تا برش ``[:10]`` در markdown.py هم آزموده شود.
        files_by_extension={f".ext{i}": (12 - i) for i in range(12)},
        largest_directories=[("src", 40), ("tests", 30)],
        # 16 entries so the ``[:15]`` slice in markdown.py is exercised.
        # ۱۶ مورد تا برش ``[:15]`` در markdown.py هم آزموده شود.
        largest_files=[(f"big/file-{i}.bin", 1024 * (i + 1)) for i in range(16)],
        duplicate_files=[("hash-abc", ["a.txt", "b.txt"])],
        broken_symlinks=["dead-link"],
        temporary_files=["scratch.tmp"],
        unused_cache_files=["__pycache__/x.pyc"],
        empty_files=["empty.txt"],
        executable_scripts=["run.sh"],
        hidden_files=3,
        binary_files=2,
    )

    # 103 TODOs so the ``[:100]`` slice + "(N more)" line in markdown.py
    # is exercised.
    # ۱۰۳ TODO تا برش ``[:100]`` و خط «(N مورد بیشتر)» در markdown.py هم
    # آزموده شود.
    todos = [
        TodoItem(
            path=f"src/todo_{i}.py", line_number=i + 1, kind="TODO", content=f"item {i}"
        )
        for i in range(103)
    ]

    test_results = [
        CommandResult(
            kind="pytest",
            returncode=0,
            summary="120 passed",
            raw_output="120 passed in 4.20s",
            duration_seconds=4.2,
        ),
        CommandResult(
            kind="cargo test",
            returncode=1,
            summary="1 failed, 40 passed",
            raw_output="test add ... FAILED\nthread 'main' panicked",
            errors=[
                Issue(source="cargo test", message="add() off by one", severity="error")
            ],
            duration_seconds=1.1,
        ),
        CommandResult(
            kind="go test",
            returncode=0,
            summary="",
            skipped=True,
            skip_reason="go not installed",
        ),
    ]

    quality_results = [
        CommandResult(
            kind="ruff",
            returncode=0,
            summary="All checks passed!",
            raw_output="All checks passed!",
            warnings=[
                Issue(source="ruff", message="line too long", severity="warning")
            ],
        ),
        CommandResult(
            kind="cargo clippy",
            returncode=1,
            summary="2 warnings",
            raw_output="warning: unused import\nwarning: needless clone",
            warnings=[
                Issue(source="clippy", message="unused import", severity="warning"),
                Issue(source="clippy", message="needless clone", severity="warning"),
            ],
        ),
    ]

    security_results = [
        CommandResult(
            kind="bandit",
            returncode=0,
            summary="No issues identified.",
            raw_output="No issues identified.",
        ),
        CommandResult(
            kind="gitleaks",
            returncode=1,
            summary="1 leak found",
            raw_output="1 leak found",
            errors=[
                Issue(source="gitleaks", message="possible API key", severity="error")
            ],
        ),
    ]

    health = HealthScore(
        score=76.0,
        max_score=100.0,
        grade="C",
        breakdown={
            "Tests": 18.0,
            "Quality": 15.0,
            "Security": 12.0,
            "Git": 10.0,
            "Code": 11.0,
            "Tooling": 10.0,
        },
        recommendations=["Fix the failing cargo test", "Rotate the leaked credential"],
        critical_failures=["1 potential secret was found in tracked source"],
        checks_run=9,
        checks_skipped=["go test (go not installed)"],
        confidence=0.9,
    )

    # 45 entries so the ``[:40]`` slice in markdown.py is exercised.
    # ۴۵ مورد تا برش ``[:40]`` در markdown.py هم آزموده شود.
    suggested_reading_order = [f"src/module_{i}.py" for i in range(45)]

    included_files = [Path("src/main.py"), Path("src/lib.rs"), Path("README.md")]
    skipped_files = [(Path("assets/huge.bin"), 50 * 1024 * 1024)]

    # One filename-based exclusion, one content-based (matches a
    # secret_finding path) -- exercises both markdown.py branches.
    # یک حذفِ مبتنی‌بر نام‌فایل، یک حذفِ مبتنی‌بر محتوا (منطبق با مسیر
    # secret_finding) -- هر دو شاخه‌ی markdown.py را آزمون می‌کند.
    excluded_secret_files = [Path(".env"), Path("config/secrets.env")]
    secret_findings = [
        SecretFinding(
            path="config/secrets.env",
            line_number=3,
            pattern_name="AWS Secret Key",
            is_test_fixture=False,
        ),
        SecretFinding(
            path="tests/fixtures/dummy_key.py",
            line_number=1,
            pattern_name="Generic API Key",
            is_test_fixture=True,
        ),
    ]

    return ReportData(
        project_root=root,
        generated_at=GENERATED_AT,
        environment=environment,
        git=git,
        stats=stats,
        detection=detection,
        used_rust_core=True,
        todos=todos,
        test_results=test_results,
        quality_results=quality_results,
        security_results=security_results,
        tree_text=f"{root.name}/\n├── src/\n│   ├── main.py\n│   └── lib.rs\n└── README.md",
        included_files=included_files,
        skipped_files=skipped_files,
        excluded_secret_files=excluded_secret_files,
        secret_findings=secret_findings,
        health=health,
        known_issues=["Compilation or lint errors were detected"],
        ai_summary="This is a hybrid Python/Rust/Go workspace with one failing test.",
        suggested_reading_order=suggested_reading_order,
    )


def build_minimal_fixture(root: Path) -> ReportData:
    """An almost-empty, unrecognized directory -- exercises every
    renderer's "nothing found" / empty-state branch (the opposite edge
    from the hybrid fixture above).

    پوشه‌ای تقریباً خالی و ناشناخته -- شاخه‌ی «چیزی یافت نشد» / حالت خالی
    هر رندرکننده را آزمون می‌کند (لبه‌ی مقابلِ فیکسچر hybrid بالا).
    """
    return ReportData(
        project_root=root,
        generated_at=GENERATED_AT,
        environment=EnvironmentInfo(),
        git=GitSnapshot(),
        stats=ProjectStats(),
        detection=ProjectDetection(),
        used_rust_core=False,
        tree_text=f"{root.name}/\n(empty)",
    )


FIXTURES = {
    "hybrid": build_hybrid_fixture,
    "minimal": build_minimal_fixture,
}
