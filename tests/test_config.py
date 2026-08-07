"""Tests for sarand.config -- CLI/env/persisted-config priority resolution."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

from sarand.config import SarandConfig, resolve_output_dir, resolve_project_path
from sarand.constants import DEFAULT_OUTPUT_DIR

from _helpers import assert_raises


def _args(**overrides: object) -> SimpleNamespace:
    defaults = dict(
        project=None,
        output_dir=None,
        output_name=None,
        format="markdown",
        skip_tests=False,
        quality=False,
        security=False,
        no_source=False,
        no_health=False,
        max_depth=None,
        max_entries=None,
        verbose=False,
        debug=False,
    )
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
    old_env = os.environ.pop("SARAND_OUTPUT_DIR", None)
    old_xdg = os.environ.pop("XDG_CONFIG_HOME", None)
    try:
        # Point XDG_CONFIG_HOME somewhere with no sarand config.json,
        # so load_persisted_config() genuinely returns {}.
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["XDG_CONFIG_HOME"] = tmp
            result = resolve_output_dir(None)
            assert result == DEFAULT_OUTPUT_DIR
    finally:
        if old_env is not None:
            os.environ["SARAND_OUTPUT_DIR"] = old_env
        if old_xdg is not None:
            os.environ["XDG_CONFIG_HOME"] = old_xdg
        else:
            os.environ.pop("XDG_CONFIG_HOME", None)


def test_output_dir_uses_persisted_config_when_present() -> None:
    old_env = os.environ.pop("SARAND_OUTPUT_DIR", None)
    old_xdg = os.environ.pop("XDG_CONFIG_HOME", None)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["XDG_CONFIG_HOME"] = tmp
            persisted_target = Path(tmp) / "persisted-reports"
            config_dir = Path(tmp) / "sarand"
            config_dir.mkdir(parents=True)
            (config_dir / "config.json").write_text(json.dumps({"output_dir": str(persisted_target)}))

            result = resolve_output_dir(None)
            assert result == persisted_target.resolve()
    finally:
        if old_env is not None:
            os.environ["SARAND_OUTPUT_DIR"] = old_env
        if old_xdg is not None:
            os.environ["XDG_CONFIG_HOME"] = old_xdg
        else:
            os.environ.pop("XDG_CONFIG_HOME", None)


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
