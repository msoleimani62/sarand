"""Regression tests for backlog item 14 (plugin system maturity) -- see
AGENTS.md section 5.45 and `analyzers/plugin_adapter.py`'s module
docstring for the audit and the rules these tests pin: real entry-point
discovery, failure isolation at every phase, the optional
`run_security`, API version gating, duplicate names, and the example
plugin that docs/PLUGINS.md points to.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from unittest import mock

from sarand.analyzers import registry
from sarand.analyzers.base import PLUGIN_API_VERSION, LanguageAnalyzer
from sarand.analyzers.plugin_adapter import PluginRejected, adapt_plugin
from sarand.models.results import CommandResult

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_SRC = ROOT / "examples" / "sarand-plugin-justfile" / "src"


def _ok(kind: str = "demo") -> CommandResult:
    return CommandResult(kind=kind, returncode=0, summary="fine")


class GoodPlugin:
    name = "Good"

    def matches(self, root: Path) -> bool:
        return True

    def entry_points(self, root: Path) -> list[str]:
        return ["main.good"]

    async def run_tests(self, root: Path) -> CommandResult | None:
        return _ok("good test")

    async def run_quality(self, root: Path) -> list[CommandResult]:
        return [_ok("good lint")]

    async def run_security(self, root: Path) -> list[CommandResult]:
        return [_ok("good audit")]


class FakeEntryPoint:
    def __init__(self, name: str, factory: type, value: str = "x:Y") -> None:
        self.name = name
        self.value = value
        self._factory = factory

    def load(self) -> type:
        return self._factory


def _discover(*eps: FakeEntryPoint) -> list[LanguageAnalyzer]:
    with mock.patch.object(registry, "entry_points", return_value=list(eps)):
        return registry.discover_analyzers()


def _plugin_names(analyzers: list[LanguageAnalyzer]) -> list[str]:
    builtin = {a.name for a in registry._BUILTIN}
    return [a.name for a in analyzers if a.name not in builtin]


def _rejection(instance: object) -> str:
    try:
        adapt_plugin(instance, "p")
    except PluginRejected as exc:
        return str(exc)
    raise AssertionError("plugin was not rejected")


def test_the_api_version_constant_starts_at_one() -> None:
    assert PLUGIN_API_VERSION == 1


def test_real_entry_point_discovery_through_importlib_metadata() -> None:
    """Not a mock: a real dist-info on sys.path with an entry_points.txt."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "zzplug_mod.py").write_text(
            "from pathlib import Path\n"
            "class ZzAnalyzer:\n"
            "    name = 'Zz'\n"
            "    def matches(self, root): return False\n"
            "    def entry_points(self, root): return []\n"
            "    async def run_tests(self, root): return None\n"
            "    async def run_quality(self, root): return []\n",
            encoding="utf-8",
        )
        info = base / "zzplug-0.1.dist-info"
        info.mkdir()
        (info / "METADATA").write_text(
            "Metadata-Version: 2.1\nName: zzplug\nVersion: 0.1\n", encoding="utf-8"
        )
        (info / "entry_points.txt").write_text(
            "[sarand.analyzers]\nzz = zzplug_mod:ZzAnalyzer\n", encoding="utf-8"
        )
        sys.path.insert(0, str(base))
        importlib.invalidate_caches()
        try:
            found = registry.discover_analyzers()
        finally:
            sys.path.remove(str(base))
            sys.modules.pop("zzplug_mod", None)
            importlib.invalidate_caches()
        assert _plugin_names(found) == ["Zz"]
        assert found[-1].matches(base) is False
        assert asyncio.run(found[-1].run_security(base)) == []


def test_a_good_plugin_is_discovered_wrapped_and_usable() -> None:
    found = _discover(FakeEntryPoint("good", GoodPlugin))
    assert _plugin_names(found) == ["Good"]
    plugin = found[-1]
    assert isinstance(plugin, LanguageAnalyzer)
    assert plugin.matches(Path(".")) is True
    assert plugin.entry_points(Path(".")) == ["main.good"]
    tests = asyncio.run(plugin.run_tests(Path(".")))
    assert tests is not None and tests.kind == "good test"
    assert [r.kind for r in asyncio.run(plugin.run_quality(Path(".")))] == ["good lint"]
    assert [r.kind for r in asyncio.run(plugin.run_security(Path(".")))] == [
        "good audit"
    ]


def test_no_plugins_means_exactly_the_builtins() -> None:
    assert _discover() == list(registry._BUILTIN)


