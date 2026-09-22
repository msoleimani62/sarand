"""The coverage matrix: what sarand does for each ecosystem, derived from
the code itself.

Which languages sarand supports, and *how deeply*, is easy to state wrongly
by hand (a README says "31 analyzers"; `--doctor` lists tools; the analyzers
themselves decide what actually runs). This module builds one table from
those real sources and `docs/COVERAGE.md` is generated from it, with a test
that fails when the file is stale:

- **Tests / Quality / Security** -- true when the analyzer's `run_tests` /
  `run_quality` / `run_security` is more than a bare `return None` /
  `return []` (read from the analyzer's source with `ast`, so it cannot drift
  from the code).
- **Tools** -- the external tools `--doctor` lists for that ecosystem.
- **Build tools** -- the build/package manager sarand's project detector
  recognises from the project's marker files.
- **Fixture coverage** -- true when the analyzer's class name is referenced
  anywhere under `tests/` (read from the actual test source, not a filename
  convention -- several analyzers share one test module).
- **CI-installed** -- true when at least one of the ecosystem's tool binaries
  is a token `.github/workflows/ci.yml` actually installs *and* invokes (read
  from the workflow file itself). This is deliberately narrow: being listed
  as a Python `[dev]` extra does not count unless the binary is also run as a
  command in the workflow -- see `_ci_installs_tool`.
- **Depth** -- Deep / Partial / Shallow, a fixed rule over the four booleans
  above (Deep = tests and quality and security and fixture coverage; Shallow
  = none of tests/quality/security; else Partial). A rule, not a per-analyzer
  judgment call, so no analyzer can be labeled Deep just because someone
  thought its wrapper looked substantial (backlog item 7.1's own warning).

`Real-project validation` (backlog item 7.1's last column) is deliberately
NOT part of this generated table: whether an ecosystem's tools were ever run
for real against a real project is a fact about a past session, not
something derivable from the current source tree, and mixing hand-curated
history into a "regenerate from code, do not edit by hand" file would rot
the moment nobody remembers to re-verify it. That evidence lives in
AGENTS.md section 5.22 instead, cited with its own commit/date, exactly like
every other historical claim in that file.

Regenerate the file with `python -m sarand.core.coverage > docs/COVERAGE.md`.

ماتریس پوشش: sarand برای هر اکوسیستم چه می‌کند، مستقیماً از خودِ کد استخراج
می‌شود. اینکه sarand کدام زبان‌ها را و *با چه عمقی* پشتیبانی می‌کند به‌سادگی
با دست غلط نوشته می‌شود (README می‌گوید «۳۱ آنالایزر»؛ `--doctor` ابزارها را
فهرست می‌کند؛ خودِ آنالایزرها تصمیم می‌گیرند واقعاً چه اجرا شود). این ماژول
یک جدول از همان منابع واقعی می‌سازد و `docs/COVERAGE.md` از آن تولید می‌شود،
با تستی که وقتی فایل کهنه باشد شکست می‌خورد.

- **پوشش fixture** -- زمانی درست است که نام کلاس آنالایزر جایی زیر `tests/`
  ارجاع داده شده باشد (از خودِ سورس تست خوانده می‌شود، نه یک قرارداد نام‌گذاری
  فایل -- چند آنالایزر یک ماژول تست مشترک دارند).
- **نصب‌شده در CI** -- زمانی درست است که دست‌کم یکی از باینری‌های ابزار آن
  اکوسیستم، توکنی باشد که `.github/workflows/ci.yml` واقعاً نصب *و* اجرا
  می‌کند (از خودِ فایل workflow خوانده می‌شود). عمداً محدود: فقط لیست‌شدن
  به‌عنوان extra مربوط به `[dev]` پایتون کافی نیست، مگر باینری هم به‌عنوان
  یک دستور در workflow اجرا شود -- `_ci_installs_tool` را ببینید.
- **عمق** -- Deep / Partial / Shallow، یک قاعده‌ی ثابت روی چهار مقدار بولی
  بالا (Deep = tests و quality و security و پوشش fixture؛ Shallow = هیچ‌کدام
  از tests/quality/security؛ در غیر این صورت Partial). یک قاعده است، نه
  قضاوت به‌ازای هر آنالایزر، پس هیچ آنالایزری نمی‌تواند فقط چون wrapperاش
  قابل‌توجه به نظر می‌رسیده Deep برچسب بخورد (همان هشدار خودِ آیتم ۷.۱
  backlog).

«اعتبارسنجی روی پروژه‌ی واقعی» (آخرین ستونِ آیتم ۷.۱ backlog) عمداً بخشی از
این جدول تولیدشده نیست: اینکه ابزارهای یک اکوسیستم واقعاً روی یک پروژه‌ی
واقعی اجرا شده‌اند یا نه، واقعیتی درباره‌ی یک نشست گذشته است، نه چیزی
قابل‌استخراج از درخت سورس فعلی؛ و آمیختن تاریخچه‌ی دستی‌نگهداری‌شده در فایلی
با قرارداد «از کد بازتولید کن، با دست ویرایش نکن» به‌محض فراموش‌شدن
re-verify، می‌پوسد. آن شاهد در بخش ۵.۲۲ AGENTS.md است، دقیقاً مثل هر ادعای
تاریخیِ دیگر در آن فایل، با ارجاع به commit/تاریخ خودش.
"""

