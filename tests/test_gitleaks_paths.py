"""Tests for gitleaks_flagged_paths -- turning gitleaks' redacted verbose
output into the set of project files it flagged (AGENTS.md 5.67)."""

from __future__ import annotations

from pathlib import Path

from sarand.core.gitleaks import gitleaks_flagged_paths

_SAMPLE = """\

    ○
    │╲
    │ ○
    ○ ░
    ░    gitleaks

Finding:     api_key = "REDACTED"
Secret:      REDACTED
RuleID:      generic-api-key
Entropy:     4.2
File:        src/config.py
Line:        12
Fingerprint: src/config.py:generic-api-key:12

Finding:     token: REDACTED
Secret:      REDACTED
RuleID:      generic-api-key
Entropy:     3.9
File:        deploy\\prod.yaml
Line:        3
Commit:      1a2b3c4d
Fingerprint: 1a2b3c4d:deploy\\prod.yaml:generic-api-key:3

12:00AM INF scanned ~1234 bytes (1.23 KB) in 12.3ms
12:00AM WRN leaks found: 2
"""


def test_paths_are_collected_from_file_lines_only() -> None:
    assert gitleaks_flagged_paths(_SAMPLE) == {
        Path("src/config.py"),
        Path("deploy/prod.yaml"),
    }


def test_empty_or_clean_output_flags_nothing() -> None:
    assert gitleaks_flagged_paths("") == set()
    assert gitleaks_flagged_paths("12:00AM INF no leaks found\n") == set()


def test_absolute_and_escaping_paths_are_ignored() -> None:
    text = "File:        /etc/passwd\nFile:        ../outside.py\nFile:        ok/inside.py\n"
    assert gitleaks_flagged_paths(text) == {Path("ok/inside.py")}


def test_a_leading_dot_slash_is_stripped() -> None:
    assert gitleaks_flagged_paths("File:        ./a/b.py\n") == {Path("a/b.py")}
