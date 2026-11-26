"""Command-line interface for sarand."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sarand.analyzers.registry import (
    discover_analyzers,
    matching_analyzers,
    run_quality_concurrently,
    run_security_concurrently,
    run_tests_concurrently,
)
from sarand.config import SarandConfig, resolve_report_path, validate_output_name
from sarand.core.advisories import collect_advisories
from sarand.core.ai_summary import generate_ai_summary, suggest_reading_order
from sarand.core.baseline import (
    BaselineReferenceError,
    FindingsView,
    compare_findings,
    current_view,
    parse_schema,
    read_baseline_file,
)
from sarand.core.cache import (
    build_cache_entries,
    load_cache,
    partition_cache_hits,
    reconstruct_secrets,
    reconstruct_todos,
    save_cache,
)
from sarand.core.components import detect_components
from sarand.core.compose import detect_compose
from sarand.core.concurrency import jobs_argument, resolve_jobs
from sarand.core.detection_refine import refine_detection
from sarand.core.estimate import estimate_source_bytes, size_advice
from sarand.core.execution_coverage import coverage_oneline
from sarand.core.failures import classify_failures, known_issue_entries
from sarand.core.frameworks import detect_declared_frameworks
from sarand.core.gate import (
    EXIT_BASELINE_UNUSABLE,
    EXIT_GATE_FAILED,
    POLICIES,
    POLICY_NEVER,
    VERDICT_FAIL,
    VERDICT_NOT_GATED,
    evaluate_gate,
)
from sarand.core.gitleaks import gitleaks_flagged_paths, run_gitleaks
from sarand.core.health import compute_health_score
from sarand.core.kubernetes import detect_kubernetes
from sarand.core.lockfiles import run_lockfile_check
from sarand.core.makefile import detect_makefiles
from sarand.core.monorepo_tools import detect_monorepo_tools
from sarand.core.node_pm import refine_build_system
from sarand.core.per_component import (
    plan_component_runs,
    run_component_quality,
    run_component_security,
    run_component_tests,
)
from sarand.core.sbom import run_syft
from sarand.core.secrets import (
    exclude_flagged_files,
    exclude_paths,
    mark_fixture_findings,
    scan_for_secrets,
)
from sarand.core.secrets_config import SecretsConfigError, load_fixture_paths
from sarand.core.todo_config import TodoConfigError, load_exclude_globs
from sarand.core.workspace import detect_workspaces
from sarand.discovery.project_detector import detect_project
from sarand.models.results import ReportData
from sarand.progress import error, status, success, warning
from sarand.renderers import html, json_renderer, markdown, sarif, text
from sarand.rust_bridge import (
    RUST_CORE_AVAILABLE,
    build_tree_text,
    scan_project_report,
)
from sarand.scanners.environment import (
    available_memory_bytes,
    collect_environment_info,
)
from sarand.scanners.essential_files import collect_essential_files
from sarand.scanners.git import collect_git_snapshot
from sarand.scanners.stats import collect_project_stats
from sarand.scanners.todos import filter_todos, scan_todos
from sarand.userconfig import save_persisted_config
from sarand.utils.command import set_max_concurrent_commands
from sarand.utils.fs import human_size
from sarand.utils.installation import installation_info, stale_note
from sarand.utils.logging import get_logger, setup_logging
from sarand.utils.sizes import size_argument
from sarand.utils.stdio import harden_stdio

if TYPE_CHECKING:
    from sarand.structure.snapshot import Reference

logger = get_logger("cli")


def _output_name_argument(value: str) -> str:
    """argparse `type`: reject an unsafe --output-name before anything runs.
    نوع argparse: --output-name ناامن را پیش از هر کاری رد می‌کند.
    """
    try:
        validate_output_name(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return value


_RENDERERS = {
    "markdown": markdown,
    "json": json_renderer,
    "text": text,
    "html": html,
    "sarif": sarif,
}


class _VersionAction(argparse.Action):
    """`--version`: the version, plus a note when the copy that is running is a
    stale editable install (its recorded version lags the source tree).

    `--version`: نسخه، و اگر نسخه‌ای که اجرا می‌شود یک نصب editable کهنه باشد
    (نسخه‌ی ثبت‌شده‌اش از سورس عقب مانده) یک یادداشت هم می‌دهد.
    """

    def __init__(
        self,
        option_strings: Sequence[str],
        dest: str = argparse.SUPPRESS,
        default: str = argparse.SUPPRESS,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            default=default,
            nargs=0,
            **kwargs,
        )

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        info = installation_info()
        print(f"sarand {info.version}")
        note = stale_note(info)
        if note:
            print(note, file=sys.stderr)
        parser.exit()


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

Trust model:
  A scan runs the project's own test suite and, with --quality, --security
  or --full, its linters and audit tools: scanning code you do not trust
  means running it. `sarand --skip-tests` alone starts no project toolchain.
  See "Trust model" in the README and SECURITY.md.
        """,
    )

    parser.add_argument(
        "--project", "-p", default=None, help="Project root directory (default: cwd)"
    )
    parser.add_argument(
        "--output-dir",
        "-d",
        default=None,
        help="Directory for the report (default: persisted config, then SARAND_OUTPUT_DIR, then ~/Downloads)",
    )
    parser.add_argument(
        "--output-name",
        "-o",
        type=_output_name_argument,
        default=None,
        help="Report filename (default: sarand-<project>-report.<ext>)",
    )
    parser.add_argument(
        "--set-output-dir",
        metavar="PATH",
        default=None,
        help="Persist PATH as the default output directory and exit",
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
        "--full",
        action="store_true",
        help="Maximum-completeness report: enables --quality and --security, and removes all "
        "truncation limits (file size, tree depth/entries) so nothing is skipped or cut short",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["markdown", "json", "text", "html", "pdf", "sarif"],
        default="markdown",
    )
    parser.add_argument("--skip-tests", action="store_true", help="Skip running tests")
    parser.add_argument(
        "--jobs",
        metavar="N",
        type=jobs_argument,
        help=(
            "Start at most N external tools at once (1-64). Default: one per CPU "
            "and per GiB of free memory, at most 8; also SARAND_JOBS"
        ),
    )
    parser.add_argument(
        "--quality",
        action="store_true",
        help="Run quality checks (per detected language)",
    )
    parser.add_argument(
        "--security",
        action="store_true",
        help="Run security/vulnerability checks (per detected language)",
    )
    parser.add_argument(
        "--skip-audit",
        action="store_true",
        help=(
            "Skip pip-audit/cargo-audit specifically (their vulnerability-"
            "database lookups can take tens of seconds even for a couple of "
            "pinned packages -- measured, not something sarand's own code "
            "can reduce further). Static checks (bandit, ruff, clippy) "
            "still run."
        ),
    )
    parser.add_argument(
        "--no-source",
        action="store_true",
        help="Do not embed source file contents in the report",
    )
    parser.add_argument(
        "--no-health", action="store_true", help="Skip health-score calculation"
    )
    parser.add_argument(
        "--max-depth", type=int, default=None, help="Maximum project tree depth"
    )
    parser.add_argument(
        "--max-entries", type=int, default=None, help="Maximum entries per tree level"
    )
    parser.add_argument(
        "--max-file-size",
        type=size_argument,
        default=None,
        metavar="SIZE",
        help=(
            "Largest source file to embed, e.g. 512K, 2M, 1G (default: 2M). "
            "Larger files are listed as skipped. Overrides the no-limit "
            "behaviour of --full"
        ),
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose (INFO) logging"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--version",
        action=_VersionAction,
        help="Print the version (and warn if this is a stale editable install)",
    )
    from sarand.core.relevant_source import (
        TOKENS_DEFAULT,
        TOKENS_MAX,
        TOKENS_MIN,
        tokens_argument,
    )

    parser.add_argument(
        "--relevant-source",
        nargs="?",
        const=TOKENS_DEFAULT,
        default=None,
        type=tokens_argument,
        metavar="TOKENS",
        help=(
            "Add a small, bounded selection of source snippets chosen by fixed "
            "signals (TODO markers, git changes, entry points, --focus), at most "
            f"TOKENS x 3 bytes (default {TOKENS_DEFAULT}; {TOKENS_MIN}-{TOKENS_MAX}). "
            "Off by default"
        ),
    )
    parser.add_argument(
        "--focus",
        metavar="TEXT",
        default=None,
        help="With --relevant-source: prefer files whose path contains these words",
    )
    parser.add_argument(
        "--structure",
        action="store_true",
        help=(
            "Read the project's Python source with `ast` (nothing is executed) and "
            "add its structure: modules, what they import (repository, standard "
            "library, declared and unmatched external packages), unresolved and "
            "dynamic imports, and import cycles. Off by default"
        ),
    )
    parser.add_argument(
        "--structure-baseline",
        metavar="PATH",
        default=None,
        help=(
            "With --structure: compare the structure with a reference (a snapshot "
            "written by --structure-snapshot, or a JSON report that has a "
            "`structure`) and add what changed. An unusable reference is an error"
        ),
    )
    parser.add_argument(
        "--structure-snapshot",
        metavar="PATH",
        default=None,
        help=(
            "With --structure: write the structure to PATH as a snapshot, after the "
            "report succeeded. Refuses to overwrite an existing file unless "
            "--replace-structure-snapshot is given"
        ),
    )
    parser.add_argument(
        "--replace-structure-snapshot",
        action="store_true",
        help=(
            "Allow --structure-snapshot to replace an existing file; the old one is "
            "kept next to it as PATH.prev"
        ),
    )
    parser.add_argument(
        "--baseline",
        metavar="PATH",
        default=None,
        help=(
            "Compare the findings with a previous JSON report and add what is new, "
            "fixed, unchanged or changed. A finding is `fixed` only when the check "
            "that reports it ran in this run; otherwise it is `not_checked`. An "
            "unusable report is an error (exit code 4)"
        ),
    )
    parser.add_argument(
        "--baseline-gate",
        choices=POLICIES,
        default=None,
        metavar="POLICY",
        help=(
            "With --baseline: make the comparison decide the exit code. `never` "
            "(default) changes nothing; `new` fails (exit code 3) on any new valid "
            "finding; `new-critical` on a new Critical finding; `critical` on any "
            "Critical finding, new or old. Critical = a secret that is not a test "
            "fixture, an advisory of severity `critical`, or a health critical "
            "condition. What cannot be decided is listed as uncertain and never fails"
        ),
    )
    return parser


