"""Tests for sarand.core.secrets -- AGENTS.md §4.10 (never embed secrets)."""

from __future__ import annotations

import tempfile
import time
from datetime import UTC
from pathlib import Path

from _helpers import write
from sarand.core.secrets import (
    content_pattern_names,
    content_rule_signatures,
    exclude_paths,
    looks_like_secret_filename,
    looks_like_secret_path,
    mark_fixture_findings,
    matches_fixture_path,
    scan_for_secrets,
    scan_line,
    shannon_entropy,
)
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
    from datetime import datetime

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
            generated_at=datetime(2026, 1, 1, tzinfo=UTC),
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


# ---------------------------------------------------------------------------
# AGENTS.md 5.67 -- wider filename list, wider content rules, explicit fixture
# allowlist. Every credential-shaped value below is assembled at runtime from
# fragments, so no realistic token sits in this file as one literal (GitHub
# push protection and gitleaks would otherwise flag the commit). This is the
# only test file allow-listed in .gitleaks.toml.
# ---------------------------------------------------------------------------


def _cat(*parts: str) -> str:
    """Join fragments at runtime so no token exists as one source literal."""
    return "".join(parts)


_BODY = _cat("Qx7vTn2LpR9sKd4HwB6mYc8ZaE3gJf5U", "1oNiXe0AqW")  # 42 mixed chars
_B36 = _cat(*["a1B2c3D4e5F6"] * 3)  # 36 mixed chars


def _positive_lines() -> dict[str, str]:
    return {
        "AWS Access Key ID": _cat('AWS_KEY = "', "AKIA", "ABCDEFGHIJKLMNOP", '"'),
        "AWS Temporary Key ID": _cat('KEY = "', "ASIA", "ABCDEFGHIJKLMNOP", '"'),
        "Private Key Block": _cat("-----BEGIN ", "PGP PRIVATE KEY BLOCK-----"),
        "Slack Token": _cat('SLACK = "', "xoxb-", "1234567890-abcdefghij", '"'),
        "GitHub Token": _cat('GH = "', "ghp_", _B36, '"'),
        "GitHub Fine-grained Token": _cat(
            'GH = "', "github_pat_", "11ABCDEFG0abcdefghijklmnopqrstuvwxyz", '"'
        ),
        "Anthropic API Key": _cat('KEY = "', "sk-ant-", "api03-", _BODY, '"'),
        "OpenAI API Key": _cat('KEY = "', "sk-proj-", _BODY, '"'),
        "Google API Key": _cat(
            'KEY = "', "AIza", "SyA-abcdefghijklmnopqrstuvwxyz01234", '"'
        ),
        "Stripe Live Key": _cat(
            'KEY = "', "sk_", "live_", "abcdefghijklmnopqrstuvwx", '"'
        ),
        "PyPI Token": _cat('TOKEN = "', "pypi-", "AgEI", _BODY, _BODY, '"'),
        "npm Token": _cat('TOKEN = "', "npm_", _B36, '"'),
        "JSON Web Token": _cat(
            'JWT = "',
            "eyJ",
            "hbGciOiJIUzI1NiJ9",
            ".eyJ",
            "zdWIiOiIxMjM0NTY3ODkw",
            ".abcdefghijklmnop",
            '"',
        ),
        "Credentials in URL": _cat(
            "DATABASE_URL=postgres://admin:", "S3cretPass9", "@db.internal:5432/app"
        ),
        "Generic API Key Assignment": _cat('api_key = "', "A1b2C3d4E5f6G7h8I9", '"'),
        "Hardcoded Password Assignment": _cat(
            'DB_PASSWORD = "', "Tr0ub4dour9xK2qZ", '"'
        ),
    }


def _negative_lines() -> dict[str, str]:
    return {
        "AWS Access Key ID": _cat("AKIA", "ABCDEFGHIJKLMNOPQ"),  # 17 after the prefix
        "AWS Temporary Key ID": "ASIA_PACIFIC_REGION_NAME_X",
        "Private Key Block": "-----BEGIN PUBLIC KEY----- (not secret)",
        "Slack Token": "xoxb-123 is a short example here",
        "GitHub Token": _cat("ghp_", "short", " is far too short to be real"),
        "GitHub Fine-grained Token": _cat(
            "github_pat_", "short", " is too short to be real"
        ),
        "Anthropic API Key": _cat("sk-ant-", "abc", " is too short to be real"),
        "OpenAI API Key": "risk-assessment-management-framework-core-library",
        "Google API Key": _cat("AIza", "short", " is too short to be a key"),
        "Stripe Live Key": _cat("sk_", "test_", "abcdefghijklmnopqrstuvwx"),
        "PyPI Token": _cat("pypi-", "AgEI", "short", " is too short to be real"),
        "npm Token": _cat("npm_", _B36[:35], " is one char short of a token"),
        "JSON Web Token": _cat("eyJ", "hbGciOiJIUzI1NiJ9", " is only a header segment"),
        "Credentials in URL": "https://user:password@host.example.org/path/to/page",
        "Generic API Key Assignment": 'api_key = "short"  # too short to be real',
        "Hardcoded Password Assignment": 'password = "changeme-please-1234"',
    }


