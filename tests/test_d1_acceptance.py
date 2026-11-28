"""R14-D1, slice C: the real-run acceptance script (`scripts/d1_acceptance.py`).

The script runs the real command on a copy of a project and checks the real outputs
against the documented contracts. These tests defend the checks themselves: that a key
missing from the schema pages is found, that the planted change is what the contract
needs, and that on a small real project every check passes.

اسکریپت پذیرش با اجرای واقعی: تست‌ها خودِ بررسی‌ها را می‌پایند.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _ROOT / "scripts" / "d1_acceptance.py"
_DOCS = {
    "en": (_ROOT / "docs" / "JSON_SCHEMA.md").read_text(encoding="utf-8"),
    "fa": (_ROOT / "docs" / "JSON_SCHEMA.fa.md").read_text(encoding="utf-8"),
}


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("d1_acceptance", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report() -> dict:
    return {
        "schema_version": "1.12",
        "project_root": "/x",
        "baseline": {
            "schema": 1,
            "reference": {},
            "current": {},
            "summary": {},
            "findings": {},
            "gate": {
                "policy": "new",
                "verdict": "pass",
                "failed_on": [],
                "waived": [],
                "uncertain": [],
                "waivers": {},
            },
        },
    }


def test_the_two_schema_pages_list_the_same_top_level_keys() -> None:
    acc = _load()
    en, fa = (acc.documented_top_level(_DOCS[k]) for k in ("en", "fa"))
    assert en == fa and "baseline" in en and "structure_comparison" in en


def test_a_report_of_documented_keys_has_no_problem() -> None:
    assert _load().undocumented(_report(), _DOCS) == []


def test_a_top_level_key_missing_from_the_pages_is_found_in_both_languages() -> None:
    report = _report()
    report["surprise_key"] = 1
    problems = _load().undocumented(report, _DOCS)
    assert [p for p in problems if "surprise_key" in p] == [
        "top-level key `surprise_key` is not in the en table",
        "top-level key `surprise_key` is not in the fa table",
    ]


def test_a_key_the_contract_does_not_know_inside_baseline_or_gate_is_found() -> None:
    report = _report()
    report["baseline"]["extra"] = 1
    report["baseline"]["gate"]["extra_gate_key"] = 1
    problems = _load().undocumented(report, _DOCS)
    assert "`baseline` has the undocumented key `extra`" in problems
    assert "`gate` has the undocumented key `extra_gate_key`" in problems


def test_a_schema_version_the_pages_do_not_state_is_found() -> None:
    report = _report()
    report["schema_version"] = "99.99"
    problems = _load().undocumented(report, _DOCS)
    assert any(
        "schema version 99.99 is not stated in the en page" in p for p in problems
    )


def test_the_mutation_plants_a_secret_adds_a_file_and_removes_another(
    tmp_path: Path,
) -> None:
    acc = _load()
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("y = 2\n", encoding="utf-8")
    done = acc.mutate(tmp_path)
    assert done == {
        "planted": acc.PLANTED_NAME,
        "added": acc.ADDED_NAME,
        "removed": "b.py",
    }
    assert not (tmp_path / "b.py").exists() and (tmp_path / "a.py").exists()
    assert (tmp_path / acc.ADDED_NAME).is_file()
    assert acc.PLANTED_NAME in {p.name for p in tmp_path.iterdir()}


def test_the_planted_secret_is_not_a_literal_of_this_repository() -> None:
    text = _SCRIPT.read_text(encoding="utf-8")
    needle = "AKIA" + "IOSFODNN7EXAMPLE"  # not a single literal here either
    assert needle not in text
    assert needle in _load()._planted_secret()


def test_a_project_without_python_files_loses_nothing(tmp_path: Path) -> None:
    acc = _load()
    (tmp_path / "notes.md").write_text("hi\n", encoding="utf-8")
    assert acc.mutate(tmp_path)["removed"] is None
    assert (tmp_path / "notes.md").exists()


def test_the_markdown_marks_a_failed_check() -> None:
    acc = _load()
    report = {
        "environment": {"python": "3", "platform": "p", "cpu_count": 1, "code": "c"},
        "projects": [
            {
                "label": "demo",
                "facts": {"files": 3, "schema_version": "1.12", "mutation": {}},
                "checks": [
                    {"id": "A1", "ok": True, "detail": "exit 0"},
                    {"id": "A2", "ok": False, "detail": "bad"},
                ],
            }
        ],
        "passed": False,
    }
    text = acc.render_markdown(report)
    assert "| A1 | Pass | exit 0 |" in text and "| A2 | FAIL | bad |" in text
    assert "AT LEAST ONE CHECK FAILED" in text


def test_the_command_refuses_a_missing_project(tmp_path: Path) -> None:
    acc = _load()
    with pytest.raises(SystemExit) as caught:
        acc.main(["--out", str(tmp_path), "--project", f"x={tmp_path / 'nope'}"])
    assert caught.value.code == 2
    with pytest.raises(SystemExit) as caught:
        acc.main(["--out", str(tmp_path)])
    assert caught.value.code == 2


def test_every_check_passes_on_a_small_real_project(tmp_path: Path) -> None:
    if importlib.util.find_spec("rich") is None:
        pytest.skip("the sarand command needs rich")
    acc = _load()
    project = tmp_path / "proj"
    project.mkdir()
    (project / "main.py").write_text(
        "def main() -> int:\n    return 0\n", encoding="utf-8"
    )
    (project / "util.py").write_text(
        "def helper() -> int:\n    return 1\n", encoding="utf-8"
    )
    out = tmp_path / "out"
    code = acc.main(["--out", str(out), "--project", f"tiny={project}"])
    record = json.loads((out / "acceptance.json").read_text(encoding="utf-8"))
    failed = [c for c in record["projects"][0]["checks"] if not c["ok"]]
    assert code == 0 and failed == []
    assert [c["id"] for c in record["projects"][0]["checks"]] == [
        f"A{i}" for i in range(1, 12)
    ]
    assert project.joinpath("util.py").exists(), "the original project is never touched"
