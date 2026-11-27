"""Findings baseline, slice F3: waivers on the real command.

A waiver turns a failed gate into a pass and stays visible (JSON, Markdown, text and the
closing summary); an expired or an exceeded waiver does not apply and the gate fails; an
invalid waiver file is an error (exit code 1, no report) but only when a gate is on.

waiverها روی فرمان واقعی: waiver شکست gate را به قبول تبدیل می‌کند و دیده می‌شود؛ waiver
منقضی یا فراتر از `covers` اعمال نمی‌شود؛ فایل waiver نامعتبر خطاست ولی فقط وقتی gate روشن است.
"""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404
import sys
from datetime import date, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
# Built at run time from pieces so that no secret-looking literal sits in the repository.
# در زمان اجرا از تکه‌ها ساخته می‌شود تا literal شبیه secret در مخزن نماند.
_AWS = "AKIA" + "IOSFODNN7EXAMPLE"
SECRET_TEXT = f'AWS_KEY = "{_AWS}"\n'


def _project(tmp_path: Path, secrets: tuple[str, ...], toml: str = "") -> Path:
    project = tmp_path / "p"
    project.mkdir(exist_ok=True)
    (project / "ok.py").write_text("x = 1\n", encoding="utf-8")
    for old in project.glob("conf*.py"):
        old.unlink()
    for name in secrets:
        (project / name).write_text(SECRET_TEXT, encoding="utf-8")
    config = project / ".sarand.toml"
    if toml:
        config.write_text(toml, encoding="utf-8")
    else:
        config.unlink(missing_ok=True)
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


def _reference(tmp_path: Path) -> Path:
    done = _run(tmp_path, _project(tmp_path, ()), "-f", "json", "-o", "ref.json")
    assert done.returncode == 0, done.stderr
    return tmp_path / "out" / "ref.json"


def _compare(
    tmp_path: Path,
    reference: Path,
    project: Path,
    name: str,
    *extra: str,
    policy: str = "new",
) -> subprocess.CompletedProcess[str]:
    return _run(
        tmp_path,
        project,
        "--baseline",
        str(reference),
        "--baseline-gate",
        policy,
        "-f",
        "json",
        "-o",
        name,
        *extra,
    )


def _gate(tmp_path: Path, name: str) -> dict:
    payload = json.loads((tmp_path / "out" / name).read_text(encoding="utf-8"))
    return payload["baseline"]["gate"]


def _waiver(scope: str, target: str, expires: date, covers: int = 0) -> str:
    today = date.today()
    lines = [
        "[[waivers]]",
        f'{scope} = "{target}"',
        'reason = "accepted for the test"',
        'owner = "tester"',
        f"created = {today.isoformat()}",
        f"expires = {expires.isoformat()}",
    ]
    if covers:
        lines.append(f"covers = {covers}")
    return "\n".join(lines) + "\n"


def _first_failure(tmp_path: Path, reference: Path, secrets: tuple[str, ...]) -> dict:
    """The failed item a plain `new` gate reports, to learn its id and family."""
    project = _project(tmp_path, secrets)
    done = _compare(tmp_path, reference, project, "probe.json")
    assert done.returncode == 3, done.stderr
    return _gate(tmp_path, "probe.json")["failed_on"][0]


def test_an_id_waiver_turns_the_failure_into_a_pass_and_stays_visible(
    tmp_path: Path,
) -> None:
    reference = _reference(tmp_path)
    item = _first_failure(tmp_path, reference, ("conf.py",))
    toml = _waiver("id", item["id"], date.today() + timedelta(days=30))
    project = _project(tmp_path, ("conf.py",), toml)
    done = _compare(tmp_path, reference, project, "w.json")
    assert done.returncode == 0, (done.stdout, done.stderr)
    assert "Gate    : passed (policy new), 1 waived" in done.stdout
    assert "waived by #1, tester" in done.stdout
    gate = _gate(tmp_path, "w.json")
    assert gate["verdict"] == "pass" and gate["failed_on"] == []
    assert gate["waived"][0]["id"] == item["id"]
    assert gate["waived"][0]["waiver"]["reason"] == "accepted for the test"


