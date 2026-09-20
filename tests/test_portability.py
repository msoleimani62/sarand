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
import sys
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

    assert _resolve_argv(("npm", "test")) == ["npm", "test"]


def test_resolve_argv_resolves_the_executable_through_pathext_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`CreateProcess` only appends .exe, so `npm` (really npm.cmd) must be
    resolved by `shutil.which` first or it is reported "not found"."""
    monkeypatch.setattr(command_module, "os", types.SimpleNamespace(name="nt"))
    seen: list[str] = []

    # One positional argument on purpose: tests all over the suite patch
    # `shutil.which` with a one-argument lambda, and a `path=` keyword here
    # once made every such test raise TypeError on Windows.
    # عمداً فقط یک آرگومان موضعی: تست‌های زیادی `shutil.which` را با یک lambda
    # تک‌آرگومانه patch می‌کنند و یک keyword به نام `path=` یک‌بار باعث شد همه‌ی
    # آن‌ها روی Windows با TypeError بشکنند.
    def fake_which(cmd):
        seen.append(cmd)
        return "C:\\tools\\npm.CMD"

    monkeypatch.setattr(shutil, "which", fake_which)

    assert _resolve_argv(["npm", "test"]) == ["C:\\tools\\npm.CMD", "test"]
    assert seen == ["npm"]

    monkeypatch.setattr(shutil, "which", lambda cmd: None)
    assert _resolve_argv(["ghost", "x"]) == ["ghost", "x"]
    assert _resolve_argv([]) == []


def test_harden_stdio_turns_unencodable_characters_into_replacements() -> None:
    strict = io.TextIOWrapper(
        io.BytesIO(), encoding="cp1252", errors="strict", newline=""
    )
    with pytest.raises(UnicodeEncodeError):
        strict.write("\u2192 \u062a\u0633\u062a")

    raw = io.BytesIO()
    # newline="" so Windows does not turn "\n" into "\r\n" in the expected bytes
    # newline="" تا Windows در بایت‌های مورد انتظار "\n" را به "\r\n" تبدیل نکند
    stream = io.TextIOWrapper(raw, encoding="cp1252", errors="strict", newline="")
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


@pytest.mark.skipif(
    sys.platform == "win32", reason="Windows paths are case-insensitive by design"
)
def test_is_excluded_on_posix_is_case_and_prefix_exact() -> None:
    assert is_excluded(Path("/a/b"), ["/a/b/"]) is True
    assert is_excluded(Path("/a/B"), ["/a/b"]) is False
    assert is_excluded(Path("/a/bc"), ["/a/b"]) is False


_ALLOWED_TO_BRANCH_ON_REAL_TOOLS = {
    # A deliberate integration test: it only does anything if a PDF engine
    # is really installed, and a PDF engine finishes in seconds.
    # یک تست یکپارچگی عمدی: فقط وقتی کاری می‌کند که موتور PDF واقعاً نصب باشد
    # و موتور PDF در چند ثانیه تمام می‌شود.
    "test_pdf_renderer_produces_a_real_pdf_when_engine_available",
}


def test_no_test_branches_on_whether_a_real_tool_is_installed() -> None:
    """`if shutil.which("gradle") is None: assert skipped` runs the REAL tool
    whenever it is installed. On a Windows CI runner that was a real Gradle
    build with a one-hour timeout, and the job ran for six hours. A test
    that wants the "tool missing" path must patch `shutil.which` instead."""
    tests_dir = Path(__file__).resolve().parent
    offenders: list[str] = []
    for path in sorted(tests_dir.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for func in ast.walk(tree):
            if not isinstance(func, ast.FunctionDef):
                continue
            if func.name in _ALLOWED_TO_BRANCH_ON_REAL_TOOLS:
                continue
            for node in ast.walk(func):
                if not isinstance(node, ast.If):
                    continue
                offenders += [
                    f"{path.name}::{func.name}"
                    for sub in ast.walk(node.test)
                    if isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "which"
                    and isinstance(sub.func.value, ast.Name)
                    and sub.func.value.id == "shutil"
                ]

    assert sorted(set(offenders)) == []


def test_reported_entry_points_never_use_native_path_separators() -> None:
    """`str(path.relative_to(root))` gives `src\\main\\groovy` on Windows and
    `src/main/groovy` elsewhere, so the same project produced different
    reports. Entry points are reported with forward slashes: use
    `.as_posix()` (or a literal), never `str(...)`."""
    analyzers_dir = _PACKAGE_ROOT / "analyzers"
    offenders: list[str] = []
    for path in sorted(analyzers_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for func in ast.walk(tree):
            if isinstance(func, ast.FunctionDef) and func.name == "entry_points":
                offenders += [
                    f"{path.name}:{node.lineno}"
                    for node in ast.walk(func)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "str"
                ]

    assert offenders == []


_MAY_MENTION_TMP = {
    # A plain value in a fixture dict; the path is never touched.
    # فقط یک مقدار در dict فیکسچر؛ به آن مسیر هیچ‌وقت دست زده نمی‌شود.
    "test_health.py",
    # This guard names the string it forbids.
    # همین نگهبان رشته‌ای را که ممنوع می‌کند نام می‌برد.
    "test_portability.py",
}


def test_no_test_hardcodes_a_tmp_path() -> None:
    """Windows has no `/tmp`, and `resolve_config` drops scan roots that do
    not exist. Three rounds of Windows CI failures came from tests that
    passed `-r /tmp`; use `tmp_path` / `tempfile` instead."""
    tests_dir = Path(__file__).resolve().parent
    offenders: list[str] = []
    for path in sorted(tests_dir.glob("test_*.py")):
        if path.name in _MAY_MENTION_TMP:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders += [
            f"{path.name}:{node.lineno}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.startswith("/tmp")
        ]

    assert offenders == []
