"""Built-in analyzer registry, third-party plugin discovery, and
concurrent execution.

Third-party plugins register under the ``sarand.analyzers`` entry-point
group in their own package's ``pyproject.toml``:

    [project.entry-points."sarand.analyzers"]
    zig = "sarand_zig_plugin:ZigAnalyzer"

No sarand core file ever needs to change for a new language -- this is
the concrete mechanism behind "modular / plugin-ready" rather than a
promise.

پلاگین‌های شخص‌ثالث زیر گروه entry-point به نام ``sarand.analyzers``
در pyproject.toml بسته‌ی خودشان ثبت می‌شوند. هیچ فایل هسته‌ی sarand
برای اضافه‌شدن یک زبان جدید نیاز به تغییر ندارد -- این مکانیزم واقعی
پشت «ماژولار/پلاگین‌پذیر» است، نه یک وعده.
"""

from __future__ import annotations

import asyncio
from importlib.metadata import entry_points
from pathlib import Path

from sarand.analyzers.android_analyzer import AndroidAnalyzer
from sarand.analyzers.base import LanguageAnalyzer
from sarand.analyzers.cpp_analyzer import CppAnalyzer
from sarand.analyzers.go_analyzer import GoAnalyzer
from sarand.analyzers.java_analyzer import JavaAnalyzer
from sarand.analyzers.node_analyzer import NodeAnalyzer
from sarand.analyzers.python_analyzer import PythonAnalyzer
from sarand.analyzers.rust_analyzer import RustAnalyzer
from sarand.models.results import CommandResult
from sarand.utils.logging import get_logger

logger = get_logger("analyzers.registry")

_ENTRY_POINT_GROUP = "sarand.analyzers"

_BUILTIN: list[LanguageAnalyzer] = [
    PythonAnalyzer(),
    RustAnalyzer(),
    GoAnalyzer(),
    NodeAnalyzer(),
    CppAnalyzer(),
    # AndroidAnalyzer before JavaAnalyzer: matches() on both is mutually
    # exclusive by design (JavaAnalyzer defers to Android detection), so
    # order between them doesn't actually change behavior -- kept in
    # this order anyway since it reads as "more specific case first."
    # AndroidAnalyzer قبل از JavaAnalyzer: matches() دو تا به‌طور طراحی
    # متقابلاً منحصربه‌فرد است (JavaAnalyzer به تشخیص اندروید واگذار
    # می‌کند)، پس ترتیب بین این دو واقعاً رفتار را عوض نمی‌کند -- فقط
    # چون خوانشش «مورد خاص‌تر اول» است همین‌طور نگه داشته شده.
    AndroidAnalyzer(),
    JavaAnalyzer(),
]


def discover_analyzers() -> list[LanguageAnalyzer]:
    """Return built-in analyzers plus any installed plugin analyzers."""
    analyzers = list(_BUILTIN)
    try:
        eps = entry_points(group=_ENTRY_POINT_GROUP)
    except TypeError:
        # Python < 3.10 signature fallback (kept for safety, not required
        # given requires-python >= 3.10, but cheap to keep).
        eps = entry_points().get(_ENTRY_POINT_GROUP, [])  # type: ignore[union-attr]

    for ep in eps:
        try:
            cls = ep.load()
            analyzers.append(cls())
            logger.info("Loaded plugin analyzer: %s (%s)", ep.name, ep.value)
        except Exception as exc:  # noqa: BLE001 - a broken plugin must not crash sarand
            logger.warning("Failed to load analyzer plugin '%s': %s", ep.name, exc)

    return analyzers


def matching_analyzers(root: Path, analyzers: list[LanguageAnalyzer] | None = None) -> list[LanguageAnalyzer]:
    """Return the subset of analyzers whose ``matches(root)`` is True."""
    pool = analyzers if analyzers is not None else discover_analyzers()
    return [a for a in pool if a.matches(root)]


async def run_tests_concurrently(root: Path, analyzers: list[LanguageAnalyzer]) -> list[CommandResult]:
    """Run every matching analyzer's test suite concurrently.

    This is the async payoff of the plugin architecture: cargo test,
    pytest, go test and npm test all start at once instead of being
    chained sequentially.
    """
    tasks = [a.run_tests(root) for a in analyzers]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


async def run_quality_concurrently(root: Path, analyzers: list[LanguageAnalyzer]) -> list[CommandResult]:
    """Run every matching analyzer's quality checks concurrently."""
    tasks = [a.run_quality(root) for a in analyzers]
    results = await asyncio.gather(*tasks)
    flat: list[CommandResult] = []
    for group in results:
        flat.extend(group)
    return flat


async def run_security_concurrently(root: Path, analyzers: list[LanguageAnalyzer]) -> list[CommandResult]:
    """Run every matching analyzer's security/vulnerability checks concurrently."""
    tasks = [a.run_security(root) for a in analyzers]
    results = await asyncio.gather(*tasks)
    flat: list[CommandResult] = []
    for group in results:
        flat.extend(group)
    return flat
