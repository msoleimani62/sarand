"""Tests for the per-project license policy (`.sarand.toml`)."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path

import pytest
import sarand.core.sbom as sbom_module
from _helpers import write
from sarand.core.license_policy import (
    LicensePolicy,
    PolicyError,
    evaluate,
    license_alternatives,
    load_policy,
    parse_policy,
)
from sarand.core.sbom import SbomPackage, run_syft


def _pkg(name: str, *licenses: str, version: str = "1.0") -> SbomPackage:
    return SbomPackage(name, version, "python", tuple(licenses))


def _levels(policy: LicensePolicy, *packages: SbomPackage) -> dict[str, int]:
    violations, _applied = evaluate(packages, policy)
    return {v.package: v.level for v in violations}


# --- parsing -------------------------------------------------------------


def test_parse_policy_reads_every_field() -> None:
    policy = parse_policy(
        '[licenses]\nallow = ["MIT"]\ndeny = ["GPL-*"]\nwarn = ["MPL-2.0"]\n'
        'unknown = "warn"\n\n[[licenses.exceptions]]\npackage = "x"\n'
        'version = "2.0"\nreason = "build tool only"\n'
    )

    assert policy is not None
    assert policy.allow == ("MIT",)
    assert policy.deny == ("GPL-*",)
    assert policy.warn == ("MPL-2.0",)
    assert policy.unknown == "warn"
    assert policy.exceptions[0].package == "x"
    assert policy.exceptions[0].version == "2.0"


def test_a_file_without_a_licenses_table_has_no_policy() -> None:
    assert parse_policy('[something_else]\nkey = "value"\n') is None
    assert parse_policy("") is None


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ('[licenses]\nalow = ["MIT"]\n', "unknown key"),
        ('[licenses]\nallow = "MIT"\n', "list of strings"),
        ("[licenses]\ndeny = [1, 2]\n", "list of strings"),
        ('[licenses]\nunknown = "maybe"\n', "unknown must be one of"),
        ('[licenses]\nexceptions = "x"\n', "must be a list of tables"),
        ('[licenses]\n[[licenses.exceptions]]\npackage = "x"\n', "reason"),
        ('[licenses]\n[[licenses.exceptions]]\nreason = "r"\n', "package"),
        ("[licenses\n", "invalid TOML"),
    ],
)
def test_a_wrong_file_is_an_error_never_silently_ignored(
    text: str, fragment: str
) -> None:
    with pytest.raises(PolicyError, match=fragment):
        parse_policy(text)


def test_load_policy_missing_file_is_none_and_broken_file_names_itself() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert load_policy(root) is None

        write(root / ".sarand.toml", '[licenses]\nalow = ["MIT"]\n')
        with pytest.raises(PolicyError, match=r"\.sarand\.toml"):
            load_policy(root)


# --- license strings -----------------------------------------------------


def test_license_alternatives_understand_spdx_expressions() -> None:
    assert license_alternatives("MIT") == [["MIT"]]
    assert license_alternatives("MIT OR Apache-2.0") == [["MIT"], ["Apache-2.0"]]
    assert license_alternatives("(MIT AND BSD-3-Clause) OR GPL-2.0-only") == [
        ["MIT", "BSD-3-Clause"],
        ["GPL-2.0-only"],
    ]
    assert license_alternatives("GPL-2.0-only WITH Classpath-exception-2.0") == [
        ["GPL-2.0-only"]
    ]


def test_license_alternatives_map_common_non_spdx_names() -> None:
    assert license_alternatives("Apache 2.0") == [["Apache-2.0"]]
    assert license_alternatives("PSFL") == [["PSF-2.0"]]
    assert license_alternatives("MIT License") == [["MIT"]]


def test_an_unrecognised_string_stays_one_opaque_license() -> None:
    assert license_alternatives("Some Vendor License v9") == [
        ["Some Vendor License v9"]
    ]


# --- evaluation ----------------------------------------------------------


def test_deny_beats_everything_and_globs_do_not_leak_across_families() -> None:
    policy = LicensePolicy(deny=("GPL-*",), warn=("LGPL-*",))

    levels = _levels(
        policy,
        _pkg("strong", "GPL-3.0-only"),
        _pkg("weak", "LGPL-2.1-only"),
        _pkg("fine", "MIT"),
    )

    assert levels == {"strong": 2, "weak": 1}


def test_allow_list_flags_everything_outside_it() -> None:
    policy = LicensePolicy(allow=("MIT", "Apache-2.0"), warn=("MPL-2.0",))

    levels = _levels(
        policy,
        _pkg("ok", "MIT"),
        _pkg("review", "MPL-2.0"),
        _pkg("bad", "BSD-3-Clause"),
        _pkg("weird", "Some Vendor License"),
    )

    assert levels == {"review": 1, "bad": 2, "weird": 2}


def test_or_takes_the_best_alternative_and_and_needs_every_part() -> None:
    policy = LicensePolicy(allow=("MIT", "Apache-2.0"), deny=("GPL-*",))

    levels = _levels(
        policy,
        _pkg("dual", "MIT OR GPL-3.0-only"),
        _pkg("both", "MIT AND GPL-3.0-only"),
        _pkg("entries", "GPL-3.0-only", "Apache-2.0"),
    )

    assert levels == {"both": 2}


def test_unknown_licenses_follow_the_configured_mode() -> None:
    package = _pkg("mystery")

    assert _levels(LicensePolicy(unknown="allow"), package) == {}
    assert _levels(LicensePolicy(unknown="warn"), package) == {"mystery": 1}
    assert _levels(LicensePolicy(unknown="deny"), package) == {"mystery": 2}


def test_exceptions_match_by_normalised_name_and_optional_version() -> None:
    policy = parse_policy(
        '[licenses]\ndeny = ["GPL-*"]\n'
        '[[licenses.exceptions]]\npackage = "My_Lib"\nreason = "build tool"\n'
        '[[licenses.exceptions]]\npackage = "pinned"\nversion = "1.0"\nreason = "r"\n'
    )
    assert policy is not None

    violations, applied = evaluate(
        [
            _pkg("my-lib", "GPL-3.0-only"),
            _pkg("pinned", "GPL-3.0-only", version="1.0"),
            _pkg("pinned", "GPL-3.0-only", version="2.0"),
        ],
        policy,
    )

    assert [(v.package, v.version) for v in violations] == [("pinned", "2.0")]
    assert len(applied) == 2


def test_real_license_mix_from_a_full_scan_of_this_project_is_clean() -> None:
    """The licenses a real `sarand --full` SBOM listed for this repo,
    including the non-SPDX spellings ("PSFL", "Apache 2.0")."""
    policy = LicensePolicy(
        allow=("MIT", "Apache-2.0", "BSD-*", "ISC", "PSF-2.0"),
        warn=("MPL-2.0",),
    )
    packages = [
        _pkg("a", "MIT"),
        _pkg("b", "Apache-2.0"),
        _pkg("c", "BSD-2-Clause"),
        _pkg("d", "BSD-3-Clause"),
        _pkg("e", "PSFL"),
        _pkg("f", "PSF-2.0"),
        _pkg("g", "Apache 2.0"),
        _pkg("h", "Apache-2.0 OR BSD-2-Clause"),
        _pkg("certifi", "MPL-2.0"),
    ]

    assert _levels(policy, *packages) == {"certifi": 1}


# --- integration with the syft check ------------------------------------


def _syft_json(*artifacts: tuple[str, str]) -> str:
    return json.dumps(
        {
            "artifacts": [
                {
                    "name": name,
                    "version": "1.0",
                    "type": "python",
                    "licenses": [{"value": lic, "spdxExpression": lic}],
                }
                for name, lic in artifacts
            ]
        }
    )


def _run_with(
    monkeypatch: pytest.MonkeyPatch,
    policy_text: str | None,
    *artifacts: tuple[str, str],
):
    async def fake_run_cmd_async(cmd, cwd, timeout):
        return 0, _syft_json(*artifacts), 0.1

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(sbom_module, "run_cmd_async", fake_run_cmd_async)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        if policy_text is not None:
            write(root / ".sarand.toml", policy_text)
        return asyncio.run(run_syft(root))


def test_a_denied_license_fails_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run_with(
        monkeypatch,
        '[licenses]\ndeny = ["GPL-*"]\n',
        ("fine", "MIT"),
        ("bad", "GPL-3.0-only"),
    )

    assert result.passed is False
    assert "problem: license policy: GPL-3.0-only is denied by the policy" in (
        result.raw_output
    )
    assert "bad 1.0 (python)" in result.raw_output
    assert "1 violation(s)" in result.raw_output


def test_a_clean_policy_passes_and_keeps_the_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _run_with(
        monkeypatch,
        '[licenses]\nallow = ["MIT"]\n',
        ("fine", "MIT"),
    )

    assert result.passed is True
    assert "SBOM: 1 package(s)" in result.raw_output
    assert "0 violation(s)" in result.raw_output


def test_exceptions_are_reported_not_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run_with(
        monkeypatch,
        '[licenses]\ndeny = ["GPL-*"]\n[[licenses.exceptions]]\n'
        'package = "bad"\nreason = "build tool, never shipped"\n',
        ("bad", "GPL-3.0-only"),
    )

    assert result.passed is True
    assert "note: exception for bad 1.0: build tool, never shipped" in result.raw_output


def test_an_invalid_policy_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run_with(monkeypatch, '[licenses]\nalow = ["MIT"]\n', ("fine", "MIT"))

    assert result.passed is False
    assert "problem: license policy: .sarand.toml: [licenses] unknown key(s): alow" in (
        result.raw_output
    )


def test_without_a_policy_the_builtin_advisory_still_applies_and_never_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _run_with(monkeypatch, None, ("bad", "GPL-3.0-only"))

    assert result.passed is True
    assert "warning: strong-copyleft license GPL-3.0-only" in result.raw_output


def test_policy_output_avoids_the_words_the_issue_scanner_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _run_with(
        monkeypatch,
        '[licenses]\ndeny = ["GPL-*"]\n',
        ("bad", "GPL-3.0-only"),
    )

    lowered = result.raw_output.lower()
    assert "error:" not in lowered
    assert "failed" not in lowered
