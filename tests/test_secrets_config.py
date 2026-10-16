"""Tests for sarand.core.secrets_config -- the `[secrets]` table of .sarand.toml
(AGENTS.md 5.67). The fixture allowlist is explicit; nothing is guessed."""

from __future__ import annotations

import tempfile
from pathlib import Path

from _helpers import write
from sarand.core.license_policy import parse_policy
from sarand.core.secrets_config import (
    SecretsConfigError,
    load_fixture_paths,
    parse_fixture_paths,
)


def _raises(text: str) -> str:
    try:
        parse_fixture_paths(text)
    except SecretsConfigError as exc:
        return str(exc)
    raise AssertionError("expected SecretsConfigError")


def test_no_secrets_table_means_an_empty_allowlist() -> None:
    assert parse_fixture_paths("") == ()
    assert parse_fixture_paths('[licenses]\nallow = ["MIT"]\n') == ()


def test_fixture_paths_are_read_and_normalised() -> None:
    text = '[secrets]\nfixture_paths = ["tests/test_secrets.py", " tests\\\\golden\\\\* "]\n'
    assert parse_fixture_paths(text) == ("tests/test_secrets.py", "tests/golden/*")


def test_an_empty_secrets_table_is_fine() -> None:
    assert parse_fixture_paths("[secrets]\n") == ()


def test_unknown_key_is_an_error_not_a_silent_no_op() -> None:
    message = _raises('[secrets]\nfixture_path = ["a.py"]\n')
    assert "unknown key" in message
    assert "fixture_path" in message


def test_bad_types_are_errors() -> None:
    assert "list of strings" in _raises('[secrets]\nfixture_paths = "a.py"\n')
    assert "non-empty strings" in _raises("[secrets]\nfixture_paths = [1]\n")
    assert "non-empty strings" in _raises('[secrets]\nfixture_paths = ["  "]\n')
    assert "must be a table" in _raises('secrets = "x"\n')


def test_invalid_toml_is_an_error() -> None:
    assert "invalid TOML" in _raises("[secrets\n")


def test_a_glob_that_matches_everything_is_rejected() -> None:
    for pattern in ("*", "**", "*/*", "**/*", "/"):
        message = _raises(f'[secrets]\nfixture_paths = ["{pattern}"]\n')
        assert "every file" in message, pattern


def test_load_fixture_paths_without_a_file_is_empty() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert load_fixture_paths(Path(tmp)) == ()


def test_load_fixture_paths_reports_the_file_name_on_error() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / ".sarand.toml", "[secrets]\nbogus = 1\n")
        try:
            load_fixture_paths(root)
        except SecretsConfigError as exc:
            assert str(exc).startswith(".sarand.toml:")
        else:
            raise AssertionError("expected SecretsConfigError")


def test_the_secrets_table_does_not_disturb_the_license_policy() -> None:
    text = (
        '[licenses]\nallow = ["MIT"]\nunknown = "allow"\n\n'
        '[secrets]\nfixture_paths = ["tests/test_secrets.py"]\n'
    )
    policy = parse_policy(text)
    assert policy is not None
    assert policy.allow == ("MIT",)
    assert parse_fixture_paths(text) == ("tests/test_secrets.py",)


def test_sarand_own_config_lists_its_one_fixture_file() -> None:
    root = Path(__file__).resolve().parent.parent
    config = root / ".sarand.toml"
    if not config.is_file():
        return
    assert load_fixture_paths(root) == ("tests/test_secrets.py",)
