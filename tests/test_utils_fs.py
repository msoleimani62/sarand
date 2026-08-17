from pathlib import Path

from sarand.utils.fs import (
    default_output_name,
    human_size,
    is_binary,
    safe_relative,
    slugify_project_name,
)


def test_human_size_boundaries() -> None:
    assert human_size(0) == "0.0 B"
    assert human_size(1023) == "1023.0 B"
    assert human_size(1024) == "1.0 KiB"
    assert human_size(1024**2) == "1.0 MiB"
    assert human_size(1024**3) == "1.0 GiB"
    assert human_size(1024**4) == "1.0 TiB"


def test_human_size_fractional_values() -> None:
    assert human_size(1536) == "1.5 KiB"
    assert human_size(1024**2 + 512 * 1024) == "1.5 MiB"


def test_is_binary_detects_text(tmp_path: Path) -> None:
    path = tmp_path / "text.txt"
    path.write_text("hello\nworld\n", encoding="utf-8")

    assert is_binary(path) is False


def test_is_binary_detects_nul_byte(tmp_path: Path) -> None:
    path = tmp_path / "binary.bin"
    path.write_bytes(b"hello\x00world")

    assert is_binary(path) is True


def test_is_binary_respects_sample_size(tmp_path: Path) -> None:
    path = tmp_path / "late-binary.bin"
    path.write_bytes(b"a" * 32 + b"\x00" + b"b" * 32)

    assert is_binary(path, sample_size=32) is False
    assert is_binary(path, sample_size=33) is True


def test_is_binary_empty_file_is_text(tmp_path: Path) -> None:
    path = tmp_path / "empty"
    path.write_bytes(b"")

    assert is_binary(path) is False


def test_is_binary_unreadable_path_is_binary(tmp_path: Path) -> None:
    path = tmp_path / "missing"

    assert is_binary(path) is True


def test_safe_relative_returns_relative_path() -> None:
    root = Path("/project")
    path = root / "src" / "main.py"

    assert safe_relative(path, root) == Path("src/main.py")


def test_safe_relative_returns_original_path_outside_root() -> None:
    root = Path("/project")
    path = Path("/other/main.py")

    assert safe_relative(path, root) == path


def test_slugify_project_name() -> None:
    assert slugify_project_name("My Project") == "my-project"
    assert slugify_project_name("my_project") == "my_project"
    assert slugify_project_name("My.Project-2") == "my.project-2"


def test_slugify_project_name_collapses_separators() -> None:
    assert slugify_project_name("  My   Project---Name  ") == "my-project-name"


def test_slugify_project_name_removes_unsafe_characters() -> None:
    assert (
        slugify_project_name("project/path:name@example.com")
        == "project-path-name-example.com"
    )


def test_slugify_project_name_falls_back_for_empty_input() -> None:
    assert slugify_project_name("") == "project"
    assert slugify_project_name("...") == "project"
    assert slugify_project_name("---") == "project"


def test_default_output_name_uses_project_and_format(tmp_path: Path) -> None:
    project = tmp_path / "My Project"

    assert default_output_name(project, "markdown") == "sarand-my-project-report.md"
    assert default_output_name(project, "json") == "sarand-my-project-report.json"
    assert default_output_name(project, "html") == "sarand-my-project-report.html"


def test_default_output_name_uses_md_for_unknown_format(tmp_path: Path) -> None:
    project = tmp_path / "My Project"

    assert default_output_name(project, "unknown") == "sarand-my-project-report.md"
