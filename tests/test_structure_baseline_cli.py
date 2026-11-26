"""Structural baseline, slice S2: snapshot files and the command line.

What these tests defend (the acceptance criteria of `docs/R14D1_PLAN.md`, section 5):
a snapshot is written all or nothing and never over a file unasked; a replacement keeps
the previous generation; reading never raises; an unusable baseline or target is
refused before any work and writes no report; the comparison reaches the JSON report
(schema 1.11) and the other formats; a run without the options is unchanged.

مقایسه‌ی ساختاری (قطعه‌ی S2): snapshot یا کامل نوشته می‌شود یا هیچ و هرگز بی‌اجازه روی فایل
نمی‌نشیند؛ جایگزینی نسل قبلی را نگه می‌دارد؛ خواندن exception نمی‌دهد؛ baseline یا مقصد نامعتبر
پیش از هر کاری رد می‌شود و گزارشی نمی‌نویسد؛ مقایسه به گزارش‌ها می‌رسد.
"""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Any

import pytest
from sarand import cli
from sarand.structure import build_structure
from sarand.structure import snapshot_io as io
from sarand.structure.serialize import structure_payload
from sarand.structure.snapshot import make_snapshot, read_reference

_ROOT = Path(__file__).resolve().parent.parent
BASE = {
    "pkg/__init__.py": "",
    "pkg/a.py": "import os\n\n\ndef f():\n    return 1\n",
}
CHANGED = {"pkg/a.py": "def f():\n    return 2\n\n\ndef g():\n    return f()\n"}


def _project(root: Path, name: str, files: dict[str, str]) -> Path:
    project = root / name
    for rel, text in files.items():
        target = project / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return project


def _snapshot(tmp_path: Path) -> dict[str, Any]:
    project = _project(tmp_path, "src", BASE)
    included = sorted(p.relative_to(project) for p in project.rglob("*") if p.is_file())
    payload = json.loads(
        json.dumps(structure_payload(build_structure(project, included)))
    )
    return make_snapshot(payload)


