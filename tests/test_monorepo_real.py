"""sarand's reading of turbo.json against the real Turborepo (round R12).

Runs only when SARAND_REAL_TURBO is set (the CI job `turbo` sets it, and
SARAND_TURBO_BIN points at the pinned binary), so a normal `pytest` skips it
visibly.

What this is: **evidence of compatibility** for one pinned Turborepo version on
one small fixture, not proof that every Turborepo version or feature is
supported. It compares what sarand reads from `turbo.json` with what Turborepo
itself resolves for the same tasks: `turbo run <task> --dry=json` lists, per task
instance, `resolvedTaskDefinition` (declared `dependsOn`, `outputs`, `cache`,
`persistent`). Not comparable, and therefore not compared: the per-package task
instances and the computed graph (sarand does not compute one), package-level
`turbo.json` overrides, and the legacy `pipeline` key of Turborepo 1.x (covered
by unit tests only).

مقایسه‌ی خوانش sarand از turbo.json با Turborepo واقعی؛ شاهد سازگاری برای یک نسخه‌ی
پین‌شده و یک fixture کوچک، نه اثبات پشتیبانی از همه‌ی نسخه‌ها و قابلیت‌ها.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml
from _helpers import write
from sarand.core.monorepo_tools import detect_monorepo_tools
from sarand.core.workspace import detect_workspaces

_CI = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"
_TASKS = {
    "build": {"dependsOn": ["^build"], "outputs": ["dist/**", ".next/**"]},
    "test": {"dependsOn": ["build"]},
    "lint": {},
    "dev": {"cache": False, "persistent": True},
}


def _require() -> str:
    if not os.environ.get("SARAND_REAL_TURBO"):
        pytest.skip("SARAND_REAL_TURBO is not set; see the CI job `turbo`")
    binary = os.environ.get("SARAND_TURBO_BIN", "")
    assert binary and Path(binary).exists(), f"SARAND_TURBO_BIN is wrong: {binary!r}"
    return binary


def _fixture(root: Path) -> None:
    write(
        root / "package.json",
        json.dumps(
            {
                "name": "demo",
                "private": True,
                "packageManager": "npm@10.9.0",
                "workspaces": ["packages/*"],
            }
        ),
    )
    write(
        root / "turbo.json",
        json.dumps({"$schema": "https://turbo.build/schema.json", "tasks": _TASKS}),
    )
    scripts = {name: f"echo {name}" for name in _TASKS}
    for name, deps in (("lib", {}), ("app", {"lib": "*"})):
        write(
            root / "packages" / name / "package.json",
            json.dumps(
                {
                    "name": name,
                    "version": "1.0.0",
                    "dependencies": deps,
                    "scripts": scripts,
                }
            ),
        )
    # A lockfile makes Turborepo's workspace resolution the same as in real use;
    # a failure here only costs a warning from Turborepo, so it is not fatal.
    # lockfile رفتار واقعی را می‌سازد؛ شکستش فقط یک هشدار است.
    subprocess.run(
        ["npm", "install", "--package-lock-only", "--ignore-scripts", "--silent"],
        cwd=root,
        capture_output=True,
        check=False,
        timeout=180,
    )


def _dry_run(binary: str, root: Path, task: str) -> list[dict[str, object]]:
    env = {
        **os.environ,
        "TURBO_TELEMETRY_DISABLED": "1",
        "DO_NOT_TRACK": "1",
        "TURBO_NO_UPDATE_NOTIFIER": "1",
    }
    done = subprocess.run(
        [binary, "run", task, "--dry=json"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    try:
        payload = json.loads(done.stdout)
    except ValueError:
        pytest.fail(
            f"turbo printed no JSON for {task}: {done.stdout[:300]!r} {done.stderr[:300]!r}"
        )
    tasks = payload.get("tasks")
    assert isinstance(tasks, list) and tasks, (
        f"no tasks in the dry run of {task}: {payload!r:.400}"
    )
    return [item for item in tasks if isinstance(item, dict)]


def test_the_tasks_sarand_reads_match_what_turborepo_resolves() -> None:
    binary = _require()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _fixture(root)
        tools = detect_monorepo_tools(root, detect_workspaces(root))
        assert [tool.kind for tool in tools] == ["turbo"]
        ours = {task.name: task for task in tools[0].tasks}
        assert set(ours) == set(_TASKS)
        for name, task in ours.items():
            instances = _dry_run(binary, root, name)
            assert any(item.get("task") == name for item in instances), (
                f"turbo does not know the task {name}"
            )
            for item in instances:
                if item.get("task") != name:
                    continue
                resolved = item.get("resolvedTaskDefinition")
                assert isinstance(resolved, dict), (
                    f"no resolvedTaskDefinition: {item!r:.400}"
                )
                assert list(resolved.get("dependsOn", [])) == task.depends_on, (
                    name,
                    resolved,
                )
                outputs = resolved.get("outputs") or []
                expected = f"{len(outputs)} output pattern(s)" if outputs else ""
                assert expected in task.detail or not expected, (
                    name,
                    resolved,
                    task.detail,
                )
                assert ("cache off" in task.detail) == (
                    resolved.get("cache") is False
                ), (
                    name,
                    resolved,
                )
                assert ("persistent" in task.detail) == (
                    resolved.get("persistent") is True
                ), (
                    name,
                    resolved,
                )


def test_ci_has_a_turbo_job_that_pins_the_version_and_sets_the_switch() -> None:
    job = yaml.safe_load(_CI.read_text(encoding="utf-8"))["jobs"]["turbo"]
    steps = job["steps"]
    switched = [s for s in steps if "SARAND_REAL_TURBO" in s.get("env", {})]
    assert switched
    assert all(s.get("continue-on-error") is not True for s in switched)
    assert any(
        "bash scripts/ci_install_turbo.sh" in str(s.get("run", "")) for s in steps
    )
    script = _CI.parent.parent.parent / "scripts" / "ci_install_turbo.sh"
    text = script.read_text(encoding="utf-8")
    assert 'version="2.' in text  # an exact version, not a range or latest
    assert "turbo@${version}" in text
