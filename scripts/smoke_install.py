#!/usr/bin/env python3
"""Fresh-install smoke test: install the built wheel into a brand-new
virtual environment and use it.

Why it exists: the normal CI job installs the wheel into an environment
that already has every development dependency, so a runtime dependency
missing from `pyproject.toml` stays invisible (that is how `PyYAML` was
once used but undeclared). Here only what the wheel itself declares is
installed. The test then checks that

1. `sarand --version` reports exactly the version in pyproject.toml,
2. `sarand --doctor` exits cleanly, and
3. a scan of a tiny Helm chart works end to end (this path imports
   `yaml`, so it fails if PyYAML is not a declared dependency).

Usage: python3 scripts/smoke_install.py [WHEEL_DIR]   (default: dist)

تست دود نصب تازه: wheel ساخته‌شده را در یک virtualenv کاملاً تازه نصب و
استفاده می‌کند تا وابستگیِ اعلام‌نشده در `pyproject.toml` پنهان نماند.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def project_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    if match is None:
        raise SystemExit("no version in pyproject.toml")
    return match.group(1)


def find_wheel(wheel_dir: Path) -> Path:
    wheels = sorted(wheel_dir.glob("sarand-*.whl"))
    if not wheels:
        raise SystemExit(f"no sarand wheel in {wheel_dir}")
    return wheels[-1]


def venv_python(env_dir: Path) -> Path:
    sub = "Scripts" if os.name == "nt" else "bin"
    exe = "python.exe" if os.name == "nt" else "python"
    return env_dir / sub / exe


def run(python: Path, *args: str, cwd: Path | None = None) -> str:
    done = subprocess.run(
        [str(python), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        print(done.stdout)
        print(done.stderr, file=sys.stderr)
        raise SystemExit(f"FAILED: {' '.join(args)} (exit {done.returncode})")
    return done.stdout


def make_helm_project(root: Path) -> None:
    (root / "chart" / "templates").mkdir(parents=True)
    (root / "chart" / "Chart.yaml").write_text(
        "apiVersion: v2\nname: demo\nversion: 0.1.0\n", encoding="utf-8"
    )
    (root / "chart" / "templates" / "cm.yaml").write_text(
        "kind: ConfigMap\n", encoding="utf-8"
    )


def main(argv: list[str]) -> None:
    wheel = find_wheel(Path(argv[0] if argv else "dist"))
    expected = project_version()
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        env_dir = base / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(env_dir)
        python = venv_python(env_dir)
        run(python, "-m", "pip", "install", "--quiet", str(wheel))

        out = run(python, "-m", "sarand", "--version").strip()
        if out != f"sarand {expected}":
            raise SystemExit(f"version mismatch: got {out!r}, expected {expected!r}")
        print(f"ok  version {out}")

        run(python, "-m", "sarand", "--doctor")
        print("ok  --doctor exits cleanly")

        project = base / "project"
        project.mkdir()
        make_helm_project(project)
        reports = base / "reports"
        reports.mkdir()
        run(
            python,
            "-m",
            "sarand",
            "-p",
            str(project),
            "-d",
            str(reports),
            "--skip-tests",
            "-o",
            "report.md",
        )
        report = (reports / "report.md").read_text(encoding="utf-8")
        if "### Helm charts" not in report:
            raise SystemExit("scan of the Helm chart did not produce a Helm section")
        print("ok  scan of a Helm chart (imports yaml)")
    print("Fresh-install smoke test passed.")


if __name__ == "__main__":
    main(sys.argv[1:])
