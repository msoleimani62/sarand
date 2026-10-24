"""Plugin hardening (backlog item 11, round R10a) and the filelock range.

* A plugin phase that never finishes is cancelled and reported as a skipped
  check (it used to hang the scan).
* `--doctor` can list installed plugins and say why one was skipped.
* `filelock` 4.x is allowed: the whole suite passed with it.

سخت‌سازی پلاگین (آیتم ۱۱): سقف زمانی برای هر فاز، فهرست پلاگین‌ها در --doctor، و
بازشدن سقف filelock.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest import mock

from sarand.analyzers import registry
from sarand.analyzers.plugin_adapter import PLUGIN_PHASE_TIMEOUT, PluginAnalyzer
from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult

_ROOT = Path(__file__).resolve().parent.parent


class _Slow:
    name = "Slow"

    def matches(self, root: Path) -> bool:
        return True

    def entry_points(self, root: Path) -> list[str]:
        return []

    async def run_tests(self, root: Path) -> CommandResult | None:
        await asyncio.sleep(30)
        return None

    async def run_quality(self, root: Path) -> list[CommandResult]:
        await asyncio.sleep(30)
        return []

    async def run_security(self, root: Path) -> list[CommandResult]:
        await asyncio.sleep(30)
        return []


class _RaisesTimeout(_Slow):
    name = "Raises"

    async def run_tests(self, root: Path) -> CommandResult | None:
        raise TimeoutError("its own network call")


def _wrap(inner: _Slow, limit: float = 0.05) -> PluginAnalyzer:
    return PluginAnalyzer(inner, inner.name, phase_timeout=limit)


def test_the_phase_limit_is_longer_than_the_longest_command() -> None:
    assert PLUGIN_PHASE_TIMEOUT > LONG_CMD_TIMEOUT


def test_a_plugin_that_never_finishes_tests_is_cancelled_and_reported() -> None:
    started = time.monotonic()
    result = asyncio.run(_wrap(_Slow()).run_tests(Path(".")))
    assert time.monotonic() - started < 5
    assert isinstance(result, CommandResult)
    assert result.skipped
    assert "Slow" in result.skip_reason
    assert "did not finish" in result.skip_reason


def test_quality_and_security_phases_are_cancelled_too() -> None:
    plugin = _wrap(_Slow())
    quality = asyncio.run(plugin.run_quality(Path(".")))
    security = asyncio.run(plugin.run_security(Path(".")))
    for results in (quality, security):
        assert len(results) == 1
        assert results[0].skipped
        assert "did not finish" in results[0].skip_reason


def test_a_timeout_raised_by_the_plugin_is_not_called_a_phase_timeout() -> None:
    result = asyncio.run(_wrap(_RaisesTimeout(), limit=5).run_tests(Path(".")))
    assert isinstance(result, CommandResult)
    assert result.skipped
    assert "did not finish" not in result.skip_reason
    assert "TimeoutError" in result.skip_reason


class _EntryPoint:
    def __init__(self, name: str, value: str, target: object) -> None:
        self.name = name
        self.value = value
        self._target = target

    def load(self) -> object:
        if isinstance(self._target, Exception):
            raise self._target
        return self._target


class _Good(_Slow):
    name = "GoodPlugin"


class _NamedLikeABuiltin(_Slow):
    name = "Python"


class _Incomplete:
    name = "Incomplete"


def test_plugin_statuses_say_what_loaded_and_why_the_rest_did_not() -> None:
    entries = [
        _EntryPoint("a-good", "pkg.good:Plugin", _Good),
        _EntryPoint("b-clash", "pkg.clash:Plugin", _NamedLikeABuiltin),
        _EntryPoint("c-incomplete", "pkg.inc:Plugin", _Incomplete),
        _EntryPoint("d-broken", "pkg.broken:Plugin", RuntimeError("boom")),
    ]
    with mock.patch.object(registry, "entry_points", return_value=entries):
        statuses = registry.plugin_statuses()
        analyzers = registry.discover_analyzers()
    by_name = {status.entry_name: status for status in statuses}
    assert list(by_name) == ["a-good", "b-clash", "c-incomplete", "d-broken"]
    assert by_name["a-good"].loaded and by_name["a-good"].detail == "GoodPlugin"
    assert not by_name["b-clash"].loaded
    assert "already registered" in by_name["b-clash"].detail
    assert not by_name["c-incomplete"].loaded
    assert "matches" in by_name["c-incomplete"].detail
    assert not by_name["d-broken"].loaded
    assert "boom" in by_name["d-broken"].detail
    assert [a.name for a in analyzers].count("GoodPlugin") == 1
    assert "Incomplete" not in [a.name for a in analyzers]


def test_unreadable_entry_points_give_no_statuses_and_no_crash() -> None:
    with mock.patch.object(registry, "entry_points", side_effect=OSError("bad")):
        assert registry.plugin_statuses() == []
        assert registry.discover_analyzers()


def test_filelock_four_is_allowed() -> None:
    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"filelock>=3.14,<5"' in text
