"""The `--doctor` plugin section (round R10a).

القسم الخاص بالإضافات؛ بخش پلاگین‌ها در --doctor.
"""

from __future__ import annotations

from sarand.analyzers.registry import PluginStatus
from sarand.core import doctor


def _render(statuses: list[PluginStatus]) -> str:
    with doctor.console.capture() as capture:
        doctor._print_plugins(statuses)
    # Panel borders and wrapping are not part of the contract: compare the words.
    # کادر و شکستن خط جزو قرارداد نیست؛ فقط کلمات مقایسه می‌شوند.
    return " ".join(capture.get().replace("│", " ").split())


def test_no_plugins_say_so_and_point_to_the_guide() -> None:
    text = _render([])
    assert "Plugins" in text
    assert "none installed" in text
    assert "PLUGINS.md" in text


def test_loaded_and_skipped_plugins_are_listed_with_the_reason() -> None:
    text = _render(
        [
            PluginStatus("zig-extra", "pkg.zig:Plugin", True, "ZigExtra"),
            PluginStatus("old-one", "pkg.old:Plugin", False, "it targets plugin API 9"),
        ]
    )
    assert "zig-extra" in text and "ZigExtra" in text
    assert "old-one" in text
    assert "skipped" in text
    assert "plugin API 9" in text


def test_text_from_a_plugin_is_never_read_as_markup() -> None:
    text = _render([PluginStatus("x", "p:q", False, "failed [red]loud[/red]")])
    assert "[red]loud[/red]" in text
