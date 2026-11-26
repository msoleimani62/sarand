"""Findings baseline, slice F1: the `--baseline` option on the real command.

The comparison reaches every format; an unusable report is refused before any work; a run
without the option is unchanged; and a findings-only run never loads the structure
package (docs/FINDINGS_BASELINE.md, "Independence").

baseline یافته‌ها (قطعه‌ی F1): گزینه‌ی `--baseline` روی فرمان واقعی؛ گزارش نامعتبر پیش از هر
کاری رد می‌شود؛ اجرای بدون گزینه تغییری ندارد؛ و اجرای فقط-یافته‌ها بسته‌ی structure را بار نمی‌کند.
"""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
# Built at run time from pieces: no secret-looking literal sits in the repository (gitleaks
# scans it); the scanner under test sees the joined text in the project it scans.
# در زمان اجرا از تکه‌ها ساخته می‌شود: هیچ literal شبیه secret در مخزن نمی‌ماند (gitleaks آن را
# می‌گردد)؛ اسکنرِ مورد آزمون متن چسبیده را در پروژه‌ی اسکن‌شده می‌بیند.
_AWS = "AKIA" + "IOSFODNN7EXAMPLE"
_PAT = "ghp_" + "1234567890abcdefghijklmnopqrstuvwxyz12"
SECRETS = f'AWS_KEY = "{_AWS}"\nTOKEN = "{_PAT}"\n'


def _project(tmp_path: Path, secret_text: str | None) -> Path:
    project = tmp_path / "p"
    project.mkdir(exist_ok=True)
    (project / "ok.py").write_text("x = 1\n", encoding="utf-8")
    config = project / "conf.py"
    if secret_text is None:
        config.unlink(missing_ok=True)
    else:
        config.write_text(secret_text, encoding="utf-8")
    return project


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(_ROOT / "python"), *filter(None, [env.get("PYTHONPATH")])]
    )
    return env


def _run(tmp_path: Path, project: Path, *args: str) -> subprocess.CompletedProcess[str]:
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
        env=_env(),
        capture_output=True,
        text=True,
        check=False,
    )


def _json(tmp_path: Path, name: str) -> dict:
    return json.loads((tmp_path / "out" / name).read_text(encoding="utf-8"))


def _reference(tmp_path: Path) -> Path:
    project = _project(tmp_path, SECRETS)
    done = _run(tmp_path, project, "-f", "json", "-o", "ref.json")
    assert done.returncode == 0, done.stderr
    return tmp_path / "out" / "ref.json"


def test_the_findings_reach_the_json_report_and_the_key_rule_holds(
    tmp_path: Path,
) -> None:
    reference = _reference(tmp_path)
    project = _project(tmp_path, SECRETS)

    same = _run(
        tmp_path, project, "--baseline", str(reference), "-f", "json", "-o", "same.json"
    )
    assert same.returncode == 0, same.stderr
    payload = _json(tmp_path, "same.json")
    assert payload["schema_version"] == "1.12"
    assert payload["baseline"]["summary"]["secrets"]["unchanged"] == 2
    assert payload["baseline"]["findings"]["secrets"] == []

    _project(tmp_path, "x = 2\n")
    cleaned = _run(
        tmp_path,
        project,
        "--baseline",
        str(reference),
        "-f",
        "json",
        "-o",
        "clean.json",
    )
    assert cleaned.returncode == 0, cleaned.stderr
    states = {
        e["state"]
        for e in _json(tmp_path, "clean.json")["baseline"]["findings"]["secrets"]
    }
    assert states == {"fixed"}

    _project(tmp_path, None)
    gone = _run(
        tmp_path, project, "--baseline", str(reference), "-f", "json", "-o", "gone.json"
    )
    assert gone.returncode == 0, gone.stderr
    entries = _json(tmp_path, "gone.json")["baseline"]["findings"]["secrets"]
    assert {(e["state"], e["reason"]) for e in entries} == {
        ("not_checked", "file_not_scanned")
    }


def test_the_comparison_reaches_the_other_formats(tmp_path: Path) -> None:
    reference = _reference(tmp_path)
    project = _project(tmp_path, "x = 2\n")
    outputs = {}
    for fmt, name in (("markdown", "b.md"), ("html", "b.html"), ("text", "b.txt")):
        done = _run(
            tmp_path, project, "--baseline", str(reference), "-f", fmt, "-o", name
        )
        assert done.returncode == 0, done.stderr
        outputs[fmt] = (tmp_path / "out" / name).read_text(encoding="utf-8")
    assert "## Findings since the baseline" in outputs["markdown"]
    assert "| secrets | fixed |" in outputs["markdown"]
    assert "<h2>Findings since the baseline</h2>" in outputs["html"]
    assert "Findings since the baseline: 0 new, 2 fixed" in outputs["text"]


def test_an_unusable_baseline_is_refused_before_any_report_is_written(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path, SECRETS)
    (tmp_path / "bad.json").write_text('{"schema_version": "9.0"}', encoding="utf-8")
    (tmp_path / "text.json").write_text("not json", encoding="utf-8")
    for baseline in ("bad.json", "text.json", "missing.json"):
        done = _run(
            tmp_path, project, "--baseline", baseline, "-f", "json", "-o", "x.json"
        )
        assert done.returncode == 4  # a baseline error is never a general error
    assert not (tmp_path / "out").exists() or list((tmp_path / "out").iterdir()) == []


def test_a_run_without_the_option_has_no_baseline_key(tmp_path: Path) -> None:
    project = _project(tmp_path, SECRETS)
    done = _run(tmp_path, project, "-f", "json", "-o", "a.json")
    assert done.returncode == 0, done.stderr
    assert "baseline" not in _json(tmp_path, "a.json")


def _loaded(tmp_path: Path, project: Path, *args: str) -> str:
    """Run the command in-process with an exit hook that reports whether the structure
    package was loaded."""
    code = (
        "import atexit, runpy, sys\n"
        "atexit.register(lambda: print('STRUCTURE_LOADED=' + "
        "str(any(m.startswith('sarand.structure') for m in sys.modules))))\n"
        f"sys.argv = ['sarand', '--project', {str(project)!r}, '--skip-tests', '--no-health', "
        f"'--no-source', '--output-dir', {str(tmp_path / 'out')!r}, *{list(args)!r}]\n"
        "runpy.run_module('sarand', run_name='__main__')\n"
    )
    done = subprocess.run(  # nosec B603
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    return next(
        (
            line
            for line in done.stdout.splitlines()
            if line.startswith("STRUCTURE_LOADED=")
        ),
        f"no marker: {done.stderr[-300:]}",
    )


def test_a_findings_only_run_never_loads_the_structure_package(tmp_path: Path) -> None:
    reference = _reference(tmp_path)
    project = _project(tmp_path, "x = 2\n")
    only = _loaded(
        tmp_path, project, "--baseline", str(reference), "-f", "json", "-o", "i.json"
    )
    assert only == "STRUCTURE_LOADED=False"
    with_structure = _loaded(
        tmp_path, project, "--structure", "-f", "json", "-o", "j.json"
    )
    assert with_structure == "STRUCTURE_LOADED=True"
