"""Isolation layer between sarand and third-party analyzer plugins
(backlog item 14, "Plugin System").

Evidence-first audit of the existing `sarand.analyzers` entry-point
mechanism found it works for the happy path only:

1. **Load-time isolation only.** `discover_analyzers()` caught errors
   while importing/instantiating a plugin, but every later call was
   unguarded: `matches()` ran bare in `matching_analyzers`, and the
   three `run_*_concurrently` helpers use `asyncio.gather` without
   `return_exceptions`. One plugin raising anywhere crashed the whole
   run and discarded every other analyzer's results.
2. **The documented contract was incomplete.** The README told authors
   to implement four methods (`matches`, `entry_points`, `run_tests`,
   `run_quality`); the registry calls a fifth, `run_security`. A plugin
   written from the README loaded fine and then crashed the security
   phase with `AttributeError`.
3. **No version compatibility story.** The protocol already grew once
   (`run_security`) and nothing told an old plugin or a new sarand.
4. **Duplicates were not handled.** A plugin named like a built-in
   (the README's own example is a Zig plugin; Zig is built in) ran the
   same checks twice and reported every finding twice.
5. **Nothing tested plugin discovery or failure isolation,** and there
   was no example plugin or author documentation.

This module fixes 1-4 without changing the `LanguageAnalyzer` protocol
for authors. Every plugin instance is wrapped in `PluginAnalyzer`:

- `matches`/`entry_points` swallow exceptions (logged, `False`/`[]`);
- `run_tests`/`run_quality`/`run_security` turn an exception or a wrong
  return type into one *skipped* `CommandResult` naming the plugin,
  phase and error -- visible in the report, listed by health as a
  skipped check, and never counted as a failing test of the project;
- `run_security` is optional (a plugin without it just has no security
  checks), which keeps README-era plugins working;
- invalid entries in a returned list are dropped and reported once.

Built-in analyzers are NOT wrapped: they are trusted, tested code and
keep their exact behaviour. Not covered: plugin timeouts (sarand's
subprocess helper already enforces them for the tools a plugin runs, but
a plugin awaiting something else forever would still hang) and sandboxing.

لایه‌ی جداسازی بین sarand و پلاگین‌های آنالایزر شخص‌ثالث (آیتم ۱۴).

ممیزی نشان داد مکانیزم entry-point فقط مسیر خوشبینانه را پوشش می‌داد:
فقط هنگام بارگذاری خطا گرفته می‌شد و بعد از آن یک استثنا در هر پلاگین
کل اجرا را می‌انداخت؛ README چهار متد را مستند کرده بود ولی ثبت‌کننده
متد پنجم (`run_security`) را صدا می‌زند؛ سازوکار سازگاری نسخه نبود؛ و
پلاگینی با نام یک آنالایزر داخلی همه‌ی بررسی‌ها را دوبار اجرا می‌کرد.

هر نمونه‌ی پلاگین در `PluginAnalyzer` پیچیده می‌شود: استثنا و نوع بازگشتیِ
نادرست به یک نتیجه‌ی skipped با نام پلاگین و فاز تبدیل می‌شود (در گزارش
دیده می‌شود و هرگز شکستِ تستِ پروژه حساب نمی‌شود)، `run_security`
اختیاری است و آنالایزرهای داخلی پیچیده نمی‌شوند.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from sarand.analyzers.base import PLUGIN_API_VERSION
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result
from sarand.utils.logging import get_logger

logger = get_logger("analyzers.plugin")

_REQUIRED_METHODS = ("matches", "entry_points", "run_tests", "run_quality")
_MAX_ERROR_CHARS = 200


class PluginRejected(Exception):
    """A plugin that cannot be used; the message says why."""


def _clip(text: str) -> str:
    flat = " ".join(text.split())
    if len(flat) <= _MAX_ERROR_CHARS:
        return flat
    return flat[: _MAX_ERROR_CHARS - 1] + "…"


class PluginAnalyzer:
    """Wraps one plugin instance so it cannot take sarand down with it."""

    def __init__(self, inner: object, name: str) -> None:
        self._inner = inner
        self.name = name

    def _skipped(self, phase: str, reason: str) -> CommandResult:
        return make_command_result(
            f"{self.name} plugin: {phase}",
            1,
            "",
            0.0,
            skipped=True,
            skip_reason=f"plugin '{self.name}' {reason}",
        )

    def _crashed(self, phase: str, exc: BaseException) -> CommandResult:
        logger.warning("Plugin '%s' failed in %s: %r", self.name, phase, exc)
        detail = _clip(f"{type(exc).__name__}: {exc}")
        return self._skipped(phase, f"failed in {phase}: {detail}")

    def matches(self, root: Path) -> bool:
        try:
            return bool(self._inner.matches(root))  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001 - isolate a broken plugin
            logger.warning("Plugin '%s' failed in matches: %r", self.name, exc)
            return False

    def entry_points(self, root: Path) -> list[str]:
        try:
            found = self._inner.entry_points(root)  # type: ignore[attr-defined]
            return [e for e in found if isinstance(e, str)]
        except Exception as exc:  # noqa: BLE001 - isolate a broken plugin
            logger.warning("Plugin '%s' failed in entry_points: %r", self.name, exc)
            return []

    async def _call(self, method: str, root: Path) -> object:
        """Call an `async def` plugin method; a plain `def` gets a clear error."""
        outcome = getattr(self._inner, method)(root)
        if not inspect.isawaitable(outcome):
            raise TypeError(
                f"{method} must be `async def` "
                f"(it returned {type(outcome).__name__}, not a coroutine)"
            )
        return await outcome

    async def run_tests(self, root: Path) -> CommandResult | None:
        try:
            result = await self._call("run_tests", root)
        except Exception as exc:  # noqa: BLE001 - isolate a broken plugin
            return self._crashed("tests", exc)
        if result is None or isinstance(result, CommandResult):
            return result
        kind = type(result).__name__
        return self._skipped(
            "tests", f"returned {kind} from run_tests, not CommandResult"
        )

    async def run_quality(self, root: Path) -> list[CommandResult]:
        return await self._run_list("quality", "run_quality", root)

    async def run_security(self, root: Path) -> list[CommandResult]:
        if not hasattr(self._inner, "run_security"):
            return []
        return await self._run_list("security", "run_security", root)

    async def _run_list(
        self, phase: str, method: str, root: Path
    ) -> list[CommandResult]:
        try:
            raw = await self._call(method, root)
        except Exception as exc:  # noqa: BLE001 - isolate a broken plugin
            return [self._crashed(phase, exc)]
        if not isinstance(raw, list):
            return [
                self._skipped(
                    phase, f"returned {type(raw).__name__} from {method}, not a list"
                )
            ]
        good = [r for r in raw if isinstance(r, CommandResult)]
        dropped = len(raw) - len(good)
        if dropped:
            logger.warning(
                "Plugin '%s': dropped %d invalid item(s) from %s",
                self.name,
                dropped,
                method,
            )
            good.append(self._skipped(phase, f"returned {dropped} invalid item(s)"))
        return good


def adapt_plugin(instance: object, entry_name: str) -> PluginAnalyzer:
    """Validate a freshly created plugin instance and wrap it.

    Raises `PluginRejected` when the instance cannot satisfy the contract:
    no usable `name`, a missing required method, or an `api_version`
    newer than this sarand supports.
    """
    name = getattr(instance, "name", None)
    if not isinstance(name, str) or not name.strip():
        raise PluginRejected("it has no non-empty string `name`")
    for method in _REQUIRED_METHODS:
        if not callable(getattr(instance, method, None)):
            raise PluginRejected(f"it does not implement `{method}`")
    declared = getattr(instance, "api_version", PLUGIN_API_VERSION)
    if isinstance(declared, bool) or not isinstance(declared, int) or declared < 1:
        raise PluginRejected(f"its api_version {declared!r} is not a positive integer")
    if declared > PLUGIN_API_VERSION:
        raise PluginRejected(
            f"it targets plugin API {declared}, this sarand supports "
            f"up to {PLUGIN_API_VERSION} -- upgrade sarand or the plugin"
        )
    return PluginAnalyzer(instance, name.strip())
