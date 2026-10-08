"""Regression tests for package-manager awareness of Node projects -- see
AGENTS.md section 5.53 and `core/node_pm.py` for the audit: `build system`
said npm for pnpm/Yarn repositories, and `npm audit` (which needs a
package-lock.json) was recorded as a FAILED check there."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from unittest import mock

from _helpers import write
from sarand import cli
from sarand.analyzers import node_analyzer
from sarand.analyzers.node_analyzer import NodeAnalyzer
from sarand.core.node_pm import (
    audit_skip_reason,
    node_package_manager,
    refine_build_system,
)
from sarand.discovery.project_detector import detect_project
from sarand.models.results import CommandResult, ProjectDetection


def _pkg(**extra: object) -> str:
    data: dict[str, object] = {"name": "x", "scripts": {"test": "echo ok"}}
    data.update(extra)
    return json.dumps(data)


def _project(
    lock: str | None = None, **extra: object
) -> tempfile.TemporaryDirectory[str]:
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    write(root / "package.json", _pkg(**extra))
    if lock:
        write(root / lock, "")
    return tmp


def test_package_manager_from_lockfiles() -> None:
    cases = {
        "pnpm-lock.yaml": "pnpm",
        "yarn.lock": "yarn",
        "bun.lock": "bun",
        "bun.lockb": "bun",
        "package-lock.json": "npm",
        "npm-shrinkwrap.json": "npm",
        None: "npm",
    }
    for lock, expected in cases.items():
        with _project(lock) as tmp:
            assert node_package_manager(Path(tmp)) == expected, lock


def test_the_package_manager_field_beats_the_lockfile() -> None:
    cases = {
        "pnpm@9.1.0": "pnpm",
        "yarn@4.2.2+sha256.abc": "yarn",
        "npm@10.8.0": "npm",
        "bun@1.1.0": "bun",
    }
    for declared, expected in cases.items():
        with _project("package-lock.json", packageManager=declared) as tmp:
            assert node_package_manager(Path(tmp)) == expected, declared


def test_an_unknown_or_malformed_declaration_falls_back_to_the_lockfile() -> None:
    for declared in ("deno@2", 7, None, ""):
        with _project("pnpm-lock.yaml", packageManager=declared) as tmp:
            assert node_package_manager(Path(tmp)) == "pnpm", declared
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", "{not json")
        write(root / "yarn.lock", "")
        assert node_package_manager(root) == "yarn"


def test_a_pnpm_workspace_file_alone_means_pnpm() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pnpm-workspace.yaml", "packages:\n  - 'packages/*'\n")
        assert node_package_manager(root) == "pnpm"


def test_the_audited_gap_build_system_is_corrected_for_pnpm_and_yarn() -> None:
    for lock, expected in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn")):
        with _project(lock) as tmp:
            before = detect_project(Path(tmp))
            assert before.build_system == "npm"  # the audited behaviour
            assert refine_build_system(before, Path(tmp)).build_system == expected


def test_refinement_changes_only_the_label_and_only_when_needed() -> None:
    with _project("pnpm-lock.yaml") as tmp:
        root = Path(tmp)
        before = detect_project(root)
        after = refine_build_system(before, root)
        assert after.languages == before.languages
        assert after.primary_language == before.primary_language
        assert after.markers_found == before.markers_found
    with _project("package-lock.json") as tmp:
        before = detect_project(Path(tmp))
        assert refine_build_system(before, Path(tmp)) is before
    cargo = ProjectDetection(
        languages=["Rust"], primary_language="Rust", build_system="cargo"
    )
    with _project("pnpm-lock.yaml") as tmp:
        assert refine_build_system(cargo, Path(tmp)) is cargo


def test_a_pnpm_only_root_gets_a_pnpm_label_instead_of_none_detected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pnpm-workspace.yaml", "packages:\n  - 'packages/*'\n")
        write(root / "packages" / "a" / "package.json", _pkg())
        before = detect_project(root)
        assert before.build_system in ("none detected", "unknown")
        assert refine_build_system(before, root).build_system == "pnpm"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pnpm-workspace.yaml", "packages:\n  - 'packages/*'\n")
        write(root / "packages" / "a" / "package.json", _pkg())
        write(root / "packages" / "a" / "index.js", "module.exports = 1\n")
        before = detect_project(root)
        assert before.build_system in ("none detected", "unknown")
        assert refine_build_system(before, root).build_system == "pnpm"


def test_audit_skip_reason_names_the_real_reason_and_the_right_command() -> None:
    with _project("package-lock.json") as tmp:
        assert audit_skip_reason(Path(tmp)) is None
    with _project("npm-shrinkwrap.json") as tmp:
        assert audit_skip_reason(Path(tmp)) is None
    with _project("pnpm-lock.yaml") as tmp:
        reason = audit_skip_reason(Path(tmp))
        assert (
            reason and "uses pnpm (pnpm-lock.yaml)" in reason and "pnpm audit" in reason
        )
    with _project("yarn.lock") as tmp:
        reason = audit_skip_reason(Path(tmp))
        assert reason and "yarn npm audit" in reason and "yarn audit" in reason
    with _project("bun.lock") as tmp:
        reason = audit_skip_reason(Path(tmp))
        assert reason and "uses bun (bun.lock)" in reason
    with _project() as tmp:
        reason = audit_skip_reason(Path(tmp))
        assert reason and "npm install" in reason
    with _project(packageManager="pnpm@9") as tmp:
        reason = audit_skip_reason(Path(tmp))
        assert reason and "uses pnpm --" in reason


def _run_security(root: Path) -> tuple[list[CommandResult], mock.AsyncMock]:
    fake = mock.AsyncMock(return_value=(0, "audited", 0.1))
    with (
        mock.patch.object(node_analyzer.shutil, "which", return_value="/usr/bin/npm"),
        mock.patch.object(node_analyzer, "run_cmd_async", fake),
    ):
        results = asyncio.run(NodeAnalyzer().run_security(root))
    return results, fake


def test_a_project_without_a_usable_lockfile_gets_a_skipped_audit_not_a_failure() -> (
    None
):
    for lock in ("pnpm-lock.yaml", "yarn.lock", None):
        with _project(lock) as tmp:
            results, fake = _run_security(Path(tmp))
            assert len(results) == 1 and results[0].kind == "npm audit"
            assert results[0].skipped and not results[0].passed
            assert results[0].skip_reason
            fake.assert_not_called()


def test_a_project_with_a_package_lock_still_runs_npm_audit() -> None:
    with _project("package-lock.json") as tmp:
        results, fake = _run_security(Path(tmp))
        fake.assert_called_once()
        assert fake.call_args.args[0][:2] == ["npm", "audit"]
        assert results[0].passed and not results[0].skipped


def test_a_missing_npm_is_still_reported_first() -> None:
    with _project("pnpm-lock.yaml") as tmp:
        with mock.patch.object(node_analyzer.shutil, "which", return_value=None):
            results = asyncio.run(NodeAnalyzer().run_security(Path(tmp)))
        assert results[0].skip_reason == "npm not found in PATH"


def test_the_report_shows_the_real_build_system() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        project = base / "proj"
        project.mkdir()
        write(project / "package.json", _pkg())
        write(project / "pnpm-lock.yaml", "")
        reports = base / "reports"
        reports.mkdir()
        code = cli.main(
            ["-p", str(project), "-d", str(reports), "--skip-tests", "-o", "r.md"]
        )
        assert code == 0
        text = (reports / "r.md").read_text(encoding="utf-8")
        assert "- **Build system:** pnpm" in text
        assert "build pnpm" in text
