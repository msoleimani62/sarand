"""Command-line interface for sarand."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
from datetime import datetime
from pathlib import Path

from sarand.analyzers.registry import (
    discover_analyzers,
    matching_analyzers,
    run_quality_concurrently,
    run_security_concurrently,
    run_tests_concurrently,
)
from sarand.config import SarandConfig
from sarand.core.ai_summary import generate_ai_summary, suggest_reading_order
from sarand.core.cache import (
    build_cache_entries,
    load_cache,
    partition_cache_hits,
    reconstruct_secrets,
    reconstruct_todos,
    save_cache,
)
from sarand.core.health import compute_health_score
from sarand.core.issues import detect_known_issues
from sarand.core.secrets import exclude_flagged_files, scan_for_secrets
from sarand.discovery.project_detector import detect_project
from sarand.models.results import ReportData
from sarand.progress import error, status, success, warning
from sarand.renderers import html, json_renderer, markdown, sarif, text
from sarand.rust_bridge import RUST_CORE_AVAILABLE, build_tree_text, scan_project
from sarand.scanners.environment import collect_environment_info
from sarand.scanners.essential_files import collect_essential_files
from sarand.scanners.git import collect_git_snapshot
from sarand.scanners.stats import collect_project_stats
from sarand.scanners.todos import scan_todos
from sarand.userconfig import save_persisted_config
from sarand.utils.logging import get_logger, setup_logging

logger = get_logger("cli")

_RENDERERS = {"markdown": markdown, "json": json_renderer, "text": text, "html": html, "sarif": sarif}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sarand",
        description="Cross-platform CLI that scans any project, detects its architecture, "
        "runs its tests, and generates an AI-ready intelligence report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sarand                                  # analyse the current directory
  sarand --project ~/myproject --quality
  sarand --skip-tests --format json -o report.json
  sarand --set-output-dir ~/ai-reports    # persist output location, once
        """,
    )

    parser.add_argument("--project", "-p", default=None, help="Project root directory (default: cwd)")
    parser.add_argument(
        "--output-dir",
        "-d",
        default=None,
        help="Directory for the report (default: persisted config, then SARAND_OUTPUT_DIR, then ~/Downloads)",
    )
    parser.add_argument(
        "--output-name", "-o", default=None, help="Report filename (default: sarand-<project>-report.<ext>)"
    )
    parser.add_argument(
        "--set-output-dir", metavar="PATH", default=None, help="Persist PATH as the default output directory and exit"
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Run environment diagnostics (Rust core, per-language toolchains) and exit",
    )
    parser.add_argument(
        "--cache",
        action="store_true",
        help="Skip re-scanning TODOs/secrets in files unchanged since the last --cache run (opt-in, see AGENTS.md Phase E)",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Delete the incremental-scan cache for this project (in the output dir) and exit",
    )
    parser.add_argument(
        "--format", "-f", choices=["markdown", "json", "text", "html", "pdf", "sarif"], default="markdown"
    )
    parser.add_argument("--skip-tests", action="store_true", help="Skip running tests")
    parser.add_argument("--quality", action="store_true", help="Run quality checks (per detected language)")
    parser.add_argument(
        "--security", action="store_true", help="Run security/vulnerability checks (per detected language)"
    )
    parser.add_argument("--no-source", action="store_true", help="Do not embed source file contents in the report")
    parser.add_argument("--no-health", action="store_true", help="Skip health-score calculation")
    parser.add_argument("--max-depth", type=int, default=None, help="Maximum project tree depth")
    parser.add_argument("--max-entries", type=int, default=None, help="Maximum entries per tree level")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose (INFO) logging")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--version", action="version", version="sarand 0.1.0")
    return parser


