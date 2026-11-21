"""The comparison of two structure outputs (`scripts/structure_diff.py`, R14-A3)."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "structure_diff", _ROOT / "scripts" / "structure_diff.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _payload(tmp_path: Path) -> tuple[ModuleType, dict[str, Any]]:
    module = _load()
    project = tmp_path / "proj"
    (project / "pkg").mkdir(parents=True)
    (project / "pyproject.toml").write_text(
        "[project]\nname = 'p'\ndependencies = ['PyYAML']\n", encoding="utf-8"
    )
    (project / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (project / "pkg" / "a.py").write_text(
        "import os\nimport yaml\nimport numpy\n\n\ndef f():\n    return os, yaml, numpy\n",
        encoding="utf-8",
    )
    payload = module.dump(project, tmp_path / "out" / "a.json")
    return module, json.loads(json.dumps(payload))


def test_two_dumps_of_the_same_code_are_identical(tmp_path: Path) -> None:
    module, payload = _payload(tmp_path)
    report = module.compare(payload, copy.deepcopy(payload))
    assert report["changed_parts"] == []
    assert report["edges_changed"] == 0
    assert report["only_external_edges_changed"] is True
    assert report["summary_changed"] == {} and report["sites_changed"] == {}
    assert (
        json.loads((tmp_path / "out" / "a.json").read_text(encoding="utf-8")) == payload
    )


def test_a_change_of_external_classification_alone_is_recognised(
    tmp_path: Path,
) -> None:
    module, payload = _payload(tmp_path)
    new = copy.deepcopy(payload)
    edge = next(e for e in new["edges"] if e["requested"] == "numpy")
    edge["target_class"] = "external_declared"
    edge["confidence"] = "probable"
    external = next(x for x in new["externals"] if x["name"] == "numpy")
    external["target_class"] = "external_declared"
    external["declared_in"] = ["pyproject.toml#dependency-groups.x"]
    report = module.compare(payload, new)
    assert report["only_external_edges_changed"] is True
    assert report["edges_changed"] == 1
    assert report["edge_fields_changed"] == {"target_class": 1}
    assert [x["name"] for x in report["externals_changed"]] == ["numpy"]
    assert report["changed_parts"] == []


def test_a_change_to_anything_else_is_not_hidden(tmp_path: Path) -> None:
    module, payload = _payload(tmp_path)
    new = copy.deepcopy(payload)
    edge = next(e for e in new["edges"] if e["requested"] == "os")
    edge["target_class"] = "internal"
    new["symbols"] = new["symbols"][:-1]
    report = module.compare(payload, new)
    assert report["only_external_edges_changed"] is False
    assert "symbols" in report["changed_parts"]
    new["edges"] = new["edges"][:-1]
    assert module.compare(payload, new)["only_external_edges_changed"] is False