from __future__ import annotations

import ast
import inspect
import re
from dataclasses import dataclass
from pathlib import Path

from sarand.analyzers.registry import builtin_analyzers
from sarand.constants import PROJECT_MARKERS
from sarand.core.doctor import tool_catalog

# The repo root, to read tests/ and the CI workflow the same way
# `test_docs_coverage_md_is_up_to_date` locates docs/COVERAGE.md.
# ریشه‌ی مخزن، برای خواندن tests/ و workflow ماژول CI، به همان شکلی که
# `test_docs_coverage_md_is_up_to_date` مسیر docs/COVERAGE.md را پیدا می‌کند.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_TESTS_DIR = _REPO_ROOT / "tests"
_CI_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "ci.yml"

# analyzer name -> the `--doctor` categories that show it. Every analyzer must
# be visible there: either through the tools it drives or, for the ones that
# need none (Assembly), through a "built-in" detection-only row.
# نام آنالایزر -> دسته‌های `--doctor` که آن را نشان می‌دهند. هر آنالایزر باید
# آنجا دیده شود: یا از راه ابزارهایی که اجرا می‌کند، یا -- برای آن‌هایی که
# ابزاری لازم ندارند (Assembly) -- با یک ردیف «داخلی» فقط-شناسایی.
DOCTOR_CATEGORIES: dict[str, tuple[str, ...]] = {
    "Python": ("Python",),
    "Rust": ("Rust",),
    "Go": ("Go",),
    "Node.js": ("Node.js",),
    "TypeScript": ("TypeScript",),
    "CSS": ("CSS",),
    "Zig": ("Zig",),
    "Assembly": ("Assembly",),
    "Swift": ("Swift",),
    "Objective-C": ("Objective-C",),
    "C/C++": ("C/C++",),
    "Lua": ("Lua",),
    "Ruby": ("Ruby",),
    "PHP": ("PHP",),
    "Dart": ("Dart / Flutter",),
    "R": ("R",),
    "Perl": ("Perl",),
    "Julia": ("Julia",),
    "SQL": ("SQL",),
    "Android/Kotlin": ("Java / Kotlin / Android",),
    "Java/Kotlin": ("Java / Kotlin / Android",),
    "Kotlin": ("Kotlin",),
    "Groovy": ("Groovy",),
    "C#": ("C#",),
    "Shell": ("Shell",),
    "PowerShell": ("PowerShell",),
    "Nix": ("Nix",),
    "YAML": ("YAML",),
    "JSON": ("JSON",),
    "TOML": ("TOML",),
    "XML": ("XML",),
    "Markdown": ("Markdown",),
    "Haskell": ("Haskell",),
    "Elixir": ("Elixir",),
    "Erlang": ("Erlang",),
    "Scala": ("Scala",),
    "Dockerfile": ("Dockerfile",),
    "GitHub Actions": ("GitHub Actions",),
    "Terraform": ("Terraform",),
    "Protobuf": ("Protobuf",),
}

# Doctor categories that are not an ecosystem an analyzer detects.
# دسته‌های doctor که اکوسیستمِ قابل‌شناسایی برای یک آنالایزر نیستند.
NON_ECOSYSTEM_CATEGORIES = frozenset({"Supply chain", "PDF export"})

# analyzer name -> language names used in constants.PROJECT_MARKERS
# (defaults to the analyzer's own name).
_MARKER_LANGUAGES: dict[str, tuple[str, ...]] = {
    "Dart": ("Dart/Flutter",),
    "Java/Kotlin": ("Java", "Java/Kotlin"),
    "Android/Kotlin": ("Java/Kotlin",),
}


@dataclass(frozen=True)
class CoverageRow:
    ecosystem: str
    tests: bool
    quality: bool
    security: bool
    tools: tuple[str, ...]
    build_tools: tuple[str, ...]
    fixture_coverage: bool
    ci_installed: bool
    depth: str


