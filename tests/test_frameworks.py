"""Regression tests for Quick Context R11a: declared frameworks (decision
D-QC2, docs/QUICK_CONTEXT_DESIGN.md section 4, `core/frameworks.py`).

Dependency-free like the other tests (no `import pytest`).
تست‌های رگرسیون R11a: فریم‌ورک‌های اعلام‌شده در Quick Context.
"""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from html import escape
from pathlib import Path

from _golden_fixtures import FIXTURES
from _helpers import write
from sarand.core.components import declared_dependencies
from sarand.core.frameworks import (
    FRAMEWORK_TABLE,
    FRAMEWORK_TABLE_VERSION,
    detect_declared_frameworks,
)
from sarand.core.quick_context import (
    build_quick_context,
    format_framework,
    quick_context_lines,
)
from sarand.models.results import FrameworkEntry, ReportData
from sarand.renderers import html, json_renderer, markdown, text

# The pinned table. A change to FRAMEWORK_TABLE is a deliberate edit: bump
# FRAMEWORK_TABLE_VERSION and replace the digest below in the same commit.
# جدول قفل‌شده: هر تغییر جدول یک ویرایش عمدی است؛ نسخه و digest را با هم عوض کنید.
_TABLE_DIGEST = "a5630620b3d8ef623a859258add0123ad594d5a3fbe1c60ee5264cc32f9c3176"
_TABLE_SIZE = 64


@contextmanager
def _root() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "proj"
        root.mkdir()
        yield root


def _entries(root: Path) -> list[tuple[str, str, str]]:
    return [(e.manifest, e.name, e.scope) for e in detect_declared_frameworks(root)]


def _fixture(name: str) -> Iterator[ReportData]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / f"{name}-project"
        root.mkdir()
        yield FIXTURES[name](root)


