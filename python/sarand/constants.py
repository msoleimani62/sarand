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
        ".sarand-cache",
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
        ".kts",
        ".xml",
        ".gradle",
        ".properties",
        ".lua",
        ".rockspec",
        ".rb",
        ".gemspec",
        ".php",
        ".dart",
        ".css",
        ".scss",
        ".less",
        ".zig",
        ".swift",
        ".sql",
        ".cs",
        ".r",
        ".pl",
        ".pm",
        ".jl",
        ".m",
        ".mm",
        ".groovy",
        ".ps1",
        ".psm1",
        ".psd1",
        ".nix",
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
    ".kts": "kotlin",
    ".xml": "xml",
    ".gradle": "groovy",
    ".lua": "lua",
    ".rockspec": "lua",
    ".rb": "ruby",
    ".gemspec": "ruby",
    ".php": "php",
    ".dart": "dart",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".zig": "zig",
    ".swift": "swift",
    ".sql": "sql",
    ".cs": "csharp",
    ".r": "r",
    ".pl": "perl",
    ".pm": "perl",
    ".jl": "julia",
    ".m": "objectivec",
    ".mm": "objectivec",
    ".groovy": "groovy",
    ".ps1": "powershell",
    ".psm1": "powershell",
    ".psd1": "powershell",
    ".nix": "nix",
}

# Diagnostics are recognised by the SHAPE of a line, not by a bare substring
# (AGENTS.md 5.68). A substring match listed syft's healthy "0 exception(s)
# applied" as an error and made the report claim "compilation or lint errors"
# while ruff, mypy and clippy all passed. Errors are only extracted from a
# command that exited non-zero (utils/command.py), so these patterns can be
# permissive about *which* tool printed the line.
# تشخیص diagnostic بر اساس «شکل خط» است، نه substring خالی (AGENTS.md 5.68).
# خطا فقط از دستوری استخراج می‌شود که با کد غیرصفر تمام شده.
_ERROR_COLON = r"(?:^|[:\s])(?i:error)(?:\[[^\]\s]+\])?:"
WARNING_LINE_PATTERNS: tuple[str, ...] = (
    r"(?:^|[:\s])(?i:warning)(?:\[[^\]\s]+\])?:",
    r"\b(?:Deprecation|PendingDeprecation|Future|User|Runtime)Warning:",
)
ERROR_LINE_PATTERNS: tuple[str, ...] = (
    _ERROR_COLON,
    r"^Traceback \(most recent call last\)",
    r"^(?:\w+\.)*\w*(?:Error|Exception):",
    r"\bpanicked at\b",
    r"^(?:FAILED|ERROR)\b",
    r"^npm ERR!",
    r"^(?:--- )?FAIL\b",
    r"\btest result: FAILED\b",
    r"\b[1-9]\d* failed\b",
)

# Patterns are regexes, matched per line over the output of FAILED checks only.
# الگوها regex هستند و فقط روی خروجی چک‌های شکست‌خورده خط‌به‌خط اعمال می‌شوند.
KNOWN_ISSUE_PATTERNS: list[tuple[str, str]] = [
    (r"Failed to parse", "One or more source files contain syntax errors."),
    (r"ModuleNotFoundError", "A required Python dependency is missing."),
    (_ERROR_COLON, "Compilation or lint errors were detected."),
]

