"""The READMEs must not drift from the real command-line options.

`README.md` (English) and `README.fa.md` (Persian) document every option
by hand. This test pins them to the argparse definitions in the source:
every long option must be documented in both files, and neither file may
mention a long option that no parser defines (a real case: the old README
documented `--max-file-size`, which never existed).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PARSER_SOURCES = (
    _ROOT / "python" / "sarand" / "cli.py",
    _ROOT / "python" / "sarand" / "rc" / "command.py",
    _ROOT / "python" / "sarand" / "device_report" / "config.py",
)
_READMES = (_ROOT / "README.md", _ROOT / "README.fa.md")
# Long options that belong to other tools and appear in install/dev
# instructions, or that argparse adds on its own.
# گزینه‌های بلندی که مال ابزارهای دیگرند (pip، maturin) یا argparse خودش
# اضافه می‌کند.
_NOT_ECOSYSTEMS = {"Supply chain", "PDF export"}
_FOREIGN_OPTIONS = {"--break-system-packages", "--user", "--release", "--help"}


def _defined_long_options() -> set[str]:
    options: set[str] = set()
    for source in _PARSER_SOURCES:
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == (
                "add_argument"
            ):
                options.update(
                    arg.value
                    for arg in node.args
                    if isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and arg.value.startswith("--")
                )
    return options


def _documented_long_options(readme: Path) -> set[str]:
    text = readme.read_text(encoding="utf-8")
    return set(re.findall(r"(?<![\w-])(--[a-z][a-z0-9-]*)", text))


def test_the_parsers_define_options() -> None:
    defined = _defined_long_options()

    assert {"--full", "--quality", "--security", "--doctor", "--source"} <= defined
    assert {"--summary-only", "--expand-aggregates"} <= defined


def test_every_option_is_documented_in_both_readmes() -> None:
    defined = _defined_long_options()

    for readme in _READMES:
        missing = sorted(defined - _documented_long_options(readme))
        assert missing == [], f"{readme.name} does not document: {missing}"


def test_readmes_mention_no_option_that_does_not_exist() -> None:
    known = _defined_long_options() | _FOREIGN_OPTIONS

    for readme in _READMES:
        unknown = sorted(_documented_long_options(readme) - known)
        assert unknown == [], f"{readme.name} mentions unknown options: {unknown}"


def test_the_readmes_link_each_other_and_their_assets() -> None:
    english, persian = (readme.read_text(encoding="utf-8") for readme in _READMES)

    assert "README.fa.md" in english
    assert "README.md" in persian
    for text in (english, persian):
        for target in ("assets/banner.svg", "LICENSE", "docs/RC-AI-RECEIVER.md"):
            assert target in text
            assert (_ROOT / target).is_file(), f"{target} is linked but missing"


def test_every_ecosystem_sarand_can_drive_is_listed_in_both_readmes() -> None:
    from sarand.core.doctor import detection_only_catalog, tool_catalog

    categories = {category for category, _bin, _hint, _use in tool_catalog()}
    categories |= {category for category, _name, _what in detection_only_catalog()}
    for readme in _READMES:
        text = readme.read_text(encoding="utf-8")
        missing = sorted(
            category
            for category in categories - _NOT_ECOSYSTEMS
            if f"| {category} |" not in text
        )
        assert missing == [], f"{readme.name} does not list: {missing}"


def test_the_readmes_link_the_coverage_matrix() -> None:
    for readme in _READMES:
        assert "docs/COVERAGE.md" in readme.read_text(encoding="utf-8")
    assert (_ROOT / "docs" / "COVERAGE.md").is_file()
