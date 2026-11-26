"""Findings baseline, slice F2: `--baseline-gate` and the exit codes on the real command.

`0` success, `1` general error, `3` the gate failed, `4` the baseline is unusable. A gate
failure still writes the report; an unusable baseline writes nothing; the option is valid
only with `--baseline`; a fixture secret is never Critical; what cannot be decided is
listed and never fails.

`--baseline-gate` و کدهای خروج روی فرمان واقعی: ۰ موفق، ۱ خطای عمومی، ۳ شکست gate، ۴ baseline
نامعتبر. شکست gate گزارش را می‌نویسد؛ baseline نامعتبر چیزی نمی‌نویسد؛ گزینه فقط با
`--baseline` معتبر است؛ secret از نوع fixture هرگز بحرانی نیست.
"""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
# Built at run time from pieces so that no secret-looking literal sits in the repository
# (gitleaks scans it); the scanner under test sees the joined text.
# در زمان اجرا از تکه‌ها ساخته می‌شود تا literal شبیه secret در مخزن نماند.
_AWS = "AKIA" + "IOSFODNN7EXAMPLE"
SECRET_TEXT = f'AWS_KEY = "{_AWS}"\n'


def _project(tmp_path: Path, secret: bool, fixture: bool = False) -> Path:
    project = tmp_path / "p"
    project.mkdir(exist_ok=True)
    (project / "ok.py").write_text("x = 1\n", encoding="utf-8")
    config = project / "conf.py"
    if secret:
        config.write_text(SECRET_TEXT, encoding="utf-8")
    else:
        config.unlink(missing_ok=True)
    toml = project / ".sarand.toml"
    if fixture:
        toml.write_text('[secrets]\nfixture_paths = ["conf.py"]\n', encoding="utf-8")
    else:
        toml.unlink(missing_ok=True)
    return project


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(_ROOT / "python"), *filter(None, [env.get("PYTHONPATH")])]
    )
    return env


