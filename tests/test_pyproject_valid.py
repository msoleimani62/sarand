"""`pyproject.toml` must be valid TOML with the metadata PyPI shows (AGENTS.md
section 5.63). A duplicated `[project.urls]` table once made the file
unparseable (ruff, maturin and pip all refuse it) while every regex-based test
still passed, so this test parses the file for real.

`pyproject.toml` باید TOML معتبر باشد؛ این تست آن را واقعاً parse می‌کند.
"""

from __future__ import annotations

from pathlib import Path

try:  # tomllib exists from Python 3.11; the 3.10 CI job skips this test.
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _load() -> dict:  # type: ignore[type-arg]
    assert tomllib is not None
    with _PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)


def test_pyproject_parses_and_names_the_distribution() -> None:
    if tomllib is None:
        return
    project = _load()["project"]
    assert project["name"] == "sarand-cli"
    assert project["scripts"]["sarand"].startswith("sarand.")


def test_the_project_urls_table_has_the_links_pypi_shows() -> None:
    if tomllib is None:
        return
    urls = _load()["project"]["urls"]
    for key in ("Homepage", "Repository", "Changelog", "Issues"):
        assert urls[key].startswith("https://github.com/msoleimani62/sarand")
