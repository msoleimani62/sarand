"""Which sarand is this, and where did it come from?

Several copies of sarand can exist on one machine at once: a pipx install,
a development virtualenv (`maturin develop`), a pip install. Which one runs
depends on `PATH` order, and an *editable* install records the version it
had when it was installed -- it does not follow `pyproject.toml`. The result
is the confusing situation this module makes visible: `pipx` says it just
installed 0.5.1 while `sarand --version` prints 0.1.5, because the shell ran
a stale development copy that shadows the new one.

هم‌زمان چند نسخه از sarand می‌تواند روی یک ماشین باشد: نصب pipx، یک
virtualenv توسعه (`maturin develop`)، نصب pip. اینکه کدام اجرا شود به ترتیب
`PATH` بستگی دارد، و یک نصب *editable* همان نسخه‌ای را ثبت می‌کند که موقع
نصب داشت -- از `pyproject.toml` پیروی نمی‌کند. نتیجه وضعیت گیج‌کننده‌ای است
که این ماژول آن را آشکار می‌کند: `pipx` می‌گوید تازه 0.5.1 نصب کرده ولی
`sarand --version` عدد 0.1.5 را چاپ می‌کند، چون شل یک نسخه‌ی توسعه‌ی کهنه را
اجرا کرده که روی نسخه‌ی جدید سایه انداخته.
"""

from __future__ import annotations

import json
import os
import re
import sys
import sysconfig
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from sarand.utils.command import run_cmd

_VERSION_IN_PYPROJECT = re.compile(
    r'^\[project\]\s.*?^version\s*=\s*"([^"]+)"', re.MULTILINE | re.DOTALL
)
_EXECUTABLE_NAMES = ("sarand", "sarand.exe")


@dataclass(frozen=True)
class InstallationInfo:
    version: str
    package_dir: Path
    editable: bool
    source_version: str | None

    @property
    def stale(self) -> bool:
        """An editable install whose recorded version differs from the source."""
        return (
            self.editable
            and self.source_version is not None
            and self.source_version != self.version
        )


def _direct_url_says_editable(distribution: metadata.Distribution) -> bool:
    raw = distribution.read_text("direct_url.json")
    if not raw:
        return False
    try:
        data = json.loads(raw)
    except ValueError:
        return False
    return bool(data.get("dir_info", {}).get("editable"))


def _source_pyproject(package_dir: Path) -> Path | None:
    """`<root>/pyproject.toml` when the package is imported from a checkout."""
    candidate = package_dir.parent.parent / "pyproject.toml"
    try:
        text = candidate.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return candidate if 'name = "sarand"' in text else None


def installation_info() -> InstallationInfo:
    package_dir = Path(__file__).resolve().parent.parent
    try:
        distribution = metadata.distribution("sarand")
        version = distribution.version
        editable = _direct_url_says_editable(distribution)
    except metadata.PackageNotFoundError:
        version, editable = "0.0.0+unknown", False

    pyproject = _source_pyproject(package_dir)
    source_version = None
    if pyproject is not None:
        editable = True  # imported straight from a source checkout
        found = _VERSION_IN_PYPROJECT.search(
            pyproject.read_text(encoding="utf-8", errors="replace")
        )
        source_version = found.group(1) if found else None
    return InstallationInfo(version, package_dir, editable, source_version)


def stale_note(info: InstallationInfo) -> str | None:
    """One line explaining a stale editable install, or None."""
    if not info.stale:
        return None
    return (
        f"note: this editable install recorded version {info.version}, but the "
        f"source tree is {info.source_version}. Refresh it with "
        "`maturin develop --release` (or `pip install -e .`)."
    )


def _own_script_dirs() -> set[Path]:
    directories = {Path(sys.executable).parent, Path(sysconfig.get_path("scripts"))}
    return {directory.resolve() for directory in directories if directory.exists()}


def other_sarand_executables() -> list[Path]:
    """`sarand` executables on PATH that belong to a different installation
    than the one running (symlinks are resolved, so pipx's `~/.local/bin`
    link into its own venv counts as the same installation)."""
    own = _own_script_dirs()
    found: list[Path] = []
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        for name in _EXECUTABLE_NAMES:
            candidate = Path(entry) / name
            try:
                if not candidate.is_file():
                    continue
                resolved = candidate.resolve()
            except OSError:
                continue
            if resolved.parent in own or resolved in found:
                continue
            found.append(resolved)
    return found


def probe_version(executable: Path) -> str | None:
    """`X` from `<executable> --version` printing `sarand X`, or None."""
    return_code, output, _ = run_cmd(
        [str(executable), "--version"], cwd=Path.home(), timeout=10
    )
    if return_code != 0:
        return None
    match = re.match(r"\s*sarand\s+(\S+)", output)
    return match.group(1) if match else None
