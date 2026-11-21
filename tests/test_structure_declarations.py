"""Declared dependencies in the structure (R14-A3, criterion 4).

An external import is `external_declared` when a manifest declares the package and
`external_unmatched` when none does. These tests cover which manifest sections count,
that the section name is kept in `declared_in`, how an import name that differs from its
distribution name is matched (an explicit table, never a guess) and that the other
classes do not change.
"""

from __future__ import annotations

from pathlib import Path

from _structure_helpers import build, write_tree
from sarand.core.components import (
    PythonDeclaration,
    declared_dependencies,
    python_declarations,
)
from sarand.structure.distributions import PROVIDED_BY, providers
from sarand.structure.imports import normalise_distribution
from sarand.structure.model import (
    CONF_DEFINITE,
    CONF_PROBABLE,
    TARGET_EXTERNAL_DECLARED,
    TARGET_EXTERNAL_UNMATCHED,
    TARGET_INTERNAL,
    TARGET_STDLIB,
    StructureData,
)
from sarand.structure.serialize import structure_payload

PYPROJECT = """\
[project]
name = "proj"
dependencies = ["requests[security]>=2; python_version > '3.8'", "PyYAML"]

[project.optional-dependencies]
dev = ["pytest>=8"]
docs = ["sphinx"]

[dependency-groups]
tests = ["coverage", {include-group = "lint"}]
lint = ["ruff"]

[build-system]
requires = ["setuptools>=61"]

[tool.poetry.dependencies]
python = "^3.11"
Django = "^5"

[tool.poetry.dev-dependencies]
black = "*"

[tool.poetry.group.test.dependencies]
pytest-django = "*"
"""


def _edges(data: StructureData) -> dict[str, tuple[str, str, str]]:
    """requested name -> (class, confidence, method)."""
    return {
        e.requested: (e.target_class, e.confidence, e.resolution_method)
        for e in data.edges
    }


def _declared_in(data: StructureData, name: str) -> tuple[str, ...]:
    return next(x for x in data.externals if x.name == name).declared_in


def _build(tmp_path: Path, files: dict[str, str]) -> StructureData:
    return build(tmp_path, files)


# --- the reader --------------------------------------------------------------------


def test_every_section_is_read_with_its_name(tmp_path: Path) -> None:
    write_tree(
        tmp_path, {"pyproject.toml": PYPROJECT, "requirements.txt": "# c\nFlask==3\n"}
    )
    found = python_declarations(tmp_path, {"pyproject.toml", "requirements.txt"})
    assert sorted(found) == sorted(
        [
            PythonDeclaration("requests", "project.dependencies", "pyproject.toml"),
            PythonDeclaration("pyyaml", "project.dependencies", "pyproject.toml"),
            PythonDeclaration(
                "pytest", "project.optional-dependencies.dev", "pyproject.toml"
            ),
            PythonDeclaration(
                "sphinx", "project.optional-dependencies.docs", "pyproject.toml"
            ),
            PythonDeclaration("coverage", "dependency-groups.tests", "pyproject.toml"),
            PythonDeclaration("ruff", "dependency-groups.lint", "pyproject.toml"),
            PythonDeclaration("setuptools", "build-system.requires", "pyproject.toml"),
            PythonDeclaration("django", "tool.poetry.dependencies", "pyproject.toml"),
            PythonDeclaration(
                "black", "tool.poetry.dev-dependencies", "pyproject.toml"
            ),
            PythonDeclaration(
                "pytest-django", "tool.poetry.group.test.dependencies", "pyproject.toml"
            ),
            PythonDeclaration("flask", "requirements.txt", "requirements.txt"),
        ]
    )


def test_the_interpreter_pin_of_poetry_is_not_a_package(tmp_path: Path) -> None:
    write_tree(tmp_path, {"pyproject.toml": PYPROJECT})
    names = {d.name for d in python_declarations(tmp_path, {"pyproject.toml"})}
    assert "python" not in names


