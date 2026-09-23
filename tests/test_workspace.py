"""Regression tests for backlog item 8.1/8.2 (Monorepo/Workspace
architecture, Cargo-only first scope) -- see AGENTS.md section 5.25
and `core/workspace.py`'s module docstring for the full audit and
design rationale.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from _helpers import write
from sarand.core.workspace import detect_workspace
from sarand.models.results import ReportData, WorkspaceInfo, WorkspaceMember
from sarand.renderers import json_renderer, markdown


def test_no_cargo_toml_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert detect_workspace(Path(tmp)) is None


def test_single_package_cargo_toml_returns_none() -> None:
    """A plain, non-workspace crate must not be reported as a
    workspace of one -- `RustAnalyzer` already handles this case fine
    as-is (backlog 8.1's audit)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Cargo.toml", '[package]\nname = "solo"\nversion = "0.1.0"\n')
        assert detect_workspace(root) is None


def test_malformed_cargo_toml_returns_none_not_crash() -> None:
    """Not this detector's job to report a bad Cargo.toml -- RustAnalyzer's
    own `cargo test`/`cargo fmt` runs do that loudly enough."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Cargo.toml", "this is not [ valid toml")
        assert detect_workspace(root) is None


def test_workspace_with_glob_members_and_exclude() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(
            root / "Cargo.toml",
            "[workspace]\n"
            'members = ["crates/*", "tools/cli"]\n'
            'exclude = ["crates/broken"]\n',
        )
        for name in ("a", "b", "broken"):
            write(
                root / "crates" / name / "Cargo.toml",
                f'[package]\nname = "{name}-crate"\n',
            )
        write(root / "tools" / "cli" / "Cargo.toml", '[package]\nname = "cli-tool"\n')
        # Matches the "crates/*" glob but has no Cargo.toml of its own --
        # must not be reported as a member.
        (root / "crates" / "not-a-crate").mkdir(parents=True)

        ws = detect_workspace(root)
        assert ws is not None
        assert ws.kind == "cargo"
        assert ws.exclude_patterns == ["crates/broken"]
        names = sorted((m.path, m.name) for m in ws.members)
        assert names == [
            ("crates/a", "a-crate"),
            ("crates/b", "b-crate"),
            ("tools/cli", "cli-tool"),
        ], names


def test_root_counts_as_member_when_it_has_own_package() -> None:
    """A root Cargo.toml with both `[workspace]` and its own `[package]`
    is a common, valid layout -- the root itself must show up as a
    member, path `.`."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(
            root / "Cargo.toml",
            '[workspace]\nmembers = ["sub"]\n\n[package]\nname = "root-crate"\n',
        )
        write(root / "sub" / "Cargo.toml", '[package]\nname = "sub-crate"\n')
        ws = detect_workspace(root)
        assert ws is not None
        names = sorted((m.path, m.name) for m in ws.members)
        assert names == [(".", "root-crate"), ("sub", "sub-crate")], names


def test_member_without_package_name_falls_back_to_dirname() -> None:
    """A member whose own Cargo.toml has no `[package].name` (or fails
    to parse) still counts as a member -- just named after its
    directory instead of crashing or being dropped."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Cargo.toml", '[workspace]\nmembers = ["weird"]\n')
        write(root / "weird" / "Cargo.toml", "not valid toml [ at all")
        ws = detect_workspace(root)
        assert ws is not None
        assert [(m.path, m.name) for m in ws.members] == [("weird", "weird")]


def _minimal_report_data(root: Path, workspace: WorkspaceInfo | None) -> ReportData:
    from sarand.models.results import EnvironmentInfo, GitSnapshot, ProjectStats

    return ReportData(
        project_root=root,
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        environment=EnvironmentInfo(),
        git=GitSnapshot(),
        stats=ProjectStats(),
        workspace=workspace,
    )


def test_markdown_has_no_workspace_section_when_none() -> None:
    """The whole point of only adding a section when a workspace is
    actually detected: an ordinary, non-workspace project's report
    must look exactly as it did before this feature existed."""
    with tempfile.TemporaryDirectory() as tmp:
        data = _minimal_report_data(Path(tmp), workspace=None)
        rendered = markdown.render(data, include_source=False)
        assert "## Workspace" not in rendered


def test_markdown_renders_workspace_section_when_present() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ws = WorkspaceInfo(
            kind="cargo",
            members=[
                WorkspaceMember(path=".", name="root-crate"),
                WorkspaceMember(path="crates/a", name="a-crate"),
            ],
            exclude_patterns=["crates/broken"],
        )
        data = _minimal_report_data(Path(tmp), workspace=ws)
        rendered = markdown.render(data, include_source=False)
        assert "## Workspace" in rendered
        assert "**Kind:** cargo" in rendered
        assert "**Members:** 2" in rendered
        assert "`crates/broken`" in rendered
        assert "| root-crate | `.` |" in rendered
        assert "| a-crate | `crates/a` |" in rendered


def test_json_has_no_workspace_key_when_none() -> None:
    import json

    with tempfile.TemporaryDirectory() as tmp:
        data = _minimal_report_data(Path(tmp), workspace=None)
        payload = json.loads(json_renderer.render(data, include_source=False))
        assert "workspace" not in payload


def test_json_renders_workspace_key_when_present() -> None:
    import json

    with tempfile.TemporaryDirectory() as tmp:
        ws = WorkspaceInfo(
            kind="cargo",
            members=[WorkspaceMember(path="crates/a", name="a-crate")],
            exclude_patterns=[],
        )
        data = _minimal_report_data(Path(tmp), workspace=ws)
        payload = json.loads(json_renderer.render(data, include_source=False))
        assert payload["workspace"] == {
            "kind": "cargo",
            "members": [{"path": "crates/a", "name": "a-crate"}],
            "exclude_patterns": [],
        }
