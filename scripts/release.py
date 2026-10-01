#!/usr/bin/env python3
"""Release helper: keeps every place that carries the version in sync.

Two steps, on purpose (a tag must only be created after CI is green on
the pushed commit -- see AGENTS.md):

    python3 scripts/release.py bump 0.6.11   # edit files + commit
    git push                                 # then wait for CI
    python3 scripts/release.py tag           # annotated tag vX.Y.Z

`bump` edits pyproject.toml, Cargo.toml, the `sarand_core` entry in
Cargo.lock and `pkgver` in pkgs/aur/PKGBUILD, and refuses to run unless
CHANGELOG.md already has a `## [X.Y.Z]` heading, the tree is clean and
the version really is new. `tag` checks that the files at HEAD carry the
version it is about to tag. Nothing is pushed. `--dry-run` only prints.

اسکریپت release: همه‌ی جاهایی که نسخه دارند را هماهنگ نگه می‌دارد.
دو گام عمداً جداست (تگ فقط بعد از سبز شدن CI روی commit ی push‌شده):
`bump X.Y.Z` فایل‌ها را ویرایش و commit می‌کند؛ `tag` تگ annotated
می‌سازد. چیزی push نمی‌شود.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_PYPROJECT = re.compile(r'(?m)^(version\s*=\s*")[^"]+(")')
_PYPROJECT_VERSION = re.compile(r'(?m)^version\s*=\s*"([^"]+)"')
_CARGO_TOML = re.compile(r'(?m)^(version\s*=\s*")[^"]+(")')
_CARGO_LOCK = re.compile(r'(name = "sarand_core"\nversion = ")[^"]+(")')
_PKGVER = re.compile(r"(?m)^(pkgver=).*$")
_CHANGELOG_HEADING = re.compile(r"(?m)^## \[(\d+\.\d+\.\d+)\]")


def read_version(pyproject_text: str) -> str:
    match = _PYPROJECT_VERSION.search(pyproject_text)
    if match is None:
        raise ValueError("no version in pyproject.toml")
    return match.group(1)


def bump_texts(
    version: str,
    pyproject: str,
    cargo_toml: str,
    cargo_lock: str,
    pkgbuild: str,
) -> tuple[str, str, str, str]:
    """The four file contents with `version` applied. Pure; raises
    `ValueError` if any of them does not contain what is expected."""
    if not _SEMVER.match(version):
        raise ValueError(f"not a X.Y.Z version: {version!r}")
    out: list[str] = []
    for label, pattern, text, repl in (
        ("pyproject.toml", _PYPROJECT, pyproject, rf"\g<1>{version}\g<2>"),
        ("Cargo.toml", _CARGO_TOML, cargo_toml, rf"\g<1>{version}\g<2>"),
        ("Cargo.lock", _CARGO_LOCK, cargo_lock, rf"\g<1>{version}\g<2>"),
        ("PKGBUILD", _PKGVER, pkgbuild, rf"\g<1>{version}"),
    ):
        new, count = pattern.subn(repl, text, count=1)
        if count != 1:
            raise ValueError(f"version line not found in {label}")
        out.append(new)
    return out[0], out[1], out[2], out[3]


def changelog_versions(changelog_text: str) -> list[str]:
    return _CHANGELOG_HEADING.findall(changelog_text)


def _git(*args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout.strip()


def cmd_bump(version: str, dry_run: bool) -> None:
    if not _SEMVER.match(version):
        raise SystemExit(f"Version must look like 0.6.11, got {version!r}")
    paths = {
        "pyproject": ROOT / "pyproject.toml",
        "cargo": ROOT / "Cargo.toml",
        "lock": ROOT / "Cargo.lock",
        "pkgbuild": ROOT / "pkgs" / "aur" / "PKGBUILD",
    }
    texts = {k: p.read_text(encoding="utf-8") for k, p in paths.items()}
    current = read_version(texts["pyproject"])
    if current == version:
        raise SystemExit(f"Already at {version}.")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if version not in changelog_versions(changelog):
        raise SystemExit(
            f"CHANGELOG.md has no '## [{version}]' heading -- write the entry first."
        )
    if _git("tag", "--list", f"v{version}"):
        raise SystemExit(f"Tag v{version} already exists.")
    if _git("status", "--porcelain"):
        raise SystemExit("Working tree is not clean -- commit or stash first.")

    new = bump_texts(
        version, texts["pyproject"], texts["cargo"], texts["lock"], texts["pkgbuild"]
    )
    print(f"{current} -> {version}")
    if dry_run:
        print("(dry run: nothing written)")
        return
    for key, content in zip(paths, new, strict=True):
        paths[key].write_text(content, encoding="utf-8")
    _git("add", *(str(p.relative_to(ROOT)) for p in paths.values()))
    _git("commit", "-m", f"release: v{version}")
    print("Committed. Push, wait for CI, then: python3 scripts/release.py tag")


def cmd_tag(dry_run: bool) -> None:
    version = read_version((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    tag = f"v{version}"
    if _git("tag", "--list", tag):
        raise SystemExit(f"Tag {tag} already exists.")
    if _git("status", "--porcelain"):
        raise SystemExit("Working tree is not clean.")
    if version not in changelog_versions(
        (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    ):
        raise SystemExit(f"CHANGELOG.md has no '## [{version}]' heading.")
    print(f"Tagging HEAD ({_git('rev-parse', '--short', 'HEAD')}) as {tag}")
    if dry_run:
        print("(dry run: nothing written)")
        return
    _git("tag", "-a", tag, "-m", f"{tag}")
    print(f"Created {tag}. Publish it with: git push origin {tag}")


def main(argv: list[str]) -> None:
    dry_run = "--dry-run" in argv
    args = [a for a in argv if a != "--dry-run"]
    if len(args) == 2 and args[0] == "bump":
        cmd_bump(args[1], dry_run)
    elif len(args) == 1 and args[0] == "tag":
        cmd_tag(dry_run)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
