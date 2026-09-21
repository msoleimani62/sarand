"""Tests for the Tier-1 additions: Haskell, Elixir, Erlang, Scala, Dockerfile,
GitHub Actions, Terraform and Protobuf. All hermetic: `shutil.which` and the
command runner are patched, so nothing depends on what is installed."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest
import sarand.analyzers._tooling as tooling
from _helpers import write
from sarand.analyzers.dockerfile_analyzer import DockerfileAnalyzer
from sarand.analyzers.elixir_analyzer import ElixirAnalyzer
from sarand.analyzers.erlang_analyzer import ErlangAnalyzer
from sarand.analyzers.github_actions_analyzer import GitHubActionsAnalyzer
from sarand.analyzers.haskell_analyzer import HaskellAnalyzer
from sarand.analyzers.protobuf_analyzer import ProtobufAnalyzer
from sarand.analyzers.registry import builtin_analyzers
from sarand.analyzers.scala_analyzer import ScalaAnalyzer
from sarand.analyzers.terraform_analyzer import TerraformAnalyzer
from sarand.core.doctor import tool_catalog

# analyzer, a file that makes it match, the tool binaries it drives
_SPECS: list[tuple[Any, str, tuple[str, ...]]] = [
    (HaskellAnalyzer, "stack.yaml", ("stack", "cabal", "hlint")),
    (ElixirAnalyzer, "mix.exs", ("mix",)),
    (ErlangAnalyzer, "rebar.config", ("rebar3",)),
    (ScalaAnalyzer, "build.sbt", ("sbt",)),
    (DockerfileAnalyzer, "Dockerfile", ("hadolint",)),
    (GitHubActionsAnalyzer, ".github/workflows/ci.yml", ("actionlint",)),
    (TerraformAnalyzer, "main.tf", ("terraform", "tflint")),
    (ProtobufAnalyzer, "buf.yaml", ("buf",)),
]
_IDS = [spec[0].name for spec in _SPECS]


def _run(coro):
    return asyncio.run(coro)


def _all_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)


def _record_commands(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Pretend every tool exists and record each command instead of running it."""
    captured: list[list[str]] = []

    async def fake_run_cmd_async(cmd, cwd, timeout):
        captured.append(list(cmd))
        return 0, "ok", 0.1

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(tooling, "run_cmd_async", fake_run_cmd_async)
    return captured


@pytest.mark.parametrize(("analyzer_class", "marker", "tools"), _SPECS, ids=_IDS)
def test_matches_only_on_a_real_root_marker(analyzer_class, marker, tools) -> None:
    analyzer = analyzer_class()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert analyzer.matches(root) is False

        # The same marker one directory down is not a project root.
        write(root / "vendor" / "x" / marker, "\n")
        assert analyzer.matches(root) is False

        write(root / marker, "\n")
        assert analyzer.matches(root) is True


@pytest.mark.parametrize(("analyzer_class", "marker", "tools"), _SPECS, ids=_IDS)
def test_every_tool_skips_cleanly_when_missing(
    monkeypatch: pytest.MonkeyPatch, analyzer_class, marker, tools
) -> None:
    _all_missing(monkeypatch)
    analyzer = analyzer_class()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / marker, "\n")

        results = [
            *_run(analyzer.run_quality(root)),
            *_run(analyzer.run_security(root)),
        ]
        test_result = _run(analyzer.run_tests(root))
        if test_result is not None:
            results.append(test_result)

    assert results, "an analyzer that matched must report something"
    for result in results:
        assert result.skipped is True
        assert "not installed" in result.skip_reason


@pytest.mark.parametrize(("analyzer_class", "marker", "tools"), _SPECS, ids=_IDS)
def test_every_driven_tool_is_listed_by_doctor(analyzer_class, marker, tools) -> None:
    listed = {binary for _category, binary, _hint, _used in tool_catalog()}

    assert set(tools) <= listed


def test_all_eight_are_registered_builtins() -> None:
    names = {analyzer.name for analyzer in builtin_analyzers()}

    assert {spec[0].name for spec in _SPECS} <= names


# --- Haskell -------------------------------------------------------------


def test_haskell_uses_stack_with_a_stack_yaml_and_cabal_without(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _record_commands(monkeypatch)
    analyzer = HaskellAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "app.cabal", "name: app\n")
        _run(analyzer.run_tests(root))
        write(root / "stack.yaml", "resolver: lts\n")
        _run(analyzer.run_tests(root))

    assert captured == [["cabal", "test"], ["stack", "test"]]


def test_haskell_matches_on_any_of_its_markers() -> None:
    analyzer = HaskellAnalyzer()
    for marker in ("stack.yaml", "cabal.project", "package.yaml", "demo.cabal"):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / marker, "\n")

            assert analyzer.matches(root) is True, marker


