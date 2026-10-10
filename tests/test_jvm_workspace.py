"""Maven multi-module and Gradle multi-project (AGENTS.md section 5.61): the
structure is read, and a Gradle root that holds only `settings.gradle[.kts]`
is recognised as a Gradle project (it used to match no analyzer, so each
subproject was planned alone, without the root wrapper).

ساختار چندماژوله‌ی Maven و چندپروژه‌ی Gradle (بخش ۵.۶۱).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from _helpers import write
from sarand.analyzers.java_analyzer import JavaAnalyzer
from sarand.analyzers.registry import builtin_analyzers, matching_analyzers
from sarand.constants import PROJECT_MARKERS
from sarand.core.components import detect_components
from sarand.core.jvm_workspace import detect_gradle_workspace, detect_maven_workspace
from sarand.core.per_component import plan_component_runs
from sarand.core.workspace import detect_workspace, detect_workspaces

_POM = (
    '<project xmlns="http://maven.apache.org/POM/4.0.0">'
    "<modelVersion>4.0.0</modelVersion><groupId>g</groupId>"
    "<artifactId>{a}</artifactId><version>1</version>{x}</project>"
)


def _pom(artifact: str, *modules: str, profile: bool = False) -> str:
    listed = "".join(f"<module>{m}</module>" for m in modules)
    body = f"<modules>{listed}</modules>" if modules else ""
    if profile:
        body = f"<profiles><profile><id>p</id>{body}</profile></profiles>"
    return _POM.format(a=artifact, x=f"<packaging>pom</packaging>{body}")


def _members(info) -> list[tuple[str, str]]:  # type: ignore[no-untyped-def]
    return [(m.path, m.name) for m in info.members]


# ------------------------------------------------------------------ Maven --


def test_a_maven_reactor_lists_its_modules_with_their_artifact_ids() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pom.xml", _pom("parent", "core", "web"))
        write(root / "core" / "pom.xml", _pom("core-lib"))
        write(root / "web" / "pom.xml", _pom("web-app"))
        info = detect_maven_workspace(root)
        assert info is not None and info.kind == "maven"
        assert _members(info) == [("core", "core-lib"), ("web", "web-app")]


def test_nested_aggregators_are_followed_and_modules_may_be_pom_paths() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pom.xml", _pom("parent", "core", "tools/pom-alt.xml"))
        write(root / "core" / "pom.xml", _pom("core", "api", "impl"))
        write(root / "core" / "api" / "pom.xml", _pom("api"))
        write(root / "core" / "impl" / "pom.xml", _pom("impl"))
        write(root / "tools" / "pom-alt.xml", _pom("tools"))
        info = detect_maven_workspace(root)
        assert info is not None
        assert [m.path for m in info.members] == [
            "core",
            "core/api",
            "core/impl",
            "tools",
        ]


def test_missing_and_escaping_modules_are_left_out() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pom.xml", _pom("parent", "real", "ghost", "../outside"))
        write(root / "real" / "pom.xml", _pom("real"))
        info = detect_maven_workspace(root)
        assert info is not None and [m.path for m in info.members] == ["real"]


def test_no_modules_a_profile_only_module_and_bad_xml_give_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pom.xml", _pom("single"))
        assert detect_maven_workspace(root) is None
        write(root / "pom.xml", _pom("p", "m", profile=True))
        write(root / "m" / "pom.xml", _pom("m"))
        assert detect_maven_workspace(root) is None  # profile modules not read
        write(root / "pom.xml", "<project><modules><module>m</module></project>")
        assert detect_maven_workspace(root) is None


def test_a_pom_with_a_doctype_or_entity_is_never_parsed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        hostile = (
            '<?xml version="1.0"?><!DOCTYPE project [<!ENTITY a "aaaa">]>'
            "<project><modules><module>m</module></modules></project>"
        )
        write(root / "pom.xml", hostile)
        write(root / "m" / "pom.xml", _pom("m"))
        assert detect_maven_workspace(root) is None


# ----------------------------------------------------------------- Gradle --


def _gradle(root: Path, settings: str, *dirs: str, name: str = "settings.gradle.kts"):
    write(root / name, settings)
    for directory in dirs:
        write(root / directory / "build.gradle.kts", "plugins { }\n")
    return detect_gradle_workspace(root)


def test_kotlin_dsl_includes_are_read() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        info = _gradle(
            Path(tmp), 'rootProject.name = "r"\ninclude(":app", ":lib")\n', "app", "lib"
        )
        assert info is not None and info.kind == "gradle"
        assert _members(info) == [("app", "app"), ("lib", "lib")]


def test_groovy_dsl_and_multi_line_includes_are_read() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        info = _gradle(
            root,
            "include 'app', 'lib'\ninclude(\n  ':tools',\n  ':docs'\n)\n",
            "app",
            "lib",
            "tools",
            "docs",
            name="settings.gradle",
        )
        assert info is not None
        assert [m.path for m in info.members] == ["app", "lib", "tools", "docs"]


def test_a_nested_project_path_lists_its_parent_first() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        info = _gradle(Path(tmp), 'include(":services:api")\n', "services/api")
        assert info is not None
        assert _members(info) == [
            ("services", "services"),
            ("services/api", "services:api"),
        ]


def test_include_build_comments_urls_and_missing_directories_are_ignored() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        settings = (
            "pluginManagement { repositories { maven { "
            'url = uri("https://plugins.example.com/m") } } }\n'
            'includeBuild("../other")\n'
            '// include(":commented")\n'
            '/* include(":block") */\n'
            'include(":real", ":ghost")\n'
        )
        info = _gradle(Path(tmp), settings, "real", "commented", "block")
        assert info is not None and _members(info) == [("real", "real")]


def test_no_include_or_no_settings_file_gives_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert detect_gradle_workspace(root) is None
        assert _gradle(root, 'rootProject.name = "solo"\n') is None


def test_the_member_cap_applies() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        names = [f"p{i:03d}" for i in range(210)]
        settings = "include(" + ", ".join(f'":{n}"' for n in names) + ")\n"
        info = _gradle(root, settings, *names[:210])
        assert info is not None and len(info.members) == 200


# ----------------------------------------------------- the workspace list --


def test_maven_and_gradle_come_after_cargo_and_node_in_detect_workspaces() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "package.json", '{"name": "r", "workspaces": ["packages/*"]}')
        write(root / "packages" / "a" / "package.json", '{"name": "a"}')
        write(root / "pom.xml", _pom("parent", "m"))
        write(root / "m" / "pom.xml", _pom("m"))
        assert [w.kind for w in detect_workspaces(root)] == ["npm", "maven"]
        first = detect_workspace(root)
        assert first is not None and first.kind == "npm"


# ------------------------------------------- the settings-only Gradle root --


def _settings_only(root: Path) -> None:
    write(root / "settings.gradle.kts", 'include(":app", ":lib")\n')
    write(root / "gradlew", "#!/bin/sh\n")
    write(root / "app" / "build.gradle.kts", "plugins { }\n")
    write(root / "lib" / "build.gradle.kts", "plugins { }\n")


def test_a_settings_only_gradle_root_is_a_gradle_project() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _settings_only(root)
        assert JavaAnalyzer().matches(root)
        assert JavaAnalyzer()._build_tool(root) == "gradle"


def test_subprojects_are_not_planned_alone_when_the_root_runs_them() -> None:
    """The audited gap: before 5.61 the root matched no analyzer, so each
    subproject was planned alone (no root wrapper, the wrong invocation)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _settings_only(root)
        analyzers = builtin_analyzers()
        active = matching_analyzers(root, analyzers)
        assert "Java/Kotlin" in [a.name for a in active]
        plan = plan_component_runs(
            root,
            detect_components(root, None, None, None),
            analyzers,
            active,
            detect_workspaces(root),
        )
        assert not any(
            a.name == "Java/Kotlin" for t in plan.targets for a in t.analyzers
        )


def test_the_gradle_settings_files_are_project_markers() -> None:
    assert PROJECT_MARKERS["settings.gradle"][2] == "gradle"
    assert PROJECT_MARKERS["settings.gradle.kts"][2] == "gradle"