def _run(
    tmp_path: Path, project: Path, *args: str, health: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603
        [
            sys.executable,
            "-m",
            "sarand",
            "--project",
            str(project),
            "--skip-tests",
            *([] if health else ["--no-health"]),
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


def _reference(tmp_path: Path, secret: bool, fixture: bool = False) -> Path:
    done = _run(
        tmp_path, _project(tmp_path, secret, fixture), "-f", "json", "-o", "ref.json"
    )
    assert done.returncode == 0, done.stderr
    return tmp_path / "out" / "ref.json"


def _gate(tmp_path: Path, name: str) -> dict:
    payload = json.loads((tmp_path / "out" / name).read_text(encoding="utf-8"))
    return payload["baseline"]["gate"]


def _compare(
    tmp_path: Path,
    reference: Path,
    project: Path,
    policy: str | None,
    name: str,
    health: bool = False,
) -> subprocess.CompletedProcess[str]:
    args = ["--baseline", str(reference), "-f", "json", "-o", name]
    if policy is not None:
        args += ["--baseline-gate", policy]
    return _run(tmp_path, project, *args, health=health)


def test_new_fails_with_exit_3_and_the_report_is_still_written(tmp_path: Path) -> None:
    reference = _reference(tmp_path, secret=False)
    project = _project(tmp_path, secret=True)
    done = _compare(tmp_path, reference, project, "new", "g.json")
    assert done.returncode == 3, done.stderr
    assert "Gate    : FAILED (policy new): 1 finding(s)" in done.stdout
    assert "secrets:" in done.stdout and "(new_finding)" in done.stdout
    gate = _gate(tmp_path, "g.json")
    assert gate["verdict"] == "fail" and gate["policy"] == "new"
    assert gate["failed_on"][0]["class"] == "secrets"


def test_new_passes_when_the_secret_was_already_in_the_reference(
    tmp_path: Path,
) -> None:
    reference = _reference(tmp_path, secret=True)
    project = _project(tmp_path, secret=True)
    done = _compare(tmp_path, reference, project, "new", "g.json")
    assert done.returncode == 0, done.stderr
    assert "Gate    : passed (policy new)" in done.stdout
    assert _gate(tmp_path, "g.json")["verdict"] == "pass"


def test_critical_fails_on_an_old_secret_that_new_and_new_critical_accept(
    tmp_path: Path,
) -> None:
    reference = _reference(tmp_path, secret=True)
    project = _project(tmp_path, secret=True)
    codes = {
        policy: _compare(tmp_path, reference, project, policy, f"{policy}.json")
        for policy in ("new", "new-critical", "critical")
    }
    assert {p: d.returncode for p, d in codes.items()} == {
        "new": 0,
        "new-critical": 0,
        "critical": 3,
    }


def test_the_default_and_never_change_no_exit_code(tmp_path: Path) -> None:
    reference = _reference(tmp_path, secret=False)
    project = _project(tmp_path, secret=True)
    for policy, name in ((None, "a.json"), ("never", "b.json")):
        done = _compare(tmp_path, reference, project, policy, name)
        assert done.returncode == 0, done.stderr
        assert "Gate    :" not in done.stdout
        gate = _gate(tmp_path, name)
        assert gate["verdict"] == "not_gated" and gate["failed_on"] == []


def test_the_gate_option_needs_a_baseline_and_a_known_policy(tmp_path: Path) -> None:
    project = _project(tmp_path, secret=False)
    alone = _run(
        tmp_path, project, "--baseline-gate", "new", "-f", "json", "-o", "x.json"
    )
    assert alone.returncode == 1
    unknown = _run(
        tmp_path, project, "--baseline-gate", "sometimes", "-f", "json", "-o", "x.json"
    )
    assert unknown.returncode == 2  # refused by the argument parser
    assert not (tmp_path / "out").exists() or list((tmp_path / "out").iterdir()) == []


def test_an_unusable_baseline_is_exit_4_with_or_without_a_gate(tmp_path: Path) -> None:
    project = _project(tmp_path, secret=True)
    (tmp_path / "bad.json").write_text('{"schema_version": "9.0"}', encoding="utf-8")
    for policy in (None, "new", "critical"):
        done = _compare(tmp_path, tmp_path / "bad.json", project, policy, "x.json")
        assert done.returncode == 4, (policy, done.stderr)
    assert not (tmp_path / "out").exists() or list((tmp_path / "out").iterdir()) == []


def test_a_fixture_secret_is_never_critical(tmp_path: Path) -> None:
    reference = _reference(tmp_path, secret=False)
    project = _project(tmp_path, secret=True, fixture=True)
    for policy in ("new", "new-critical", "critical"):
        done = _compare(tmp_path, reference, project, policy, f"{policy}.json")
        assert done.returncode == 0, (policy, done.stdout, done.stderr)
        assert _gate(tmp_path, f"{policy}.json")["failed_on"] == []


def test_without_health_the_conditions_are_uncertain_and_never_fail(
    tmp_path: Path,
) -> None:
    reference = _reference(tmp_path, secret=False)
    project = _project(tmp_path, secret=False)
    done = _compare(tmp_path, reference, project, "critical", "g.json")
    assert done.returncode == 0, done.stderr
    gate = _gate(tmp_path, "g.json")
    assert gate["verdict"] == "pass"
    assert [u["reason"] for u in gate["uncertain"]] == ["health_not_computed"]
    assert "1 uncertain" in done.stdout


def test_a_clean_run_with_health_passes_every_policy(tmp_path: Path) -> None:
    reference = _reference(tmp_path, secret=False)
    project = _project(tmp_path, secret=False)
    for policy in ("new", "new-critical", "critical"):
        done = _compare(
            tmp_path, reference, project, policy, f"{policy}.json", health=True
        )
        assert done.returncode == 0, (policy, done.stdout, done.stderr)
        assert _gate(tmp_path, f"{policy}.json")["failed_on"] == []


def test_the_gate_reaches_every_format(tmp_path: Path) -> None:
    reference = _reference(tmp_path, secret=False)
    project = _project(tmp_path, secret=True)
    outputs = {}
    for fmt, name in (("markdown", "g.md"), ("html", "g.html"), ("text", "g.txt")):
        done = _run(
            tmp_path,
            project,
            "--baseline",
            str(reference),
            "--baseline-gate",
            "new",
            "-f",
            fmt,
            "-o",
            name,
        )
        assert done.returncode == 3, done.stderr
        outputs[fmt] = (tmp_path / "out" / name).read_text(encoding="utf-8")
    assert "### Gate" in outputs["markdown"]
    assert "Gate (policy new): FAILED on 1 finding(s)" in outputs["markdown"]
    assert "| failed | secrets |" in outputs["markdown"]
    assert "<h3>Gate</h3>" in outputs["html"]
    assert "Gate (policy new): FAILED on 1 finding(s)" in outputs["text"]


def test_a_run_without_a_baseline_has_no_gate_output(tmp_path: Path) -> None:
    project = _project(tmp_path, secret=True)
    done = _run(tmp_path, project, "-f", "json", "-o", "a.json")
    assert done.returncode == 0, done.stderr
    assert "Gate    :" not in done.stdout
    assert "baseline" not in json.loads(
        (tmp_path / "out" / "a.json").read_text(encoding="utf-8")
    )
