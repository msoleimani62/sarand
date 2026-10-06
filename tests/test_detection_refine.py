"""Regression tests for backlog status follow-up 3 -- see AGENTS.md section
5.51 and `core/detection_refine.py` for the audit and the rules."""

from __future__ import annotations

import copy
import tempfile
from pathlib import Path

from _helpers import write
from sarand import cli
from sarand.core.components import detect_components
from sarand.core.compose import detect_compose
from sarand.core.detection_refine import refine_detection
from sarand.core.kubernetes import detect_kubernetes
from sarand.core.makefile import detect_makefiles
from sarand.discovery.project_detector import detect_project
from sarand.models.results import Component, ComponentsInfo, ProjectDetection
from test_components import build_hybrid


def _detect(root: Path) -> tuple[ProjectDetection, ComponentsInfo | None]:
    components = detect_components(
        root, detect_kubernetes(root), detect_compose(root), detect_makefiles(root)
    )
    return detect_project(root), components


def test_the_audited_gap_makefile_only_root_no_longer_says_generic() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build_hybrid(root)
        before, components = _detect(root)
        assert before.primary_language == "Generic"  # the audited behaviour
        after = refine_detection(before, components)
        assert after.primary_language == "Python + Node.js"
        assert after.languages == ["Python", "Node.js"]
        assert after.project_type == "hybrid: backend (Python), frontend (Node.js)"
        assert after.build_system == "make"
        assert "Makefile" in after.markers_found
        assert "backend/pyproject.toml" in after.markers_found
        assert "frontend/package.json" in after.markers_found


def test_a_real_root_language_is_kept_and_component_languages_are_added() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build_hybrid(root)
        write(root / "pyproject.toml", '[project]\nname = "x"\nversion = "1"\n')
        before, components = _detect(root)
        assert before.languages == ["Python", "Generic"]
        after = refine_detection(before, components)
        assert after.primary_language == "Python"
        assert after.project_type == before.project_type
        assert after.languages == ["Python", "Node.js"]


def test_a_non_hybrid_project_gets_the_very_same_object_back() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pyproject.toml", '[project]\nname = "x"\nversion = "1"\n')
        before, components = _detect(root)
        assert components is None
        assert refine_detection(before, components) is before


def test_components_without_an_application_change_nothing() -> None:
    detection = ProjectDetection(
        languages=["Generic"],
        primary_language="Generic",
        markers_found=["Makefile"],
    )
    only_infra = ComponentsInfo(
        components=[Component(path="compose.yaml", role="infrastructure")],
        total_components=1,
    )
    assert refine_detection(detection, only_infra) is detection


def test_the_input_is_never_mutated() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build_hybrid(root)
        before, components = _detect(root)
        snapshot = copy.deepcopy(before)
        components_snapshot = copy.deepcopy(components)
        refine_detection(before, components)
        assert before == snapshot and components == components_snapshot


def test_many_languages_and_components_are_capped_in_the_labels() -> None:
    langs = ["Go", "Ruby", "Rust", "Lua", "PHP"]
    components = ComponentsInfo(
        components=[
            Component(
                path=f"svc{i}",
                role="application",
                languages=[lang],
                evidence=[f"marker{i}"],
            )
            for i, lang in enumerate(langs)
        ],
        total_components=5,
    )
    detection = ProjectDetection(
        languages=["Generic"], primary_language="Generic", markers_found=["Makefile"]
    )
    after = refine_detection(detection, components)
    assert after.primary_language == "Go + Ruby + Rust +2 more"
    assert after.project_type.endswith(", +1 more")
    assert after.project_type.count("(") == 4
    assert after.languages == langs


def test_marker_list_is_capped_deduplicated_and_ordered() -> None:
    components = ComponentsInfo(
        components=[
            Component(
                path="a",
                role="application",
                languages=["Go"],
                evidence=[f"m{i}" for i in range(30)] + ["m0"],
            )
        ],
        total_components=1,
    )
    detection = ProjectDetection(
        languages=["Generic"], primary_language="Generic", markers_found=["Makefile"]
    )
    markers = refine_detection(detection, components).markers_found
    assert markers[0] == "Makefile" and markers[1] == "a/m0"
    assert len(markers) == 1 + 20 and len(set(markers)) == len(markers)


def test_a_root_component_keeps_its_marker_without_a_path_prefix() -> None:
    components = ComponentsInfo(
        components=[
            Component(
                path=".", role="application", languages=["Go"], evidence=["go.mod"]
            )
        ],
        total_components=1,
    )
    detection = ProjectDetection(
        languages=["Generic"], primary_language="Generic", markers_found=["Makefile"]
    )
    assert refine_detection(detection, components).markers_found == [
        "Makefile",
        "go.mod",
    ]


def test_the_report_of_a_hybrid_project_describes_it_correctly() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        project = base / "proj"
        project.mkdir()
        build_hybrid(project)
        reports = base / "reports"
        reports.mkdir()
        code = cli.main(
            ["-p", str(project), "-d", str(reports), "--skip-tests", "-o", "r.md"]
        )
        assert code == 0
        text = (reports / "r.md").read_text(encoding="utf-8")
        assert "- **Primary language:** Python + Node.js" in text
        assert "- **All detected languages:** Python, Node.js" in text
        assert (
            "- **Project type:** hybrid: backend (Python), frontend (Node.js)" in text
        )
        assert "Generic" not in text.split("## Project Components")[0]
