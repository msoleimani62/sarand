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
version it is about to tag AND that every GitHub Actions run for HEAD has
finished successfully (asked of the `gh` CLI); it refuses when there is no
run yet, one is still going, or one failed -- tagging a commit before CI
finished is how v0.6.10 landed on a red Windows job. `--skip-ci-check`
overrides the gate (offline, or `gh` unavailable) and says so loudly.
Nothing is pushed. `--dry-run` only prints.

اسکریپت release: همه‌ی جاهایی که نسخه دارند را هماهنگ نگه می‌دارد.
دو گام عمداً جداست (تگ فقط بعد از سبز شدن CI روی commit ی push‌شده):
`bump X.Y.Z` فایل‌ها را ویرایش و commit می‌کند؛ `tag` تگ annotated
می‌سازد و فقط وقتی که همه‌ی runهای CI برای HEAD (با `gh`) تمام و موفق
باشند؛ `--skip-ci-check` این بررسی را رد می‌کند. چیزی push نمی‌شود.
"""

from __future__ import annotations

import json
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


def ci_verdict(runs: list[dict[str, object]], sha: str) -> tuple[bool, str]:
    """Decide from `gh run list` rows whether CI is green for `sha`.

    Only runs for exactly this commit count. When a workflow ran more than
    once for it (a re-run), the newest run of that workflow decides.
    Pure function: no network, no subprocess.
    فقط runهای همین commit؛ برای هر workflow جدیدترین run تصمیم می‌گیرد.
    """
    mine = [r for r in runs if r.get("headSha") == sha]
    if not mine:
        return False, "no CI run for this commit yet (not pushed, or CI not started)"
    newest: dict[str, dict[str, object]] = {}
    for run in mine:
        key = str(run.get("name", ""))
        current = newest.get(key)
        if current is None or _run_id(run) > _run_id(current):
            newest[key] = run
    pending = [k for k, r in newest.items() if r.get("status") != "completed"]
    if pending:
        return False, "still running: " + ", ".join(sorted(pending))
    bad = {
        k: r.get("conclusion")
        for k, r in newest.items()
        if r.get("conclusion") != "success"
    }
    if bad:
        detail = ", ".join(f"{k} ({c})" for k, c in sorted(bad.items()))
        return False, "not green: " + detail
    return True, f"{len(newest)} workflow run(s) succeeded"


def _run_id(run: dict[str, object]) -> int:
    value = run.get("databaseId", 0)
    return value if isinstance(value, int) else 0


def fetch_runs() -> list[dict[str, object]]:
    """Recent workflow runs from the GitHub CLI. Raises `RuntimeError` with
    a human-readable reason when `gh` is missing, fails or answers garbage."""
    try:
        done = subprocess.run(
            [
                "gh",
                "run",
                "list",
                "--limit",
                "30",
                "--json",
                "databaseId,headSha,status,conclusion,name",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("the GitHub CLI (`gh`) is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("`gh run list` timed out") from exc
    if done.returncode != 0:
        reason = " ".join(done.stderr.split())[:200] or f"exit {done.returncode}"
        raise RuntimeError(f"`gh run list` failed: {reason}")
    try:
        data = json.loads(done.stdout)
    except ValueError as exc:
        raise RuntimeError("`gh run list` returned invalid JSON") from exc
    rows = data if isinstance(data, list) else None
    if rows is None:
        raise RuntimeError("`gh run list` returned an unexpected shape")
    return [row for row in rows if isinstance(row, dict)]


def require_green_ci(sha: str, skip: bool) -> None:
    """Refuse to continue unless CI is green for `sha` (or `skip` is set)."""
    if skip:
        print("WARNING: --skip-ci-check given; CI status is NOT verified.")
        return
    try:
        ok, detail = ci_verdict(fetch_runs(), sha)
    except RuntimeError as exc:
        raise SystemExit(
            f"Cannot verify CI: {exc}. Check the Actions page yourself, then "
            "rerun with --skip-ci-check."
        ) from exc
    if not ok:
        raise SystemExit(
            f"Refusing to tag: CI is not green for {sha[:7]} -- {detail}. "
            "Wait for it, or rerun with --skip-ci-check."
        )
    print(f"CI is green for {sha[:7]}: {detail}")


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


def cmd_tag(dry_run: bool, skip_ci_check: bool = False) -> None:
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
    require_green_ci(_git("rev-parse", "HEAD"), skip_ci_check)
    print(f"Tagging HEAD ({_git('rev-parse', '--short', 'HEAD')}) as {tag}")
    if dry_run:
        print("(dry run: nothing written)")
        return
    _git("tag", "-a", tag, "-m", f"{tag}")
    print(f"Created {tag}. Publish it with: git push origin {tag}")


def main(argv: list[str]) -> None:
    dry_run = "--dry-run" in argv
    skip_ci_check = "--skip-ci-check" in argv
    args = [a for a in argv if a not in ("--dry-run", "--skip-ci-check")]
    if len(args) == 2 and args[0] == "bump":
        cmd_bump(args[1], dry_run)
    elif len(args) == 1 and args[0] == "tag":
        cmd_tag(dry_run, skip_ci_check)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
