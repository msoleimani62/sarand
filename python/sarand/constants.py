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

# --- R13-A: failure classification ---------------------------------------
# A failed check is classified from WHAT RAN (the tool) and WHAT IT PRINTED
# (strong signatures), never from a bare "error:" line. The old catch-all that
# turned every `error:` of any failed command into "Compilation or lint errors
# were detected." is gone: on a real report it was produced by cargo audit and
# cargo deny (security tools), not by a compiler or a linter.
# طبقه‌بندی شکست از «چه چیزی اجرا شد» و «چه چاپ کرد» می‌آید، نه از یک خط
# `error:` عمومی. پیام کلی قدیمی حذف شد؛ روی گزارش واقعی از cargo audit و
# cargo deny می‌آمد، نه از کامپایلر یا linter.
FAILURE_COMPILATION = "compilation_failure"
FAILURE_TEST = "test_failure"
FAILURE_LINT = "lint_failure"
FAILURE_SECURITY_TOOL = "security_tool_failure"
FAILURE_SECURITY_FINDING = "security_finding_detected"
FAILURE_CONFIGURATION = "configuration_failure"
FAILURE_DEPENDENCY_POLICY = "dependency_policy_failure"
FAILURE_REPORT_GENERATION = "report_generation_failure"
FAILURE_UNKNOWN_TOOL = "unknown_tool_failure"
# Fixed order: it is the order of the known-issue lines and of the JSON enum.
# `report_generation_failure` is part of the vocabulary; no check result
# produces it today (it is reserved for failures of Sarand's own rendering).
# ترتیب ثابت است. `report_generation_failure` در واژگان هست ولی هیچ نتیجه‌ی چکی
# امروز آن را تولید نمی‌کند (برای شکست رندر خود سرند رزرو شده).
FAILURE_CATEGORIES: tuple[str, ...] = (
    FAILURE_COMPILATION,
    FAILURE_TEST,
    FAILURE_LINT,
    FAILURE_SECURITY_TOOL,
    FAILURE_SECURITY_FINDING,
    FAILURE_CONFIGURATION,
    FAILURE_DEPENDENCY_POLICY,
    FAILURE_REPORT_GENERATION,
    FAILURE_UNKNOWN_TOOL,
)

# Why a check failed, apart from its category (`cause`): the tool exited with
# a code (`exit_code`), or the runner itself could not run it. The runner marks
# the second kind with a sentinel line (utils/command.py), so a real tool exit
# code 124 or 127 is not mistaken for a timeout or a missing tool.
# `cause`: خروج با کد، یا ناتوانی خود runner در اجرا (با خط نشانگر مشخص می‌شود).
CAUSE_EXIT_CODE = "exit_code"
CAUSE_TIMEOUT = "timeout"
CAUSE_TOOL_NOT_FOUND = "tool_not_found"
CAUSE_OS_ERROR = "os_error"
SENTINEL_TIMEOUT = "Command timed out."
SENTINEL_NOT_FOUND = "Command not found:"
SENTINEL_OS_ERROR = "OS error while running command:"
EXECUTION_SENTINELS: tuple[tuple[int, str, str], ...] = (
    (124, SENTINEL_TIMEOUT, CAUSE_TIMEOUT),
    (127, SENTINEL_NOT_FOUND, CAUSE_TOOL_NOT_FOUND),
    (1, SENTINEL_OS_ERROR, CAUSE_OS_ERROR),
)

