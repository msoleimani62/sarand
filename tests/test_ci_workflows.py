"""The CI, audit and release workflows keep the guarantees AGENTS.md 5.72 gives them.

Workflows cannot be run from a unit test, so this pins their *shape*: the checks
that must exist, the order that makes a release safe, and the files they depend on.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_GITHUB = _ROOT / ".github"


def _load(path: Path) -> dict[Any, Any]:
    data: dict[Any, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data


def _triggers(workflow: dict[Any, Any]) -> dict[str, Any]:
    # PyYAML reads the bare key `on` as the boolean True.
    value = workflow["on"] if "on" in workflow else workflow[True]
    assert isinstance(value, dict)
    return {str(key): item for key, item in value.items()}


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = job["steps"]
    return steps


def _step_text(step: dict[str, Any]) -> str:
    return f"{step.get('name', '')} {step.get('uses', '')} {step.get('run', '')}"


def test_ci_has_least_privilege_and_cancels_superseded_pull_request_runs() -> None:
    ci = _load(_GITHUB / "workflows" / "ci.yml")
    assert ci["permissions"] == {"contents": "read"}
    group = ci["concurrency"]["group"]
    assert "github.ref" in group
    cancel = str(ci["concurrency"]["cancel-in-progress"])
    assert "pull_request" in cancel  # never cancel a push to main


def test_the_static_job_runs_every_check_and_reports_all_of_them() -> None:
    ci = _load(_GITHUB / "workflows" / "ci.yml")
    steps = _steps(ci["jobs"]["static"])
    text = " ".join(_step_text(s) for s in steps)
    for tool in ("bandit", "markdownlint", "actionlint", "cargo deny", "gitleaks"):
        assert tool in text, tool
    gitleaks = [s for s in steps if "gitleaks" in str(s.get("uses", ""))]
    assert gitleaks, "gitleaks must run through its action"
    assert str(gitleaks[0]["uses"]).startswith("gitleaks/gitleaks-action@v3")
    # Every check after the first still runs when an earlier one failed, so one
    # run reports every problem instead of one per push.
    tools = [s for s in steps if s.get("run") or "gitleaks" in str(s.get("uses", ""))]
    checks = [
        s
        for s in tools
        if any(
            t in _step_text(s)
            for t in (
                "bandit -c",
                "markdownlint",
                "actionlint",
                "cargo deny",
                "gitleaks",
            )
        )
    ]
    for step in checks[1:]:
        assert "cancelled()" in str(step.get("if", "")), step.get("name")
    # gitleaks reads history, so the checkout must be complete.
    checkout = [s for s in steps if "actions/checkout" in str(s.get("uses", ""))]
    assert checkout[0]["with"]["fetch-depth"] == 0


def test_release_checks_ci_before_publishing_and_creates_a_github_release() -> None:
    release = _load(_GITHUB / "workflows" / "release.yml")
    jobs = release["jobs"]
    assert "ci-gate" in jobs
    assert "ci-gate" in jobs["publish-pypi"]["needs"]
    gate = " ".join(_step_text(s) for s in _steps(jobs["ci-gate"]))
    assert "--commit" in gate
    assert "success" in gate
    assert jobs["ci-gate"]["permissions"]["actions"] == "read"
    publish_github = jobs["github-release"]
    assert publish_github["needs"] == "publish-pypi"
    assert publish_github["permissions"] == {"contents": "write"}
    text = " ".join(_step_text(s) for s in _steps(publish_github))
    assert "SHA256SUMS" in text
    assert "gh release" in text
    # Only a real release gets a GitHub Release; TestPyPI dry runs never do.
    assert "publish-testpypi" not in str(publish_github["needs"])


def test_every_wheel_is_smoke_tested_natively() -> None:
    release = _load(_GITHUB / "workflows" / "release.yml")
    wheel_names = {
        f"dist-wheels-{entry['name']}"
        for entry in release["jobs"]["wheels"]["strategy"]["matrix"]["include"]
    }
    smoked = {
        entry["artifact"]
        for entry in release["jobs"]["smoke"]["strategy"]["matrix"]["include"]
    }
    assert wheel_names == smoked
    runners = {
        entry["runner"]
        for entry in release["jobs"]["smoke"]["strategy"]["matrix"]["include"]
    }
    assert {"ubuntu-24.04-arm", "macos-15-intel"} <= runners


def test_the_audit_workflow_is_scheduled_and_separate_from_ci() -> None:
    audit = _load(_GITHUB / "workflows" / "audit.yml")
    triggers = _triggers(audit)
    assert "schedule" in triggers
    assert "workflow_dispatch" in triggers
    assert "Cargo.lock" in triggers["pull_request"]["paths"]
    assert set(audit["jobs"]) == {"pip-audit", "cargo-advisories"}
    assert audit["permissions"] == {"contents": "read"}


def test_dependabot_watches_all_three_ecosystems() -> None:
    config = _load(_GITHUB / "dependabot.yml")
    ecosystems = {u["package-ecosystem"] for u in config["updates"]}
    assert ecosystems == {"github-actions", "cargo", "pip"}


def test_markdownlint_scope_lists_only_files_that_exist() -> None:
    entries = [
        line.strip()
        for line in (_ROOT / ".markdownlintignore")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert "AGENTS.md" in entries
    for entry in entries:
        if entry.endswith(".md"):
            assert (_ROOT / entry).is_file(), (
                f"stale entry in .markdownlintignore: {entry}"
            )


def test_bandit_is_configured_in_pyproject() -> None:
    import tomllib

    config = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "tests" in config["tool"]["bandit"]["exclude_dirs"]
