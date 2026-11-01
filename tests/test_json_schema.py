"""The JSON report schema (docs/JSON_SCHEMA.md and its Persian twin): the version
is in the report, and the documents list every key and field the code writes.

A key added to the renderer without a line in both documents fails here; so does a
documented key that no longer exists. Dependency-free like the other tests.
نسخه‌ی شما در گزارش هست و مستندها همه‌ی کلیدها و فیلدهای کد را فهرست می‌کنند.
"""

from __future__ import annotations

import dataclasses
import json
import re
import tempfile
from pathlib import Path

from _golden_fixtures import FIXTURES
from sarand.core.architecture import Architecture
from sarand.core.quick_context import QuickContext
from sarand.core.risks import Risk, RiskReport
from sarand.models import results
from sarand.renderers import json_renderer

_ROOT = Path(__file__).resolve().parent.parent
_DOCS = {
    "en": (_ROOT / "docs" / "JSON_SCHEMA.md").read_text(encoding="utf-8"),
    "fa": (_ROOT / "docs" / "JSON_SCHEMA.fa.md").read_text(encoding="utf-8"),
}
_SOURCE = (_ROOT / "python" / "sarand" / "renderers" / "json_renderer.py").read_text(
    encoding="utf-8"
)


def _keys_in_code() -> set[str]:
    """Every top-level key the renderer can write: the literal plus the
    conditional `payload["key"] = ...` assignments."""
    start = _SOURCE.index("    payload = {\n")
    end = _SOURCE.index("\n    }\n", start)
    literal = set(re.findall(r'^\s{8}"(\w+)":', _SOURCE[start:end], re.MULTILINE))
    conditional = set(re.findall(r'(?<!\w)payload\["(\w+)"\]\s*=', _SOURCE))
    return literal | conditional


def _keys_in_doc(text: str) -> set[str]:
    section = text.split("\n## ", 3)
    table = next(part for part in section if part.startswith(("Top-level", "کلیدهای")))
    return set(re.findall(r"^\| `(\w+)` \|", table, re.MULTILINE))


def _render(name: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "proj"
        root.mkdir()
        data = FIXTURES[name](root)
        return json.loads(json_renderer.render(data, include_source=False))  # type: ignore[no-any-return]


def test_the_report_carries_the_schema_version_as_its_first_key() -> None:
    for name in FIXTURES:
        payload = _render(name)
        assert next(iter(payload)) == "schema_version"
        assert payload["schema_version"] == json_renderer.JSON_SCHEMA_VERSION


def test_the_version_is_major_dot_minor() -> None:
    assert re.fullmatch(r"\d+\.\d+", json_renderer.JSON_SCHEMA_VERSION)


def test_both_documents_state_the_current_version() -> None:
    version = json_renderer.JSON_SCHEMA_VERSION
    assert f"Current version: **{version}**" in _DOCS["en"]
    assert f"نسخه‌ی فعلی: **{version}**" in _DOCS["fa"]


def test_every_top_level_key_the_code_can_write_is_documented_in_both_languages() -> (
    None
):
    code = _keys_in_code()
    assert "schema_version" in code and "relevant_source" in code and len(code) > 30
    for lang, text in _DOCS.items():
        assert code - _keys_in_doc(text) == set(), lang


def test_no_documented_key_is_missing_from_the_code() -> None:
    code = _keys_in_code()
    for lang, text in _DOCS.items():
        assert _keys_in_doc(text) - code == set(), lang


def test_the_two_documents_list_the_same_keys() -> None:
    assert _keys_in_doc(_DOCS["en"]) == _keys_in_doc(_DOCS["fa"])


def test_every_rendered_key_is_documented() -> None:
    documented = _keys_in_doc(_DOCS["en"])
    for name in FIXTURES:
        assert set(_render(name)) - documented == set(), name


def _mentioned(text: str, name: str) -> bool:
    """`name` appears inside some backtick span, alone or in a list such as
    `{rule_id, category}` or `[path, reason]`."""
    return any(
        re.search(rf"\b{re.escape(name)}\b", span)
        for span in re.findall(r"`([^`]+)`", text)
    )


def _fields(cls: type) -> list[str]:
    return [f.name for f in dataclasses.fields(cls)]


def test_the_fields_of_the_nested_objects_are_documented() -> None:
    classes: list[type] = [
        QuickContext,
        Architecture,
        RiskReport,
        Risk,
        results.ProjectDetection,
        results.EnvironmentInfo,
        results.GitSnapshot,
        results.ProjectStats,
        results.HealthScore,
        results.CommandResult,
        results.FrameworkEntry,
    ]
    for lang, text in _DOCS.items():
        for cls in classes:
            for field in _fields(cls):
                assert _mentioned(text, field), (lang, cls.__name__, field)


def test_the_relevant_source_payload_keys_are_documented() -> None:
    from sarand.core.relevant_source import relevant_source_payload
    from sarand.models.results import RelevantSource

    payload = relevant_source_payload(RelevantSource())
    budget = payload["budget"]
    assert isinstance(budget, dict)
    for key in [*payload, *budget]:
        for lang, text in _DOCS.items():
            assert _mentioned(text, key), (lang, key)