# Tool kind (lower case, as in CommandResult.kind) -> (default category, what
# the tool checks). The default applies only when no execution cause and no
# stronger signature explains the failure. Security audit-style tools default
# to "tool failure" until a findings signature proves the tool reported findings.
# نوع ابزار -> (دسته‌ی پیش‌فرض، موضوع بررسی). پیش‌فرض فقط وقتی به کار می‌آید که
# علت اجرا یا امضای قوی‌تری شکست را توضیح ندهد.
TOOL_FAILURE_CLASSES: dict[str, tuple[str, str]] = {
    # lint, format and static-analysis tools
    "ruff": (FAILURE_LINT, "Python source"),
    "ruff check": (FAILURE_LINT, "Python source"),
    "ruff format --check": (FAILURE_LINT, "Python formatting"),
    "mypy": (FAILURE_LINT, "Python type checking"),
    "cargo fmt --check": (FAILURE_LINT, "Rust formatting"),
    "cargo fmt/clippy": (FAILURE_LINT, "Rust formatting and lints"),
    "cargo clippy": (FAILURE_LINT, "Rust lints"),
    "actionlint": (FAILURE_LINT, "GitHub Actions workflow files"),
    "yamllint": (FAILURE_LINT, "YAML files"),
    "markdownlint": (FAILURE_LINT, "Markdown documentation"),
    "taplo lint": (FAILURE_LINT, "TOML files"),
    "jsonlint": (FAILURE_LINT, "JSON files"),
    "json syntax check": (FAILURE_LINT, "JSON syntax"),
    "shellcheck": (FAILURE_LINT, "shell scripts"),
    "shfmt -d": (FAILURE_LINT, "shell formatting"),
    "eslint": (FAILURE_LINT, "JavaScript and TypeScript source"),
    "npm run lint": (FAILURE_LINT, "JavaScript and TypeScript source"),
    "stylelint": (FAILURE_LINT, "CSS source"),
    "sqlfluff lint": (FAILURE_LINT, "SQL source"),
    "xmllint --noout": (FAILURE_LINT, "XML well-formedness"),
    "go vet": (FAILURE_LINT, "Go source"),
    "staticcheck": (FAILURE_LINT, "Go source"),
    "clang-format --dry-run": (FAILURE_LINT, "C, C++ and Objective-C formatting"),
    "clang-tidy": (FAILURE_LINT, "C and C++ source"),
    "cppcheck": (FAILURE_LINT, "C and C++ source"),
    "dotnet format --verify-no-changes": (FAILURE_LINT, ".NET formatting"),
    "dart analyze": (FAILURE_LINT, "Dart source"),
    "phpstan": (FAILURE_LINT, "PHP source"),
    "rubocop": (FAILURE_LINT, "Ruby source"),
    "luacheck": (FAILURE_LINT, "Lua source"),
    "perlcritic": (FAILURE_LINT, "Perl source"),
    "lintr": (FAILURE_LINT, "R source"),
    "swiftlint": (FAILURE_LINT, "Swift source"),
    "swift-format lint": (FAILURE_LINT, "Swift formatting"),
    "detekt": (FAILURE_LINT, "Kotlin source"),
    "ktlint": (FAILURE_LINT, "Kotlin source"),
    "codenarc": (FAILURE_LINT, "Groovy source"),
    "nixpkgs-fmt --check": (FAILURE_LINT, "Nix formatting"),
    "zig fmt --check": (FAILURE_LINT, "Zig formatting"),
    "invoke-scriptanalyzer": (FAILURE_LINT, "PowerShell source"),
    "helm lint": (FAILURE_LINT, "Helm charts"),
    "kubeconform": (FAILURE_LINT, "Kubernetes manifests"),
    # the compiler itself
    "tsc --noemit": (FAILURE_COMPILATION, "TypeScript compilation"),
    # test runners
    "cargo test": (FAILURE_TEST, "Rust tests"),
    "pytest": (FAILURE_TEST, "Python tests"),
    "go test": (FAILURE_TEST, "Go tests"),
    "npm test": (FAILURE_TEST, "JavaScript and TypeScript tests"),
    "phpunit": (FAILURE_TEST, "PHP tests"),
    "rspec": (FAILURE_TEST, "Ruby tests"),
    "ctest": (FAILURE_TEST, "C and C++ tests"),
    "dotnet test": (FAILURE_TEST, ".NET tests"),
    "dart test": (FAILURE_TEST, "Dart tests"),
    "mvn test": (FAILURE_TEST, "Java tests"),
    "swift test": (FAILURE_TEST, "Swift tests"),
    "busted": (FAILURE_TEST, "Lua tests"),
    "testthat": (FAILURE_TEST, "R tests"),
    "prove": (FAILURE_TEST, "Perl tests"),
    "bats": (FAILURE_TEST, "shell tests"),
    "invoke-pester": (FAILURE_TEST, "PowerShell tests"),
    "zig build test": (FAILURE_TEST, "Zig tests"),
    # security tools: default = the tool failed, unless a findings signature
    # (SECURITY_FINDING_SIGNATURES) shows it reported findings
    "cargo audit": (FAILURE_SECURITY_TOOL, "Rust dependency advisories"),
    "cargo deny check": (
        FAILURE_SECURITY_TOOL,
        "Rust dependency policy and advisories",
    ),
    "pip-audit": (FAILURE_SECURITY_TOOL, "Python dependency advisories"),
    "npm audit": (FAILURE_SECURITY_TOOL, "JavaScript dependency advisories"),
    "govulncheck": (FAILURE_SECURITY_TOOL, "Go vulnerabilities"),
    "bundler-audit": (FAILURE_SECURITY_TOOL, "Ruby dependency advisories"),
    "composer audit": (FAILURE_SECURITY_TOOL, "PHP dependency advisories"),
    "dotnet list package --vulnerable": (
        FAILURE_SECURITY_TOOL,
        ".NET dependency advisories",
    ),
    "gradle dependencycheckanalyze": (
        FAILURE_SECURITY_TOOL,
        "Gradle dependency advisories",
    ),
    "mvn dependency-check": (FAILURE_SECURITY_TOOL, "Maven dependency advisories"),
    "bandit": (FAILURE_SECURITY_TOOL, "Python source security checks"),
    "gitleaks": (FAILURE_SECURITY_TOOL, "secret scanning"),
    "syft (sbom)": (FAILURE_SECURITY_TOOL, "SBOM generation"),
    # configuration checks
    "lockfile check": (FAILURE_CONFIGURATION, "dependency lockfile"),
}
# Kinds that carry a file or target name are matched by prefix.
# نوع‌هایی که نام فایل یا هدف دارند با پیشوند تطبیق داده می‌شوند.
TOOL_FAILURE_PREFIXES: tuple[tuple[str, str, str], ...] = (
    ("docker compose config", FAILURE_CONFIGURATION, "Docker Compose configuration"),
    ("helm lint", FAILURE_LINT, "Helm charts"),
    ("kubeconform", FAILURE_LINT, "Kubernetes manifests"),
    ("gradle ", FAILURE_UNKNOWN_TOOL, "Gradle task"),
)

