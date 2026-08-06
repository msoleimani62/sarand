"""Project-wide constants for sarand."""

from __future__ import annotations

from pathlib import Path

# There is no fixed default project. sarand always analyses the
# current working directory unless --project is given.
# هیچ پروژه پیش‌فرض ثابتی وجود ندارد. sarand همیشه دایرکتوری فعلی را
# تحلیل می‌کند مگر اینکه --project داده شود.

DEFAULT_OUTPUT_DIR = Path.home() / "Downloads"

MAX_TREE_DEPTH = 8
MAX_TREE_ENTRIES = 100
MAX_FILE_SIZE = 2 * 1024 * 1024
MAX_ISSUE_ROWS = 500
HASH_MAX_BYTES = 512 * 1024
MAX_HASH_FILES = 5000

IGNORE_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".cache",
        "target",
        "build",
        "dist",
        "node_modules",
        ".tox",
        ".eggs",
        ".idea",
        ".vscode",
    }
)

ESSENTIAL_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".rs",
        ".toml",
        ".json",
        ".yaml",
        ".yml",
        ".md",
        ".txt",
        ".lock",
        ".sh",
        ".bash",
        ".zsh",
        ".ini",
        ".cfg",
        ".conf",
        ".proto",
        ".c",
        ".h",
        ".cpp",
        ".hpp",
        ".go",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".java",
        ".kt",
    }
)

LANG_MAP: dict[str, str] = {
    ".py": "python",
    ".rs": "rust",
    ".toml": "toml",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".proto": "protobuf",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".go": "go",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "jsx",
    ".tsx": "tsx",
    ".java": "java",
    ".kt": "kotlin",
}

WARNING_PATTERNS: tuple[str, ...] = ("warning:", "warning[", "deprecated", "unused")
ERROR_PATTERNS: tuple[str, ...] = ("error:", "failed", "traceback", "panic", "exception")

KNOWN_ISSUE_PATTERNS: list[tuple[str, str]] = [
    ("Failed to parse", "One or more source files contain syntax errors."),
    ("ModuleNotFoundError", "A required Python dependency is missing."),
    ("error:", "Compilation or lint errors were detected."),
]

TODO_PATTERNS: tuple[str, ...] = ("TODO", "FIXME", "BUG", "HACK", "SAFETY", "XXX")

AI_NOTICE = (
    "This report is generated for AI analysis and contains project metadata, "
    "test results and source files."
)

DEFAULT_CMD_TIMEOUT = 300
LONG_CMD_TIMEOUT = 3600

# Marker files used for project/language discovery, in priority order.
# فایل‌های نشانگر برای تشخیص پروژه/زبان، به ترتیب اولویت.
PROJECT_MARKERS: dict[str, tuple[str, str, str]] = {
    "Cargo.toml": ("Rust", "binary/library", "cargo"),
    "pyproject.toml": ("Python", "package", "pip/poetry/uv"),
    "setup.py": ("Python", "package", "setuptools"),
    "setup.cfg": ("Python", "package", "setuptools"),
    "requirements.txt": ("Python", "application", "pip"),
    "package.json": ("Node.js", "application", "npm"),
    "go.mod": ("Go", "module", "go"),
    "CMakeLists.txt": ("C/C++", "binary/library", "cmake"),
    "pom.xml": ("Java", "application", "maven"),
    "build.gradle": ("Java/Kotlin", "application", "gradle"),
    "build.gradle.kts": ("Java/Kotlin", "application", "gradle"),
    "Makefile": ("Generic", "unknown", "make"),
}

ENTRY_POINT_CANDIDATES: dict[str, tuple[str, ...]] = {
    "Rust": ("src/main.rs", "src/lib.rs"),
    "Python": ("src/main.py", "main.py", "cli.py", "__main__.py", "app.py"),
    "Node.js": ("index.js", "src/index.js", "server.js", "src/index.ts"),
    "Go": ("main.go", "cmd/main.go"),
    "Java/Kotlin": ("src/main/java", "src/main/kotlin"),
}
