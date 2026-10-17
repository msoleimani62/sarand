"""One Python floor, everywhere (AGENTS.md 5.71).

The minimum supported Python used to be written in a dozen places (the package
metadata, the PyO3 abi3 feature, the CI matrix, the release smoke tests, the
doctor check, both READMEs, a compatibility shim for `tomllib`). Dropping a
version meant finding all of them by hand. This test reads the floor from
`pyproject.toml` and requires every other place to agree with it.
"""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path
from typing import Any

import yaml
from sarand.core import doctor

_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT: dict[str, Any] = tomllib.loads(
    (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
)


def _floor() -> tuple[int, int]:
    match = re.fullmatch(r">=\s*(\d+)\.(\d+)", _PYPROJECT["project"]["requires-python"])
    assert match, _PYPROJECT["project"]["requires-python"]
    return int(match.group(1)), int(match.group(2))


def _version_key(text: str) -> tuple[int, int]:
    major, minor = str(text).split(".")[:2]
    return int(major), int(minor)


def _workflow(name: str) -> dict[str, Any]:
    path = _ROOT / ".github" / "workflows" / name
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data


def test_the_floor_is_at_least_python_311() -> None:
    # 3.10 reached end of life in October 2026 (AGENTS.md 5.71).
    assert _floor() >= (3, 11)


def test_classifiers_start_at_the_floor() -> None:
    versions = [
        _version_key(item.rsplit("::", 1)[1].strip())
        for item in _PYPROJECT["project"]["classifiers"]
        if re.fullmatch(r"Programming Language :: Python :: 3\.\d+", item)
    ]
    assert min(versions) == _floor()


def test_the_abi3_wheel_targets_the_floor() -> None:
    major, minor = _floor()
    features = _PYPROJECT["tool"]["maturin"]["features"]
    assert f"pyo3/abi3-py{major}{minor}" in features
    assert sum(1 for f in features if f.startswith("pyo3/abi3-py")) == 1


def test_tomli_is_no_longer_a_dependency_or_an_import() -> None:
    dependencies = _PYPROJECT["project"]["dependencies"]
    assert not any(str(item).lower().startswith("tomli") for item in dependencies)
    offenders: list[str] = []
    for folder in ("python", "tests", "scripts"):
        for path in sorted((_ROOT / folder).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import) and any(
                    alias.name == "tomli" for alias in node.names
                ):
                    offenders.append(f"{path.relative_to(_ROOT)}:{node.lineno}")
    assert offenders == []


def test_the_doctor_check_uses_the_floor() -> None:
    assert doctor._MIN_PYTHON == _floor()


def test_the_ci_matrix_starts_at_the_floor_and_the_newest_is_not_blocking() -> None:
    matrix = _workflow("ci.yml")["jobs"]["quality"]["strategy"]["matrix"]
    versions = [str(v) for v in matrix["python-version"]]
    versions += [str(i["python-version"]) for i in matrix["include"]]
    assert min(_version_key(v) for v in versions) == _floor()
    experimental = [i for i in matrix["include"] if i.get("experimental")]
    for entry in experimental:
        assert _version_key(str(entry["python-version"])) > _floor()
    blocking = [i for i in matrix["include"] if not i.get("experimental")]
    assert blocking, "at least one non-experimental extra Python must run"


def test_the_release_smoke_tests_run_the_floor_on_every_os() -> None:
    entries = _workflow("release.yml")["jobs"]["smoke"]["strategy"]["matrix"]["include"]
    wanted = f"{_floor()[0]}.{_floor()[1]}"
    for runner in ("ubuntu-24.04", "macos-latest", "windows-latest"):
        pythons = {str(e["python"]) for e in entries if e["runner"] == runner}
        assert wanted in pythons, runner


def test_both_readmes_show_the_floor_in_the_badge() -> None:
    major, minor = _floor()
    for name in ("README.md", "README.fa.md"):
        text = (_ROOT / name).read_text(encoding="utf-8")
        assert f"python-{major}.{minor}%2B" in text, name
        assert f'alt="Python {major}.{minor}+"' in text, name