def _is_trivial(function: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    """True if the body is only a docstring and `return None` / `return []`."""
    body = [
        statement
        for statement in function.body
        if not (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        )
    ]
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        return False
    value = body[0].value
    if value is None:
        return True
    if isinstance(value, ast.Constant):
        return value.value is None
    return isinstance(value, ast.List) and not value.elts


def _capabilities(analyzer: object) -> tuple[bool, bool, bool]:
    source_file = inspect.getsourcefile(type(analyzer))
    if source_file is None:
        return (False, False, False)
    tree = ast.parse(Path(source_file).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == type(analyzer).__name__:
            methods = {
                child.name: child
                for child in node.body
                if isinstance(child, (ast.AsyncFunctionDef, ast.FunctionDef))
            }
            flags = [
                name in methods and not _is_trivial(methods[name])
                for name in ("run_tests", "run_quality", "run_security")
            ]
            return (flags[0], flags[1], flags[2])
    return (False, False, False)


def _has_fixture_coverage(analyzer: object, tests_dir: Path) -> bool:
    """True when the analyzer's class name is referenced anywhere under
    `tests/`. A grep, not a filename convention -- several analyzers
    (Haskell/Elixir/Erlang/Scala/Dockerfile/GitHub Actions/Terraform/
    Protobuf, for instance) share one test module instead of getting
    `test_<name>_analyzer.py` each, so filename-matching would
    under-report real coverage.

    زمانی درست است که نام کلاس آنالایزر جایی زیر `tests/` ارجاع داده
    شده باشد. یک grep است، نه یک قرارداد نام‌گذاری فایل -- چند آنالایزر
    (مثلاً Haskell/Elixir/Erlang/Scala/Dockerfile/GitHub Actions/
    Terraform/Protobuf) به‌جای یک `test_<name>_analyzer.py` مجزا، یک
    ماژول تست مشترک دارند، پس تطبیق بر اساس نام فایل پوشش واقعی را
    کمتر از حد گزارش می‌کرد.
    """
    class_name = type(analyzer).__name__
    if not tests_dir.is_dir():
        return False
    pattern = re.compile(rf"\b{re.escape(class_name)}\b")
    for test_file in tests_dir.glob("*.py"):
        try:
            if pattern.search(test_file.read_text(encoding="utf-8")):
                return True
        except OSError:
            continue
    return False


def _ci_installs_tool(binaries: tuple[str, ...], ci_workflow: Path) -> bool:
    """True when at least one of `binaries` is a token the CI workflow
    file actually contains -- i.e. sarand's own CI installs *and*
    invokes it, not merely lists it as a package extra.

    A `cargo-xxx` doctor binary name (e.g. `cargo-clippy`) is matched
    against its bare subcommand too (`clippy`), since that is the token
    that actually appears in a rustup `components:` line or a `cargo
    xxx` invocation -- CI never literally writes `cargo-clippy`.

    زمانی درست است که دست‌کم یکی از `binaries` توکنی باشد که خودِ فایل
    workflow CI واقعاً دارد -- یعنی CI خودِ sarand واقعاً آن را نصب *و*
    اجرا می‌کند، نه فقط به‌عنوان یک extra بسته فهرست کرده باشد.

    یک نام باینری doctor به‌شکل `cargo-xxx` (مثلاً `cargo-clippy`) با
    زیردستور خامش هم (`clippy`) مقایسه می‌شود، چون همان توکنی است که
    واقعاً در خط `components:` روباپ یا یک فراخوانی `cargo xxx` ظاهر
    می‌شود -- CI هرگز عیناً `cargo-clippy` نمی‌نویسد.
    """
    if not ci_workflow.is_file() or not binaries:
        return False
    try:
        raw = ci_workflow.read_text(encoding="utf-8")
    except OSError:
        return False
    # Drop comment lines before matching. A first pass matched Haskell's
    # "stack" against the prose comment "...prints every thread's
    # *stack*...", a real false positive -- ci.yml's own `#`-comments
    # discuss tools by name without installing or invoking them, and a
    # bare word-boundary search over the whole file cannot tell prose
    # from a command.
    #
    # پیش از تطبیق، خطوط کامنت کنار گذاشته می‌شوند. یک تلاش اول باعث شد
    # "stack" مربوط به Haskell با کامنتِ نثریِ «...stack هر thread را
    # چاپ می‌کند...» تطبیق پیدا کند -- یک false positive واقعی -- چون
    # کامنت‌های `#` خودِ ci.yml درباره‌ی ابزارها با نام صحبت می‌کنند بدون
    # اینکه نصب یا اجرایشان کنند، و یک جست‌وجوی سادهٔ word-boundary روی
    # کل فایل نمی‌تواند نثر را از یک دستور تشخیص دهد.
    text = "\n".join(
        line for line in raw.splitlines() if not line.strip().startswith("#")
    )
    for binary in binaries:
        candidates = {binary}
        if binary.startswith("cargo-"):
            candidates.add(binary[len("cargo-") :])
        for candidate in candidates:
            if re.search(rf"\b{re.escape(candidate)}\b", text, re.IGNORECASE):
                return True
    return False


def _classify_depth(
    tests: bool, quality: bool, security: bool, fixture_coverage: bool
) -> str:
    """Deep / Partial / Shallow from a fixed rule, not a per-analyzer
    judgment call -- see the module docstring's "Depth" bullet for why.
    """
    if not (tests or quality or security):
        return "Shallow"
    if tests and quality and security and fixture_coverage:
        return "Deep"
    return "Partial"


def build_coverage() -> list[CoverageRow]:
    catalog = tool_catalog()
    rows: list[CoverageRow] = []
    for analyzer in builtin_analyzers():
        categories = DOCTOR_CATEGORIES[analyzer.name]
        tools: list[str] = []
        for category, binary, _hint, _used in catalog:
            if category in categories and binary not in tools:
                tools.append(binary)
        languages = _MARKER_LANGUAGES.get(analyzer.name, (analyzer.name,))
        builds: list[str] = []
        for language, _type, build in PROJECT_MARKERS.values():
            if language in languages and build not in builds and build != "none":
                builds.append(build)
        tests, quality, security = _capabilities(analyzer)
        fixture_coverage = _has_fixture_coverage(analyzer, _TESTS_DIR)
        ci_installed = _ci_installs_tool(tuple(tools), _CI_WORKFLOW)
        depth = _classify_depth(tests, quality, security, fixture_coverage)
        rows.append(
            CoverageRow(
                analyzer.name,
                tests,
                quality,
                security,
                tuple(tools),
                tuple(builds),
                fixture_coverage,
                ci_installed,
                depth,
            )
        )
    return rows


def render_markdown() -> str:
    def flag(value: bool) -> str:
        return "yes" if value else "-"

    lines = [
        "# Coverage matrix",
        "",
        "What sarand does for each ecosystem, derived from the code (see",
        "`sarand/core/coverage.py`). **Do not edit by hand:** regenerate with",
        "`python -m sarand.core.coverage > docs/COVERAGE.md`; a test fails when",
        "this file is stale.",
        "",
        "- **Tests / Quality / Security**: the analyzer implements that check.",
        "- **Tools**: external tools `sarand --doctor` lists for it (all optional;",
        "  a missing tool is skipped, never fatal).",
        "- **Build tools**: recognised from the project's marker files.",
        "- **Fixtures**: the analyzer's class is referenced by a real test under",
        "  `tests/` (several analyzers share one test module, so this is a grep of",
        "  test source, not a filename convention).",
        "- **CI**: at least one of the ecosystem's tools is actually installed *and*",
        "  invoked by sarand's own `.github/workflows/ci.yml` -- not merely listed as",
        '  a package extra. **This is almost always "-"**: sarand\'s CI runs its own',
        "  Python test suite and its own Rust core's tests, it does not install the",
        "  ~35 other per-language tools and run `sarand --full`/`--quality`/",
        "  `--security` against a real target project in any language. See AGENTS.md",
        "  section 5.22 for what real-project validation evidence exists instead, and",
        "  backlog items 6.1/7.1 for the CLI-level golden-report and real-tool-",
        "  validation work this gap motivates.",
        "- **Depth**: Deep / Partial / Shallow, a fixed rule over the four columns",
        "  above (Deep = Tests and Quality and Security and Fixtures; Shallow = none",
        "  of Tests/Quality/Security; otherwise Partial) -- never a per-analyzer",
        "  judgment call.",
        "",
        "| Ecosystem | Tests | Quality | Security | Fixtures | CI | Depth | Tools | Build tools |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in build_coverage():
        tools = ", ".join(f"`{t}`" for t in row.tools) or "none needed (detection only)"
        builds = ", ".join(row.build_tools) or "-"
        lines.append(
            f"| {row.ecosystem} | {flag(row.tests)} | {flag(row.quality)} | "
            f"{flag(row.security)} | {flag(row.fixture_coverage)} | "
            f"{flag(row.ci_installed)} | {row.depth} | {tools} | {builds} |"
        )
    lines.append("")
    lines.append(
        "Project-wide checks (`--security`, any ecosystem): gitleaks, syft (SBOM and "
        "license policy), lockfile check."
    )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    print(render_markdown(), end="")
