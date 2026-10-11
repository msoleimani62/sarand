"""The distribution is `sarand-cli` (AGENTS.md section 5.63): the PyPI name
`sarand` belongs to an unrelated bioinformatics tool, so the package is
published as `sarand-cli`. The import package (`sarand`) and the command
(`sarand`) do not change. This module pins the places that must agree on the
name.

توزیع بسته `sarand-cli` است (بخش ۵.۶۳): نام `sarand` در PyPI مال ابزاری بی‌ربط
است. بسته‌ی import و دستور `sarand` می‌مانند.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _text(relative: str) -> str:
    return (_ROOT / relative).read_text(encoding="utf-8")


def test_pyproject_names_the_distribution_sarand_cli() -> None:
    assert re.search(r'(?m)^name = "sarand-cli"$', _text("pyproject.toml"))


def test_the_command_and_the_import_package_keep_the_name_sarand() -> None:
    pyproject = _text("pyproject.toml")
    assert re.search(r'(?m)^sarand = "sarand\.', pyproject)
    assert 'module-name = "sarand._core"' in pyproject
    assert (_ROOT / "python" / "sarand" / "__init__.py").is_file()


def test_runtime_lookups_use_the_distribution_name() -> None:
    assert 'metadata.version("sarand-cli")' in _text("python/sarand/__init__.py")
    assert 'metadata.distribution("sarand-cli")' in _text(
        "python/sarand/utils/installation.py"
    )


def test_the_pipx_app_is_named_sarand_cli_in_every_hint_and_doc() -> None:
    stale = []
    for relative in (
        "README.md",
        "README.fa.md",
        "docs/PLUGINS.md",
        "docs/PLUGINS.fa.md",
        "python/sarand/core/doctor.py",
        "python/sarand/renderers/pdf.py",
    ):
        for match in re.finditer(
            r"pipx (?:inject|uninstall) sarand\b(?!-)", _text(relative)
        ):
            stale.append(f"{relative}: {match.group(0)}")
    assert stale == []


def test_the_readmes_say_this_is_not_the_bioinformatics_tool() -> None:
    assert "github.com/beiko-lab/sarand" in _text("README.md")
    assert "github.com/beiko-lab/sarand" in _text("README.fa.md")