def write_sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    checksum_path = path.with_suffix(path.suffix + ".sha256")
    checksum_path.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def remove_previous_report(output_path: Path) -> None:
    """If a report already exists at this exact output path, remove it
    first and say so explicitly.

    `write_text()`/the PDF renderer would silently overwrite it anyway
    -- this exists purely to make that replacement visible to the user
    (same "check, remove, announce, then create fresh" pattern as
    install.sh), rather than a silent overwrite they have to infer from
    the file's new mtime.

    اگر گزارشی از قبل دقیقاً در همین مسیر خروجی وجود داشته باشد، ابتدا
    آن را حذف می‌کند و صریحاً اعلام می‌کند. `write_text()`/رندرر PDF در
    هر صورت آن را بی‌صدا بازنویسی می‌کردند -- این تابع صرفاً برای
    مرئی‌کردن آن جایگزینی برای کاربر است (همان الگوی «چک کن، حذف کن،
    اعلام کن، بعد تازه بساز» که در install.sh هم هست)، نه یک overwrite
    خاموش که کاربر باید از mtime جدید فایل حدس بزند.
    """
    checksum_path = output_path.with_suffix(output_path.suffix + ".sha256")
    if output_path.exists():
        status(f"Found an existing report at {output_path} -- replacing it.")
        output_path.unlink()
    if checksum_path.exists():
        checksum_path.unlink()


