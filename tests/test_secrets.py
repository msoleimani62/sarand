"""Tests for sarand.core.secrets -- AGENTS.md §4.10 (never embed secrets)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from _helpers import write
from sarand.core.secrets import looks_like_secret_filename, scan_for_secrets
from sarand.scanners.essential_files import collect_essential_files


def test_looks_like_secret_filename_matches_known_patterns() -> None:
    assert looks_like_secret_filename("id_rsa")
    assert looks_like_secret_filename("id_ed25519")
    assert looks_like_secret_filename(".env")
    assert looks_like_secret_filename(".env.production")
    assert looks_like_secret_filename("server.pem")
    assert looks_like_secret_filename("private.key")
    assert looks_like_secret_filename("gcp-service-account.json")
    assert looks_like_secret_filename("aws-credentials.json")


def test_looks_like_secret_filename_does_not_flag_public_keys() -> None:
    """A .pub file is the public half -- never a secret."""
    assert not looks_like_secret_filename("id_rsa.pub")


def test_looks_like_secret_filename_does_not_flag_ordinary_files() -> None:
    assert not looks_like_secret_filename("main.py")
    assert not looks_like_secret_filename("config.json")
    assert not looks_like_secret_filename("README.md")


def test_essential_files_excludes_credential_shaped_filenames() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "main.py", "print('hi')\n")
        write(root / ".env", "SECRET=abc123\n")
        write(
            root / "id_rsa",
            "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----\n",
        )

        # .env and id_rsa have no ESSENTIAL_EXTENSIONS match anyway in some
        # cases, so also test a JSON credential file, which *does* match
        # an essential extension and would be included without the filter.
        write(root / "service-account.json", '{"type": "service_account"}')

        included, _skipped, excluded = collect_essential_files(root)

        assert Path("main.py") in included
        assert Path("service-account.json") in excluded
        assert Path("service-account.json") not in included


def test_content_scan_detects_aws_key_without_leaking_the_value() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "config.py", 'AWS_KEY = "AKIAABCDEFGHIJKLMNOP"\n')

        findings = scan_for_secrets(root, [Path("config.py")])

        assert len(findings) == 1
        assert findings[0].pattern_name == "AWS Access Key ID"
        assert findings[0].path == "config.py"
        assert findings[0].line_number == 1
        # The finding object must never carry the matched secret text.
        assert not hasattr(findings[0], "value")
        assert not hasattr(findings[0], "matched_text")


def test_content_scan_detects_private_key_block() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "notes.txt", "-----BEGIN RSA PRIVATE KEY-----\n")

        findings = scan_for_secrets(root, [Path("notes.txt")])

        assert any(f.pattern_name == "Private Key Block" for f in findings)


def test_content_scan_finds_nothing_in_clean_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "clean.py", "def add(a, b):\n    return a + b\n")

        findings = scan_for_secrets(root, [Path("clean.py")])

        assert findings == []


def test_exclude_flagged_files_moves_matched_file_out_of_included() -> None:
    from sarand.core.secrets import exclude_flagged_files
    from sarand.models.results import SecretFinding

    included = [Path("clean.py"), Path("config.py")]
    excluded = [Path("service-account.json")]
    findings = [
        SecretFinding(path="config.py", line_number=1, pattern_name="AWS Access Key ID")
    ]

    new_included, new_excluded = exclude_flagged_files(included, excluded, findings)

    assert new_included == [Path("clean.py")]
    assert set(new_excluded) == {Path("service-account.json"), Path("config.py")}


def test_exclude_flagged_files_is_a_noop_with_no_findings() -> None:
    from sarand.core.secrets import exclude_flagged_files

    included = [Path("a.py"), Path("b.py")]
    excluded = [Path("c.env")]

    new_included, new_excluded = exclude_flagged_files(included, excluded, [])

    assert new_included == included
    assert new_excluded == excluded


def test_end_to_end_flagged_file_content_never_reaches_markdown_report() -> None:
    """Full regression test for the exact leak this rule exists to prevent:
    a hardcoded key in a normal .py file must not show up anywhere in the
    rendered report, including the source-embedding section."""
    import tempfile as _tempfile
    from datetime import datetime, timezone

    from sarand.core.secrets import exclude_flagged_files
    from sarand.models.results import (
        EnvironmentInfo,
        GitSnapshot,
        ProjectStats,
        ReportData,
    )
    from sarand.renderers import markdown as _markdown

    with _tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "config.py", 'AWS_KEY = "AKIAABCDEFGHIJKLMNOP"\n')
        write(root / "clean.py", "x = 1\n")

        included = [Path("clean.py"), Path("config.py")]
        findings = scan_for_secrets(root, included)
        included, excluded = exclude_flagged_files(included, [], findings)

        data = ReportData(
            project_root=root,
            generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            environment=EnvironmentInfo(),
            git=GitSnapshot(),
            stats=ProjectStats(),
            included_files=included,
            excluded_secret_files=excluded,
            secret_findings=findings,
        )

        output = _markdown.render(data, include_source=True)

        assert "AKIAABCDEFGHIJKLMNOP" not in output
        assert "`config.py`" in output  # named in the exclusion list
        assert "### FILE: `config.py`" not in output  # but never source-dumped
