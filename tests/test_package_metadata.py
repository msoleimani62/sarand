"""Guards for the package metadata fixed in audit R8c (finding C3).

Three facts must stay true together: the license is declared the PEP 639 way, the
Rust minimum version is declared in `Cargo.toml`, and CI really builds with that
exact toolchain (so the declared number cannot rot).

سه حقیقت باید با هم درست بمانند: لایسنس به شکل PEP 639، حداقل نسخه‌ی Rust در
Cargo.toml، و CI که واقعاً با همان نسخه می‌سازد.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parent.parent


def _toml(name: str) -> dict[str, Any]:
    data: dict[str, Any] = tomllib.loads((_ROOT / name).read_text(encoding="utf-8"))
    return data


def test_license_is_an_spdx_expression_with_the_license_file() -> None:
    project = _toml("pyproject.toml")["project"]
    assert project["license"] == "MIT"
    assert project["license-files"] == ["LICENSE"]
    assert (_ROOT / "LICENSE").is_file()


def test_no_license_classifier_next_to_the_spdx_expression() -> None:
    classifiers = _toml("pyproject.toml")["project"]["classifiers"]
    assert not [c for c in classifiers if c.startswith("License ::")]


def test_the_cargo_license_matches_the_python_license() -> None:
    cargo = _toml("Cargo.toml")["package"]["license"]
    assert cargo == _toml("pyproject.toml")["project"]["license"]


def test_the_build_backend_floor_is_a_verified_maturin() -> None:
    requires = _toml("pyproject.toml")["build-system"]["requires"]
    assert "maturin>=1.14.1,<2.0" in requires


def test_the_minimum_rust_version_is_declared() -> None:
    version = _toml("Cargo.toml")["package"]["rust-version"]
    assert re.fullmatch(r"1\.\d+", version)
    assert tuple(int(part) for part in version.split(".")) >= (1, 88)


def test_ci_builds_with_exactly_the_declared_minimum_rust_version() -> None:
    version = _toml("Cargo.toml")["package"]["rust-version"]
    ci = yaml.safe_load(
        (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    steps = ci["jobs"]["msrv"]["steps"]
    toolchains = [
        step.get("with", {}).get("toolchain")
        for step in steps
        if step.get("uses", "").startswith("dtolnay/rust-toolchain@")
    ]
    assert toolchains == [version]
    runs = " ".join(step.get("run", "") for step in ci["jobs"]["msrv"]["steps"])
    assert "cargo check --locked" in runs


def test_both_readmes_state_the_minimum_rust_version() -> None:
    version = _toml("Cargo.toml")["package"]["rust-version"]
    for name in ("README.md", "README.fa.md"):
        text = (_ROOT / name).read_text(encoding="utf-8")
        assert version in text, name
