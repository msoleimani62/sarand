"""Tests for the device_report subsystem (ported from device-audit.sh)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sarand.device_report.classify import (
    DO_NOT_DELETE_AUTOMATICALLY,
    LIKELY_RECLAIMABLE,
    REQUIRES_REVIEW,
    SAFE_TO_REVIEW,
    SYSTEM_CRITICAL,
    classify_path,
)
from sarand.device_report.config import UNLIMITED, build_parser, resolve_config
from sarand.device_report.walking import (
    find_dirs_named,
    is_excluded,
    path_size_bytes,
    sha256_file,
    walk_pruned,
)

# --- classify_path -----------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/home/user/.cache/pip", LIKELY_RECLAIMABLE),
        ("/home/user/project/node_modules/x", LIKELY_RECLAIMABLE),
        ("/home/user/project/target/debug", LIKELY_RECLAIMABLE),
        ("/home/user/.cargo/registry/src", SAFE_TO_REVIEW),
        ("/home/user/.cargo/git/checkouts", SAFE_TO_REVIEW),
        ("/home/user/Downloads", SAFE_TO_REVIEW),
        ("/home/user/project/.git", DO_NOT_DELETE_AUTOMATICALLY),
        ("/home/user/project/.git/objects/ab", DO_NOT_DELETE_AUTOMATICALLY),
        ("/system/bin/sh", SYSTEM_CRITICAL),
        ("/data/app/com.foo", SYSTEM_CRITICAL),
        ("/data/misc/wifi", SYSTEM_CRITICAL),
        ("/home/user/random/stuff", REQUIRES_REVIEW),
    ],
)
def test_classify_path(path: str, expected: str) -> None:
    assert classify_path(path) == expected


# --- config: --full / --quick / --top interaction --------------------------


def test_full_overrides_quick_and_removes_top_cap() -> None:
    parser = build_parser()
    args = parser.parse_args(["--quick", "--full", "-r", "/tmp"])
    config = resolve_config(args)
    assert config.quick_mode is False
    assert config.top_n == UNLIMITED


def test_explicit_top_beats_full() -> None:
    parser = build_parser()
    args = parser.parse_args(["--full", "--top", "5", "-r", "/tmp"])
    config = resolve_config(args)
    assert config.top_n == 5


def test_plain_quick_without_full() -> None:
    parser = build_parser()
    args = parser.parse_args(["--quick", "-r", "/tmp"])
    config = resolve_config(args)
    assert config.quick_mode is True


def test_missing_scan_root_raises() -> None:
    parser = build_parser()
    args = parser.parse_args(["-r", "/this/path/does/not/exist/xyz"])
    with pytest.raises(ValueError, match="No valid scan roots"):
        resolve_config(args)


def test_default_top_n_when_neither_full_nor_explicit() -> None:
    parser = build_parser()
    args = parser.parse_args(["-r", "/tmp"])
    config = resolve_config(args)
    assert config.top_n == 30


# --- walking: portable primitives -------------------------------------


def test_path_size_bytes_file(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_bytes(b"hello world")
    assert path_size_bytes(f) == 11


def test_path_size_bytes_directory_sums_children(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_bytes(b"12345")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_bytes(b"1234567890")
    assert path_size_bytes(tmp_path) == 15


def test_path_size_bytes_missing_path_is_zero(tmp_path: Path) -> None:
    assert path_size_bytes(tmp_path / "does-not-exist") == 0


def test_sha256_file_matches_known_hash(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_bytes(b"")
    # SHA-256 of the empty string, a well-known constant value.
    assert (
        sha256_file(f)
        == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"[:64]
    )


def test_sha256_file_missing_path_returns_none(tmp_path: Path) -> None:
    assert sha256_file(tmp_path / "does-not-exist") is None


def test_is_excluded_matches_exact_and_children() -> None:
    assert is_excluded(Path("/a/b"), ["/a/b"]) is True
    assert is_excluded(Path("/a/b/c"), ["/a/b"]) is True
    assert is_excluded(Path("/a/bc"), ["/a/b"]) is False
    assert is_excluded(Path("/a/other"), ["/a/b"]) is False


def test_walk_pruned_respects_max_depth(tmp_path: Path) -> None:
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (tmp_path / "a" / "shallow.txt").write_text("x")
    (deep / "deepfile.txt").write_text("x")

    shallow_files = {
        name
        for _root, _dirs, files in walk_pruned(tmp_path, max_depth=2)
        for name in files
    }
    assert "shallow.txt" in shallow_files
    assert "deepfile.txt" not in shallow_files

    all_files = {
        name
        for _root, _dirs, files in walk_pruned(tmp_path, max_depth=0)
        for name in files
    }
    assert "deepfile.txt" in all_files


def test_walk_pruned_respects_excludes(tmp_path: Path) -> None:
    excluded_dir = tmp_path / "skip_me"
    excluded_dir.mkdir()
    (excluded_dir / "secret.txt").write_text("x")
    (tmp_path / "keep.txt").write_text("x")

    seen_files = {
        name
        for _root, _dirs, files in walk_pruned(
            tmp_path, exclude_paths=[str(excluded_dir)]
        )
        for name in files
    }
    assert "keep.txt" in seen_files
    assert "secret.txt" not in seen_files


def test_find_dirs_named_prunes_matched_subtree(tmp_path: Path) -> None:
    nm = tmp_path / "project" / "node_modules"
    nm.mkdir(parents=True)
    (nm / "nested_pkg").mkdir()
    (nm / "nested_pkg" / "node_modules").mkdir()

    found = list(find_dirs_named(tmp_path, {"node_modules"}))
    # Only the outer node_modules should be reported -- its own subtree
    # (including the nested node_modules inside it) must be pruned.
    assert found == [nm]


# --- environment: run_tool_checked (present-but-broken binaries) ----------


def test_run_tool_checked_treats_nonzero_exit_as_not_ok(tmp_path: Path) -> None:
    # Regression test: lscpu is commonly installed but still exits
    # non-zero under a Termux/Kali proot (confirmed live on-device --
    # `/sys/devices/system/cpu/possible` isn't reachable there). A
    # present-but-failing binary must be treated the same as a missing
    # one so callers fall back to their portable /proc reader instead
    # of printing the raw error text into the report.
    from sarand.device_report import environment as env

    ok, _output = env.run_tool_checked(tmp_path, "false")
    assert ok is False


def test_run_tool_checked_treats_zero_exit_with_output_as_ok(tmp_path: Path) -> None:
    from sarand.device_report import environment as env

    ok, output = env.run_tool_checked(tmp_path, "echo", "hello")
    assert ok is True
    assert "hello" in output


def test_run_tool_checked_missing_binary_is_not_ok(tmp_path: Path) -> None:
    from sarand.device_report import environment as env

    ok, _output = env.run_tool_checked(tmp_path, "this-binary-does-not-exist-xyz")
    assert ok is False


# --- feedback-driven fixes (sarand-report-feedback.md) ---------------------


def test_classify_path_ruff_cache_is_reclaimable() -> None:
    assert classify_path("/home/user/project/.ruff_cache") == LIKELY_RECLAIMABLE


def test_full_sets_expand_aggregates_and_removes_min_top_space() -> None:
    parser = build_parser()
    config = resolve_config(parser.parse_args(["--full", "-r", "/tmp"]))
    assert config.expand_aggregates is True
    assert config.min_top_space_mb == 0.0


def test_default_min_top_space_and_expand_aggregates() -> None:
    parser = build_parser()
    config = resolve_config(parser.parse_args(["-r", "/tmp"]))
    assert config.min_top_space_mb == 1.0
    assert config.expand_aggregates is False
    assert config.summary_only is False


def test_full_and_summary_only_are_mutually_exclusive() -> None:
    parser = build_parser()
    args = parser.parse_args(["--full", "--summary-only", "-r", "/tmp"])
    with pytest.raises(ValueError, match="mutually exclusive"):
        resolve_config(args)


def _isolate_fixed_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent generate_report() from touching real, possibly huge
    system paths during a test.

    BUG FIX: sections 5/6/11 (toolchain, Android/Termux/Kali, downloads)
    check a handful of *fixed* real paths (`~/.cargo`, `/data/data/
    com.termux/...`, `/sdcard/Download`) independently of
    `config.scan_roots` -- correct for the tool's actual job (auditing
    the whole device), but it means a test that only sets `scan_roots`
    to an isolated tmp_path still ends up running path_size_bytes()
    (an uncapped, un-timeout-able recursive os.walk) against the real
    device's actual `~/.cargo/registry` or `/data/data/com.termux/...`.
    Confirmed live: this made the test suite appear to hang on-device,
    since this project's own `~/.cargo/registry` (a real Rust+PyO3
    dependency cache) is genuinely large. Monkeypatching these lists to
    empty keeps every test fast and deterministic regardless of the
    real device's state.

    اصلاح باگ: بخش‌های ۵/۶/۱۱ (toolchain، Android/Termux/Kali،
    downloads) چند مسیر *ثابت* واقعی (`~/.cargo`، `/data/data/
    com.termux/...`، `/sdcard/Download`) را مستقل از
    `config.scan_roots` چک می‌کنند -- برای کار واقعیِ ابزار (بازرسی کل
    دستگاه) درست است، اما یعنی تستی که فقط `scan_roots` را به یک
    tmp_path ایزوله تنظیم کرده، همچنان path_size_bytes() (یک os.walk
    بازگشتیِ بدون سقف و بدون timeout) را روی `~/.cargo/registry` یا
    `/data/data/com.termux/...` واقعیِ دستگاه اجرا می‌کند. زنده تأیید
    شد: همین باعث شد مجموعه‌تست روی دستگاه هنگ به‌نظر برسد، چون
    `~/.cargo/registry` همین پروژه (کش واقعی وابستگی‌های Rust+PyO3)
    واقعاً بزرگ است. مانک‌پچ‌کردن این لیست‌ها به خالی، هر تست را صرف‌نظر
    از وضعیت واقعی دستگاه سریع و قطعی نگه می‌دارد.
    """
    from sarand.device_report import environment as env

    monkeypatch.setattr(env, "TOOLCHAIN_CANDIDATES", ())
    monkeypatch.setattr(env, "TERMUX_PATHS", ())
    monkeypatch.setattr(env, "NETHUNTER_PATHS", ())
    monkeypatch.setattr(env, "DOWNLOAD_CANDIDATES", ())