# Strong compilation signatures: (regex, signal label, subject). Only rustc and
# comparable compilers print these; a linter that merely says `error:` does not.
# Rust: `error[E0425]:`. Clippy lints promoted to errors print `error: <lint>`
# followed by "could not compile", which is deliberately NOT a signature.
# امضای قوی کامپایل. `error:` ساده از linter امضا نیست؛ lintهای clippy که به
# error ارتقا یافته‌اند هم «could not compile» می‌آورند و عمداً امضا حساب نمی‌شوند.
COMPILE_SIGNATURES: tuple[tuple[str, str, str], ...] = (
    (r"\berror\[E\d{4}\]:", "rust-error-code", "Rust compilation"),
    (
        r"\b(?:SyntaxError|IndentationError|TabError)\b",
        "python-syntax",
        "Python syntax",
    ),
    (r"Failed to parse", "python-syntax", "Python syntax"),
    (r"\[build failed\]", "go-build-failed", "Go build"),
    (r"\berror TS\d+:", "typescript-error-code", "TypeScript compilation"),
    (r"COMPILATION ERROR", "java-compilation-error", "Java compilation"),
    (r"\berror CS\d+:", "dotnet-error-code", ".NET compilation"),
)
# Signal labels that keep their historical one-line known issue.
# برچسب‌هایی که جمله‌ی قدیمیِ known issue خود را نگه می‌دارند.
SIGNAL_PYTHON_SYNTAX = "python-syntax"
SIGNAL_PYTHON_MISSING_MODULE = "python-missing-module"
MISSING_MODULE_PATTERN = r"ModuleNotFoundError"
KNOWN_ISSUE_SYNTAX = "One or more source files contain syntax errors."
KNOWN_ISSUE_MISSING_MODULE = "A required Python dependency is missing."