def test_plugins_load_in_a_stable_order_regardless_of_discovery_order() -> None:
    class Alpha(GoodPlugin):
        name = "Alpha"

    class Beta(GoodPlugin):
        name = "Beta"

    one = _discover(FakeEntryPoint("b", Beta), FakeEntryPoint("a", Alpha))
    two = _discover(FakeEntryPoint("a", Alpha), FakeEntryPoint("b", Beta))
    assert _plugin_names(one) == _plugin_names(two) == ["Alpha", "Beta"]


def test_a_plugin_that_fails_to_import_or_construct_is_skipped() -> None:
    class Explodes:
        def __init__(self) -> None:
            raise RuntimeError("boom in __init__")

    class BrokenImport(FakeEntryPoint):
        def load(self) -> type:
            raise ImportError("no module named gone")

    found = _discover(
        BrokenImport("gone", GoodPlugin),
        FakeEntryPoint("explodes", Explodes),
        FakeEntryPoint("good", GoodPlugin),
    )
    assert _plugin_names(found) == ["Good"]


def test_unreadable_entry_point_metadata_does_not_crash_discovery() -> None:
    with mock.patch.object(registry, "entry_points", side_effect=OSError("bad")):
        assert registry.discover_analyzers() == list(registry._BUILTIN)


def test_a_plugin_named_like_a_builtin_or_an_earlier_plugin_is_skipped() -> None:
    class ShadowsBuiltin(GoodPlugin):
        name = "python"

    class Twin(GoodPlugin):
        name = "Good"

    found = _discover(
        FakeEntryPoint("shadow", ShadowsBuiltin),
        FakeEntryPoint("good1", GoodPlugin),
        FakeEntryPoint("good2", Twin),
    )
    assert _plugin_names(found) == ["Good"]
    assert sum(1 for a in found if a.name.lower() == "python") == 1


def test_contract_violations_are_rejected_with_a_reason() -> None:
    class NoName(GoodPlugin):
        name = ""

    class NoQuality(GoodPlugin):
        run_quality = None  # type: ignore[assignment]

    class Newer(GoodPlugin):
        api_version = PLUGIN_API_VERSION + 1

    class BadVersion(GoodPlugin):
        api_version = "1"  # type: ignore[assignment]

    assert "name" in _rejection(NoName())
    assert "run_quality" in _rejection(NoQuality())
    assert "upgrade sarand" in _rejection(Newer())
    assert "positive integer" in _rejection(BadVersion())
    assert "name" in _rejection(object())


def test_run_security_is_optional_for_readme_era_plugins() -> None:
    class NoSecurity:
        name = "Legacy"

        def matches(self, root: Path) -> bool:
            return True

        def entry_points(self, root: Path) -> list[str]:
            return []

        async def run_tests(self, root: Path) -> CommandResult | None:
            return None

        async def run_quality(self, root: Path) -> list[CommandResult]:
            return []

    found = _discover(FakeEntryPoint("legacy", NoSecurity))
    assert _plugin_names(found) == ["Legacy"]
    assert asyncio.run(found[-1].run_security(Path("."))) == []


def test_a_declared_older_or_equal_api_version_is_accepted() -> None:
    class Declares(GoodPlugin):
        api_version = 1

    assert _plugin_names(_discover(FakeEntryPoint("d", Declares))) == ["Good"]


class CrashEverywhere:
    name = "Crashy"

    def matches(self, root: Path) -> bool:
        raise RuntimeError("matches blew up")

    def entry_points(self, root: Path) -> list[str]:
        raise RuntimeError("entry_points blew up")

    async def run_tests(self, root: Path) -> CommandResult | None:
        raise RuntimeError("tests blew up\nwith a second line")

    async def run_quality(self, root: Path) -> list[CommandResult]:
        raise ValueError("quality blew up")

    async def run_security(self, root: Path) -> list[CommandResult]:
        raise KeyError("security")


def test_a_crashing_plugin_never_raises_and_reports_a_skipped_result() -> None:
    plugin = adapt_plugin(CrashEverywhere(), "crashy")
    root = Path(".")
    assert plugin.matches(root) is False
    assert plugin.entry_points(root) == []

    tests = asyncio.run(plugin.run_tests(root))
    assert tests is not None and tests.skipped and not tests.passed
    assert "failed in tests: RuntimeError: tests blew up with a second line" in (
        tests.skip_reason
    )
    quality = asyncio.run(plugin.run_quality(root))
    security = asyncio.run(plugin.run_security(root))
    assert [r.skipped for r in quality + security] == [True, True]
    assert "ValueError: quality blew up" in quality[0].skip_reason
    assert tests.kind == "Crashy plugin: tests"