def test_odd_manifests_are_skipped_not_fatal(tmp_path: Path) -> None:
    write_tree(
        tmp_path,
        {
            "pyproject.toml": (
                "[project]\ndependencies = 'not a list'\n"
                "[project.optional-dependencies]\ndev = 5\n"
                "[dependency-groups]\ng = [{include-group = 'x'}, 3]\n"
                "[tool.poetry.group.bad]\ndependencies = 7\n"
                "[tool.poetry.group.alsobad]\n"
            ),
            "requirements.txt": "-r other.txt\n\n# only a comment\n",
        },
    )
    assert python_declarations(tmp_path, {"pyproject.toml", "requirements.txt"}) == []
    write_tree(tmp_path / "broken", {"pyproject.toml": "[project\nnot toml"})
    assert python_declarations(tmp_path / "broken", {"pyproject.toml"}) == []


def test_the_older_reader_keeps_reporting_only_its_three_sections(
    tmp_path: Path,
) -> None:
    write_tree(
        tmp_path, {"pyproject.toml": PYPROJECT, "requirements.txt": "Flask==3\n"}
    )
    entries = [
        (d.manifest, d.name, d.scope)
        for d in declared_dependencies(tmp_path, {"pyproject.toml", "requirements.txt"})
    ]
    assert entries == [
        ("pyproject.toml", "requests", "runtime"),
        ("pyproject.toml", "pyyaml", "runtime"),
        ("pyproject.toml", "django", "runtime"),
        ("requirements.txt", "flask", ""),
    ]


# --- the structure -----------------------------------------------------------------


def test_declared_in_names_the_section_of_every_kind_of_declaration(
    tmp_path: Path,
) -> None:
    data = _build(
        tmp_path,
        {
            "pyproject.toml": PYPROJECT,
            "requirements.txt": "Flask==3\n",
            "a.py": (
                "import requests\nimport pytest\nimport sphinx\nimport coverage\n"
                "import ruff\nimport setuptools\nimport django\nimport black\n"
                "import pytest_django\nimport flask\nimport numpy\n"
            ),
        },
    )
    edges = _edges(data)
    expected = {
        "requests": "pyproject.toml#project.dependencies",
        "pytest": "pyproject.toml#project.optional-dependencies.dev",
        "sphinx": "pyproject.toml#project.optional-dependencies.docs",
        "coverage": "pyproject.toml#dependency-groups.tests",
        "ruff": "pyproject.toml#dependency-groups.lint",
        "setuptools": "pyproject.toml#build-system.requires",
        "django": "pyproject.toml#tool.poetry.dependencies",
        "black": "pyproject.toml#tool.poetry.dev-dependencies",
        "pytest_django": "pyproject.toml#tool.poetry.group.test.dependencies",
        "flask": "requirements.txt",
    }
    for name, label in expected.items():
        assert edges[name][:2] == (TARGET_EXTERNAL_DECLARED, CONF_DEFINITE), name
        assert edges[name][2] == "declared-dependency", name
        assert _declared_in(data, name) == (label,), name
    # a dependency that no manifest declares stays unmatched
    assert edges["numpy"][:2] == (TARGET_EXTERNAL_UNMATCHED, CONF_PROBABLE)
    assert edges["numpy"][2] == "external-by-elimination"
    assert _declared_in(data, "numpy") == ()


def test_a_package_declared_in_several_places_lists_every_place(
    tmp_path: Path,
) -> None:
    data = _build(
        tmp_path,
        {
            "pyproject.toml": (
                "[project]\nname = 'p'\ndependencies = ['requests']\n"
                "[project.optional-dependencies]\nnet = ['requests>=2']\n"
                "[dependency-groups]\ntests = ['requests']\n"
            ),
            "requirements.txt": "requests==2.31\n",
            "a.py": "import requests\n",
        },
    )
    assert _declared_in(data, "requests") == (
        "pyproject.toml#dependency-groups.tests",
        "pyproject.toml#project.dependencies",
        "pyproject.toml#project.optional-dependencies.net",
        "requirements.txt",
    )