def _fsync_file(path: Path) -> None:
    """Flush a finished file to disk before it is renamed into place.
    فایل تمام‌شده را پیش از جایگزینی روی دیسک می‌نویسد.
    """
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


def _fsync_directory(path: Path) -> None:
    """Flush the directory entry so the rename itself survives a crash.
    خودِ ورودیِ دایرکتوری را هم می‌نویسد تا جایگزینی از کرش جان به در ببرد.
    """
    # Windows cannot open a directory for fsync; the rename is still atomic there.
    # Windows دایرکتوری را برای fsync باز نمی‌کند؛ جایگزینی آنجا هم اتمی است.
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _report_file_mode(previous: Path) -> int:
    """Permission bits for a new report: the previous report's, else the umask's.

    `tempfile.mkstemp` makes private (0600) files; a report written with
    `write_text` before was 0666 minus the umask, and a replacement must not
    silently change who can read it.
    `mkstemp` فایل خصوصی (۰۶۰۰) می‌سازد؛ گزارشی که قبلاً با `write_text` نوشته می‌شد
    ۰۶۶۶ منهای umask بود و جایگزینی نباید بی‌صدا تعیین کند چه کسی می‌تواند بخواندش.
    """
    try:
        return stat.S_IMODE(previous.stat().st_mode)
    except OSError:
        # umask can only be read by setting it; sarand runs one scan at a time here.
        # umask فقط با تنظیم‌کردن خوانده می‌شود؛ اینجا هر بار یک اسکن اجرا می‌شود.
        current = os.umask(0)
        os.umask(current)
        return 0o666 & ~current


def _apply_mode(path: Path, mode: int) -> None:
    if os.name != "nt":
        path.chmod(mode)