async def run(config: SarandConfig) -> int:
    """Execute one full analysis run."""
    setup_logging(verbose=config.verbose, debug=config.debug)
    logger.info("Starting sarand run on %s", config.project_root)

    try:
        config.validate()
    except ValueError as exc:
        error(str(exc))
        return 1

    root = config.project_root
    config.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = config.output_dir / config.output_name

    detection = detect_project(root)
    if detection.is_recognized:
        status(f"Detected: {', '.join(detection.languages)} ({detection.build_system})")
    else:
        status("No known project marker found -- running generic analysis")
    status(f"Scan engine: {'Rust core' if RUST_CORE_AVAILABLE else 'pure-Python fallback'}")

    # Single filesystem scan, shared by tree/stats/essential-files/todos.
    # یک اسکن فایل‌سیستمی واحد، به‌اشتراک‌گذاشته‌شده بین tree/stats/essential-files/todos.
    records = scan_project(root)
    tree_text = build_tree_text(root, max_depth=config.max_tree_depth, max_entries=config.max_tree_entries)
    included, skipped, excluded_secrets = collect_essential_files(
        root, records=records, max_file_size=config.max_file_size
    )
    stats = collect_project_stats(root, records=records)

    # Incremental cache (opt-in via --cache, AGENTS.md Phase E): split
    # this run's files into "hash matches last run, reuse cached
    # TODO/secret results" vs "changed or new, must actually scan."
    # کش افزایشی (اختیاری با --cache): تفکیک فایل‌های این اجرا به
    # «هش با اجرای قبلی یکی است، از نتایج کش‌شده استفاده کن» در برابر
    # «تغییرکرده یا جدید، باید واقعاً اسکن شود».
    cache_hits: dict = {}
    changed_paths: set[str] | None = None
    if config.use_cache:
        cache = load_cache(config.output_dir, root)
        cache_hits, changed_paths = partition_cache_hits(records, cache)
        if cache_hits:
            status(f"Cache: reusing TODO/secret results for {len(cache_hits)} unchanged file(s)")

    todos = scan_todos(root, records=records, only=changed_paths)
    if cache_hits:
        todos = todos + reconstruct_todos(cache_hits)

    # Secrets content scan runs unconditionally (AGENTS.md §4.10, §7 priority 1)
    # اسکن محتوایی secret همیشه اجرا می‌شود (§4.10، اولویت ۱ در §7)
    secret_scan_targets = included if changed_paths is None else [p for p in included if str(p) in changed_paths]
    secret_findings = scan_for_secrets(root, secret_scan_targets)
    if cache_hits:
        secret_findings = secret_findings + reconstruct_secrets(cache_hits)

    # A file with a content-level finding must not have its full source
    # embedded either -- move it from "included" to "excluded" (§4.10).
    # فایلی که یافته‌ی سطح-محتوا دارد نباید سورس کاملش هم embed شود (§4.10).
    included, excluded_secrets = exclude_flagged_files(included, excluded_secrets, secret_findings)

    if config.use_cache:
        save_cache(config.output_dir, root, build_cache_entries(records, todos, secret_findings))

    if secret_findings:
        warning(f"{len(secret_findings)} potential secret(s) found -- affected file(s) excluded from the report.")
    if excluded_secrets:
        warning(f"{len(excluded_secrets)} credential-shaped file(s) excluded from the report.")

    env = collect_environment_info(root)
    git = collect_git_snapshot(root)

    # Analyzer pipeline: discover, filter to matching languages, run
    # tests and quality checks *concurrently* per language.
    # خط‌لوله‌ی آنالایزر: کشف، فیلتر به زبان‌های منطبق، اجرای *هم‌زمان*
    # تست و کیفیت به‌ازای هر زبان.
    all_analyzers = discover_analyzers()
    active = matching_analyzers(root, all_analyzers)

    if config.skip_tests:
        status("Tests skipped by user request")
        test_results = []
    else:
        test_results = await run_tests_concurrently(root, active)

    quality_results = await run_quality_concurrently(root, active) if config.run_quality else []
    security_results = await run_security_concurrently(root, active) if config.run_security else []

    known = detect_known_issues(test_results + quality_results + security_results)

    data = ReportData(
        project_root=root,
        generated_at=datetime.now(),
        environment=env,
        git=git,
        stats=stats,
        detection=detection,
        used_rust_core=RUST_CORE_AVAILABLE,
        todos=todos,
        test_results=test_results,
        quality_results=quality_results,
        security_results=security_results,
        tree_text=tree_text,
        included_files=included,
        skipped_files=skipped,
        excluded_secret_files=excluded_secrets,
        secret_findings=secret_findings,
        known_issues=known,
    )

    data.ai_summary = generate_ai_summary(data)
    data.suggested_reading_order = suggest_reading_order(root, included)

    if config.health_score:
        data.health = compute_health_score(data)

    remove_previous_report(output_path)

    if config.output_format == "pdf":
        # PDF is binary and rendered via an external tool (renderers/pdf.py)
        # rather than the string-returning Renderer protocol -- see that
        # module's docstring for why. Never crashes on a missing engine.
        # PDF باینری است و از طریق ابزار خارجی رندر می‌شود (renderers/pdf.py)
        # نه از طریق پروتکل رشته‌محور Renderer -- دلیلش در docstring همان
        # ماژول است. هرگز به‌خاطر نبودِ ابزار کرش نمی‌کند.
        from sarand.renderers import pdf as pdf_renderer

        outcome = pdf_renderer.render_to_file(data, output_path, include_source=config.include_source)
        if not outcome.ok:
            error(f"PDF rendering failed: {outcome.detail}")
            return 1
        digest = write_sha256(output_path)
    else:
        content = _RENDERERS[config.output_format].render(data, include_source=config.include_source)
        output_path.write_text(content, encoding="utf-8")
        digest = write_sha256(output_path)

    success("Report completed")
    print()
    print("=" * 60)
    print(f"Project: {root}")
    print(f"Detected: {', '.join(detection.languages) or 'unknown'}")
    print(f"Engine  : {'Rust core' if RUST_CORE_AVAILABLE else 'pure-Python fallback'}")
    print(f"Output  : {output_path}")
    print(f"SHA256  : {digest}")
    print(f"Files   : {len(included)} included / {len(skipped)} skipped / {len(excluded_secrets)} excluded (secrets)")
    if secret_findings:
        print(f"Secrets : {len(secret_findings)} potential secret(s) found -- affected files excluded, see report")
    if config.use_cache:
        print(f"Cache   : {len(cache_hits)} file(s) skipped (unchanged since last --cache run)")
    if data.health:
        print(f"Health  : {data.health.score}/100 ({data.health.grade})")
    print("=" * 60)
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.doctor:
        from sarand.core.doctor import run_doctor

        return run_doctor()

    if args.set_output_dir:
        target = Path(args.set_output_dir).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        config_path = save_persisted_config({"output_dir": str(target)})
        success(f"Default output directory set to: {target}")
        print(f"(saved in {config_path})")
        return 0

    if args.clear_cache:
        from sarand.core.cache import _cache_path

        config = SarandConfig.from_args(args)
        cache_file = _cache_path(config.output_dir, config.project_root)
        if cache_file.exists():
            cache_file.unlink()
            success(f"Cleared cache: {cache_file}")
        else:
            status(f"No cache found at {cache_file} -- nothing to clear.")
        return 0

    config = SarandConfig.from_args(args)
    return asyncio.run(run(config))


if __name__ == "__main__":
    raise SystemExit(main())
