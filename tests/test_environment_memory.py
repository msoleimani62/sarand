"""Memory reporting must say the same thing on every OS (AGENTS.md §5.13)."""

from __future__ import annotations

import sys
import types

import pytest
import sarand.scanners.environment as env

_MEMINFO = "MemTotal:        8000000 kB\nMemFree:          100000 kB\nMemAvailable:    2000000 kB\n"
_VM_STAT = (
    "Mach Virtual Memory Statistics: (page size of 16384 bytes)\n"
    "Pages free:                               1000.\n"
    "Pages active:                            50000.\n"
    "Pages inactive:                           2000.\n"
    "Pages speculative:                         500.\n"
)


def test_parse_meminfo_reads_total_and_available() -> None:
    assert env._parse_meminfo(_MEMINFO) == (2000000 * 1024, 8000000 * 1024)


def test_parse_meminfo_without_a_total_is_unusable() -> None:
    assert env._parse_meminfo("MemAvailable: 5 kB\n") is None
    assert env._parse_meminfo("") is None


def test_parse_vm_stat_adds_free_inactive_and_speculative_pages() -> None:
    assert env._parse_vm_stat(_VM_STAT) == (1000 + 2000 + 500) * 16384


def test_parse_vm_stat_rejects_unrecognized_output() -> None:
    assert env._parse_vm_stat("something else") is None
    assert (
        env._parse_vm_stat(
            "Mach Virtual Memory Statistics: (page size of 4096 bytes)\n"
        )
        is None
    )


def test_summary_format_is_unchanged_for_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(env, "_proc_meminfo", lambda: env._parse_meminfo(_MEMINFO))
    monkeypatch.setattr(env, "sys", types.SimpleNamespace(platform="linux"))

    assert env._memory_summary() == "1953 MiB available / 7812 MiB total"


def test_windows_uses_its_own_reading_and_never_proc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(env, "sys", types.SimpleNamespace(platform="win32"))
    monkeypatch.setattr(env, "_windows_memory", lambda: (2 * 1024**3, 8 * 1024**3))

    def must_not_be_read():
        raise AssertionError("/proc/meminfo must not be consulted on Windows")

    monkeypatch.setattr(env, "_proc_meminfo", must_not_be_read)

    assert env._memory_summary() == "2048 MiB available / 8192 MiB total"


def test_macos_combines_sysconf_total_with_vm_stat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(env, "sys", types.SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(env, "_proc_meminfo", lambda: None)
    monkeypatch.setattr(env, "_sysconf_total", lambda: 16 * 1024**3)
    monkeypatch.setattr(env, "run_cmd", lambda cmd, cwd, timeout: (0, _VM_STAT, 0.0))

    available, total = env._memory_reading() or (None, 0)

    assert total == 16 * 1024**3
    assert available == 3500 * 16384


def test_unreadable_vm_stat_still_reports_the_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(env, "sys", types.SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(env, "_proc_meminfo", lambda: None)
    monkeypatch.setattr(env, "_sysconf_total", lambda: 4 * 1024**3)
    monkeypatch.setattr(env, "run_cmd", lambda cmd, cwd, timeout: (1, "", 0.0))

    assert env._memory_summary() == "4096 MiB total"


def test_nothing_readable_is_reported_as_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(env, "sys", types.SimpleNamespace(platform="freebsd"))
    monkeypatch.setattr(env, "_proc_meminfo", lambda: None)
    monkeypatch.setattr(env, "_sysconf_total", lambda: None)

    assert env._memory_summary() == "(unknown)"


@pytest.mark.skipif(sys.platform == "win32", reason="os.sysconf is POSIX-only")
def test_sysconf_total_multiplies_pages_by_page_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {"SC_PHYS_PAGES": 1000, "SC_PAGE_SIZE": 4096}
    monkeypatch.setattr(env.os, "sysconf", lambda name: values[name])

    assert env._sysconf_total() == 4096000


@pytest.mark.skipif(sys.platform == "win32", reason="os.sysconf is POSIX-only")
def test_sysconf_total_tolerates_unknown_names(monkeypatch: pytest.MonkeyPatch) -> None:
    def unknown(name):
        raise ValueError("unrecognized configuration name")

    monkeypatch.setattr(env.os, "sysconf", unknown)

    assert env._sysconf_total() is None


def test_the_real_summary_is_never_empty() -> None:
    summary = env._memory_summary()

    assert summary == "(unknown)" or "MiB" in summary
