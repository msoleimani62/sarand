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
from collections.abc import Sequence
from importlib.metadata import entry_points
from pathlib import Path

from sarand.analyzers.android_analyzer import AndroidAnalyzer
from sarand.analyzers.base import LanguageAnalyzer
from sarand.analyzers.cpp_analyzer import CppAnalyzer
from sarand.analyzers.csharp_analyzer import CSharpAnalyzer
from sarand.analyzers.css_analyzer import CssAnalyzer
from sarand.analyzers.dart_analyzer import DartAnalyzer
from sarand.analyzers.go_analyzer import GoAnalyzer
from sarand.analyzers.groovy_analyzer import GroovyAnalyzer
from sarand.analyzers.java_analyzer import JavaAnalyzer
from sarand.analyzers.json_analyzer import JsonAnalyzer
from sarand.analyzers.julia_analyzer import JuliaAnalyzer
from sarand.analyzers.kotlin_analyzer import KotlinAnalyzer
from sarand.analyzers.lua_analyzer import LuaAnalyzer
from sarand.analyzers.nix_analyzer import NixAnalyzer
from sarand.analyzers.node_analyzer import NodeAnalyzer
from sarand.analyzers.objectivec_analyzer import ObjectiveCAnalyzer
from sarand.analyzers.perl_analyzer import PerlAnalyzer
from sarand.analyzers.php_analyzer import PhpAnalyzer
from sarand.analyzers.powershell_analyzer import PowerShellAnalyzer
from sarand.analyzers.python_analyzer import PythonAnalyzer
from sarand.analyzers.r_analyzer import RAnalyzer
from sarand.analyzers.ruby_analyzer import RubyAnalyzer
from sarand.analyzers.rust_analyzer import RustAnalyzer
from sarand.analyzers.shell_analyzer import ShellAnalyzer
from sarand.analyzers.sql_analyzer import SqlAnalyzer
from sarand.analyzers.swift_analyzer import SwiftAnalyzer
from sarand.analyzers.toml_analyzer import TomlAnalyzer
from sarand.analyzers.typescript_analyzer import TypeScriptAnalyzer
from sarand.analyzers.xml_analyzer import XmlAnalyzer
from sarand.analyzers.yaml_analyzer import YamlAnalyzer
from sarand.analyzers.zig_analyzer import ZigAnalyzer
from sarand.models.results import CommandResult
from sarand.utils.logging import get_logger

logger = get_logger("analyzers.registry")

_ENTRY_POINT_GROUP = "sarand.analyzers"

