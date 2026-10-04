"""`scripts/release.py tag` must not tag a commit whose CI is not green
(AGENTS.md section 5.49). Everything here is hermetic: `gh` is never run,
`subprocess.run` is patched, so it behaves the same on every OS."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SHA = "a" * 40


def _load() -> ModuleType:
    path = ROOT / "scripts" / "release.py"
    spec = importlib.util.spec_from_file_location("_release_ci", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


release = _load()


def _run(
    run_id: int, status: str, conclusion: str | None, name: str = "CI", sha: str = SHA
) -> dict[str, object]:
    return {
        "databaseId": run_id,
        "headSha": sha,
        "status": status,
        "conclusion": conclusion,
        "name": name,
    }


def test_a_completed_successful_run_for_head_is_green() -> None:
    ok, detail = release.ci_verdict([_run(1, "completed", "success")], SHA)
    assert ok and "succeeded" in detail


def test_no_run_for_this_commit_is_not_green() -> None:
    ok, detail = release.ci_verdict(
        [_run(1, "completed", "success", sha="b" * 40)], SHA
    )
    assert not ok and "no CI run" in detail
    assert release.ci_verdict([], SHA)[0] is False


def test_a_run_still_going_blocks_the_tag() -> None:
    for status in ("in_progress", "queued", "waiting"):
        ok, detail = release.ci_verdict([_run(1, status, None)], SHA)
        assert not ok and "still running" in detail and "CI" in detail


def test_any_non_success_conclusion_blocks_the_tag() -> None:
    for conclusion in ("failure", "cancelled", "timed_out", "skipped", "neutral"):
        ok, detail = release.ci_verdict([_run(1, "completed", conclusion)], SHA)
        assert not ok and "not green" in detail and conclusion in detail


def test_the_newest_run_of_a_workflow_wins_over_an_older_one() -> None:
    red_then_green = [_run(1, "completed", "failure"), _run(2, "completed", "success")]
    assert release.ci_verdict(red_then_green, SHA)[0] is True
    green_then_red = [_run(1, "completed", "success"), _run(2, "completed", "failure")]
    assert release.ci_verdict(green_then_red, SHA)[0] is False


def test_every_workflow_must_be_green_not_just_one() -> None:
    runs = [
        _run(1, "completed", "success", "CI"),
        _run(2, "completed", "failure", "Lint"),
    ]
    ok, detail = release.ci_verdict(runs, SHA)
    assert not ok and "Lint" in detail


def test_runs_for_other_commits_are_ignored() -> None:
    runs = [
        _run(1, "completed", "failure", sha="c" * 40),
        _run(2, "completed", "success"),
    ]
    assert release.ci_verdict(runs, SHA)[0] is True


def _gh(
    stdout: str = "", stderr: str = "", code: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["gh"], code, stdout, stderr)


def test_fetch_runs_parses_the_gh_json() -> None:
    payload = json.dumps([_run(1, "completed", "success"), "junk", 3])
    with mock.patch.object(release.subprocess, "run", return_value=_gh(payload)) as run:
        rows = release.fetch_runs()
    assert rows == [_run(1, "completed", "success")]
    argv = run.call_args.args[0]
    assert argv[:3] == ["gh", "run", "list"] and "headSha" in argv[-1]


def test_fetch_runs_explains_every_way_gh_can_fail() -> None:
    cases = [
        (FileNotFoundError(), "not installed"),
        (subprocess.TimeoutExpired("gh", 60), "timed out"),
        (None, "failed: error connecting to api.github.com"),
    ]
    for side_effect, expected in cases:
        if side_effect is None:
            patch = mock.patch.object(
                release.subprocess,
                "run",
                return_value=_gh(stderr="error connecting to api.github.com", code=1),
            )
        else:
            patch = mock.patch.object(
                release.subprocess, "run", side_effect=side_effect
            )
        with patch:
            try:
                release.fetch_runs()
            except RuntimeError as exc:
                assert expected in str(exc)
            else:
                raise AssertionError(f"no error for {expected!r}")
    with mock.patch.object(release.subprocess, "run", return_value=_gh("not json")):
        try:
            release.fetch_runs()
        except RuntimeError as exc:
            assert "invalid JSON" in str(exc)
    with mock.patch.object(release.subprocess, "run", return_value=_gh('{"a": 1}')):
        try:
            release.fetch_runs()
        except RuntimeError as exc:
            assert "unexpected shape" in str(exc)


def test_require_green_ci_refuses_with_a_reason_and_names_the_escape_hatch() -> None:
    with mock.patch.object(
        release, "fetch_runs", return_value=[_run(1, "in_progress", None)]
    ):
        try:
            release.require_green_ci(SHA, skip=False)
        except SystemExit as exc:
            message = str(exc)
        else:
            raise AssertionError("did not refuse")
    assert "Refusing to tag" in message and "still running" in message
    assert "--skip-ci-check" in message and SHA[:7] in message


def test_require_green_ci_fails_closed_when_ci_cannot_be_checked() -> None:
    with mock.patch.object(release, "fetch_runs", side_effect=RuntimeError("no gh")):
        try:
            release.require_green_ci(SHA, skip=False)
        except SystemExit as exc:
            assert "Cannot verify CI: no gh" in str(exc)
        else:
            raise AssertionError("did not refuse")


def test_require_green_ci_passes_when_green_and_skips_when_told_to() -> None:
    with mock.patch.object(
        release, "fetch_runs", return_value=[_run(1, "completed", "success")]
    ):
        release.require_green_ci(SHA, skip=False)
    with mock.patch.object(
        release, "fetch_runs", side_effect=AssertionError("must not be called")
    ):
        release.require_green_ci(SHA, skip=True)


def test_the_flag_is_wired_through_main() -> None:
    with mock.patch.object(release, "cmd_tag") as tag:
        release.main(["tag"])
        release.main(["tag", "--skip-ci-check", "--dry-run"])
    assert tag.call_args_list == [mock.call(False, False), mock.call(True, True)]
