"""Tests for core/sbom.py."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path

import pytest
from sarand.core.sbom import classify_license, parse_packages, render_sbom, run_syft


def test_run_syft_skips_cleanly_without_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)

    with tempfile.TemporaryDirectory() as tmp:
        result = asyncio.run(run_syft(Path(tmp)))

    assert result.kind == "syft (SBOM)"
    assert result.skipped is True
    assert "not installed" in result.skip_reason


def _syft_json(*artifacts: dict) -> str:
    return json.dumps({"artifacts": list(artifacts)})


def _artifact(name: str, version: str, kind: str, *licenses: str) -> dict:
    return {
        "name": name,
        "version": version,
        "type": kind,
        "licenses": [{"value": lic, "spdxExpression": lic} for lic in licenses],
    }


def test_run_syft_asks_for_json_and_renders_an_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sarand.core.sbom as sbom_module

    captured_cmds: list[list[str]] = []

    async def fake_run_cmd_async(cmd, cwd, timeout):
        captured_cmds.append(cmd)
        return 0, _syft_json(_artifact("requests", "2.31.0", "python", "MIT")), 0.1

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(sbom_module, "run_cmd_async", fake_run_cmd_async)

    with tempfile.TemporaryDirectory() as tmp:
        result = asyncio.run(run_syft(Path(tmp)))

    assert result.skipped is False
    assert captured_cmds == [["syft", "dir:.", "-o", "json", "--quiet"]]
    assert "SBOM: 1 package(s) -- python: 1" in result.raw_output
    assert "requests" in result.raw_output


def test_run_syft_falls_back_to_the_plain_table_when_json_is_unusable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sarand.core.sbom as sbom_module

    captured_cmds: list[list[str]] = []

    async def fake_run_cmd_async(cmd, cwd, timeout):
        captured_cmds.append(cmd)
        return 0, "NAME  VERSION  TYPE\nrequests  2.31.0  python", 0.1

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(sbom_module, "run_cmd_async", fake_run_cmd_async)

    with tempfile.TemporaryDirectory() as tmp:
        result = asyncio.run(run_syft(Path(tmp)))

    assert captured_cmds == [
        ["syft", "dir:.", "-o", "json", "--quiet"],
        ["syft", "dir:.", "-o", "table", "--quiet"],
    ]
    assert result.passed is True
    assert "requests  2.31.0  python" in result.raw_output


def test_classify_license_levels() -> None:
    assert classify_license("MIT") == 0
    assert classify_license("Apache-2.0") == 0
    assert classify_license("GPL-3.0-only") == 2
    assert classify_license("AGPL-3.0-or-later") == 2
    assert classify_license("LGPL-2.1-only") == 1
    assert classify_license("MPL-2.0") == 1
    # OR = the consumer chooses, so the most permissive option wins.
    assert classify_license("MIT OR GPL-3.0-only") == 0
    assert classify_license("(MIT OR Apache-2.0)") == 0
    # AND binds to the strictest term.
    assert classify_license("MIT AND GPL-2.0-only") == 2
    assert classify_license("") == 0


def test_parse_packages_rejects_unexpected_shapes_and_tolerates_noise() -> None:
    assert parse_packages("not json") is None
    assert parse_packages(json.dumps({"other": []})) is None
    assert parse_packages(json.dumps([1, 2])) is None

    noisy = "note: something\n" + _syft_json(_artifact("a", "1", "python", "MIT"))
    packages = parse_packages(noisy)

    assert packages is not None
    assert [p.name for p in packages] == ["a"]


def test_parse_packages_dedupes_and_merges_licenses() -> None:
    text = _syft_json(
        _artifact("a", "1", "python", "MIT"),
        _artifact("a", "1", "python", "MIT", "Apache-2.0"),
        _artifact("a", "2", "python"),
    )

    packages = parse_packages(text)

    assert packages is not None
    assert len(packages) == 2
    first = next(p for p in packages if p.version == "1")
    assert first.licenses == ("MIT", "Apache-2.0")


def test_render_sbom_summarizes_and_flags_copyleft_advisorily() -> None:
    packages = parse_packages(
        _syft_json(
            _artifact("permissive", "1", "python", "MIT"),
            _artifact("strong", "2", "rust-crate", "GPL-3.0-only"),
            _artifact("weak", "3", "rust-crate", "LGPL-2.1-only"),
            _artifact("dual", "4", "python", "MIT OR GPL-3.0-only"),
            _artifact("mystery", "5", "python"),
        )
    )
    assert packages is not None

    text = render_sbom(packages)

    assert "SBOM: 5 package(s) -- python: 3, rust-crate: 2" in text
    assert "no license reported: 1" in text
    assert "warning: strong-copyleft license GPL-3.0-only -- strong 2" in text
    assert "warning: weak-copyleft license LGPL-2.1-only -- weak 3" in text
    assert "-- dual" not in text
    assert "-- permissive" not in text
    assert "NAME" in text and "LICENSES" in text