# A dependency-audit tool can exit 0 although it could not finish (cargo audit
# printed "couldn't check if the package is yanked: ... timeframe" three times
# and still passed). Such a result is INCONCLUSIVE: neither PASS nor FAIL.
# Detection is limited to audit-style kinds and to exit code 0: a failing exit
# is never downgraded, because a tool that found real vulnerabilities may
# also print a network warning.
# ابزار audit می‌تواند با کد ۰ تمام شود بی‌آنکه کارش را تمام کرده باشد.
# چنین نتیجه‌ای INCONCLUSIVE است. شناسایی فقط برای نوع‌های audit و فقط با
# کد خروج ۰ انجام می‌شود؛ شکست هرگز تنزل داده نمی‌شود.
INCONCLUSIVE_KIND_MARKERS: tuple[str, ...] = ("audit", "vuln")
INCONCLUSIVE_SIGNATURES: tuple[tuple[str, str], ...] = (
    (
        r"couldn't check if the package is yanked",
        "the yanked-crate check could not complete (network)",
    ),
    (
        r"(?i:couldn't fetch advisory database|failed to fetch advisory database)",
        "the advisory database could not be fetched",
    ),
    (
        r"(?i:temporary failure in name resolution|could not resolve host)",
        "the network was unreachable",
    ),
    (
        (
            r"(?i:max retries exceeded|failed to establish a new connection"
            r"|connection timed out|read timed out)"
        ),
        "the audit service could not be reached",
    ),
    (
        r"\b(?:ETIMEDOUT|ENOTFOUND|EAI_AGAIN|ECONNREFUSED)\b",
        "the audit service could not be reached",
    ),
    (
        r"(?i:error sending request for url)",
        "the audit service could not be reached",
    ),
)

# TODO scan: places skipped by default (AGENTS.md 5.68). Directory names are
# compared case-insensitively against every directory segment of the path;
# suffixes against the file name. Extra project globs live in `.sarand.toml`
# `[todo] exclude_globs`. The report states how many markers were suppressed.
# مکان‌هایی که اسکن TODO به‌طور پیش‌فرض رد می‌کند.
TODO_EXCLUDE_DIRS: tuple[str, ...] = (
    "golden",
    "fixtures",
    "snapshots",
    "__snapshots__",
)
TODO_EXCLUDE_SUFFIXES: tuple[str, ...] = (".md", ".mdx", ".rst")

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
    "settings.gradle": ("Java/Kotlin", "application", "gradle"),
    "settings.gradle.kts": ("Java/Kotlin", "application", "gradle"),
    "Makefile": ("Generic", "unknown", "make"),
    "init.lua": ("Lua", "module/library", "none"),
    "Gemfile": ("Ruby", "application/gem", "bundler"),
    "composer.json": ("PHP", "application/package", "composer"),
    "pubspec.yaml": ("Dart/Flutter", "application/package", "pub"),
    "tsconfig.json": ("TypeScript", "application/library", "npm/tsc"),
    "build.zig": ("Zig", "binary/library", "zig"),
    "Package.swift": ("Swift", "application/library", "swift package manager"),
    "DESCRIPTION": ("R", "package", "renv (optional)"),
    "cpanfile": ("Perl", "application/module", "cpanm"),
    "Project.toml": ("Julia", "package", "Pkg"),
    "stack.yaml": ("Haskell", "application/library", "stack"),
    "cabal.project": ("Haskell", "application/library", "cabal"),
    "mix.exs": ("Elixir", "application/library", "mix"),
    "rebar.config": ("Erlang", "application/library", "rebar3"),
    "build.sbt": ("Scala", "application/library", "sbt"),
}

ENTRY_POINT_CANDIDATES: dict[str, tuple[str, ...]] = {
    "Rust": ("src/main.rs", "src/lib.rs"),
    "Python": ("src/main.py", "main.py", "cli.py", "__main__.py", "app.py"),
    "Node.js": ("index.js", "src/index.js", "server.js", "src/index.ts"),
    "Go": ("main.go", "cmd/main.go"),
    "Java/Kotlin": ("src/main/java", "src/main/kotlin"),
    "C/C++": ("src/main.cpp", "src/main.c", "main.cpp", "main.c"),
    "Lua": ("init.lua", "main.lua", "app.lua", "src/main.lua", "src/init.lua"),
    "Ruby": ("main.rb", "app.rb", "lib/main.rb"),
    "PHP": ("public/index.php", "index.php", "src/index.php"),
    "Dart/Flutter": ("lib/main.dart", "bin/main.dart"),
    "TypeScript": ("src/index.ts", "src/main.ts", "index.ts"),
    "Zig": ("src/main.zig", "build.zig"),
    "Swift": ("Sources/main.swift", "main.swift"),
    "R": ("R/main.R", "main.R", "app.R"),
    "Perl": ("bin/app.pl", "script/app.pl", "main.pl"),
    "Julia": ("src/main.jl", "main.jl"),
    "Haskell": ("app/Main.hs", "Main.hs", "src/Main.hs"),
    "Elixir": ("mix.exs", "config/config.exs"),
    "Erlang": ("rebar.config", "src"),
    "Scala": ("build.sbt", "src/main/scala"),
}

