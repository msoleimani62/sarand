"""Maven multi-module and Gradle multi-project structure (AGENTS.md 5.61).

Both build tools already test every module natively from the root
(`mvn test`, `./gradlew test`), so this module changes no execution: it only
makes the report see the structure, as a `WorkspaceInfo` of kind ``maven`` or
``gradle``. Nothing here runs a tool.

Maven: the `<modules>` of the root `pom.xml`, followed into nested aggregators
(three levels). A `<module>` is a directory, or a path to a pom file. Modules
that live only in a `<profile>` are not read. Gradle: the `include` calls of
`settings.gradle[.kts]` (`:a:b` is the directory `a/b`, and its parent `a` is a
project too); `includeBuild` / `includeFlat` and a custom `projectDir` are not
followed, and a project whose default directory does not exist is left out
rather than guessed. Dynamic includes (a loop) are invisible to a static read.

A pom is parsed with the standard library only after a DOCTYPE / ENTITY
declaration is ruled out, so a hostile pom cannot expand entities.

ساختار چندماژوله‌ی Maven و چندپروژه‌ی Gradle. هر دو ابزار از ریشه همه‌ی
ماژول‌ها را تست می‌کنند؛ این ماژول اجرا را عوض نمی‌کند و فقط ساختار را به
گزارش می‌دهد. هیچ ابزاری اجرا نمی‌شود، و pom فقط بعد از رد DOCTYPE/ENTITY
parse می‌شود.
"""

from __future__ import annotations

import posixpath
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from sarand.models.results import WorkspaceInfo, WorkspaceMember

_MAX_MEMBERS = 200
_MAX_DEPTH = 3
_MAX_FILE_BYTES = 1024 * 1024

_GRADLE_SETTINGS = ("settings.gradle.kts", "settings.gradle")

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?<!:)//[^\n]*")
# include(":a", ":b")  /  include 'a', 'b'  (multi-line works). The `\b`
# after `include` keeps `includeBuild` and `includeFlat` out.
_INCLUDE = re.compile(
    r"\binclude\s*\(([^)]*)\)|\binclude\s+((?:[\"'][^\"'\n]+[\"']\s*,?\s*)+)"
)
_QUOTED = re.compile(r"[\"']([^\"']+)[\"']")


def _read(path: Path) -> str | None:
    try:
        if path.stat().st_size > _MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _local(tag: str) -> str:
    # `{http://maven.apache.org/POM/4.0.0}modules` -> `modules`
    return tag.rsplit("}", 1)[-1]


def _child(element: ET.Element, name: str) -> ET.Element | None:
    for child in element:
        if _local(child.tag) == name:
            return child
    return None


def _pom(path: Path) -> ET.Element | None:
    text = _read(path)
    if text is None or "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        return None
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        return None


def _module_entries(pom: ET.Element) -> list[str]:
    modules = _child(pom, "modules")
    if modules is None:
        return []
    return [
        (m.text or "").strip()
        for m in modules
        if _local(m.tag) == "module" and (m.text or "").strip()
    ]


def _artifact_id(pom: ET.Element, fallback: str) -> str:
    artifact = _child(pom, "artifactId")
    text = (artifact.text or "").strip() if artifact is not None else ""
    return text or fallback


def _collect_maven(
    root: Path,
    base: str,
    pom: ET.Element,
    depth: int,
    members: list[WorkspaceMember],
    seen: set[str],
) -> None:
    for entry in _module_entries(pom):
        if len(members) >= _MAX_MEMBERS:
            return
        joined = posixpath.normpath(posixpath.join(base, entry.replace("\\", "/")))
        if joined.startswith("..") or posixpath.isabs(joined):
            continue  # a module outside the project root
        if joined.lower().endswith(".xml"):
            pom_path = root / joined
            module_dir = posixpath.dirname(joined) or "."
        else:
            module_dir = joined
            pom_path = root / joined / "pom.xml"
        if module_dir in seen or module_dir == ".":
            continue
        module_pom = _pom(pom_path)
        if module_pom is None:
            continue
        seen.add(module_dir)
        members.append(
            WorkspaceMember(
                path=module_dir,
                name=_artifact_id(module_pom, posixpath.basename(module_dir)),
            )
        )
        if depth < _MAX_DEPTH:
            _collect_maven(root, module_dir, module_pom, depth + 1, members, seen)


def detect_maven_workspace(root: Path) -> WorkspaceInfo | None:
    """The modules of the root `pom.xml`, or `None` when it declares none that
    exist."""
    pom = _pom(root / "pom.xml")
    if pom is None:
        return None
    members: list[WorkspaceMember] = []
    _collect_maven(root, ".", pom, 1, members, set())
    return WorkspaceInfo(kind="maven", members=members) if members else None


def _gradle_projects(text: str) -> list[str]:
    cleaned = _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", text))
    found: list[str] = []
    for match in _INCLUDE.finditer(cleaned):
        found.extend(_QUOTED.findall(match.group(1) or match.group(2) or ""))
    return found


def detect_gradle_workspace(root: Path) -> WorkspaceInfo | None:
    """The `include`d projects of `settings.gradle[.kts]` whose default
    directory exists, or `None`."""
    text = None
    for name in _GRADLE_SETTINGS:
        text = _read(root / name)
        if text is not None:
            break
    if text is None:
        return None
    members: list[WorkspaceMember] = []
    seen: set[str] = set()
    for project in _gradle_projects(text):
        parts = [p for p in project.split(":") if p]
        # `:a:b` is also the project `:a`: list the parents first.
        for end in range(1, len(parts) + 1):
            if len(members) >= _MAX_MEMBERS:
                break
            directory = "/".join(parts[:end])
            if (
                directory in seen
                or ".." in parts[:end]
                or not (root / directory).is_dir()
            ):
                continue
            seen.add(directory)
            members.append(WorkspaceMember(path=directory, name=":".join(parts[:end])))
    return WorkspaceInfo(kind="gradle", members=members) if members else None
