"""Cross-platform contract tests (AGENTS.md §5.13).

sarand must behave the same on Linux, macOS, Windows and Android/Termux.
Most of these run on any OS and pin the *rules* that keep that true:
explicit text encodings, no import-time POSIX-only modules, Windows
executable resolution, stdio that cannot crash on Unicode, and path
comparison that honors the platform's spelling.
"""

from __future__ import annotations

import ast
import io
import ntpath
import shutil
import types
from pathlib import Path

import pytest
import sarand.device_report.walking as walking_module
import sarand.utils.command as command_module
from sarand.device_report.walking import is_excluded
from sarand.utils.command import _resolve_argv
from sarand.utils.stdio import harden_stdio

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "python" / "sarand"
_POSIX_ONLY_MODULES = {
    "pwd",
    "grp",
    "fcntl",
    "termios",
    "tty",
    "resource",
    "syslog",
    "posix",
    "curses",
}
_SUBPROCESS_FUNCTIONS = {"run", "Popen", "check_output", "check_call", "call"}
_TEMPFILE_FUNCTIONS = {"NamedTemporaryFile", "TemporaryFile", "SpooledTemporaryFile"}


def _sources() -> list[Path]:
    if not _PACKAGE_ROOT.is_dir():
        pytest.skip("package source tree not available")
    return sorted(_PACKAGE_ROOT.rglob("*.py"))


def _const_str(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _is_true(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _text_io_without_encoding(tree: ast.AST) -> list[int]:
    """Line numbers of text-mode I/O that relies on the locale's encoding."""
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
        if "encoding" in kwargs:
            continue
        if name in {"read_text", "write_text"}:
            lines.append(node.lineno)
        elif name == "open":
            mode = _const_str(kwargs.get("mode"))
            if isinstance(node.func, ast.Name):  # builtin open(file, mode)
                if mode is None and len(node.args) >= 2:
                    mode = _const_str(node.args[1])
                is_text = mode is None or "b" not in mode
            else:  # path.open(mode)
                if mode is None and node.args:
                    mode = _const_str(node.args[0])
                is_text = mode is not None and "b" not in mode
            if is_text:
                lines.append(node.lineno)
        elif name in _TEMPFILE_FUNCTIONS:
            mode = _const_str(kwargs.get("mode"))
            if mode is not None and "b" not in mode:
                lines.append(node.lineno)
        elif name in _SUBPROCESS_FUNCTIONS and (
            _is_true(kwargs.get("text")) or _is_true(kwargs.get("universal_newlines"))
        ):
            lines.append(node.lineno)
    return lines


def test_text_io_always_names_its_encoding() -> None:
    """Windows (and a C locale) default to a non-UTF-8 encoding: an implicit
    one turns Persian/emoji content into mojibake or a UnicodeEncodeError."""
    offenders: list[str] = []
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders += [
            f"{path.relative_to(_PACKAGE_ROOT)}:{line}"
            for line in _text_io_without_encoding(tree)
        ]

    assert offenders == []


def test_the_encoding_rule_detects_violations() -> None:
    tree = ast.parse(
        "p.read_text()\n"
        "p.write_text('x')\n"
        "open('f')\n"
        "open('f', 'w')\n"
        "p.open('r')\n"
        "tempfile.NamedTemporaryFile(mode='w')\n"
        "subprocess.run(['x'], text=True)\n"
    )
    assert len(_text_io_without_encoding(tree)) == 7

    fine = ast.parse(
        "p.read_text(encoding='utf-8')\n"
        "open('f', 'rb')\n"
        "p.open('rb')\n"
        "open('f', encoding='utf-8')\n"
        "tempfile.NamedTemporaryFile()\n"
        "subprocess.run(['x'], text=True, encoding='utf-8')\n"
    )
    assert _text_io_without_encoding(fine) == []


def test_posix_only_modules_are_never_imported_at_module_level() -> None:
    """`import pwd` at the top of a module is an ImportError on Windows the
    moment anything imports it; inside a function/try it can be handled."""
    offenders: list[str] = []
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            offenders += [
                f"{path.relative_to(_PACKAGE_ROOT)}:{node.lineno} imports {n}"
                for n in names
                if n in _POSIX_ONLY_MODULES
            ]

    assert offenders == []


def test_resolve_argv_leaves_the_command_alone_off_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(command_module, "os", types.SimpleNamespace(name="posix"))

    def must_not_be_called(*args, **kwargs):
        raise AssertionError("shutil.which must not be consulted off Windows")

    monkeypatch.setattr(shutil, "which", must_not_be_called)

    assert _resolve_argv(("npm", "test"), None) == ["npm", "test"]


def test_resolve_argv_resolves_the_executable_through_pathext_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`CreateProcess` only appends .exe, so `npm` (really npm.cmd) must be
    resolved by `shutil.which` first or it is reported "not found"."""
    monkeypatch.setattr(command_module, "os", types.SimpleNamespace(name="nt"))
    seen: dict[str, object] = {}

    def fake_which(cmd, path=None):
        seen["cmd"], seen["path"] = cmd, path
        return "C:\\tools\\npm.CMD"

    monkeypatch.setattr(shutil, "which", fake_which)

    assert _resolve_argv(["npm", "test"], {"PATH": "C:\\tools"}) == [
        "C:\\tools\\npm.CMD",
        "test",
    ]
    assert seen == {"cmd": "npm", "path": "C:\\tools"}

    monkeypatch.setattr(shutil, "which", lambda cmd, path=None: None)
    assert _resolve_argv(["ghost", "x"], None) == ["ghost", "x"]
    assert _resolve_argv([], None) == []


def test_harden_stdio_turns_unencodable_characters_into_replacements() -> None:
    strict = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    with pytest.raises(UnicodeEncodeError):
        strict.write("\u2192 \u062a\u0633\u062a")

    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
    harden_stdio([stream])
    stream.write("\u2192 ok\n")
    stream.flush()

    assert raw.getvalue() == b"? ok\n"


def test_harden_stdio_ignores_streams_it_cannot_reconfigure() -> None:
    closed = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    closed.close()

    harden_stdio([object(), io.StringIO(), closed])


def test_is_excluded_honors_the_platforms_separator_and_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On Windows an exclude typed as `C:\\Users\\Me\\Big` must match paths
    that Python spells with `/` or different case; on POSIX the same
    function is the plain string comparison."""
    monkeypatch.setattr(
        walking_module, "os", types.SimpleNamespace(path=ntpath, sep="\\")
    )

    assert is_excluded(Path("C:/Users/me/big/sub"), ["c:\\users\\ME\\Big"]) is True
    assert is_excluded(Path("C:/Users/me/bigger"), ["c:\\users\\me\\big"]) is False


def test_is_excluded_on_posix_is_case_and_prefix_exact() -> None:
    assert is_excluded(Path("/a/b"), ["/a/b/"]) is True
    assert is_excluded(Path("/a/B"), ["/a/b"]) is False
    assert is_excluded(Path("/a/bc"), ["/a/b"]) is False
