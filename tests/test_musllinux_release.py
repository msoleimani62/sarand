"""musllinux (Alpine) wheels are built and smoke-tested before publishing (R9a, D4).

Nothing here can run the workflow; these tests keep its shape: two musllinux
wheels, each installed and run inside an Alpine container, and no publish job
that does not wait for that check.

wheelهای musllinux ساخته می‌شوند، داخل Alpine امتحان می‌شوند و انتشار منتظر آن می‌ماند.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_PATH = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "release.yml"


def _jobs() -> dict[str, Any]:
    jobs: dict[str, Any] = yaml.safe_load(_PATH.read_text(encoding="utf-8"))["jobs"]
    return jobs


def _musl_entries() -> list[dict[str, Any]]:
    matrix = _jobs()["wheels"]["strategy"]["matrix"]["include"]
    return [entry for entry in matrix if str(entry["name"]).startswith("musllinux")]


def test_two_musllinux_wheels_are_built() -> None:
    entries = {entry["name"]: entry for entry in _musl_entries()}
    assert set(entries) == {"musllinux-x86_64", "musllinux-aarch64"}
    assert entries["musllinux-x86_64"]["target"] == "x86_64"
    assert entries["musllinux-aarch64"]["target"] == "aarch64"
    assert {entry["manylinux"] for entry in entries.values()} == {"musllinux_1_2"}


def test_each_musllinux_wheel_is_smoke_tested_in_alpine() -> None:
    job = _jobs()["smoke-musl"]
    assert job["needs"] == "wheels"
    artifacts = {entry["artifact"] for entry in job["strategy"]["matrix"]["include"]}
    assert artifacts == {f"dist-wheels-{entry['name']}" for entry in _musl_entries()}
    runners = {entry["runner"] for entry in job["strategy"]["matrix"]["include"]}
    assert runners == {"ubuntu-24.04", "ubuntu-24.04-arm"}
    runs = " ".join(step.get("run", "") for step in job["steps"])
    assert "docker run" in runs and "python:3.12-alpine" in runs


def test_the_alpine_smoke_test_runs_the_command_and_loads_the_compiled_core() -> None:
    job = _jobs()["smoke-musl"]
    script = " ".join(
        step.get("env", {}).get("SCRIPT", "") for step in job["steps"] if "env" in step
    )
    assert "sarand --version" in script
    assert "sarand._core" in script


def test_no_publish_job_skips_the_alpine_smoke_test() -> None:
    jobs = _jobs()
    assert "smoke-musl" in jobs["publish-testpypi"]["needs"]
    assert "smoke-musl" in jobs["publish-pypi"]["needs"]
