"""PyPI readiness (AGENTS.md section 5.62): `README.md` is the package's long
description, and PyPI shows it away from the repository, so a relative link or
image breaks there. Links are absolute and every one that points into this
repository must name a file or directory that exists. CI also runs
`twine check --strict` on the built wheel and sdist.

آمادگی PyPI (بخش ۵.۶۲): README.md توضیح بلند بسته است و PyPI آن را بیرون از
مخزن نشان می‌دهد؛ پس لینک و تصویر نسبی آنجا خراب می‌شود.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_README = _ROOT / "README.md"
_REPO = "https://github.com/msoleimani62/sarand"
_RAW = "https://raw.githubusercontent.com/msoleimani62/sarand"
_REFERENCE = (
    re.compile(r"\]\(([^)\s]+)\)"),
    re.compile(r'(?:href|src)="([^"]+)"'),
)
_EXTERNAL = ("http://", "https://", "#", "mailto:", "data:")


def _references() -> list[str]:
    text = _README.read_text(encoding="utf-8")
    return [m.group(1) for pattern in _REFERENCE for m in pattern.finditer(text)]


def test_readme_has_no_relative_links_or_images() -> None:
    relative = [r for r in _references() if not r.startswith(_EXTERNAL)]
    assert relative == [], f"relative references break on PyPI: {relative}"


def test_links_into_this_repository_name_something_that_exists() -> None:
    checked = 0
    for reference in _references():
        match = re.match(
            rf"(?:{re.escape(_REPO)}/(?:blob|tree)|{re.escape(_RAW)})/main/([^#?]+)",
            reference,
        )
        if match is None:
            continue
        checked += 1
        target = _ROOT / match.group(1)
        assert target.exists(), f"{reference} points at a missing path"
    assert checked >= 8, "the README should link its docs, license and banner"


def test_ci_checks_the_package_metadata_with_twine() -> None:
    ci = (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "twine check --strict" in ci
    assert "maturin sdist" in ci