def test_a_failing_plugin_does_not_cost_other_analyzers_their_results() -> None:
    found = _discover(
        FakeEntryPoint("crashy", CrashEverywhere), FakeEntryPoint("good", GoodPlugin)
    )
    plugins = [a for a in found if a.name in {"Crashy", "Good"}]
    results = asyncio.run(registry.run_tests_concurrently(Path("."), plugins))
    by_kind = {r.kind: r for r in results}
    assert by_kind["good test"].passed
    assert by_kind["Crashy plugin: tests"].skipped
    quality = asyncio.run(registry.run_quality_concurrently(Path("."), plugins))
    security = asyncio.run(registry.run_security_concurrently(Path("."), plugins))
    assert {r.kind for r in quality} == {"good lint", "Crashy plugin: quality"}
    assert {r.kind for r in security} == {"good audit", "Crashy plugin: security"}


def test_matching_analyzers_survives_a_plugin_whose_matches_raises() -> None:
    found = _discover(
        FakeEntryPoint("crashy", CrashEverywhere), FakeEntryPoint("good", GoodPlugin)
    )
    with tempfile.TemporaryDirectory() as tmp:
        names = [a.name for a in registry.matching_analyzers(Path(tmp), found)]
    assert "Good" in names and "Crashy" not in names


def test_wrong_return_types_become_skipped_results_not_crashes() -> None:
    class Sloppy(GoodPlugin):
        name = "Sloppy"

        async def run_tests(self, root: Path) -> CommandResult | None:
            return {"kind": "x"}  # type: ignore[return-value]

        async def run_quality(self, root: Path) -> list[CommandResult]:
            return ("a", "b")  # type: ignore[return-value]

        async def run_security(self, root: Path) -> list[CommandResult]:
            return [_ok("kept"), "junk", 3]  # type: ignore[list-item]

    plugin = adapt_plugin(Sloppy(), "sloppy")
    tests = asyncio.run(plugin.run_tests(Path(".")))
    assert tests is not None and tests.skipped and "dict" in tests.skip_reason
    quality = asyncio.run(plugin.run_quality(Path(".")))
    assert len(quality) == 1 and quality[0].skipped
    assert "tuple" in quality[0].skip_reason
    security = asyncio.run(plugin.run_security(Path(".")))
    assert security[0].kind == "kept"
    assert security[-1].skipped and "2 invalid item(s)" in security[-1].skip_reason


def test_a_synchronous_run_method_is_isolated_too() -> None:
    class Sync(GoodPlugin):
        name = "Sync"

        def run_tests(  # type: ignore[override]
            self, root: Path
        ) -> CommandResult | None:
            return _ok("sync")

    plugin = adapt_plugin(Sync(), "sync")
    result = asyncio.run(plugin.run_tests(Path(".")))
    assert result is not None and result.skipped
    assert "run_tests must be `async def`" in result.skip_reason


def _load_example() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "sarand_justfile_plugin", EXAMPLE_SRC / "sarand_justfile_plugin" / "__init__.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_example_plugin_satisfies_the_documented_contract() -> None:
    module = _load_example()
    plugin = adapt_plugin(module.JustfileAnalyzer(), "justfile")
    assert plugin.name == "Just"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert plugin.matches(root) is False
        (root / "justfile").write_text("test:\n    echo ok\n", encoding="utf-8")
        assert plugin.matches(root) is True
        assert plugin.entry_points(root) == ["justfile"]
        with mock.patch.object(shutil, "which", return_value=None):
            result = asyncio.run(plugin.run_tests(root))
        assert result is not None and result.skipped
        assert result.skip_reason == "just not found in PATH"
        assert asyncio.run(plugin.run_quality(root)) == []
        assert asyncio.run(plugin.run_security(root)) == []


def test_the_example_plugin_declares_the_entry_point_group_the_docs_name() -> None:
    text = (ROOT / "examples" / "sarand-plugin-justfile" / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    assert '[project.entry-points."sarand.analyzers"]' in text
    assert 'justfile = "sarand_justfile_plugin:JustfileAnalyzer"' in text
    docs = (ROOT / "docs" / "PLUGINS.md").read_text(encoding="utf-8")
    assert "sarand.analyzers" in docs and "api_version" in docs
    assert f"`PLUGIN_API_VERSION` is **{PLUGIN_API_VERSION}**" in docs