# Security tools whose non-zero exit can mean "findings reported": (substring of
# the lower-cased kind, regex over the output, signal label). A match proves the
# tool completed and reported findings (an advisory or a leak); it does NOT prove
# exploitability. cargo deny is read by diagnostic code instead (below).
# امضای «ابزار امنیتی گزارش یافته داد»؛ اثبات نمی‌کند که قابل بهره‌برداری است.
SECURITY_FINDING_SIGNATURES: tuple[tuple[str, str, str], ...] = (
    (
        "cargo audit",
        r"(?m)error: \d+ vulnerabilit(?:y|ies) found|^ID:\s+RUSTSEC-",
        "advisory-reported",
    ),
    ("pip-audit", r"Found \d+ known vulnerabilit", "advisory-reported"),
    ("npm audit", r"(?i)\b[1-9]\d* vulnerabilit", "advisory-reported"),
    ("govulncheck", r"Vulnerability #\d+", "advisory-reported"),
    ("bundler-audit", r"(?m)Vulnerabilities found!|^Name: ", "advisory-reported"),
    ("composer audit", r"(?i)found \d+ security vulnerabilit", "advisory-reported"),
    ("vulnerable", r"has the following vulnerable packages", "advisory-reported"),
    (
        "dependency-check",
        r"(?i)identified with (?:known )?vulnerabilities|CVSS score",
        "advisory-reported",
    ),
    ("bandit", r">> Issue:|Issue: \[", "static-finding-reported"),
    (
        "gitleaks",
        r"(?im)\b[1-9]\d* leaks? found|\bleaks found:\s*[1-9]|^Finding:",
        "leak-reported",
    ),
)
# cargo deny prints `error[code]:` diagnostics. Advisory codes are security
# findings; every other error code is a dependency POLICY violation (licenses,
# bans, sources). Warnings (`warning[code]:`) are not failures.
# کدهای advisory یافته‌ی امنیتی‌اند؛ هر کد error دیگر نقض سیاست وابستگی است.
CARGO_DENY_ERROR_PATTERN = r"(?m)^error\[([a-z0-9-]+)\]:"
CARGO_DENY_ADVISORY_CODES: frozenset[str] = frozenset(
    {"vulnerability", "unmaintained", "unsound", "yanked", "notice"}
)

# R13-C: the kinds of a dependency advisory as the advisory databases name them
# (RustSec: a vulnerability, or a warning of kind unmaintained / unsound /
# yanked / notice). Fixed order: it is the sort order of the advisory list. An
# advisory is a tool result: `APPLICABILITY_UNKNOWN` says nobody checked whether
# this project reaches the affected code; no code path sets any other value.
# R13-C: انواع advisory وابستگی به نام پایگاه‌های advisory. advisory نتیجه‌ی ابزار
# است؛ `APPLICABILITY_UNKNOWN` یعنی کسی بررسی نکرده که پروژه به کد آسیب‌دیده
# می‌رسد یا نه؛ هیچ مسیری مقدار دیگری نمی‌گذارد.
ADVISORY_KINDS: tuple[str, ...] = (
    "vulnerability",
    "unsound",
    "unmaintained",
    "yanked",
    "notice",
)
APPLICABILITY_UNKNOWN = "unknown"
# The public repository, used as the SARIF `informationUri` (R13-C).
# مخزن عمومی؛ به‌عنوان `informationUri` در SARIF.
SARAND_INFO_URI = "https://github.com/msoleimani62/sarand"

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
# Version of how a line is turned into markers (every occurrence per line, one
# category each, R13-E). Part of the cache fingerprint: a change here makes every
# cached marker result stale.
# نسخه‌ی روش تبدیل خط به مارکر؛ جزو fingerprint کش.
MARKER_RULES_VERSION = 2

AI_NOTICE = (
    "This report is generated for AI analysis and contains project metadata, "
    "test results and source files."
)

DEFAULT_CMD_TIMEOUT = 300
LONG_CMD_TIMEOUT = 3600

# External commands run at most this many at once unless `--jobs` / SARAND_JOBS say
# otherwise (core/concurrency.py): one per CPU and per MEMORY_PER_JOB_MIB of free
# memory, at most DEFAULT_MAX_JOBS. A command's output is kept up to
# MAX_COMMAND_OUTPUT_BYTES: its head and its tail, the middle dropped and marked.
# ابزارهای بیرونی حداکثر به این تعداد هم‌زمان اجرا می‌شوند، مگر `--jobs` یا
# SARAND_JOBS چیز دیگری بگوید؛ از خروجی هر دستور فقط ابتدا و انتها نگه داشته می‌شود.
DEFAULT_MAX_JOBS = 8
MEMORY_PER_JOB_MIB = 1024
MAX_JOBS_LIMIT = 64
MAX_COMMAND_OUTPUT_BYTES = 8 * 1024 * 1024

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