def test_a_nested_manifest_keeps_its_directory_in_the_label(tmp_path: Path) -> None:
    data = _build(
        tmp_path,
        {
            "tools/pyproject.toml": "[project]\nname = 't'\ndependencies = ['rich']\n",
            "tools/run.py": "import rich\n",
            "other/requirements.txt": "rich\n",
        },
    )
    assert _declared_in(data, "rich") == (
        "other/requirements.txt",
        "tools/pyproject.toml#project.dependencies",
    )


def test_an_import_name_that_differs_from_its_distribution_is_matched_by_the_table(
    tmp_path: Path,
) -> None:
    data = _build(
        tmp_path,
        {
            "pyproject.toml": "[dependency-groups]\nio = ['PyYAML', 'Pillow']\n",
            "a.py": "import yaml\nfrom PIL import Image\n",
        },
    )
    edges = _edges(data)
    assert edges["yaml"] == (
        TARGET_EXTERNAL_DECLARED,
        CONF_PROBABLE,
        "declared-distribution",
    )
    assert edges["PIL"][:2] == (TARGET_EXTERNAL_DECLARED, CONF_PROBABLE)
    assert _declared_in(data, "yaml") == ("pyproject.toml#dependency-groups.io",)
    assert _declared_in(data, "PIL") == ("pyproject.toml#dependency-groups.io",)
    note = next(e.note for e in data.edges if e.requested == "yaml")
    assert "distributions.py" in note


def test_the_table_does_not_declare_what_nothing_declares(tmp_path: Path) -> None:
    data = _build(
        tmp_path,
        {
            "pyproject.toml": "[project]\nname = 'p'\ndependencies = ['requests']\n",
            "a.py": "import yaml\nimport cv2\n",
        },
    )
    edges = _edges(data)
    assert edges["yaml"][:2] == (TARGET_EXTERNAL_UNMATCHED, CONF_PROBABLE)
    assert edges["cv2"][:2] == (TARGET_EXTERNAL_UNMATCHED, CONF_PROBABLE)


def test_a_pair_that_is_not_in_the_table_is_not_guessed(tmp_path: Path) -> None:
    data = _build(
        tmp_path,
        {
            "pyproject.toml": (
                "[project]\nname = 'p'\ndependencies = ['pymupdf', 'foobar', 'tool-box']\n"
            ),
            "a.py": "import fitz\nimport foo_bar\nimport toolbox\n",
        },
    )
    edges = _edges(data)
    # `fitz` is shipped by `pymupdf`, but that pair is not in the table; `foo_bar` and
    # `toolbox` are not the normalised names `foobar` and `tool-box`
    for name in ("fitz", "foo_bar", "toolbox"):
        assert edges[name][:2] == (TARGET_EXTERNAL_UNMATCHED, CONF_PROBABLE), name


def test_a_name_with_several_providers_keeps_every_declared_one(tmp_path: Path) -> None:
    data = _build(
        tmp_path,
        {
            "pyproject.toml": (
                "[project]\nname = 'p'\ndependencies = ['opencv-python-headless']\n"
                "[dependency-groups]\nextra = ['opencv-contrib-python']\n"
            ),
            "a.py": "import cv2\n",
        },
    )
    assert _edges(data)["cv2"][:2] == (TARGET_EXTERNAL_DECLARED, CONF_PROBABLE)
    assert _declared_in(data, "cv2") == (
        "pyproject.toml#dependency-groups.extra",
        "pyproject.toml#project.dependencies",
    )