def test_toolchain_aggregates_pycache_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sarand.device_report.config import DeviceReportConfig
    from sarand.device_report.report import generate_report

    _isolate_fixed_paths(monkeypatch)
    project = tmp_path / "project"
    for i in range(12):
        pycache = project / "pkgroot" / f"pkg{i}" / "__pycache__"
        pycache.mkdir(parents=True)
        (pycache / "mod.pyc").write_bytes(b"x" * 1024)

    config = DeviceReportConfig(
        output_file=tmp_path / "out.md",
        scan_roots=[project],
        top_n=50,
        min_file_size_mb=0.0001,
        dup_min_size_mb=0.0001,
        min_top_space_mb=0.0,
    )
    text = generate_report(config)

    assert "Aggregated: 12 x __pycache__ directories" in text
    # Only the top-5 individual pycache paths should appear in the
    # Build Artifact Directories detail listing, not all 12 -- scope
    # the count to that section specifically, since __pycache__ also
    # legitimately appears elsewhere (e.g. Largest Individual Files,
    # since the tiny .pyc fixtures above clear this test's
    # deliberately tiny min_file_size_mb threshold).
    section = text.split("### Build Artifact Directories")[1].split("\n## ")[0]
    # record_space() doesn't print anything itself -- the aggregate's
    # synthetic path only ever appears later, in the Executive
    # Summary's Top Space Users table, not in this section's own text.
    assert section.count("/__pycache__") == 5  # exactly the top-5 detail lines