def test_the_waiver_reaches_markdown_and_text(tmp_path: Path) -> None:
    reference = _reference(tmp_path)
    item = _first_failure(tmp_path, reference, ("conf.py",))
    toml = _waiver("id", item["id"], date.today() + timedelta(days=30))
    project = _project(tmp_path, ("conf.py",), toml)
    outputs = {}
    for fmt, name in (("markdown", "w.md"), ("text", "w.txt")):
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
        assert done.returncode == 0, done.stderr
        outputs[fmt] = (tmp_path / "out" / name).read_text(encoding="utf-8")
    assert (
        "1 waived" in outputs["markdown"]
        and "| waived | secrets |" in outputs["markdown"]
    )
    assert "accepted for the test" in outputs["markdown"]
    assert "1 waived" in outputs["text"]


def test_an_expired_waiver_does_not_apply_and_the_gate_fails(tmp_path: Path) -> None:
    reference = _reference(tmp_path)
    item = _first_failure(tmp_path, reference, ("conf.py",))
    # created today cannot expire before today, so the waiver is created in the past
    # by hand: the expiry is yesterday and the creation date a day before it.
    # waiver نمی‌تواند پیش از امروز منقضی شود مگر ایجادش در گذشته باشد.
    today = date.today()
    toml = (
        "[[waivers]]\n"
        f'id = "{item["id"]}"\n'
        'reason = "accepted for the test"\nowner = "tester"\n'
        f"created = {(today - timedelta(days=5)).isoformat()}\n"
        f"expires = {(today - timedelta(days=1)).isoformat()}\n"
    )
    project = _project(tmp_path, ("conf.py",), toml)
    done = _compare(tmp_path, reference, project, "e.json")
    assert done.returncode == 3, done.stderr
    assert "Waivers : 1 expired" in done.stdout
    assert _gate(tmp_path, "e.json")["waivers"]["expired"][0]["matches"] == 1


def test_a_rule_waiver_that_covers_less_than_what_matches_applies_to_none(
    tmp_path: Path,
) -> None:
    reference = _reference(tmp_path)
    item = _first_failure(tmp_path, reference, ("conf.py", "conf2.py"))
    rule = f"{item['class']}:{item['family']}"
    toml = _waiver("rule", rule, date.today() + timedelta(days=30), covers=1)
    project = _project(tmp_path, ("conf.py", "conf2.py"), toml)
    done = _compare(tmp_path, reference, project, "r.json")
    assert done.returncode == 3, done.stderr
    assert "Waivers : 1 exceeded" in done.stdout
    gate = _gate(tmp_path, "r.json")
    assert len(gate["failed_on"]) == 2 and gate["waived"] == []
    # declaring the real number makes it apply
    toml2 = _waiver("rule", rule, date.today() + timedelta(days=30), covers=2)
    project = _project(tmp_path, ("conf.py", "conf2.py"), toml2)
    done = _compare(tmp_path, reference, project, "r2.json")
    assert done.returncode == 0, done.stderr
    assert len(_gate(tmp_path, "r2.json")["waived"]) == 2


def test_a_waiver_that_matches_nothing_is_listed_as_unused(tmp_path: Path) -> None:
    reference = _reference(tmp_path)
    toml = _waiver(
        "id", "hardcoded_secrets:000000000000", date.today() + timedelta(days=30)
    )
    project = _project(tmp_path, (), toml)
    done = _compare(tmp_path, reference, project, "u.json")
    assert done.returncode == 0, done.stderr
    assert "Waivers : 1 unused" in done.stdout
    assert _gate(tmp_path, "u.json")["waivers"]["unused"][0]["number"] == 1


def test_an_invalid_waiver_file_is_an_error_only_when_a_gate_is_on(
    tmp_path: Path,
) -> None:
    reference = _reference(tmp_path)
    project = _project(tmp_path, ("conf.py",), "[[waivers]]\nbad = 1\n")
    (tmp_path / "out" / "x.json").unlink(missing_ok=True)
    gated = _compare(tmp_path, reference, project, "x.json")
    assert gated.returncode == 1
    assert not (tmp_path / "out" / "x.json").exists()
    never = _compare(tmp_path, reference, project, "y.json", policy="never")
    assert never.returncode == 0, never.stderr
    plain = _run(tmp_path, project, "-f", "json", "-o", "z.json")
    assert plain.returncode == 0, plain.stderr
