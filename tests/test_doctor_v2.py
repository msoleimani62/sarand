"""Tests for the redesigned sarand.core.doctor -- categorized tool checks."""

from __future__ import annotations

from sarand.core.doctor import _CATEGORY_ORDER, collect_checks


def test_every_language_tool_check_has_a_category_from_the_defined_order() -> None:
    checks = collect_checks()
    for check in checks:
        if check.category == "Core":
            continue
        assert check.category in _CATEGORY_ORDER


def test_android_and_java_share_the_gradle_and_maven_checks() -> None:
    """No separate Android-specific tool row -- gradle/mvn serve both
    JavaAnalyzer and AndroidAnalyzer, so a duplicate row would be
    misleading (as if a different tool were needed for each)."""
    checks = collect_checks()
    android_category_tools = {
        c.name for c in checks if c.category == "Java / Kotlin / Android"
    }
    assert android_category_tools == {"mvn", "gradle"}


def test_every_tool_check_declares_what_it_is_used_for() -> None:
    checks = collect_checks()
    for check in checks:
        if check.category == "Core":
            continue
        assert check.used_for, f"{check.name} has no 'used_for' explanation"


def test_gradle_check_mentions_the_wrapper_fallback() -> None:
    checks = collect_checks()
    gradle_check = next(c for c in checks if c.name == "gradle")
    assert "gradlew" in gradle_check.used_for


def test_ruby_php_dart_lua_checks_are_registered() -> None:
    # Regression guard: these were added later than the analyzers
    # themselves (Lua/Ruby/PHP/Dart were each missing from --doctor
    # for a while after their analyzer was added).
    checks = collect_checks()
    by_category: dict[str, set[str]] = {}
    for check in checks:
        by_category.setdefault(check.category, set()).add(check.name)

    assert by_category["Lua"] == {"busted", "luacheck"}
    assert by_category["Ruby"] == {"bundle"}
    assert by_category["PHP"] == {"composer"}
    assert by_category["Dart / Flutter"] == {"dart"}


def test_typescript_and_css_checks_are_registered() -> None:
    # Same regression guard as above, for the TypeScriptAnalyzer/
    # CssAnalyzer addition.
    checks = collect_checks()
    by_category: dict[str, set[str]] = {}
    for check in checks:
        by_category.setdefault(check.category, set()).add(check.name)

    assert by_category["TypeScript"] == {"tsc"}
    assert by_category["CSS"] == {"stylelint"}


def test_zig_swift_sql_checks_are_registered() -> None:
    # Same regression guard as above, for the ZigAnalyzer/SwiftAnalyzer/
    # SqlAnalyzer addition.
    checks = collect_checks()
    by_category: dict[str, set[str]] = {}
    for check in checks:
        by_category.setdefault(check.category, set()).add(check.name)

    assert by_category["Zig"] == {"zig"}
    assert by_category["Swift"] == {"swift", "swift-format", "swiftlint", "xcodebuild"}
    assert by_category["SQL"] == {"sqlfluff"}


def test_kotlin_csharp_shell_format_checks_are_registered() -> None:
    # Same regression guard as above, for the KotlinAnalyzer/
    # CSharpAnalyzer/ShellAnalyzer/YamlAnalyzer/JsonAnalyzer/
    # TomlAnalyzer/XmlAnalyzer addition.
    checks = collect_checks()
    by_category: dict[str, set[str]] = {}
    for check in checks:
        by_category.setdefault(check.category, set()).add(check.name)

    assert by_category["Kotlin"] == {"ktlint", "detekt"}
    assert by_category["C#"] == {"dotnet"}
    assert by_category["Shell"] == {"shellcheck", "shfmt", "bats"}
    assert by_category["YAML"] == {"yamllint"}
    assert by_category["JSON"] == {"jsonlint"}
    assert by_category["TOML"] == {"taplo"}
    assert by_category["XML"] == {"xmllint"}


def test_rust_and_python_supply_chain_checks_are_registered() -> None:
    # Regression guard for the cargo-deny/rustfmt/cargo-clippy/mypy
    # additions -- Rust originally only checked cargo/cargo-audit, and
    # Python only pytest/ruff/pip-audit/bandit (mypy was CI-only,
    # never exposed through --doctor/--quality).
    checks = collect_checks()
    by_category: dict[str, set[str]] = {}
    for check in checks:
        by_category.setdefault(check.category, set()).add(check.name)

    assert by_category["Rust"] == {
        "cargo",
        "rustfmt",
        "cargo-clippy",
        "cargo-audit",
        "cargo-deny",
    }
    assert by_category["Python"] == {
        "pytest",
        "ruff",
        "mypy",
        "pip-audit",
        "bandit",
    }

    # cargo-deny's used_for hint must point at the deny.toml
    # requirement -- otherwise a maintainer sees it installed-but-
    # skipped with no clue why (§4.11: never fail silently).
    deny_check = next(c for c in checks if c.name == "cargo-deny")
    assert "deny.toml" in deny_check.used_for

    mypy_check = next(c for c in checks if c.name == "mypy")
    assert "type checking" in mypy_check.used_for.lower()


def test_p0_language_depth_round_checks_are_registered() -> None:
    # Regression guard for the 2026-09-19 P0 round (external-audit
    # backlog, AGENTS.md §5.10): eslint (Node.js), staticcheck (Go),
    # clang-tidy (C/C++), shfmt (Shell, checked above already),
    # swiftlint (Swift), and the brand-new Markdown analyzer
    # (markdownlint). npm audit and clang-format were already
    # registered before this round -- not re-asserted here, see the
    # existing Node.js/C-C++ rows in _TOOL_CHECKS directly.
    checks = collect_checks()
    by_category: dict[str, set[str]] = {}
    for check in checks:
        by_category.setdefault(check.category, set()).add(check.name)

    assert "eslint" in by_category["Node.js"]
    assert "staticcheck" in by_category["Go"]
    assert "clang-tidy" in by_category["C/C++"]
    assert "swiftlint" in by_category["Swift"]
    assert by_category["Markdown"] == {"markdownlint"}

    # clang-tidy's used_for hint must point at the compile_commands.json
    # requirement, same reasoning as cargo-deny's deny.toml hint above.
    tidy_check = next(c for c in checks if c.name == "clang-tidy")
    assert "compile_commands.json" in tidy_check.used_for

    eslint_check = next(c for c in checks if c.name == "eslint")
    assert "eslint config" in eslint_check.used_for.lower()