def test_toolchain_expand_aggregates_lists_every_pycache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sarand.device_report.config import DeviceReportConfig
    from sarand.device_report.report import generate_report

    _isolate_fixed_paths(monkeypatch)
    project = tmp_path / "project"
    for i in range(12):
        pycache = project / "pkgroot" / f"pkg{i}" / "__pycache__"
        pycache.mkdir(parents=True)
        (pycache / "mod.pyc").write_bytes(b"x" * 1024)

    config = DeviceReportConfig(
        output_file=tmp_path / "out.md",
        scan_roots=[project],
        top_n=50,
        min_file_size_mb=0.0001,
        dup_min_size_mb=0.0001,
        min_top_space_mb=0.0,
        expand_aggregates=True,
    )
    text = generate_report(config)

    assert "Aggregated:" not in text
    for i in range(12):
        assert f"pkg{i}/__pycache__" in text


def test_min_top_space_filters_tiny_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sarand.device_report.config import DeviceReportConfig
    from sarand.device_report.report import generate_report

    _isolate_fixed_paths(monkeypatch)
    project = tmp_path / "project"
    project.mkdir()
    (project / "tiny.txt").write_bytes(b"x" * 100)

    config = DeviceReportConfig(
        output_file=tmp_path / "out.md",
        scan_roots=[project],
        min_top_space_mb=1.0,
    )
    text = generate_report(config)
    assert "tiny.txt" not in text.split("### Top Space Users")[1]


def test_summary_only_omits_detail_sections_but_keeps_executive_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sarand.device_report.config import DeviceReportConfig
    from sarand.device_report.report import generate_report

    _isolate_fixed_paths(monkeypatch)
    project = tmp_path / "project"
    project.mkdir()
    (project / "big.bin").write_bytes(b"x" * (2 * 1024 * 1024))

    config = DeviceReportConfig(
        output_file=tmp_path / "out.md",
        scan_roots=[project],
        summary_only=True,
        min_top_space_mb=0.0,
    )
    text = generate_report(config)

    assert "## 1. System Overview" in text
    assert "## 12. Executive Summary" in text
    for heading in (
        "## 2. Filesystems",
        "## 3. Storage Overview",
        "## 4. Installed Packages",
        "## 5. Development Toolchain",
        "## 6. Android",
        "## 7. Git Repositories",
        "## 8. Largest Individual Files",
        "## 9. Duplicate Files",
        "## 10. Stale Files",
        "## 11. Downloads",
    ):
        assert heading not in text
    # The scan still ran, so the big file must still show up in the summary.
    assert "big.bin" in text