def _digest() -> str:
    payload = json.dumps(sorted(FRAMEWORK_TABLE.items()), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_table_snapshot_is_pinned_with_its_version() -> None:
    assert FRAMEWORK_TABLE_VERSION == 1
    assert len(FRAMEWORK_TABLE) == _TABLE_SIZE
    assert _digest() == _TABLE_DIGEST


def test_table_keys_are_normalised_and_labels_are_non_empty() -> None:
    for name, label in FRAMEWORK_TABLE.items():
        assert name == name.lower() and "_" not in name and label.strip()


def test_no_framework_is_ever_reported_from_the_directory_layout() -> None:
    with _root() as root:
        for name in ("react", "django", "fastapi", "express", "vue", "next"):
            write(root / name / "readme.txt", "x")
            write(root / f"{name}.py", "x = 1\n")
            write(root / "src" / name / "index.js", "x\n")
        write(root / "main.py", "import django\nimport fastapi\n")
        assert detect_declared_frameworks(root) == []


def test_node_scopes_come_only_from_the_section_that_declares_them() -> None:
    with _root() as root:
        write(
            root / "package.json",
            json.dumps(
                {
                    "dependencies": {"react": "^18", "express": "4"},
                    "devDependencies": {"vite": "5", "jest": "29"},
                    "peerDependencies": {"vue": "3"},
                }
            ),
        )
        assert _entries(root) == [
            ("package.json", "express", "runtime"),
            ("package.json", "jest", "dev"),
            ("package.json", "react", "runtime"),
            ("package.json", "vite", "dev"),
            ("package.json", "vue", ""),
        ]


def test_python_scopes_requirements_is_not_guessed_as_runtime() -> None:
    with _root() as root:
        write(
            root / "pyproject.toml",
            '[project]\nname = "p"\ndependencies = ["FastAPI>=0.1", "requests"]\n'
            '[tool.poetry.dependencies]\npython = "^3.11"\nDjango = "^5"\n',
        )
        write(root / "requirements.txt", "# c\n-r other.txt\nFlask==3\npytest\n")
        assert _entries(root) == [
            ("pyproject.toml", "django", "runtime"),
            ("pyproject.toml", "fastapi", "runtime"),
            ("requirements.txt", "flask", ""),
            ("requirements.txt", "pytest", ""),
        ]


def test_python_names_are_normalised_before_the_table_lookup() -> None:
    with _root() as root:
        write(root / "requirements.txt", "Scikit_Learn>=1\nSOCKET.IO\n")
        assert _entries(root) == [("requirements.txt", "scikit-learn", "")]


def test_application_components_are_read_with_a_relative_manifest_path() -> None:
    with _root() as root:
        write(root / "frontend" / "package.json", '{"dependencies": {"react": "1"}}')
        write(
            root / "backend" / "pyproject.toml",
            '[project]\nname = "b"\ndependencies = ["fastapi"]\n',
        )
        assert _entries(root) == [
            ("backend/pyproject.toml", "fastapi", "runtime"),
            ("frontend/package.json", "react", "runtime"),
        ]


def test_fixture_vendor_and_example_directories_are_not_read() -> None:
    with _root() as root:
        for skipped in ("examples", "tests", "vendor", "node_modules", "fixtures"):
            write(root / skipped / "package.json", '{"dependencies": {"react": "1"}}')
        assert detect_declared_frameworks(root) == []


def test_cargo_and_go_manifests_yield_nothing_by_design() -> None:
    """Their dependency names are not parsed anywhere (design file, R11a)."""
    with _root() as root:
        write(
            root / "Cargo.toml", '[package]\nname = "x"\n[dependencies]\ntokio = "1"\n'
        )
        write(root / "go.mod", "module x\n\nrequire github.com/gin-gonic/gin v1\n")
        assert detect_declared_frameworks(root) == []


def test_broken_oversized_and_non_object_manifests_do_not_crash() -> None:
    with _root() as root:
        write(root / "package.json", "{not json")
        write(root / "pyproject.toml", "[project\n")
        write(root / "requirements.txt", "\x00\x01 garbage \n")
        assert detect_declared_frameworks(root) == []
        write(root / "package.json", "[1, 2]")
        assert detect_declared_frameworks(root) == []
        write(root / "package.json", " " * (1024 * 1024 + 10) + '{"dependencies":{}}')
        assert detect_declared_frameworks(root) == []


def test_output_is_deterministic_sorted_and_not_a_mutation_of_anything() -> None:
    with _root() as root:
        write(root / "package.json", '{"dependencies": {"vue": "1", "astro": "1"}}')
        write(root / "requirements.txt", "flask\nfastapi\n")
        first = detect_declared_frameworks(root)
        second = detect_declared_frameworks(root)
        assert first == second
        assert json.dumps([asdict(e) for e in first]) == json.dumps(
            [asdict(e) for e in second]
        )
        keys = [(e.manifest, e.label, e.name) for e in first]
        assert keys == sorted(keys)


def test_a_dependency_declared_in_two_scopes_keeps_both_entries() -> None:
    with _root() as root:
        write(
            root / "package.json",
            '{"dependencies": {"react": "1"}, "devDependencies": {"react": "1"}}',
        )
        assert _entries(root) == [
            ("package.json", "react", "dev"),
            ("package.json", "react", "runtime"),
        ]


def test_shared_reader_returns_the_scope_manifest_and_name() -> None:
    with _root() as root:
        write(root / "package.json", '{"devDependencies": {"left-pad": "1"}}')
        deps = declared_dependencies(root, {"package.json"})
        assert [tuple(d) for d in deps] == [("left-pad", "dev", "package.json")]


def _many(count: int) -> list[FrameworkEntry]:
    return [
        FrameworkEntry(
            name=f"pkg{i:02d}", label=f"Label{i:02d}", scope="runtime", manifest="m"
        )
        for i in range(count)
    ]


def test_quick_context_caps_the_list_and_keeps_the_real_total() -> None:
    for data in _fixture("minimal"):
        data.frameworks_declared = _many(12)
        qc = build_quick_context(data)
        assert len(qc.frameworks_declared) == 8
        assert qc.frameworks_declared_total == 12
        line = [
            ln
            for ln in markdown.render(data).splitlines()
            if "Declared frameworks" in ln
        ]
        assert len(line) == 1
        assert "(from manifests, not verified in code)" in line[0]
        assert line[0].endswith("(+4 more)") and "Label07" in line[0]
        assert "Label08" not in line[0]


def test_no_frameworks_means_no_line_in_any_renderer() -> None:
    for data in _fixture("minimal"):
        for render in (markdown.render, text.render, html.render):
            assert "Declared frameworks" not in render(data)
        assert build_quick_context(data).frameworks_declared == []


def test_markdown_html_and_text_all_carry_the_framework_line() -> None:
    for data in _fixture("hybrid"):
        assert "FastAPI (fastapi, runtime; pyproject.toml)" in markdown.render(data)
        assert "FastAPI (fastapi, runtime; pyproject.toml)" in text.render(data)
        assert "FastAPI (fastapi, runtime; pyproject.toml)" in html.render(data)


def test_html_and_text_share_one_lines_function() -> None:
    for name in FIXTURES:
        for data in _fixture(name):
            lines = quick_context_lines(build_quick_context(data))
            out_text = text.render(data)
            out_html = html.render(data)
            for line in lines:
                assert f"  {line}" in out_text
                assert escape(line) in out_html


def test_html_escapes_names_that_come_from_a_manifest() -> None:
    for data in _fixture("minimal"):
        data.frameworks_declared = [
            FrameworkEntry(name="<script>x</script>", label="A&B", manifest="m.json")
        ]
        out = html.render(data)
        assert "<script>x</script>" not in out
        assert "&lt;script&gt;" in out and "A&amp;B" in out


def test_markdown_line_cannot_break_out_with_backticks_or_pipes() -> None:
    for data in _fixture("minimal"):
        data.frameworks_declared = [
            FrameworkEntry(name="a`b|c", label="L`|", manifest="m")
        ]
        line = next(ln for ln in markdown.render(data).splitlines() if "Declared" in ln)
        assert "`" not in line.split(":**", 1)[1]


def test_the_block_is_the_same_object_in_json_and_never_touches_analysis() -> None:
    for data in _fixture("hybrid"):
        before = copy.deepcopy(data)
        payload = json.loads(json_renderer.render(data))
        qc = payload["quick_context"]
        assert qc["frameworks_declared_total"] == 2
        assert [e["name"] for e in qc["frameworks_declared"]] == ["fastapi", "pytest"]
        assert data == before
        assert build_quick_context(data) == build_quick_context(before)


def test_format_framework_is_clipped_and_stable() -> None:
    entry = FrameworkEntry(name="n" * 300, label="L", scope="dev", manifest="m" * 300)
    out = format_framework(entry)
    assert len(out) <= 100 and out.endswith("…")
    assert format_framework(FrameworkEntry(name="x", label="X")) == "X (x)"