def test_haskell_quality_runs_hlint(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _record_commands(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        _run(HaskellAnalyzer().run_quality(Path(tmp)))

    assert captured == [["hlint", "."]]


# --- Elixir --------------------------------------------------------------


def test_elixir_runs_credo_and_mixaudit_only_when_the_project_depends_on_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _record_commands(monkeypatch)
    analyzer = ElixirAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "mix.exs", "defmodule M.MixProject do\nend\n")
        _run(analyzer.run_quality(root))
        _run(analyzer.run_security(root))
        plain = list(captured)
        captured.clear()

        write(
            root / "mix.exs",
            '{:credo, "~> 1.7"},\n{:mix_audit, "~> 2.1"},\n',
        )
        _run(analyzer.run_quality(root))
        _run(analyzer.run_security(root))

    assert plain == [
        ["mix", "format", "--check-formatted"],
        ["mix", "hex.audit"],
    ]
    assert captured == [
        ["mix", "format", "--check-formatted"],
        ["mix", "credo"],
        ["mix", "hex.audit"],
        ["mix", "deps.audit"],
    ]


def test_elixir_tests_and_entry_points(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _record_commands(monkeypatch)
    analyzer = ElixirAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "mix.exs", "\n")
        write(root / "config" / "config.exs", "\n")
        _run(analyzer.run_tests(root))

        assert analyzer.entry_points(root) == ["mix.exs", "config/config.exs"]

    assert captured == [["mix", "test"]]


# --- Erlang and Scala ----------------------------------------------------


def test_erlang_runs_eunit_and_xref_but_not_dialyzer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _record_commands(monkeypatch)
    analyzer = ErlangAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _run(analyzer.run_tests(root))
        _run(analyzer.run_quality(root))

    assert captured == [["rebar3", "eunit"], ["rebar3", "xref"]]
    assert ["rebar3", "dialyzer"] not in captured


def test_scala_runs_sbt_in_batch_mode_and_scalafmt_only_when_adopted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _record_commands(monkeypatch)
    analyzer = ScalaAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "build.sbt", 'name := "x"\n')
        _run(analyzer.run_tests(root))
        assert _run(analyzer.run_quality(root)) == []

        write(
            root / "project" / "plugins.sbt",
            'addSbtPlugin("org.scalameta" % "sbt-scalafmt" % "2")\n',
        )
        _run(analyzer.run_quality(root))

    assert captured == [
        ["sbt", "-batch", "test"],
        ["sbt", "-batch", "scalafmtCheckAll"],
    ]


# --- infrastructure formats ---------------------------------------------


def test_dockerfile_names_and_command(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _record_commands(monkeypatch)
    analyzer = DockerfileAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name in ("Dockerfile", "Dockerfile.dev", "api.Dockerfile", "Containerfile"):
            write(root / name, "FROM scratch\n")
        write(root / "Dockerfile-notes.txt", "not a dockerfile\n")

        assert analyzer.entry_points(root) == [
            "Containerfile",
            "Dockerfile",
            "Dockerfile.dev",
            "api.Dockerfile",
        ]
        _run(analyzer.run_quality(root))

    assert captured == [
        [
            "hadolint",
            "--no-color",
            "Containerfile",
            "Dockerfile",
            "Dockerfile.dev",
            "api.Dockerfile",
        ]
    ]


def test_github_actions_passes_explicit_forward_slash_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _record_commands(monkeypatch)
    analyzer = GitHubActionsAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / ".github" / "workflows" / "ci.yml", "on: push\n")
        write(root / ".github" / "workflows" / "release.yaml", "on: push\n")
        write(root / ".github" / "workflows" / "notes.md", "not a workflow\n")

        _run(analyzer.run_quality(root))

    assert captured == [
        [
            "actionlint",
            "-no-color",
            ".github/workflows/ci.yml",
            ".github/workflows/release.yaml",
        ]
    ]


def test_terraform_only_formats_and_lints_never_init_plan_or_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _record_commands(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "main.tf", "terraform {}\n")
        analyzer = TerraformAnalyzer()
        _run(analyzer.run_quality(root))
        _run(analyzer.run_security(root))

        assert analyzer.entry_points(root) == ["main.tf"]

    assert captured == [
        ["terraform", "fmt", "-check", "-diff", "-no-color", "-recursive"],
        ["tflint", "--no-color"],
    ]
    for command in captured:
        assert not {"init", "plan", "apply"} & set(command)


def test_protobuf_matches_on_proto_files_and_the_proto_directory() -> None:
    analyzer = ProtobufAnalyzer()
    for relative in ("api.proto", "proto/api.proto", "buf.work.yaml"):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / relative, 'syntax = "proto3";\n')

            assert analyzer.matches(root) is True, relative


def test_protobuf_lints_with_buf(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _record_commands(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        _run(ProtobufAnalyzer().run_quality(Path(tmp)))

    assert captured == [["buf", "lint"]]