# --- explicit coverage: fixed-path candidate lists really get scanned -----
#
# The tests above monkeypatch TOOLCHAIN_CANDIDATES/TERMUX_PATHS/
# NETHUNTER_PATHS/DOWNLOAD_CANDIDATES to empty so they run fast and
# don't depend on the real device's state (see _isolate_fixed_paths).
# That's coverage of everything BUT those lists. The two tests below
# point them at a fake, controlled directory instead of emptying them,
# so the actual "these fixed paths get walked and recorded" behavior
# has its own explicit test, not just prior manual on-device checks.
#
# پوششِ صریح: این‌که لیست‌های مسیر ثابت واقعاً اسکن می‌شوند
#
# تست‌های بالا TOOLCHAIN_CANDIDATES/TERMUX_PATHS/NETHUNTER_PATHS/
# DOWNLOAD_CANDIDATES را به خالی مانک‌پچ می‌کنند تا سریع اجرا شوند و به
# وضعیت واقعی دستگاه وابسته نباشند (_isolate_fixed_paths را ببینید).
# آن پوششِ همه‌چیز *به‌جز* آن لیست‌هاست. دو تست پایین به‌جای خالی‌کردن،
# آن‌ها را به یک دایرکتوری جعلی و کنترل‌شده اشاره می‌دهند، تا رفتار
# واقعیِ «این مسیرهای ثابت پیمایش و ثبت می‌شوند» تست صریح خودش را
# داشته باشد، نه فقط چک‌های دستیِ قبلی روی خودِ دستگاه.


def test_toolchain_candidates_are_actually_scanned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sarand.device_report import environment as env
    from sarand.device_report.config import DeviceReportConfig
    from sarand.device_report.report import generate_report

    fake_cache = tmp_path / "fake_home" / ".cache"
    fake_cache.mkdir(parents=True)
    (fake_cache / "blob.bin").write_bytes(b"x" * (2 * 1024 * 1024))

    # Only TOOLCHAIN_CANDIDATES points at real (here: fake-but-real-on-
    # disk) content; the other fixed-path lists stay empty so this test
    # isolates exactly the one code path it's meant to cover.
    monkeypatch.setattr(env, "TOOLCHAIN_CANDIDATES", (str(fake_cache),))
    monkeypatch.setattr(env, "TERMUX_PATHS", ())
    monkeypatch.setattr(env, "NETHUNTER_PATHS", ())
    monkeypatch.setattr(env, "DOWNLOAD_CANDIDATES", ())

    # scan_roots is a completely separate, unrelated, empty directory --
    # proving fake_cache is only found because TOOLCHAIN_CANDIDATES
    # names it directly, not because it happens to sit under scan_roots.
    unrelated_root = tmp_path / "unrelated_project"
    unrelated_root.mkdir()

    config = DeviceReportConfig(
        output_file=tmp_path / "out.md",
        scan_roots=[unrelated_root],
        min_top_space_mb=0.0,
    )
    text = generate_report(config)

    section = text.split("### Known Toolchain and Cache Directories")[1].split(
        "\n### "
    )[0]
    assert str(fake_cache) in section
    assert "2.0 MiB" in section
    # It must also reach the Executive Summary's Top Space Users table,
    # i.e. record_space() actually fired for it, not just the listing.
    summary = text.split("### Top Space Users")[1]
    assert str(fake_cache) in summary


def test_download_candidates_are_actually_scanned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sarand.device_report import environment as env
    from sarand.device_report.config import DeviceReportConfig
    from sarand.device_report.report import generate_report

    fake_downloads = tmp_path / "fake_home" / "Downloads"
    fake_downloads.mkdir(parents=True)
    (fake_downloads / "archive.zip").write_bytes(b"x" * (1024 * 1024))

    monkeypatch.setattr(env, "TOOLCHAIN_CANDIDATES", ())
    monkeypatch.setattr(env, "TERMUX_PATHS", ())
    monkeypatch.setattr(env, "NETHUNTER_PATHS", ())
    monkeypatch.setattr(env, "DOWNLOAD_CANDIDATES", (str(fake_downloads),))

    unrelated_root = tmp_path / "unrelated_project"
    unrelated_root.mkdir()

    config = DeviceReportConfig(
        output_file=tmp_path / "out.md",
        scan_roots=[unrelated_root],
        min_top_space_mb=0.0,
    )
    text = generate_report(config)

    section = text.split("## 11. Downloads and Archives")[1].split("\n## ")[0]
    assert "archive.zip" in section
    summary = text.split("### Top Space Users")[1]
    assert str(fake_downloads) in summary