def announce_report_replacement(output_path: Path) -> None:
    """Say that an existing report will be replaced, and when. Deletes nothing.
    اعلام می‌کند که گزارش موجود جایگزین می‌شود و کی؛ چیزی را حذف نمی‌کند.
    """
    if output_path.exists():
        status(
            f"Found an existing report at {output_path}; it will be replaced "
            "only after the new report is ready."
        )


class _PdfRenderFailure(Exception):
    """A recoverable PDF rendering failure that permits Markdown fallback.

    Only an explicit `RenderOutcome(ok=False)` raises it; a failure while
    committing or rolling back must never be taken for a missing PDF engine.
    فقط `RenderOutcome(ok=False)` صریح آن را برمی‌انگیزد؛ شکست حین commit یا rollback
    را نباید با نبودِ موتور PDF اشتباه گرفت.
    """


def atomic_write_report(output_path: Path, writer: Callable[[Path], None]) -> str:
    """Render and checksum a report before atomically replacing its destination.

    The order is the contract: render into a temporary file in the destination
    directory, fsync it, hash it, stage the checksum, keep a backup of the previous
    report, then `os.replace` the report and the checksum. A failure before the
    first replace leaves the previous report and checksum untouched; a failure of
    the checksum replace restores the previous report (or removes the new one).
    The two renames cannot be one atomic step: a crash between them leaves a
    detectable checksum mismatch, which this function does not claim to prevent.
    ترتیب خودش قرارداد است: رندر در فایل موقتِ همان دایرکتوری، fsync، هش، آماده‌سازی
    checksum، نگه‌داشتن پشتیبان گزارش قبلی، سپس `os.replace` گزارش و checksum. شکست
    پیش از اولین replace گزارش و checksum قبلی را دست‌نخورده می‌گذارد؛ شکست replace
    مربوط به checksum گزارش قبلی را برمی‌گرداند (یا گزارش تازه را حذف می‌کند). این دو
    rename یک گامِ اتمی نمی‌شوند: کرش میانشان ناهمخوانیِ قابل‌تشخیص checksum می‌گذارد
    که این تابع ادعای جلوگیری از آن را ندارد.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    checksum_path = output_path.with_suffix(output_path.suffix + ".sha256")
    report_fd, report_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.",
        suffix=output_path.suffix,
        dir=output_path.parent,
    )
    os.close(report_fd)
    staged_report = Path(report_name)
    mode = _report_file_mode(output_path)
    _apply_mode(staged_report, mode)
    staged_checksum: Path | None = None
    backup_path: Path | None = None
    preserve_backup = False

    try:
        checksum_fd, checksum_name = tempfile.mkstemp(
            prefix=f".{checksum_path.name}.",
            suffix=".tmp",
            dir=output_path.parent,
        )
        os.close(checksum_fd)
        staged_checksum = Path(checksum_name)
        _apply_mode(staged_checksum, mode)
        previous_report_exists = output_path.exists()

        writer(staged_report)
        if staged_report.is_symlink() or not staged_report.is_file():
            raise OSError("renderer did not produce a regular report file")
        _fsync_file(staged_report)
        digest = _sha256_file(staged_report)
        staged_checksum.write_text(f"{digest}  {output_path.name}\n", encoding="utf-8")
        _fsync_file(staged_checksum)

        # The backup is what makes a failed checksum commit recoverable.
        # پشتیبان همان چیزی است که شکست commit مربوط به checksum را قابل‌بازیابی می‌کند.
        if previous_report_exists:
            backup_fd, backup_name = tempfile.mkstemp(
                prefix=f".{output_path.name}.backup.",
                dir=output_path.parent,
            )
            os.close(backup_fd)
            backup_path = Path(backup_name)
            shutil.copy2(output_path, backup_path)
            _fsync_file(backup_path)

        os.replace(staged_report, output_path)
        try:
            os.replace(staged_checksum, checksum_path)
        except OSError as commit_error:
            # Roll back: the report and its checksum must not disagree in-process.
            # برگشت: گزارش و checksum نباید در همین فرایند با هم ناهمخوان بمانند.
            try:
                if backup_path is not None:
                    os.replace(backup_path, output_path)
                    backup_path = None
                else:
                    output_path.unlink(missing_ok=True)
            except OSError as rollback_error:
                # Keep the backup and name it: manual recovery stays possible.
                # پشتیبان را نگه می‌دارد و نامش را می‌آورد تا بازیابی دستی ممکن بماند.
                preserve_backup = backup_path is not None
                backup_detail = (
                    f"; previous report backup preserved at {backup_path}"
                    if preserve_backup
                    else ""
                )
                raise RuntimeError(
                    "checksum commit failed and report rollback failed: "
                    f"{rollback_error}{backup_detail}"
                ) from commit_error
            raise
        try:
            _fsync_directory(output_path.parent)
        except OSError:
            logger.warning(
                "Report and checksum were committed, but directory durability "
                "could not be confirmed for %s",
                output_path.parent,
            )
        return digest
    finally:
        # Never leave temporary files behind, except a backup kept after a failed
        # rollback.
        # هرگز فایل موقت باقی نگذار، جز پشتیبانی که پس از rollbackِ ناموفق نگه داشته شد.
        staged_report.unlink(missing_ok=True)
        if staged_checksum is not None:
            staged_checksum.unlink(missing_ok=True)
        if backup_path is not None and not preserve_backup:
            backup_path.unlink(missing_ok=True)


def _write_pdf_fallback(
    data: ReportData, output_path: Path, detail: str, config: SarandConfig
) -> Path:
    """The PDF could not be made: say why, and keep the scan.

    Writes the same report as Markdown next to the intended PDF path, through the
    same staged replacement, so the minutes the scan took are not lost. A previous
    PDF is left as it was. The caller still exits non-zero, because the requested
    artifact does not exist.
    PDF ساخته نشد: دلیل را بگو و نتیجه‌ی اسکن را نگه دار. همان گزارش را به‌صورت
    Markdown کنار مسیر PDF و با همان جایگزینیِ مرحله‌ای می‌نویسد؛ PDF قبلی دست‌نخورده
    می‌ماند. فراخواننده همچنان با کد غیرصفر خارج می‌شود، چون مصنوع خواسته‌شده وجود ندارد.
    """
    error(f"PDF rendering failed: {detail}")
    fallback = resolve_report_path(
        output_path.parent, output_path.with_suffix(".md").name
    )
    announce_report_replacement(fallback)

    def render(markdown_path: Path) -> None:
        content = _RENDERERS["markdown"].render(
            data, include_source=config.include_source, full_output=config.full
        )
        markdown_path.write_text(content, encoding="utf-8")

    digest = atomic_write_report(fallback, render)
    warning(f"No PDF was produced. The full report was written as Markdown: {fallback}")
    logger.info("Fallback report SHA256: %s", digest)
    return fallback


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
    try:
        output_path = resolve_report_path(config.output_dir, config.output_name)
    except (OSError, RuntimeError, ValueError) as exc:
        error(
            "The report output path is invalid or resolves outside the "
            f"configured output directory: {exc}"
        )
        return 1

    # R14-D1 (S2): refuse an unusable baseline or snapshot target now, before any
    # work, so a mistake costs nothing.
    # R14-D1 (S2): baseline یا مقصد snapshotِ نامعتبر همین الان رد می‌شود، پیش از هر
    # کاری، تا اشتباه هزینه‌ای نداشته باشد.
    baseline_reference: Reference | None = None
    if config.structure_baseline is not None:
        from sarand.structure.snapshot_io import read_reference_file

        baseline_reference = read_reference_file(config.structure_baseline)
        if not baseline_reference.usable:
            error(
                f"Cannot use the structure baseline {config.structure_baseline}: "
                f"{baseline_reference.problem}"
            )
            return EXIT_BASELINE_UNUSABLE
    if config.structure_snapshot is not None:
        from sarand.structure.snapshot_io import (
            SnapshotTargetError,
            check_snapshot_target,
        )

        try:
            check_snapshot_target(
                config.structure_snapshot, replace=config.replace_structure_snapshot
            )
        except SnapshotTargetError as exc:
            error(f"Cannot write the structure snapshot: {exc}")
            return 1

    # R14-D1 (F1): the findings baseline is read now too, so an unusable report costs
    # nothing.
    # R14-D1 (F1): baseline یافته‌ها هم همین حالا خوانده می‌شود تا گزارش نامعتبر
    # هزینه‌ای نداشته باشد.
    findings_reference: FindingsView | None = None
    if config.baseline is not None:
        try:
            findings_reference = read_baseline_file(config.baseline)
        except BaselineReferenceError as exc:
            error(f"Cannot use the findings baseline {config.baseline}: {exc}")
            return EXIT_BASELINE_UNUSABLE

    # One process-wide limit on external tools (AGENTS.md 5.73): --jobs, then
    # SARAND_JOBS, then one per CPU and per GiB of free memory.
    # یک سقف سراسری روی ابزارهای بیرونی: --jobs، بعد SARAND_JOBS، بعد پیش‌فرض دستگاه.
    cpus = os.cpu_count()
    free_memory = available_memory_bytes()
    try:
        jobs = resolve_jobs(config.jobs, os.environ, cpus, free_memory)
    except ValueError as exc:
        warning(f"{exc} -- using the default number of parallel tools.")
        jobs = resolve_jobs(config.jobs, {}, cpus, free_memory)
    set_max_concurrent_commands(jobs)
    logger.info("Running at most %d external tool(s) at once", jobs)

    detection = detect_project(root)
    # Cheap (one small TOML parse at most) and self-gating -- returns
    # None immediately for the common case of no root Cargo.toml or a
    # single-package (non-workspace) one. See core/workspace.py for
    # which workspace models this does and does not detect yet.
    # ارزان (حداکثر یک پارس کوچک TOML) و خودش تصمیم می‌گیرد -- برای
    # حالت رایجِ نبودِ Cargo.toml ریشه یا یک Cargo.toml تک‌بسته‌ای
    # (غیر-workspace) بلافاصله None برمی‌گرداند. برای اینکه کدام
    # مدل‌های workspace فعلاً تشخیص داده می‌شوند و کدام نه،
    # core/workspace.py را ببینید.
    workspaces = detect_workspaces(root)
    workspace = workspaces[0] if workspaces else None
    kubernetes = detect_kubernetes(root)
    compose = detect_compose(root)
    makefile = detect_makefiles(root)
    monorepo_tools = detect_monorepo_tools(root, workspaces)
    frameworks_declared = detect_declared_frameworks(root)
    components = detect_components(root, kubernetes, compose, makefile)
    # Hybrid projects: describe the whole project, not just its root.
    # پروژه‌ی ترکیبی: کل پروژه را توصیف کن، نه فقط ریشه را.
    detection = refine_detection(detection, components)
    detection = refine_build_system(detection, root)
    if detection.is_recognized:
        status(f"Detected: {', '.join(detection.languages)} ({detection.build_system})")
    else:
        status("No known project marker found -- running generic analysis")
    status(
        f"Scan engine: {'Rust core' if RUST_CORE_AVAILABLE else 'pure-Python fallback'}"
    )

    # Single filesystem scan, shared by tree/stats/essential-files/todos.
    # یک اسکن فایل‌سیستمی واحد، به‌اشتراک‌گذاشته‌شده بین tree/stats/essential-files/todos.
    records, scan_problems = scan_project_report(root)
    if scan_problems.skipped:
        first = "; ".join(scan_problems.samples[:2])
        warning(
            f"{scan_problems.skipped} path(s) could not be read and are missing "
            f"from the report (first: {first})."
        )
    tree_text = build_tree_text(
        root, max_depth=config.max_tree_depth, max_entries=config.max_tree_entries
    )
    included, skipped, excluded_secrets = collect_essential_files(
        root, records=records, max_file_size=config.max_file_size
    )
    stats = collect_project_stats(root, records=records)

    # Say up front how much source will be embedded, and warn when that looks
    # too big for this machine (a 2 GB laptop or a phone can run out of memory
    # on a large `--full` report). Informational only: never blocks the run.
    # از همان اول بگو چقدر سورس embed می‌شود و وقتی برای این ماشین زیاد به نظر
    # برسد هشدار بده (یک لپ‌تاپ ۲ گیگابایتی یا گوشی ممکن است روی یک گزارش
    # بزرگ `--full` حافظه کم بیاورد). فقط اطلاع‌رسانی: هرگز اجرا را متوقف نمی‌کند.
    if config.include_source:
        estimated = estimate_source_bytes(records, included)
        status(
            f"Embedding about {human_size(estimated)} of source "
            f"from {len(included)} file(s)"
        )
        advice = size_advice(estimated, available_memory_bytes())
        if advice:
            warning(advice)

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
            status(
                f"Cache: reusing TODO/secret results for {len(cache_hits)} unchanged file(s)"
            )

    # BUG FIX: scan_todos used to be called unconditionally, even when
    # `changed_paths` is an empty set (every file was a cache hit) --
    # defeating the whole point of --cache for that run. Secrets stay
    # unconditional on purpose (AGENTS.md §4.10, §7 priority 1: never
    # skip a security scan just because caching says nothing changed);
    # TODOs have no such safety requirement, so they're the ones that
    # should actually be skipped when there is nothing to scan.
    #
    # اصلاح باگ: scan_todos قبلاً بدون هیچ شرطی صدا زده می‌شد، حتی وقتی
    # `changed_paths` یک set خالی بود (همه‌ی فایل‌ها cache-hit بودند) --
    # که کل هدف --cache را برای همان اجرا از بین می‌برد. اسکن secret عمداً
    # بدون شرط باقی می‌ماند (AGENTS.md §4.10، اولویت ۱ در §7: هرگز یک
    # اسکن امنیتی را صرفاً چون کش می‌گوید چیزی تغییر نکرده رد نکن)؛ TODOها
    # چنین الزام امنیتی‌ای ندارند، پس همان چیزی هستند که واقعاً باید وقتی
    # چیزی برای اسکن نیست، رد شوند.
    if changed_paths is None or changed_paths:
        todos = scan_todos(root, records=records, only=changed_paths)
    else:
        todos = []
    if cache_hits:
        todos = todos + reconstruct_todos(cache_hits)
    # Markers in golden/fixture directories and Markdown prose are not tasks
    # (AGENTS.md 5.68). Filtering here, after the cache merge, also removes
    # stale cached markers of files that have become excluded; the count is
    # reported so nothing is hidden silently.
    # مارکر در پوشه‌های golden/fixture و متن Markdown «کار» نیست. فیلتر بعد از
    # ادغام کش، مارکرهای کهنه‌ی کش را هم حذف می‌کند؛ تعداد گزارش می‌شود.
    try:
        todo_globs = load_exclude_globs(root)
    except TodoConfigError as exc:
        warning(f"{exc} -- using only the default TODO exclusions.")
        todo_globs = ()
    todos, todos_suppressed = filter_todos(todos, todo_globs)

    # BUG FIX (part 2): scan_for_secrets was still called unconditionally
    # too, even over an empty `secret_scan_targets` list, for the same
    # reason scan_todos was above. The comment this replaces read
    # "unconditionally" from AGENTS.md §4.10, but §4.10 actually says the
    # content scan must never be gated behind --security (an *optional*
    # flag) -- it says nothing about re-scanning bytes that are provably
    # identical to a previous scan (matching content hash). Skipping a
    # scan whose result is already known and reconstructed from cache
    # isn't a safety gap; it's the same cache contract as todos.
    #
    # اصلاح باگ (بخش دوم): scan_for_secrets هم دقیقاً به همین دلیل
    # scan_todos بدون هیچ شرطی صدا زده می‌شد، حتی روی لیست خالی
    # `secret_scan_targets`. کامنتی که این را جایگزین می‌کند از
    # AGENTS.md §4.10 «بدون شرط» خوانده بود، اما §4.10 در واقع می‌گوید
    # اسکن محتوایی هرگز نباید پشت `--security` (یک فلگ *اختیاری*) قایم
    # شود -- درباره‌ی دوباره‌اسکن‌کردن بایت‌هایی که اثبات‌شده با اسکن قبلی
    # یکسانند (هش محتوا یکی است) چیزی نمی‌گوید. رد کردن اسکنی که نتیجه‌اش
    # از قبل معلوم و از کش reconstruct شده، شکاف امنیتی نیست؛ همان قرارداد
    # کشِ todos است.
    secret_scan_targets = (
        included
        if changed_paths is None
        else [p for p in included if str(p) in changed_paths]
    )
    if secret_scan_targets:
        secret_findings = scan_for_secrets(root, secret_scan_targets)
    else:
        secret_findings = []
    if cache_hits:
        secret_findings = secret_findings + reconstruct_secrets(cache_hits)

    # Which findings are deliberate test fixtures is the project's decision
    # (`[secrets] fixture_paths` in .sarand.toml), never a guess from the
    # path (AGENTS.md 5.67). The flag is recomputed here for every finding,
    # cached ones included, so an edited allowlist always wins.
    # اینکه کدام یافته‌ها fixture عمدی‌اند تصمیم خود پروژه است
    # (`[secrets] fixture_paths` در .sarand.toml) نه حدس از مسیر. پرچم برای
    # همه‌ی یافته‌ها، از کش هم، دوباره محاسبه می‌شود.
    try:
        fixture_paths = load_fixture_paths(root)
    except SecretsConfigError as exc:
        warning(f"{exc} -- every secret finding will count toward the health score.")
        fixture_paths = ()
    secret_findings = mark_fixture_findings(secret_findings, fixture_paths)

    # A file with a content-level finding must not have its full source
    # embedded either -- move it from "included" to "excluded" (§4.10).
    # فایلی که یافته‌ی سطح-محتوا دارد نباید سورس کاملش هم embed شود (§4.10).
    included, excluded_secrets = exclude_flagged_files(
        included, excluded_secrets, secret_findings
    )

    if config.use_cache:
        save_cache(
            config.output_dir,
            root,
            build_cache_entries(records, todos, secret_findings),
        )

    if secret_findings:
        warning(
            f"{len(secret_findings)} potential secret(s) found -- affected file(s) excluded from the report."
        )
    if excluded_secrets:
        warning(
            f"{len(excluded_secrets)} credential-shaped file(s) excluded from the report."
        )

    env = collect_environment_info(root)
    git = await collect_git_snapshot(root)

    # Analyzer pipeline: discover, filter to matching languages, run
    # tests and quality checks *concurrently* per language.
    # خط‌لوله‌ی آنالایزر: کشف، فیلتر به زبان‌های منطبق، اجرای *هم‌زمان*
    # تست و کیفیت به‌ازای هر زبان.
    all_analyzers = discover_analyzers()
    active = matching_analyzers(root, all_analyzers)
    # Hybrid projects only: analyzers that do not match the root run inside
    # the application components instead (core/per_component.py).
    # فقط پروژه‌ی ترکیبی: آنالایزرهایی که ریشه را match نمی‌کنند داخل
    # اجزای application اجرا می‌شوند (core/per_component.py).
    component_plan = plan_component_runs(
        root, components, all_analyzers, active, workspaces
    )

    # BUG FIX (user report: --full "gets stuck on Git information" for
    # ~9 minutes): git.py's own collection is fast -- what actually ran
    # silently for most of that time is this analyzer pipeline (cargo
    # fmt/clippy/test, cargo audit, ruff, pytest, bandit, pip-audit for
    # a Rust+Python project under --full), which never printed a single
    # status() message. The terminal's last visible line stayed
    # "Collecting Git information..." the entire time purely because
    # nothing after it ever updated the screen -- not because git
    # itself was slow. These status()/timing lines don't make the
    # underlying compile/lint/test/audit work any faster (a phone CPU
    # compiling a pyo3 crate via cargo clippy/test genuinely takes
    # real time), but they turn invisible waiting into visible,
    # diagnosable waiting, and reveal exactly which phase to
    # investigate further if it's still the actual bottleneck.
    #
    # اصلاح باگ (گزارش کاربر: --full حدود ۹ دقیقه "روی Git information
    # می‌ماند"): جمع‌آوری خودِ git.py سریع است -- چیزی که واقعاً بیشتر
    # آن مدت را بی‌صدا اجرا می‌شد همین خط‌لوله‌ی آنالایزر است (cargo
    # fmt/clippy/test، cargo audit، ruff، pytest، bandit، pip-audit
    # برای یک پروژه‌ی Rust+Python زیر --full)، که هیچ‌وقت حتی یک پیام
    # status() چاپ نمی‌کرد. آخرین خط دیده‌شده‌ی ترمینال کل آن مدت روی
    # "Collecting Git information..." می‌ماند صرفاً چون چیزی بعدش
    # صفحه را آپدیت نمی‌کرد -- نه چون خودِ git کند بود. این خطوط
    # status()/زمان‌سنجی کار زیرین کامپایل/lint/تست/audit را سریع‌تر
    # نمی‌کنند (کامپایل یک crate پای‌او‌تری با cargo clippy/test روی
    # CPU گوشی واقعاً زمان می‌برد)، اما انتظار نامرئی را به انتظار
    # مرئی و قابل‌بررسی تبدیل می‌کنند، و اگر باز هم واقعاً گلوگاه‌جایی
    # باشد، مشخص می‌کنند دقیقاً کدام فاز را باید بیشتر بررسی کرد.
    if config.skip_tests:
        status("Tests skipped by user request")
        test_results = []
    else:
        names = ", ".join(a.name for a in active) or "none"
        status(f"Running tests ({names})...")
        t0 = time.perf_counter()
        test_results = await run_tests_concurrently(root, active)
        test_results += await run_component_tests(component_plan)
        status(f"Tests finished in {time.perf_counter() - t0:.1f}s")

    quality_results = []
    if config.run_quality:
        names = ", ".join(a.name for a in active) or "none"
        status(f"Running quality checks ({names})...")
        t0 = time.perf_counter()
        quality_results = await run_quality_concurrently(root, active)
        quality_results += await run_component_quality(component_plan)
        status(f"Quality checks finished in {time.perf_counter() - t0:.1f}s")

    security_results = []
    if config.run_security:
        # Threaded through as an env var, not a new LanguageAnalyzer
        # protocol parameter: that protocol is also implemented by
        # third-party plugins (see the "Writing a plugin analyzer"
        # section of README.md, registered under the
        # `sarand.analyzers` entry-point group) -- changing its
        # run_security(root) signature would be a breaking change for
        # every existing plugin. An env var reaches the same handful
        # of security-analyzer call sites (python_analyzer.py,
        # rust_analyzer.py) without touching that contract at all.
        #
        # با یک متغیر محیطی منتقل می‌شود، نه یک پارامتر جدید در
        # پروتکل LanguageAnalyzer: آن پروتکل توسط پلاگین‌های شخص‌ثالث
        # هم پیاده‌سازی می‌شود (بخش «Writing a plugin analyzer» در
        # README.md، ثبت‌شده زیر گروه entry-point به نام
        # `sarand.analyzers`) -- تغییر امضای run_security(root) یک
        # تغییر شکننده برای هر پلاگین موجود می‌بود. یک متغیر محیطی به
        # همان چند نقطه‌ی فراخوانیِ آنالایزر امنیتی (python_analyzer.py،
        # rust_analyzer.py) می‌رسد بدون این‌که اصلاً آن قرارداد را
        # دست بزند.
        if config.skip_audit:
            os.environ["SARAND_SKIP_AUDIT"] = "1"
        names = ", ".join(a.name for a in active) or "none"
        status(f"Running security checks ({names})...")
        t0 = time.perf_counter()
        security_results = await run_security_concurrently(root, active)
        security_results += await run_component_security(component_plan)
        status(f"Security checks finished in {time.perf_counter() - t0:.1f}s")

        # Project-wide (not per-language) security passes -- gitleaks
        # and syft don't belong to any single LanguageAnalyzer, so they
        # run once here and their results join the same list, same
        # rendering, same health-score consideration as every other
        # security check. Not gated by SARAND_SKIP_AUDIT: neither makes
        # a network call to a vulnerability database, so the "fixed
        # external cost" reasoning that flag exists for doesn't apply.
        #
        # پاس‌های امنیتیِ کل‌پروژه (نه به‌ازای هر زبان) -- gitleaks و
        # syft به هیچ LanguageAnalyzer خاصی تعلق ندارند، پس یک‌بار
        # همین‌جا اجرا می‌شوند و نتیجه‌شان به همان لیست، همان رندر،
        # همان محاسبه‌ی امتیاز سلامت بقیه‌ی چک‌های امنیتی می‌پیوندد.
        # با SARAND_SKIP_AUDIT گیت نمی‌شوند: هیچ‌کدام تماس شبکه‌ای با
        # یک پایگاه‌داده‌ی آسیب‌پذیری نمی‌زنند، پس استدلال «هزینه‌ی
        # خارجیِ ثابت» که آن پرچم برایش وجود دارد، اینجا صدق نمی‌کند.
        # The lockfile check is the same shape: project-wide, offline,
        # pure Python -- it joins the same list for the same reasons.
        # چک lockfile هم همین شکل را دارد: کل‌پروژه، آفلاین، پایتون خالص --
        # به همین دلایل به همان لیست می‌پیوندد.
        gitleaks_result, syft_result, lockfile_result = await asyncio.gather(
            run_gitleaks(root), run_syft(root), run_lockfile_check(root)
        )
        security_results = security_results + [
            gitleaks_result,
            syft_result,
            lockfile_result,
        ]

        # gitleaks is the deeper detector (§4.10): a file it flagged must not
        # have its source embedded either. Only files actually slated for
        # embedding are touched; findings that exist only in git history are
        # ignored. Without --security gitleaks does not run, so this block
        # does not either.
        # gitleaks دیتکتور عمیق‌تر است (§4.10): فایلی که پرچم بزند نباید
        # سورسش embed شود. فقط فایل‌هایی که قرار است embed شوند لمس می‌شوند.
        flagged_by_gitleaks = gitleaks_flagged_paths(gitleaks_result.raw_output)
        if flagged_by_gitleaks:
            before = len(excluded_secrets)
            included, excluded_secrets = exclude_paths(
                included, excluded_secrets, flagged_by_gitleaks
            )
            moved = len(excluded_secrets) - before
            if moved:
                warning(
                    f"{moved} file(s) flagged by gitleaks excluded from the report."
                )

    failures = classify_failures(test_results, quality_results, security_results)
    known_entries = known_issue_entries(failures)
    known = [text for _, text in known_entries]
    advisories = collect_advisories(security_results)

    # R14-A: the repository structure reads only files the report may read (nothing
    # flagged as a secret) and never executes them.
    # R14-A: ساختار مخزن فقط فایل‌های مجاز گزارش را می‌خواند و هرگز اجرا نمی‌کند.
    structure = None
    if config.structure:
        status("Building the repository structure...")
        # Imported only here: a run without --structure must not load the structure
        # package (docs/FINDINGS_BASELINE.md, "Independence").
        # فقط اینجا import می‌شود: اجرای بدون --structure نباید بسته‌ی structure را
        # بارگذاری کند.
        from sarand.structure import build_structure

        structure = build_structure(root, included, skipped)
    structure_payload_plain: dict[str, Any] | None = None
    structure_comparison: dict[str, Any] | None = None
    if structure is not None and (
        baseline_reference is not None or config.structure_snapshot is not None
    ):
        from sarand.structure.serialize import structure_payload
        from sarand.structure.snapshot import canonical_json

        # One plain JSON copy serves both the comparison and the snapshot.
        # یک نسخه‌ی JSON ساده هم برای مقایسه و هم برای snapshot کافی است.
        structure_payload_plain = json.loads(
            canonical_json(structure_payload(structure))
        )
    if structure_payload_plain is not None and baseline_reference is not None:
        from sarand.structure.compare import compare_structures
        from sarand.structure.snapshot import SOURCE_CURRENT, Reference

        status("Comparing the structure with the baseline...")
        current = Reference(
            structure=structure_payload_plain,
            source=SOURCE_CURRENT,
            excluded_secret_files=tuple(sorted(p.as_posix() for p in excluded_secrets)),
            max_file_size=config.max_file_size,
        )
        structure_comparison = dict(
            compare_structures(baseline_reference, current).payload
        )

    data = ReportData(
        project_root=root,
        generated_at=datetime.now(UTC),
        environment=env,
        git=git,
        stats=stats,
        detection=detection,
        used_rust_core=RUST_CORE_AVAILABLE,
        todos=todos,
        todos_suppressed=todos_suppressed,
        scan_skipped=scan_problems.skipped,
        scan_skipped_samples=list(scan_problems.samples),
        test_results=test_results,
        quality_results=quality_results,
        security_results=security_results,
        tree_text=tree_text,
        included_files=included,
        skipped_files=skipped,
        structure=structure,
        structure_comparison=structure_comparison,
        excluded_secret_files=excluded_secrets,
        secret_findings=secret_findings,
        known_issues=known,
        known_issue_ids=[fid for fid, _ in known_entries],
        failures=failures,
        advisories=advisories,
        workspace=workspace,
        extra_workspaces=workspaces[1:],
        package_paths=list(dict.fromkeys(t.path for t in component_plan.targets)),
        kubernetes=kubernetes,
        compose=compose,
        makefile=makefile,
        monorepo_tools=monorepo_tools,
        frameworks_declared=frameworks_declared,
        components=components,
    )

    data.ai_summary = generate_ai_summary(data)
    data.suggested_reading_order = suggest_reading_order(root, included)

    if config.health_score:
        data.health = compute_health_score(data)

    # R14-D1 (F1/F2): the findings are compared after the health score exists, because
    # the gate reads its critical ids; `--no-health` leaves them unknown (reported as
    # uncertain, never guessed).
    # R14-D1 (F1/F2): مقایسه‌ی یافته‌ها بعد از ساخته‌شدن health انجام می‌شود، چون gate
    # شناسه‌های بحرانی آن را می‌خواند؛ با `--no-health` نامعلوم می‌مانند (uncertain، نه حدس).
    gate_result: dict[str, Any] | None = None
    if findings_reference is not None:
        from sarand.renderers.json_renderer import JSON_SCHEMA_VERSION

        status("Comparing the findings with the baseline...")
        findings_current = current_view(
            schema=parse_schema(JSON_SCHEMA_VERSION),
            failures=failures,
            advisories=advisories,
            secret_findings=secret_findings,
            test_results=test_results,
            quality_results=quality_results,
            security_results=security_results,
            included_files=[p.as_posix() for p in included],
            excluded_secret_files=[p.as_posix() for p in excluded_secrets],
            skipped_files=[p.as_posix() for p, _ in skipped],
            critical_ids=None if data.health is None else data.health.critical_ids,
        )
        findings_baseline = compare_findings(findings_reference, findings_current)
        gate_result = evaluate_gate(
            config.baseline_gate or POLICY_NEVER,
            findings_reference,
            findings_current,
            findings_baseline,
        )
        findings_baseline["gate"] = gate_result
        data.baseline = findings_baseline

    if config.relevant_source_tokens is not None:
        from sarand.core.relevant_source import select_relevant_source

        data.relevant_source = select_relevant_source(
            data, config.relevant_source_tokens, config.focus
        )

    announce_report_replacement(output_path)

    pdf_failed = False
    if config.output_format == "pdf":
        # PDF is binary and rendered through an external tool (renderers/pdf.py),
        # so it writes the staged file itself; `ok=False` selects the Markdown
        # fallback and never crashes on a missing engine.
        # PDF باینری است و با ابزار خارجی رندر می‌شود (renderers/pdf.py)، پس خودش فایلِ
        # مرحله‌ای را می‌نویسد؛ `ok=False` جایگزین Markdown را برمی‌گزیند و هرگز به‌خاطر
        # نبودِ موتور کرش نمی‌کند.
        from sarand.renderers import pdf as pdf_renderer

        def render_pdf(staged_path: Path) -> None:
            outcome = pdf_renderer.render_to_file(
                data,
                staged_path,
                include_source=config.include_source,
                full_output=config.full,
            )
            if not outcome.ok:
                raise _PdfRenderFailure(outcome.detail)

        try:
            digest = atomic_write_report(output_path, render_pdf)
        except _PdfRenderFailure as exc:
            output_path = _write_pdf_fallback(data, output_path, str(exc), config)
            digest = _sha256_file(output_path)
            pdf_failed = True
    else:

        def render_report(staged_path: Path) -> None:
            content = _RENDERERS[config.output_format].render(
                data, include_source=config.include_source, full_output=config.full
            )
            staged_path.write_text(content, encoding="utf-8")

        digest = atomic_write_report(output_path, render_report)

    success("Report completed")
    print()
    print("=" * 60)
    print(f"Project: {root}")
    print(f"Detected: {', '.join(detection.languages) or 'unknown'}")
    print(f"Engine  : {'Rust core' if RUST_CORE_AVAILABLE else 'pure-Python fallback'}")
    print(f"Output  : {output_path}")
    print(f"SHA256  : {digest}")
    print(
        f"Files   : {len(included)} included / {len(skipped)} skipped / {len(excluded_secrets)} excluded (secrets)"
    )
    snapshot_failed = False
    if structure_payload_plain is not None and config.structure_snapshot is not None:
        if pdf_failed:
            warning(
                "The structure snapshot was not written: the report did not succeed."
            )
        else:
            from sarand.structure.snapshot import make_snapshot
            from sarand.structure.snapshot_io import SnapshotTargetError, write_snapshot

            try:
                written = write_snapshot(
                    config.structure_snapshot,
                    make_snapshot(
                        structure_payload_plain,
                        excluded_secret_files=[p.as_posix() for p in excluded_secrets],
                        max_file_size=config.max_file_size,
                    ),
                    replace=config.replace_structure_snapshot,
                )
            except (SnapshotTargetError, OSError, ValueError) as exc:
                snapshot_failed = True
                error(f"The structure snapshot was not written: {exc}")
            else:
                print(f"Snapshot: {written.path} ({written.digest})")
                if written.previous is not None:
                    print(f"Previous: {written.previous}")
    if secret_findings:
        print(
            f"Secrets : {len(secret_findings)} potential secret(s) found -- affected files excluded, see report"
        )
    if config.use_cache:
        print(
            f"Cache   : {len(cache_hits)} file(s) skipped (unchanged since last --cache run)"
        )
    if data.health:
        health_text = (
            f"{data.health.score}/100 ({data.health.grade}) -- "
            f"{coverage_oneline(data.health)}"
        )
        print(f"Health  : {health_text}")
    gate_failed = _print_gate(gate_result)
    print("=" * 60)
    # The gate is the signal a pipeline acts on, so it wins over a report or snapshot
    # error (that error was printed above).
    # gate همان سیگنالی است که pipeline به آن عمل می‌کند، پس بر خطای گزارش یا snapshot
    # مقدم است (آن خطا بالاتر چاپ شده).
    if gate_failed:
        return EXIT_GATE_FAILED
    return 1 if pdf_failed or snapshot_failed else 0


_GATE_LINES = 10


def _print_gate(gate: dict[str, Any] | None) -> bool:
    """Print the gate result in the closing summary; True when the gate failed.
    نتیجه‌ی gate را در خلاصه‌ی پایانی چاپ می‌کند؛ وقتی gate رد شده باشد True برمی‌گرداند.
    """
    if gate is None or gate["verdict"] == VERDICT_NOT_GATED:
        return False
    failed = gate["verdict"] == VERDICT_FAIL
    uncertain = gate["uncertain"]
    tail = f", {len(uncertain)} uncertain" if uncertain else ""
    if failed:
        print(
            f"Gate    : FAILED (policy {gate['policy']}): "
            f"{len(gate['failed_on'])} finding(s){tail}"
        )
        for item in gate["failed_on"][:_GATE_LINES]:
            print(f"          - {item['class']}: {item['label']} ({item['rule']})")
        hidden = len(gate["failed_on"]) - _GATE_LINES
        if hidden > 0:
            print(f"          ... and {hidden} more (see the report)")
    else:
        print(f"Gate    : passed (policy {gate['policy']}){tail}")
    if uncertain:
        print("          uncertain findings never fail the gate; see the report")
    return failed


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    harden_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.focus is not None and args.relevant_source is None:
        parser.error("--focus needs --relevant-source")

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
