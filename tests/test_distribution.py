"""Regression tests for backlog item 13 (distribution and installation),
see AGENTS.md section 5.44: version consistency across every file that
carries it, AUR dependency coverage, and the release/smoke helpers.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
from pathlib import Path
from types import ModuleType

import pytest
from sarand.core.kubernetes import detect_kubernetes

ROOT = Path(__file__).resolve().parent.parent


def _load_script(name: str) -> ModuleType:
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_script_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


release = _load_script("release")
smoke = _load_script("smoke_install")


def _read(*parts: str) -> str:
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def test_every_file_that_carries_the_version_agrees() -> None:
    version = release.read_version(_read("pyproject.toml"))
    cargo = re.search(r'(?m)^version\s*=\s*"([^"]+)"', _read("Cargo.toml"))
    lock = re.search(r'name = "sarand_core"\nversion = "([^"]+)"', _read("Cargo.lock"))
    pkgver = re.search(r"(?m)^pkgver=(.+)$", _read("pkgs", "aur", "PKGBUILD"))
    newest = release.changelog_versions(_read("CHANGELOG.md"))[0]
    assert cargo and lock and pkgver
    assert {
        "Cargo.toml": cargo.group(1),
        "Cargo.lock": lock.group(1),
        "PKGBUILD": pkgver.group(1).strip(),
        "CHANGELOG.md": newest,
    } == dict.fromkeys(
        ("Cargo.toml", "Cargo.lock", "PKGBUILD", "CHANGELOG.md"), version
    ), "run `python3 scripts/release.py bump X.Y.Z` instead of editing by hand"


_AUR_PACKAGE_FOR = {
    "filelock": "python-filelock",
    "rich": "python-rich",
    "pyyaml": "python-yaml",
}


def _runtime_dependencies() -> list[str]:
    text = _read("pyproject.toml")
    found = re.search(r"(?ms)^dependencies = \[(.*?)^\]", text)
    assert found is not None
    block = found.group(1)
    names = []
    for line in block.splitlines():
        match = re.match(r'\s*"([A-Za-z0-9_.-]+)([^"]*)"', line)
        if match and "python_version" not in match.group(2):
            names.append(match.group(1).lower())
    return names


def test_aur_depends_cover_every_runtime_dependency() -> None:
    pkgbuild = _read("pkgs", "aur", "PKGBUILD")
    depends = re.search(r"(?s)^depends=\((.*?)\)", pkgbuild, re.MULTILINE)
    assert depends is not None
    declared = set(re.findall(r"'([^']+)'", depends.group(1)))
    for name in _runtime_dependencies():
        assert name in _AUR_PACKAGE_FOR, (
            f"new runtime dependency {name!r}: map it to its Arch package in "
            "_AUR_PACKAGE_FOR and in pkgs/aur/PKGBUILD"
        )
        assert _AUR_PACKAGE_FOR[name] in declared, f"PKGBUILD depends lacks {name}"


def test_bump_texts_updates_all_four_files_and_nothing_else() -> None:
    pyproject = '[project]\nname = "sarand"\nversion = "0.6.0"\n'
    cargo = '[package]\nname = "sarand_core"\nversion = "0.6.0"\n[dependencies]\n'
    lock = (
        'name = "other"\nversion = "1.0.0"\n\nname = "sarand_core"\nversion = "0.6.0"\n'
    )
    pkgbuild = "pkgname=sarand\npkgver=0.1.1\npkgrel=1\n"
    new = release.bump_texts("0.6.11", pyproject, cargo, lock, pkgbuild)
    assert 'version = "0.6.11"' in new[0] and 'name = "sarand"' in new[0]
    assert 'version = "0.6.11"' in new[1]
    assert 'version = "1.0.0"' in new[2]
    assert 'name = "sarand_core"\nversion = "0.6.11"' in new[2]
    assert "pkgver=0.6.11" in new[3] and "pkgrel=1" in new[3]


def test_bump_texts_rejects_bad_versions_and_missing_lines() -> None:
    good = ('version = "1.0.0"\n', 'version = "1.0.0"\n', "", "pkgver=1\n")
    with pytest.raises(ValueError):
        release.bump_texts("v1.2", *good)
    with pytest.raises(ValueError):
        release.bump_texts("1.2.3", *good)  # Cargo.lock has no sarand_core entry


def test_changelog_versions_reads_numeric_headings_in_order() -> None:
    text = "# Changelog\n\n## [Unreleased]\n\n## [0.6.11] - d\n\n## [0.6.0] - d\n"
    assert release.changelog_versions(text) == ["0.6.11", "0.6.0"]


def test_smoke_helpers_find_the_wheel_and_build_a_detectable_helm_project() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "dist").mkdir()
        (base / "dist" / "sarand-0.6.0-cp312-linux.whl").write_text("")
        (base / "dist" / "sarand-0.6.11-cp312-linux.whl").write_text("")
        assert smoke.find_wheel(base / "dist").name.startswith("sarand-0.6.11")
        project = base / "project"
        project.mkdir()
        smoke.make_helm_project(project)
        info = detect_kubernetes(project)
        assert info is not None and [c.path for c in info.helm_charts] == ["chart"]
    assert smoke.project_version() == release.read_version(_read("pyproject.toml"))