def _run(tmp_path: Path, project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(_ROOT / "python"), *filter(None, [env.get("PYTHONPATH")])]
    )
    return subprocess.run(  # nosec B603
        [
            sys.executable,
            "-m",
            "sarand",
            "--project",
            str(project),
            "--skip-tests",
            "--no-health",
            "--no-source",
            "--output-dir",
            str(tmp_path / "out"),
            *args,
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _reports(tmp_path: Path) -> list[str]:
    out = tmp_path / "out"
    return sorted(p.name for p in out.iterdir()) if out.is_dir() else []


# -------------------------------------------------------------- snapshot files


def test_a_snapshot_is_written_verified_and_readable(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    target = tmp_path / "snap.json"
    written = io.write_snapshot(target, snapshot)
    assert written.path == target and written.previous is None
    assert written.digest == snapshot["digest"]
    reference = io.read_reference_file(target)
    assert reference.usable and reference.source == "snapshot"
    assert sorted(p.name for p in tmp_path.iterdir() if p.name.startswith(".")) == []


def test_an_existing_file_is_never_overwritten_unasked(tmp_path: Path) -> None:
    target = tmp_path / "snap.json"
    target.write_text("precious", encoding="utf-8")
    with pytest.raises(io.SnapshotTargetError) as excinfo:
        io.write_snapshot(target, _snapshot(tmp_path))
    assert "--replace-structure-snapshot" in str(excinfo.value)
    assert target.read_text(encoding="utf-8") == "precious"
    assert not io.previous_path(target).exists()


def test_a_replacement_keeps_the_previous_generation_byte_for_byte(
    tmp_path: Path,
) -> None:
    first = _snapshot(tmp_path)
    target = tmp_path / "snap.json"
    io.write_snapshot(target, first)
    old_bytes = target.read_bytes()
    other = make_snapshot(first["structure"], excluded_secret_files=["x.py"])
    written = io.write_snapshot(target, other, replace=True)
    assert written.previous == io.previous_path(target)
    assert io.previous_path(target).read_bytes() == old_bytes
    assert target.read_bytes() != old_bytes
    assert io.read_reference_file(target).excluded_secret_files == ("x.py",)


def test_a_failed_verification_leaves_the_destination_and_no_temporary_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "snap.json"
    io.write_snapshot(target, _snapshot(tmp_path))
    before = target.read_bytes()

    def broken(staged: Path, expected: str) -> None:
        raise OSError("disk says no")

    monkeypatch.setattr(io, "_verify", broken)
    with pytest.raises(OSError):
        io.write_snapshot(target, _snapshot(tmp_path), replace=True)
    assert target.read_bytes() == before
    assert not io.previous_path(target).exists()
    assert sorted(p.name for p in tmp_path.iterdir() if p.name.startswith(".")) == []


def test_unwritable_targets_are_refused_with_a_reason(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    (tmp_path / "dir").mkdir()
    for target, why in (
        (tmp_path / "dir", "directory"),
        (tmp_path / "missing" / "snap.json", "does not exist"),
    ):
        with pytest.raises(io.SnapshotTargetError) as excinfo:
            io.write_snapshot(target, snapshot)
        assert why in str(excinfo.value)


@pytest.mark.skipif(os.name == "nt", reason="symbolic links need privileges on Windows")
def test_a_symbolic_link_is_never_followed(tmp_path: Path) -> None:
    real = tmp_path / "real.json"
    real.write_text("keep", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(real)
    with pytest.raises(io.SnapshotTargetError):
        io.write_snapshot(link, _snapshot(tmp_path), replace=True)
    assert real.read_text(encoding="utf-8") == "keep"


def test_reading_a_reference_file_never_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "text.json").write_text("not json", encoding="utf-8")
    (tmp_path / "binary.json").write_bytes(b"\xff\xfe\x00garbage")
    (tmp_path / "array.json").write_text("[1, 2]", encoding="utf-8")
    (tmp_path / "dir").mkdir()
    for name in ("text.json", "binary.json", "array.json", "dir", "absent.json"):
        reference = io.read_reference_file(tmp_path / name)
        assert not reference.usable and reference.problem, name
    snap = tmp_path / "snap.json"
    io.write_snapshot(snap, _snapshot(tmp_path))
    monkeypatch.setattr(io, "MAX_SNAPSHOT_BYTES", 100)
    assert "larger than" in io.read_reference_file(snap).problem


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_snapshot_files_follow_the_umask_and_keep_a_replaced_files_mode(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(tmp_path)
    target = tmp_path / "snap.json"
    previous_umask = os.umask(0o022)
    try:
        io.write_snapshot(target, snapshot)
    finally:
        os.umask(previous_umask)
    assert target.stat().st_mode & 0o777 == 0o644
    target.chmod(0o640)
    io.write_snapshot(target, snapshot, replace=True)
    assert target.stat().st_mode & 0o777 == 0o640
    assert io.previous_path(target).stat().st_mode & 0o777 == 0o640


# ------------------------------------------------------------------- the options


def test_the_new_options_need_structure_and_the_replace_flag_needs_a_target(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path, "p", BASE)

    def config(*extra: str) -> Any:
        parser = cli.build_parser()
        return cli.SarandConfig.from_args(
            parser.parse_args(["--project", str(project), *extra])
        )

    for extra in (
        ["--structure-baseline", "b.json"],
        ["--structure-snapshot", "s.json"],
        ["--replace-structure-snapshot"],
    ):
        with pytest.raises(ValueError) as excinfo:
            config(*extra).validate()
        assert "needs --structure" in str(excinfo.value)
    with pytest.raises(ValueError):
        config("--structure", "--replace-structure-snapshot").validate()
    config(
        "--structure", "--structure-baseline", "b.json", "--structure-snapshot", "s"
    ).validate()


# ------------------------------------------------------- the whole command


def test_the_comparison_reaches_every_format_and_the_json_schema(
    tmp_path: Path,
) -> None:
    old = _project(tmp_path, "old", BASE)
    new = _project(tmp_path, "new", {**BASE, **CHANGED})
    snap = tmp_path / "snap.json"
    first = _run(
        tmp_path,
        old,
        "--structure",
        "--structure-snapshot",
        str(snap),
        "-f",
        "json",
        "-o",
        "a.json",
    )
    assert first.returncode == 0, first.stderr
    assert io.read_reference_file(snap).usable

    outputs = {}
    for fmt, name in (
        ("json", "b.json"),
        ("markdown", "b.md"),
        ("html", "b.html"),
        ("text", "b.txt"),
    ):
        done = _run(
            tmp_path,
            new,
            "--structure",
            "--structure-baseline",
            str(snap),
            "-f",
            fmt,
            "-o",
            name,
        )
        assert done.returncode == 0, done.stderr
        outputs[fmt] = (tmp_path / "out" / name).read_text(encoding="utf-8")

    payload = json.loads(outputs["json"])
    assert payload["schema_version"] == "1.12"
    comparison = payload["structure_comparison"]
    assert comparison["verdict"] == "comparable"
    assert comparison["summary"]["symbols"]["added"] == 1
    assert comparison["summary"]["symbols"]["content_changed"] == 1
    assert "## Structure changes" in outputs["markdown"]
    assert "content_changed" in outputs["markdown"]
    assert "<h2>Structure changes</h2>" in outputs["html"]
    assert "Structure changes (comparable)" in outputs["text"]


def test_a_run_without_the_options_has_no_comparison_key(tmp_path: Path) -> None:
    project = _project(tmp_path, "p", BASE)
    done = _run(tmp_path, project, "--structure", "-f", "json", "-o", "a.json")
    assert done.returncode == 0, done.stderr
    payload = json.loads((tmp_path / "out" / "a.json").read_text(encoding="utf-8"))
    assert "structure_comparison" not in payload and "structure" in payload


def test_an_unusable_baseline_is_refused_before_any_report_is_written(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path, "p", BASE)
    (tmp_path / "bad.json").write_text('{"a": 1}', encoding="utf-8")
    for baseline in ("bad.json", "missing.json"):
        done = _run(
            tmp_path,
            project,
            "--structure",
            "--structure-baseline",
            baseline,
            "-f",
            "json",
            "-o",
            "x.json",
        )
        assert done.returncode == 4  # an unusable baseline: exit code 4
    assert _reports(tmp_path) == []


def test_a_baseline_without_structure_is_refused(tmp_path: Path) -> None:
    project = _project(tmp_path, "p", BASE)
    done = _run(
        tmp_path,
        project,
        "--structure-baseline",
        "b.json",
        "-f",
        "json",
        "-o",
        "x.json",
    )
    assert done.returncode == 1 and _reports(tmp_path) == []


def test_the_snapshot_is_replaced_only_on_request_and_after_a_good_report(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path, "p", BASE)
    snap = tmp_path / "snap.json"
    args = (
        "--structure",
        "--structure-snapshot",
        str(snap),
        "-f",
        "json",
        "-o",
        "r.json",
    )
    assert _run(tmp_path, project, *args).returncode == 0
    before = snap.read_bytes()

    refused = _run(tmp_path, project, *args)
    assert refused.returncode == 1
    assert snap.read_bytes() == before and not io.previous_path(snap).exists()

    (project / "pkg" / "a.py").write_text(CHANGED["pkg/a.py"], encoding="utf-8")
    replaced = _run(tmp_path, project, *args, "--replace-structure-snapshot")
    assert replaced.returncode == 0, replaced.stderr
    assert io.previous_path(snap).read_bytes() == before
    assert snap.read_bytes() != before
    assert read_reference(json.loads(snap.read_text(encoding="utf-8"))).usable