# Filename patterns that must NEVER be embedded in a generated report,
# regardless of extension (AGENTS.md §4.10). Matched against the
# lowercased filename only, not the full path -- a file named
# "id_rsa" three directories deep is exactly as dangerous as one at
# the root.
# الگوهای نام فایلی که هرگز نباید در گزارش تولیدشده درج شوند، فارغ از
# پسوند (§4.10 در AGENTS.md). فقط با نام فایل (حروف‌کوچک‌شده) مطابقت
# داده می‌شود، نه کل مسیر -- فایلی به نام "id_rsa" در سه پوشه‌ی پایین‌تر
# دقیقاً به‌همان اندازه‌ی نمونه‌ی ریشه خطرناک است.
SECRET_FILENAME_PATTERNS: tuple[str, ...] = (
    r"^id_rsa$",
    r"^id_dsa$",
    r"^id_ecdsa$",
    r"^id_ed25519$",
    r"\.pem$",
    r"\.key$",
    r"\.pfx$",
    r"\.p12$",
    r"^\.env($|\..+$)",
    r"service.?account.*\.json$",
    r"credentials.*\.json$",
    r"^\.npmrc$",
    r"^\.netrc$",
    r"^local\.properties$",
    r"\.jks$",
    r"\.keystore$",
    r"^google-services\.json$",
    # Added in 0.6.20 (AGENTS.md 5.67). Measured: secrets.{yaml,json,toml},
    # *-adminsdk-*.json, kubeconfig.yaml, *.tfvars.json and wp-config.php were
    # embedded in reports because their extension is essential and no pattern
    # matched; the rest never reach the report but are listed for the day the
    # essential-extension set grows.
    # اضافه‌شده در 0.6.20 (AGENTS.md 5.67). اندازه‌گیری: فایل‌های
    # secrets.{yaml,json,toml}، *-adminsdk-*.json، kubeconfig.yaml،
    # *.tfvars.json و wp-config.php در گزارش embed می‌شدند.
    r"^\.pypirc$",
    r"^\.git-credentials$",
    r"^credentials$",
    r"^\.dockercfg$",
    r"\.tfstate(\.backup)?$",
    r"\.tfvars(\.json)?$",
    r"^\.htpasswd$",
    r"^kube[-_]?config(\.ya?ml)?$",
    r"^secrets?\.(ya?ml|json|toml)$",
    r"\.p8$",
    r"\.ppk$",
    r"^id_(ecdsa|ed25519)_sk$",
    r"-adminsdk-.*\.json$",
    r"\.kdbx$",
    r"\.ovpn$",
    r"^wp-config\.php$",
)

# Path-suffix patterns for credential files whose bare name is too generic to
# match on its own (`config`, `config.json`, `credentials` inside a dotdir).
# Matched against the POSIX-style project-relative path.
# الگوهای پسوند مسیر برای فایل‌های اعتبارنامه‌ای که نام خالی‌شان بیش‌ازحد
# عمومی است؛ روی مسیر نسبی به‌سبک POSIX اعمال می‌شود.
SECRET_PATH_PATTERNS: tuple[str, ...] = (
    r"(^|/)\.docker/config\.json$",
    r"(^|/)\.aws/credentials$",
    r"(^|/)\.kube/config$",
    r"(^|/)\.gnupg/",
)
