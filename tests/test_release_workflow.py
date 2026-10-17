"""The release workflow (AGENTS.md section 5.64) publishes to PyPI with
trusted publishing. Nothing here can run the workflow, so this pins its safety
properties: no stored secret, publishing only from a tag (PyPI) or a manual
dry run (TestPyPI), the OIDC permission only on the two publish jobs, and the
names the PyPI trusted-publisher form must match.

workflow انتشار (بخش ۵.۶۴): این تست‌ها ویژگی‌های ایمنی آن را قفل می‌کنند.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_PATH = _ROOT / ".github" / "workflows" / "release.yml"


def _workflow() -> dict[Any, Any]:
    return yaml.safe_load(_PATH.read_text(encoding="utf-8"))


def _jobs() -> dict[str, Any]:
    return _workflow()["jobs"]


def test_the_file_is_called_release_yml() -> None:
    # The PyPI trusted-publisher form asks for exactly this file name.
    assert _PATH.is_file()


def _triggers() -> dict[str, Any]:
    workflow = _workflow()
    # PyYAML reads the key `on` as the boolean True (YAML 1.1). Indexing, not
    # `.get()`, so the type stays Any and mypy does not see an Optional.
    triggers: dict[str, Any] = workflow["on"] if "on" in workflow else workflow[True]
    return triggers


def test_it_runs_on_tags_and_by_hand_only() -> None:
    triggers = _triggers()
    assert set(triggers) == {"push", "workflow_dispatch"}
    assert triggers["push"]["tags"] == ["v*"]
    assert "branches" not in triggers["push"]


def test_no_secret_is_used_and_the_default_permission_is_read_only() -> None:
    text = _PATH.read_text(encoding="utf-8")
    assert "secrets." not in text
    assert "pull_request" not in text
    assert _workflow()["permissions"] == {"contents": "read"}


def test_only_the_two_publish_jobs_can_mint_an_oidc_token() -> None:
    jobs = _jobs()
    with_token = {
        name for name, job in jobs.items() if "id-token" in job.get("permissions", {})
    }
    assert with_token == {"publish-testpypi", "publish-pypi"}
    for name in with_token:
        assert jobs[name]["permissions"] == {"id-token": "write"}


def test_pypi_publishes_from_a_tag_and_testpypi_only_from_a_manual_dry_run() -> None:
    jobs = _jobs()
    assert "refs/tags/v" in jobs["publish-pypi"]["if"]
    dry_run = jobs["publish-testpypi"]["if"]
    assert "workflow_dispatch" in dry_run and "publish_to_testpypi" in dry_run


def test_each_publish_job_has_the_environment_named_in_the_pypi_form() -> None:
    jobs = _jobs()
    assert jobs["publish-pypi"]["environment"]["name"] == "pypi"
    assert jobs["publish-testpypi"]["environment"]["name"] == "testpypi"
    assert "sarand-cli" in jobs["publish-pypi"]["environment"]["url"]


def test_publishing_waits_for_every_build_and_the_smoke_test() -> None:
    for name in ("publish-pypi", "publish-testpypi"):
        assert set(_jobs()[name]["needs"]) == {"wheels", "sdist", "smoke"}


def test_the_publish_action_is_the_official_one_and_only_testpypi_overrides_the_index() -> (
    None
):
    jobs = _jobs()
    steps = {
        name: [
            s
            for s in jobs[name]["steps"]
            if "pypa/gh-action-pypi-publish" in s.get("uses", "")
        ]
        for name in ("publish-pypi", "publish-testpypi")
    }
    assert all(len(found) == 1 for found in steps.values())
    assert steps["publish-pypi"][0]["uses"] == "pypa/gh-action-pypi-publish@release/v1"
    assert "repository-url" not in steps["publish-pypi"][0]["with"]
    assert "test.pypi.org" in steps["publish-testpypi"][0]["with"]["repository-url"]


def test_wheels_are_built_for_the_five_platforms() -> None:
    matrix = _jobs()["wheels"]["strategy"]["matrix"]["include"]
    assert {entry["name"] for entry in matrix} == {
        "linux-x86_64",
        "linux-aarch64",
        "macos-arm64",
        "macos-x86_64",
        "windows-x64",
    }


def test_a_tag_that_disagrees_with_the_version_is_rejected() -> None:
    check = _jobs()["check"]["steps"]
    assert any("GITHUB_REF_NAME" in step.get("run", "") for step in check)


def test_pyproject_builds_one_abi3_wheel_per_platform() -> None:
    pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"pyo3/abi3-py311"' in pyproject
    assert 'requires-python = ">=3.11"' in pyproject


def test_every_step_runs_in_bash_so_the_wheel_glob_works_on_windows() -> None:
    # The first real run failed on windows-latest: PowerShell does not expand
    # `dist/*.whl`. ci.yml forces bash for the same reason.
    assert _workflow()["defaults"]["run"]["shell"] == "bash"