def test_every_content_rule_has_a_positive_and_a_negative_case() -> None:
    names = set(content_pattern_names())
    assert set(_positive_lines()) == names
    assert set(_negative_lines()) == names


def test_each_content_rule_detects_its_positive_case() -> None:
    for name, line in _positive_lines().items():
        assert name in scan_line(line), f"{name} missed its own positive case"


def test_each_content_rule_ignores_its_near_miss() -> None:
    for name, line in _negative_lines().items():
        assert name not in scan_line(line), f"{name} fired on a near-miss"


def test_placeholders_and_variables_are_not_hardcoded_passwords() -> None:
    lines = [
        'token = "${GITHUB_TOKEN_VALUE_FROM_ENV}"',
        'password = "xxxxxxxxxxxxxxxx"',
        'password = os.environ["PASSWORD_VALUE_X"]',
        'secret = "<insert-your-secret-here-123>"',
        "url = postgres://user:${DB_PASSWORD}@host/db",
    ]
    for line in lines:
        assert scan_line(line) == [], line


def test_json_style_password_assignment_is_detected() -> None:
    line = _cat('  "password": "', "Tr0ub4dour9xK2qZ", '",')
    assert scan_line(line) == ["Hardcoded Password Assignment"]


def test_one_credential_on_one_line_is_one_finding() -> None:
    line = _cat('secret_key = "', "A1b2C3d4E5f6G7h8I9j0", '"')
    assert scan_line(line) == ["Generic API Key Assignment"]


def test_a_provider_token_in_a_token_variable_is_one_finding() -> None:
    # The specific rule wins over the catch-all password rule.
    line = _cat('TOKEN = "', "pypi-", "AgEI", _BODY, _BODY, '"')
    assert scan_line(line) == ["PyPI Token"]


def test_anthropic_key_is_not_also_reported_as_an_openai_key() -> None:
    line = _cat('KEY = "', "sk-ant-", "api03-", _BODY, '"')
    assert scan_line(line) == ["Anthropic API Key"]


def test_findings_never_carry_the_matched_value() -> None:
    for name, line in _positive_lines().items():
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "config.py", line + "\n")
            findings = scan_for_secrets(root, [Path("config.py")])
            assert [f.pattern_name for f in findings] == [name]
            dumped = repr(findings)
            for fragment in (_BODY[:16], _B36[:16], "S3cretPass9", "Tr0ub4dour9xK2qZ"):
                assert fragment not in dumped


def test_scan_for_secrets_no_longer_guesses_fixtures_from_the_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "tests").mkdir()
        write(
            root / "tests" / "test_x.py", _positive_lines()["AWS Access Key ID"] + "\n"
        )
        findings = scan_for_secrets(root, [Path("tests/test_x.py")])
        assert len(findings) == 1
        assert findings[0].is_test_fixture is False


def test_mark_fixture_findings_uses_only_the_explicit_allowlist() -> None:
    from sarand.models.results import SecretFinding

    findings = [
        SecretFinding(path="tests/test_secrets.py", line_number=1, pattern_name="a"),
        SecretFinding(path="tests/test_other.py", line_number=2, pattern_name="b"),
        SecretFinding(path="src/app.py", line_number=3, pattern_name="c"),
    ]
    marked = mark_fixture_findings(findings, ["tests/test_secrets.py"])
    assert [f.is_test_fixture for f in marked] == [True, False, False]
    assert all(not f.is_test_fixture for f in mark_fixture_findings(findings, []))


def test_mark_fixture_findings_clears_a_stale_flag() -> None:
    from sarand.models.results import SecretFinding

    stale = [
        SecretFinding(
            path="tests/test_other.py",
            line_number=1,
            pattern_name="a",
            is_test_fixture=True,
        )
    ]
    assert mark_fixture_findings(stale, [])[0].is_test_fixture is False


def test_fixture_globs_use_posix_paths_and_fnmatch_semantics() -> None:
    assert matches_fixture_path("tests\\golden\\a.md", ["tests/golden/*"])
    assert matches_fixture_path("tests/a/b/c.py", ["tests/*.py"])
    assert not matches_fixture_path("Tests/a.py", ["tests/*"])
    assert not matches_fixture_path("src/a.py", [])


