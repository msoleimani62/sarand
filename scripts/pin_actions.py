#!/usr/bin/env python3
"""Pin every `uses:` in `.github/workflows` to the commit SHA its tag points at.

A tag such as `actions/checkout@v6` can be moved by whoever controls the action's
repository; a 40-character commit SHA cannot. Pinning turns "whatever the tag
points at on the day of the run" into "exactly this commit", which is the
supply-chain hardening GitHub recommends for third-party actions.

The script needs the network (it asks the GitHub API which commit each ref names),
so the maintainer runs it; nothing in CI does. Dependabot (`.github/dependabot.yml`)
then keeps the pins current and understands the `# vX.Y.Z` comment this script writes.

    python3 scripts/pin_actions.py            # show what would change
    python3 scripts/pin_actions.py --write    # rewrite the workflow files

Set GITHUB_TOKEN to avoid the anonymous API rate limit. After a successful
`--write`, flip `ENFORCE_PINNED` in `tests/test_action_pins.py` to True.

پین‌کردن هر `uses:` در workflowها به SHA کامیتی که تگ به آن اشاره می‌کند. تگ را
صاحب action می‌تواند جابه‌جا کند، SHA کامیت را نه. این اسکریپت به شبکه نیاز دارد
و نگه‌دارنده آن را اجرا می‌کند؛ هیچ‌چیز در CI آن را اجرا نمی‌کند.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

# `uses: owner/repo[/path]@ref  # optional comment`
_USES = re.compile(
    r"^(?P<head>\s*(?:-\s+)?uses:\s*)(?P<action>[^\s@#]+)@(?P<ref>[^\s#]+)"
    r"(?P<tail>\s*#.*)?$"
)
_SHA = re.compile(r"^[0-9a-f]{40}$")

Resolver = Callable[[str, str], str]


def is_pinned(ref: str) -> bool:
    """True when `ref` is already a full commit SHA."""
    return bool(_SHA.fullmatch(ref))


def find_uses(text: str) -> list[tuple[str, str]]:
    """Every (action, ref) in a workflow, local and docker actions excluded."""
    found: list[tuple[str, str]] = []
    for line in text.splitlines():
        match = _USES.match(line)
        if not match:
            continue
        action = match.group("action")
        if action.startswith(("./", "docker://")):
            continue
        found.append((action, match.group("ref")))
    return found


def pin_text(text: str, resolve: Resolver) -> tuple[str, list[tuple[str, str, str]]]:
    """Rewrite unpinned refs to SHAs. Returns the new text and (action, ref, sha) rows."""
    changes: list[tuple[str, str, str]] = []
    out: list[str] = []
    for line in text.split("\n"):
        match = _USES.match(line)
        if not match:
            out.append(line)
            continue
        action = match.group("action")
        ref = match.group("ref")
        if action.startswith(("./", "docker://")) or is_pinned(ref):
            out.append(line)
            continue
        sha = resolve(action, ref)
        changes.append((action, ref, sha))
        out.append(f"{match.group('head')}{action}@{sha} # {ref}")
    return "\n".join(out), changes


def _get(url: str, token: str | None) -> dict[str, object]:
    if not url.startswith("https://api.github.com/"):
        raise ValueError(f"refusing to open a non-GitHub URL: {url}")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "sarand-pin-actions",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    # The scheme and host were checked above: only https://api.github.com/.
    with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310
        payload: dict[str, object] = json.load(response)
    return payload


def github_resolver(token: str | None) -> Resolver:
    """Resolve `owner/repo@ref` to a commit SHA through the GitHub API."""

    def resolve(action: str, ref: str) -> str:
        owner, repo = action.split("/")[:2]
        base = f"https://api.github.com/repos/{owner}/{repo}/git"
        for kind in ("tags", "heads"):
            try:
                data = _get(f"{base}/ref/{kind}/{ref}", token)
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    continue
                raise
            obj = data["object"]
            if not isinstance(obj, dict):
                raise SystemExit(f"unexpected API answer for {action}@{ref}")
            sha = str(obj["sha"])
            if obj["type"] == "tag":  # an annotated tag: peel it to the commit
                peeled = _get(f"{base}/tags/{sha}", token)
                inner = peeled["object"]
                if not isinstance(inner, dict):
                    raise SystemExit(f"unexpected API answer for {action}@{ref}")
                sha = str(inner["sha"])
            return sha
        raise SystemExit(f"cannot resolve {action}@{ref}: no such tag or branch")

    return resolve


def main(argv: list[str]) -> int:
    write = "--write" in argv
    root = Path(__file__).resolve().parent.parent
    resolver = github_resolver(os.environ.get("GITHUB_TOKEN"))
    cache: dict[tuple[str, str], str] = {}

    def cached(action: str, ref: str) -> str:
        key = (action, ref)
        if key not in cache:
            cache[key] = resolver(action, ref)
        return cache[key]

    total = 0
    for path in sorted((root / ".github" / "workflows").glob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        new_text, changes = pin_text(text, cached)
        for action, ref, sha in changes:
            print(f"{path.name}: {action}@{ref} -> {sha}")
        total += len(changes)
        if write and changes:
            path.write_text(new_text, encoding="utf-8")
    if not total:
        print("Every action is already pinned to a commit SHA.")
    elif write:
        print(
            f"Pinned {total} reference(s). "
            "Now set ENFORCE_PINNED = True in tests/test_action_pins.py."
        )
    else:
        print(f"{total} reference(s) would be pinned. Re-run with --write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