_BUILTIN: list[LanguageAnalyzer] = [
    PythonAnalyzer(),
    RustAnalyzer(),
    GoAnalyzer(),
    NodeAnalyzer(),
    # TypeScriptAnalyzer/CssAnalyzer right after NodeAnalyzer: both are
    # JS-ecosystem-adjacent and, on a typical TS or styled front-end
    # project, run alongside it rather than instead of it (see each
    # analyzer's own module docstring for why run_tests/run_security
    # are no-ops there instead of duplicating NodeAnalyzer's work).
    # TypeScriptAnalyzer/CssAnalyzer درست بعد از NodeAnalyzer: هر دو
    # مجاور اکوسیستم JS هستند و روی یک پروژه‌ی معمولی TS یا front-end
    # استایل‌دار، به‌جای NodeAnalyzer نه، کنار آن اجرا می‌شوند (دلیل
    # no-op بودن run_tests/run_security آن‌ها را در دکیومنت ماژول خودشان
    # ببینید تا کار NodeAnalyzer تکرار نشود).
    TypeScriptAnalyzer(),
    CssAnalyzer(),
    ZigAnalyzer(),
    SwiftAnalyzer(),
    # ObjectiveCAnalyzer right after SwiftAnalyzer: same
    # complementary-match shape as TypeScriptAnalyzer/NodeAnalyzer
    # above -- a mixed Swift/Objective-C project legitimately
    # matches both at once.
    # ObjectiveCAnalyzer درست بعد از SwiftAnalyzer: همان شکل
    # تطابقِ مکملِ TypeScriptAnalyzer/NodeAnalyzer بالا -- یک
    # پروژه‌ی ترکیبیِ Swift/Objective-C به‌طور مشروع هر دو را
    # هم‌زمان تطابق می‌دهد.
    ObjectiveCAnalyzer(),
    CppAnalyzer(),
    LuaAnalyzer(),
    RubyAnalyzer(),
    PhpAnalyzer(),
    DartAnalyzer(),
    RAnalyzer(),
    PerlAnalyzer(),
    JuliaAnalyzer(),
    SqlAnalyzer(),
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
    # KotlinAnalyzer after JavaAnalyzer: same complementary-match shape
    # as TypeScriptAnalyzer/NodeAnalyzer above -- both match one Kotlin
    # Gradle project at once, KotlinAnalyzer contributing only quality
    # (ktlint/detekt) since JavaAnalyzer already owns test execution.
    # KotlinAnalyzer بعد از JavaAnalyzer: همان شکل تطابقِ مکمل
    # TypeScriptAnalyzer/NodeAnalyzer بالا -- هر دو هم‌زمان روی یک
    # پروژه‌ی Gradle با Kotlin تطابق پیدا می‌کنند، KotlinAnalyzer فقط
    # quality (ktlint/detekt) اضافه می‌کند چون اجرای تست از قبل مال
    # JavaAnalyzer است.
    KotlinAnalyzer(),
    # GroovyAnalyzer right after KotlinAnalyzer: same
    # complementary-match shape -- contributes quality only
    # (CodeNarc), JavaAnalyzer already owns Gradle test execution.
    # GroovyAnalyzer درست بعد از KotlinAnalyzer: همان شکل تطابقِ
    # مکمل -- فقط quality (CodeNarc) اضافه می‌کند، اجرای تست
    # Gradle از قبل مال JavaAnalyzer است.
    GroovyAnalyzer(),
    CSharpAnalyzer(),
    ShellAnalyzer(),
    # PowerShellAnalyzer/NixAnalyzer: same shallow, no-manifest
    # detection shape as ShellAnalyzer (top-level script/config
    # file only, no dedicated project marker to key off of).
    # PowerShellAnalyzer/NixAnalyzer: همان شکل تشخیص کم‌عمق و
    # بدون-مانیفستِ ShellAnalyzer (فقط یک فایل اسکریپت/کانفیگ
    # سطح-ریشه، بدون نشانگر اختصاصی پروژه).
    PowerShellAnalyzer(),
    NixAnalyzer(),
    # Format analyzers (YAML/JSON/TOML/XML) last: none of these gate on
    # anything exclusive to them -- a Cargo.toml, package.json or
    # pom.xml is claimed by its own language analyzer above AND matched
    # here for a separate, complementary concern (syntax/style linting
    # of that file itself). Order among themselves doesn't matter.
    # آنالایزرهای فرمت (YAML/JSON/TOML/XML) آخر: هیچ‌کدام روی چیز
    # اختصاصی به خودشان گیت نمی‌شوند -- یک Cargo.toml، package.json یا
    # pom.xml از قبل توسط آنالایزر زبان خودش بالا claim شده AND اینجا هم
    # برای یک دغدغه‌ی جدا و مکمل (لینت syntax/style همان فایل) تطابق
    # پیدا می‌کند. ترتیب بین خودشان اهمیتی ندارد.
    YamlAnalyzer(),
    JsonAnalyzer(),
    TomlAnalyzer(),
    XmlAnalyzer(),
]


def discover_analyzers() -> list[LanguageAnalyzer]:
    """Return built-in analyzers plus any installed plugin analyzers."""
    analyzers = list(_BUILTIN)
    eps = entry_points(group=_ENTRY_POINT_GROUP)

    for ep in eps:
        try:
            cls = ep.load()
            analyzers.append(cls())
            logger.info("Loaded plugin analyzer: %s (%s)", ep.name, ep.value)
        except Exception as exc:  # noqa: BLE001 - a broken plugin must not crash sarand
            logger.warning("Failed to load analyzer plugin '%s': %s", ep.name, exc)

    return analyzers


def matching_analyzers(
    root: Path, analyzers: list[LanguageAnalyzer] | None = None
) -> list[LanguageAnalyzer]:
    """Return the subset of analyzers whose ``matches(root)`` is True."""
    pool = analyzers if analyzers is not None else discover_analyzers()
    return [a for a in pool if a.matches(root)]


async def run_tests_concurrently(
    root: Path, analyzers: Sequence[LanguageAnalyzer]
) -> list[CommandResult]:
    """Run every matching analyzer's test suite concurrently.

    This is the async payoff of the plugin architecture: cargo test,
    pytest, go test and npm test all start at once instead of being
    chained sequentially.
    """
    tasks = [a.run_tests(root) for a in analyzers]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


async def run_quality_concurrently(
    root: Path, analyzers: Sequence[LanguageAnalyzer]
) -> list[CommandResult]:
    """Run every matching analyzer's quality checks concurrently."""
    tasks = [a.run_quality(root) for a in analyzers]
    results = await asyncio.gather(*tasks)
    flat: list[CommandResult] = []
    for group in results:
        flat.extend(group)
    return flat


async def run_security_concurrently(
    root: Path, analyzers: Sequence[LanguageAnalyzer]
) -> list[CommandResult]:
    """Run every matching analyzer's security/vulnerability checks concurrently."""
    tasks = [a.run_security(root) for a in analyzers]
    results = await asyncio.gather(*tasks)
    flat: list[CommandResult] = []
    for group in results:
        flat.extend(group)
    return flat