def test_new_credential_filenames_are_recognised() -> None:
    names = [
        ".pypirc",
        ".git-credentials",
        "credentials",
        ".dockercfg",
        "terraform.tfstate",
        "terraform.tfstate.backup",
        "prod.tfvars",
        "prod.auto.tfvars.json",
        ".htpasswd",
        "kubeconfig",
        "kubeconfig.yaml",
        "kube_config.yml",
        "secrets.yaml",
        "secret.yml",
        "secrets.json",
        "secrets.toml",
        "AuthKey_ABC123.p8",
        "putty.ppk",
        "id_ecdsa_sk",
        "id_ed25519_sk",
        "my-app-adminsdk-x1y2.json",
        "vault.kdbx",
        "corp.ovpn",
        "wp-config.php",
    ]
    for name in names:
        assert looks_like_secret_filename(name.lower()), name


def test_ordinary_files_with_similar_names_are_not_credential_shaped() -> None:
    names = [
        "credentials.py",
        "secrets.py",
        "secrets_test.go",
        "my_secrets.yaml",
        "kubeconfig_test.go",
        "tfvars.md",
        "server.crt",
        "wp-config-sample.php",
        "README.md",
    ]
    for name in names:
        assert not looks_like_secret_filename(name.lower()), name


def test_path_patterns_catch_dotdirs_that_bare_names_cannot() -> None:
    for path in (
        ".docker/config.json",
        "home/user/.aws/credentials",
        ".kube/config",
        "deploy\\.docker\\config.json",
        ".gnupg/pubring.kbx",
    ):
        assert looks_like_secret_path(path), path
    for path in ("docs/config.json", "my.docker/config.json", "src/aws/credentials.py"):
        assert not looks_like_secret_path(path), path


def test_essential_files_excludes_the_files_that_were_embedded_before() -> None:
    # Measured on 2026-10-15 (AGENTS.md 5.67): these six were embedded into
    # the report because their extension is essential and no pattern matched.
    risky = [
        "secrets.yaml",
        "secrets.json",
        "secrets.toml",
        "firebase-adminsdk-abc.json",
        "kubeconfig.yaml",
        "prod.auto.tfvars.json",
        "wp-config.php",
        ".docker/config.json",
    ]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "main.py", "print('hi')\n")
        for rel in risky:
            write(root / rel, "x\n")
        included, _skipped, excluded = collect_essential_files(root)
        assert included == [Path("main.py")]
        assert {p.as_posix() for p in excluded} == set(risky)


def test_exclude_paths_only_touches_files_slated_for_embedding() -> None:
    included = [Path("a.py"), Path("b.py")]
    excluded = [Path("c.env")]
    new_included, new_excluded = exclude_paths(
        included, excluded, {Path("b.py"), Path("only-in-history.py")}
    )
    assert new_included == [Path("a.py")]
    assert new_excluded == [Path("b.py"), Path("c.env")]
    same_included, same_excluded = exclude_paths(included, excluded, set())
    assert same_included == included
    assert same_excluded == excluded


def test_rule_signatures_carry_the_version_and_every_regex() -> None:
    signatures = content_rule_signatures()
    assert signatures[0].startswith("rules-v")
    assert len(signatures) == len(content_pattern_names()) + 1
    assert any(s.startswith("AWS Access Key ID=") for s in signatures)


def test_shannon_entropy_basics() -> None:
    assert shannon_entropy("") == 0.0
    assert shannon_entropy("aaaa") == 0.0
    assert shannon_entropy("abcd") == 2.0


def test_content_rules_stay_linear_on_adversarial_lines() -> None:
    # Each input aims at one rule's worst case (a long run followed by a
    # missing anchor). A quadratic pattern needs minutes here; a linear one
    # needs milliseconds, so the 5-second bound is generous even on slow CI.
    cases = {
        "jwt-start-repeats": "eyJ" * 30000,
        "password-keyword-repeats": "password" * 20000,
        "url-scheme-repeats": "://" * 30000 + "a",
        "url-long-user": "a" * 100000 + "://" + "u" * 100000,
        "private-key-header": "-----BEGIN " + "A " * 50000 + "PRIVATE KEY",
        "openai-prefix-repeats": "sk-" * 30000,
        "aws-prefix-repeats": "AKIA" * 25000,
        "key-name-then-spaces": "api_key" + " " * 100000,
        "unterminated-assignment": "token = '" + "a" * 200000,
    }
    for label, line in cases.items():
        started = time.perf_counter()
        scan_line(line)
        elapsed = time.perf_counter() - started
        assert elapsed < 5.0, f"{label} took {elapsed:.2f}s"