def test_the_same_named_distribution_makes_it_definite_and_the_provider_adds_places(
    tmp_path: Path,
) -> None:
    data = _build(
        tmp_path,
        {
            "pyproject.toml": (
                "[project]\nname = 'p'\ndependencies = ['psycopg2']\n"
                "[dependency-groups]\nbin = ['psycopg2-binary']\n"
            ),
            "a.py": "import psycopg2\n",
        },
    )
    assert _edges(data)["psycopg2"] == (
        TARGET_EXTERNAL_DECLARED,
        CONF_DEFINITE,
        "declared-dependency",
    )
    assert _declared_in(data, "psycopg2") == (
        "pyproject.toml#dependency-groups.bin",
        "pyproject.toml#project.dependencies",
    )


def test_a_literal_dynamic_import_through_the_table_is_probable(tmp_path: Path) -> None:
    data = _build(
        tmp_path,
        {
            "pyproject.toml": "[project]\nname = 'p'\ndependencies = ['PyYAML']\n",
            "a.py": "import importlib\nmod = importlib.import_module('yaml')\n",
        },
    )
    edge = next(e for e in data.edges if e.requested == "yaml")
    assert (edge.target_class, edge.confidence) == (
        TARGET_EXTERNAL_DECLARED,
        CONF_PROBABLE,
    )
    assert edge.resolution_method == "importlib-literal"


def test_internal_and_standard_library_names_are_not_taken_over(tmp_path: Path) -> None:
    data = _build(
        tmp_path,
        {
            "pyproject.toml": (
                "[project]\nname = 'p'\ndependencies = ['PyYAML', 'json', 'localmod']\n"
            ),
            "yaml.py": "x = 1\n",
            "localmod.py": "y = 2\n",
            "a.py": "import yaml\nimport json\nimport localmod\n",
        },
    )
    edges = _edges(data)
    assert edges["yaml"][0] == TARGET_INTERNAL
    assert edges["localmod"][0] == TARGET_INTERNAL
    assert edges["json"][0] == TARGET_STDLIB
    assert data.externals == tuple(
        x for x in data.externals if x.target_class == TARGET_STDLIB
    )


def test_the_json_payload_carries_the_section_labels(tmp_path: Path) -> None:
    data = _build(
        tmp_path,
        {
            "pyproject.toml": "[dependency-groups]\nt = ['pytest']\n",
            "a.py": "import pytest\n",
        },
    )
    payload = structure_payload(data)
    external = next(x for x in payload["externals"] if x["name"] == "pytest")
    assert external["target_class"] == "external_declared"
    assert external["declared_in"] == ["pyproject.toml#dependency-groups.t"]


# --- the table ---------------------------------------------------------------------


def test_the_table_is_sorted_normalised_and_never_maps_a_name_to_itself() -> None:
    assert list(PROVIDED_BY) == sorted(PROVIDED_BY)
    for import_name, distributions in PROVIDED_BY.items():
        assert import_name
        assert distributions, import_name
        assert len(set(distributions)) == len(distributions), import_name
        for name in distributions:
            assert name == normalise_distribution(name), (import_name, name)
            # the distribution of the same name is always tried first
            assert name != normalise_distribution(import_name), import_name


def test_the_table_lookup_is_exact() -> None:
    assert providers("yaml") == ("pyyaml",)
    assert providers("PIL") == ("pillow", "pillow-simd")
    assert providers("Yaml") == ()
    assert providers("numpy") == ()
    assert len(providers("cv2")) == 4


def test_usage_sites_follow_the_same_declared_rule_as_the_import_edges(
    tmp_path: Path,
) -> None:
    data = _build(
        tmp_path,
        {
            "pyproject.toml": (
                "[dependency-groups]\nio = ['PyYAML']\ntests = ['pytest']\n"
            ),
            "a.py": (
                "import yaml\nimport pytest\nimport numpy\n\n\n"
                "def f(x):\n    yaml.safe_load(x)\n    pytest.fixture(x)\n"
                "    return numpy.array(x)\n"
            ),
        },
    )
    sites = structure_payload(data)["sites"]
    # one call through each external name: the alias (`yaml`) and the same-named
    # distribution (`pytest`) are declared, `numpy` is not
    assert sites["external_declared"] == 2
    assert sites["external_unmatched"] == 1
