"""`pyproject.toml` must be valid TOML with the metadata PyPI shows (AGENTS.md
section 5.63). A duplicated `[project.urls]` table once made the file
unparseable (ruff, maturin and pip all refuse it) while every regex-based test
still passed, so this test parses the file for real.

`tomllib` exists from Python 3.11; on 3.10 the same parser is the `tomli`
package, a dependency there. The import follows the project's own idiom (see
`core/components.py`), which mypy understands on every Python version.

`pyproject.toml` باید TOML معتبر باشد؛ این تست آن را واقعاً parse می‌کند.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10: same parser, packaged separately
    import tomli as tomllib

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _load() -> dict[str, Any]:
    with _PYPROJECT.open("rb") as handle:
        data: dict[str, Any] = tomllib.load(handle)
    return data


def test_pyproject_parses_and_names_the_distribution() -> None:
    project = _load()["project"]
    assert project["name"] == "sarand-cli"
    assert project["scripts"]["sarand"].startswith("sarand.")


def test_the_project_urls_table_has_the_links_pypi_shows() -> None:
    urls = _load()["project"]["urls"]
    for key in ("Homepage", "Repository", "Changelog", "Issues"):
        assert urls[key].startswith("https://github.com/msoleimani62/sarand")
