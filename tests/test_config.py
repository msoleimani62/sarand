"""Tests for sarand.config -- CLI/env/persisted-config priority resolution."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

from _helpers import assert_raises
from sarand.config import SarandConfig, resolve_output_dir, resolve_project_path
from sarand.constants import DEFAULT_OUTPUT_DIR


def _args(**overrides: object) -> SimpleNamespace:
    defaults = {
        "project": None,
        "output_dir": None,
        "output_name": None,
        "format": "markdown",
        "skip_tests": False,
        "quality": False,
        "security": False,
        "no_source": False,
        "no_health": False,
        "max_depth": None,
        "max_entries": None,
        "verbose": False,
        "debug": False,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_resolve_project_path_defaults_to_cwd() -> None:
    assert resolve_project_path(None) == Path.cwd().resolve()


def test_resolve_project_path_explicit_value_wins() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert resolve_project_path(tmp) == Path(tmp).resolve()


def test_output_dir_priority_cli_beats_everything() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        old_env = os.environ.get("SARAND_OUTPUT_DIR")
        os.environ["SARAND_OUTPUT_DIR"] = "/somewhere/else"
        try:
            result = resolve_output_dir(tmp)
            assert result == Path(tmp).resolve()
        finally:
            if old_env is None:
                os.environ.pop("SARAND_OUTPUT_DIR", None)
            else:
                os.environ["SARAND_OUTPUT_DIR"] = old_env


def test_output_dir_priority_env_beats_persisted_and_default() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        old_env = os.environ.get("SARAND_OUTPUT_DIR")
        os.environ["SARAND_OUTPUT_DIR"] = tmp
        try:
            result = resolve_output_dir(None)
            assert result == Path(tmp).resolve()
        finally:
            if old_env is None:
                os.environ.pop("SARAND_OUTPUT_DIR", None)
            else:
                os.environ["SARAND_OUTPUT_DIR"] = old_env


def test_output_dir_falls_back_to_default_when_nothing_set() -> None:
    """Isolated via a get_config_dir() monkeypatch, not XDG_CONFIG_HOME --
    that env var is a Linux-only convention (see get_config_dir's
    docstring); relying on it made this test pass by coincidence on
    macOS/Windows CI runners rather than for the right reason, and would
    be genuinely wrong on a real macOS/Windows machine that already has
    a persisted config file from prior use."""
    from sarand import userconfig

    old_env = os.environ.pop("SARAND_OUTPUT_DIR", None)
    with tempfile.TemporaryDirectory() as tmp:
        empty_config_dir = Path(tmp) / "sarand"
        original_get_config_dir = userconfig.get_config_dir
        userconfig.get_config_dir = lambda: empty_config_dir
        try:
            result = resolve_output_dir(None)
            assert result == DEFAULT_OUTPUT_DIR
        finally:
            userconfig.get_config_dir = original_get_config_dir
            if old_env is not None:
                os.environ["SARAND_OUTPUT_DIR"] = old_env


def test_output_dir_uses_persisted_config_when_present() -> None:
    """Same cross-platform-correct isolation as the test above."""
    from sarand import userconfig

    old_env = os.environ.pop("SARAND_OUTPUT_DIR", None)
    with tempfile.TemporaryDirectory() as tmp:
        persisted_target = Path(tmp) / "persisted-reports"
        fake_config_dir = Path(tmp) / "sarand"
        fake_config_dir.mkdir(parents=True)
        (fake_config_dir / "config.json").write_text(
            json.dumps({"output_dir": str(persisted_target)})
        )

        original_get_config_dir = userconfig.get_config_dir
        userconfig.get_config_dir = lambda: fake_config_dir
        try:
            result = resolve_output_dir(None)
            assert result == persisted_target.resolve()
        finally:
            userconfig.get_config_dir = original_get_config_dir
            if old_env is not None:
                os.environ["SARAND_OUTPUT_DIR"] = old_env


def test_default_output_name_matches_project_and_format() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "My Cool Project"
        root.mkdir()
        cfg = SarandConfig.from_args(_args(project=str(root), format="json"))
        assert cfg.output_name == "sarand-my-cool-project-report.json"

        cfg2 = SarandConfig.from_args(_args(project=str(root), format="markdown"))
        assert cfg2.output_name == "sarand-my-cool-project-report.md"

        for fmt, ext in (("html", "html"), ("pdf", "pdf"), ("sarif", "sarif")):
            cfg3 = SarandConfig.from_args(_args(project=str(root), format=fmt))
            assert cfg3.output_name == f"sarand-my-cool-project-report.{ext}"


def test_explicit_output_name_overrides_default() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg = SarandConfig.from_args(_args(project=tmp, output_name="custom.md"))
        assert cfg.output_name == "custom.md"


def test_validate_rejects_missing_project_root() -> None:
    cfg = SarandConfig(project_root=Path("/definitely/does/not/exist/xyz"))
    assert_raises(ValueError, cfg.validate)


def test_validate_rejects_unsupported_format() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg = SarandConfig(project_root=Path(tmp), output_format="xml")
        assert_raises(ValueError, cfg.validate)


def test_validate_accepts_supported_formats() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        for fmt in ("markdown", "json", "text", "html", "pdf", "sarif"):
            cfg = SarandConfig(project_root=Path(tmp), output_format=fmt)
            cfg.validate()  # must not raise


def test_full_flag_enables_quality_and_security() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg = SarandConfig.from_args(_args(project=tmp, full=True))
        assert cfg.run_quality is True
        assert cfg.run_security is True


def test_full_flag_removes_truncation_limits() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg = SarandConfig.from_args(_args(project=tmp, full=True))
        assert cfg.max_tree_depth >= 10_000
        assert cfg.max_tree_entries >= 1_000_000
        assert cfg.max_file_size >= 10 * 1024 * 1024 * 1024


def test_full_flag_does_not_override_an_explicit_max_depth() -> None:
    """An explicit --max-depth must still win over --full's convenience
    default -- explicit user intent is never silently overridden."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = SarandConfig.from_args(_args(project=tmp, full=True, max_depth=3))
        assert cfg.max_tree_depth == 3
        assert cfg.run_quality is True  # the rest of --full still applies


def test_without_full_flag_limits_stay_at_normal_defaults() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg = SarandConfig.from_args(_args(project=tmp))
        assert cfg.run_quality is False
        assert cfg.run_security is False
        assert cfg.max_tree_depth < 10_000
