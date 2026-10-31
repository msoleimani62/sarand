"""Quick Context layer L4: the relevant source subset (docs/QUICK_CONTEXT_DESIGN.md,
section 5, decisions D-QC6 and D-QC7). Off unless `--relevant-source` is given.

A small, bounded, deterministic selection of source snippets taken from the files
of this report, chosen by fixed signals -- NOT a summary and NOT a ranking by
meaning. The same input gives the same bytes.

Contract (these bind this module):

- **Universe**: only `included_files`. So every exclusion that already applies to
  `--source` applies here with no extra code, and what L4 can show is always a
  subset of what `--source` could show.
- **Signals** (fixed weights below): `--focus` words in the path, files changed or
  untracked in git, entry points, the path of a secret-pattern match, files with
  TODO-style markers. Score = sum of weights of the signals that fire; ties by
  path, ascending.
- **Budget on bytes** (D-QC6): the output text, with its headers, labels, line
  numbers and footer, plus the fixed `WRAPPER_BYTES` that a renderer adds around
  it (a heading and a code fence), never exceeds `TOKENS * 3` UTF-8 bytes. Three
  bytes per token is a deliberately conservative estimate, not a promise about
  any model's tokenizer. The order of what is kept when space is short: file
  headers first (in score order), then snippets (in score order); a snippet is
  dropped before a header, and dropped items are counted.
- **No redundant files**: files with identical content (`stats.duplicate_files`)
  count as one candidate; only the first path is shown, the others are named.
- **Secrets** (D-QC7): the content of a file in `excluded_secret_files` is never
  read; a path that `looks_like_secret_path` is never a candidate; and EVERY line
  of EVERY snippet goes through `scan_line` just before it is written -- a match is
  replaced by a marker naming the pattern, never the value. Limit: a secret that no
  pattern recognises is not withheld; that is the same limit `--source` has.
- **Cost**: only the files whose header is kept are read (at most `MAX_FILES`,
  20), each with a size cap and a path-safety check (inside the project root, a
  regular file, no link out).

لایه‌ی L4: زیرمجموعه‌ی کد منبعِ مرتبط. فقط با `--relevant-source` فعال می‌شود.
دامنه‌ی انتخاب فقط `included_files` است؛ سقف روی بایت است (هر توکن ۳ بایت،
تخمین محافظه‌کارانه)؛ هر خطِ هر snippet قبل از نوشتن با `scan_line` بررسی می‌شود؛
فایل‌های هم‌محتوا یکی حساب می‌شوند؛ فقط فایل‌های انتخاب‌شده از دیسک خوانده می‌شوند.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sarand.core.secrets import looks_like_secret_path, scan_line
from sarand.models.results import (
    RelevantFile,
    RelevantSnippet,
    RelevantSource,
    ReportData,
)

TOKENS_DEFAULT = 6000
TOKENS_MIN = 200
TOKENS_MAX = 200_000
BYTES_PER_TOKEN = 3

# Bytes a renderer adds around the text (heading and code fence): reserved, so the
# whole stays under the cap. Markdown adds 34 bytes; the rest is margin.
# بایت‌هایی که رندرکننده دور متن می‌افزاید؛ از سقف کم می‌شود.
WRAPPER_BYTES = 64
_FOOTER_RESERVE = 90

# Signal weights, fixed. Set from the real report of sarand on itself (2026-10-31):
# 132 TODO-style markers spread over many files (so a marker alone must rank low),
# one entry point, a clean git tree. An explicit `--focus` outranks everything.
# وزن‌های ثابت؛ `--focus` صریح از همه بالاتر است.
WEIGHT_FOCUS = 5
WEIGHT_GIT = 4
WEIGHT_ENTRY_POINT = 3
WEIGHT_SECRET_PATH = 2
WEIGHT_TODO = 1

CONTEXT_LINES = 3
HEAD_LINES = 30
MAX_SNIPPET_LINES = 40
MAX_SNIPPETS_PER_FILE = 3
MAX_FILES = 20
MAX_LINE_CHARS = 200
MAX_READ_BYTES = 256 * 1024
_MIN_TRIMMED_LINES = 3
_MAX_SAME_AS = 3

TITLE = "Relevant source -- chosen by fixed rules from this report, not a summary"


def tokens_argument(text: str) -> int:
    """argparse `type=` for `--relevant-source`."""
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid token count {text!r}: expected a whole number"
        ) from None
    if not TOKENS_MIN <= value <= TOKENS_MAX:
        raise argparse.ArgumentTypeError(
            f"token count must be between {TOKENS_MIN} and {TOKENS_MAX}, got {value}"
        )
    return value


@dataclass
class _Candidate:
    path: str
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    signal_lines: dict[int, str] = field(default_factory=dict)
    head_reason: str = ""
    same_as: list[str] = field(default_factory=list)


def _clip_line(text: str) -> str:
    text = text.rstrip("\r\n").expandtabs(4)
    return text if len(text) <= MAX_LINE_CHARS else text[: MAX_LINE_CHARS - 1] + "…"


def _git_paths(data: ReportData) -> set[str]:
    """Paths named by `git status --short` and by the untracked list."""
    paths: set[str] = set(data.git.untracked)
    for line in data.git.status.splitlines():
        if len(line) < 4:
            continue
        name = line[3:]
        if " -> " in name:
            name = name.split(" -> ", 1)[1]
        paths.add(name.strip().strip('"'))
    return paths


def _bump(
    cands: dict[str, _Candidate], path: str, weight: int, reason: str
) -> _Candidate:
    cand = cands.setdefault(path, _Candidate(path=path))
    if reason not in cand.reasons:
        cand.reasons.append(reason)
        cand.score += weight
    return cand


def _collect(data: ReportData, focus: str) -> dict[str, _Candidate]:
    included = {p.as_posix() for p in data.included_files}
    excluded = {Path(p).as_posix() for p in data.excluded_secret_files}
    allowed = {
        p for p in included if p not in excluded and not looks_like_secret_path(p)
    }
    cands: dict[str, _Candidate] = {}

    words = [w for w in focus.lower().split() if w]
    for path in sorted(allowed):
        if words and any(w in path.lower() for w in words):
            cand = _bump(cands, path, WEIGHT_FOCUS, "matches --focus")
            cand.head_reason = cand.head_reason or "named by --focus"

    for path in sorted(_git_paths(data) & allowed):
        cand = _bump(cands, path, WEIGHT_GIT, "changed in git")
        cand.head_reason = cand.head_reason or "changed in git"

    for entry in data.detection.entry_points:
        if entry in allowed:
            cand = _bump(cands, entry, WEIGHT_ENTRY_POINT, "entry point")
            cand.head_reason = cand.head_reason or "entry point"

    for finding in data.secret_findings:
        if finding.path in allowed:
            cand = _bump(
                cands, finding.path, WEIGHT_SECRET_PATH, "secret-pattern match"
            )
            cand.signal_lines.setdefault(finding.line_number, "secret-pattern match")

    for todo in data.todos:
        if todo.path in allowed:
            cand = _bump(cands, todo.path, WEIGHT_TODO, "has TODO-style marker")
            cand.signal_lines.setdefault(todo.line_number, f"{todo.kind} marker")
    return cands


def _merge_duplicates(
    cands: dict[str, _Candidate], data: ReportData
) -> list[_Candidate]:
    """Candidates with identical content count as one: the first path of the
    group (in the group's own order) is kept, the others are named."""
    group_of: dict[str, list[str]] = {}
    for _digest, paths in data.stats.duplicate_files:
        for path in paths:
            group_of[path] = paths
    merged: dict[str, _Candidate] = {}
    for path in sorted(cands):
        cand = cands[path]
        group = group_of.get(path)
        key = next((p for p in group if p in cands), path) if group else path
        target = merged.setdefault(key, _Candidate(path=key))
        target.score = max(target.score, cand.score)
        for reason in cand.reasons:
            if reason not in target.reasons:
                target.reasons.append(reason)
        if path == key:
            target.signal_lines.update(cand.signal_lines)
            target.head_reason = target.head_reason or cand.head_reason
        else:
            target.same_as.append(path)
            target.head_reason = target.head_reason or cand.head_reason
    for target in merged.values():
        if target.path in group_of:
            for other in group_of[target.path]:
                if other != target.path and other not in target.same_as:
                    target.same_as.append(other)
        target.same_as = sorted(set(target.same_as))
    return sorted(merged.values(), key=lambda c: (-c.score, c.path))


def _read_lines(root: Path, rel: str) -> list[str] | None:
    """Lines of a project file, or None when it must not be shown: outside the
    root, not a regular file, a link out, or binary. Only the first
    `MAX_READ_BYTES` are read, so a huge file costs the same as a large one and
    only its head can be shown."""
    try:
        base = root.resolve()
        full = (root / rel).resolve()
        if not full.is_relative_to(base) or not full.is_file():
            return None
        with full.open("rb") as handle:
            raw = handle.read(MAX_READ_BYTES)
    except OSError:
        return None
    if b"\x00" in raw[:4096]:
        return None
    return raw.decode("utf-8", errors="replace").splitlines()


def _windows(cand: _Candidate, total: int) -> list[tuple[int, int, str]]:
    """Merged (start, end, reason) windows around the signal lines, then the
    file head for whole-file signals; capped in number and size."""
    raw: list[tuple[int, int, str]] = []
    for line_no, reason in sorted(cand.signal_lines.items()):
        if 1 <= line_no <= total:
            raw.append(
                (
                    max(1, line_no - CONTEXT_LINES),
                    min(total, line_no + CONTEXT_LINES),
                    reason,
                )
            )
    merged: list[tuple[int, int, str]] = []
    for start, end, reason in raw:
        if merged and start <= merged[-1][1] + 1:
            prev = merged[-1]
            joined = prev[2] if reason in prev[2] else f"{prev[2]}; {reason}"
            merged[-1] = (prev[0], max(prev[1], end), joined)
        else:
            merged.append((start, end, reason))
    if cand.head_reason and total:
        head = (1, min(total, HEAD_LINES), cand.head_reason)
        if merged and merged[0][0] <= HEAD_LINES:
            first = merged[0]
            merged[0] = (1, max(first[1], head[1]), f"{head[2]}; {first[2]}")
        else:
            merged.insert(0, head)
    capped = []
    for start, end, reason in merged[:MAX_SNIPPETS_PER_FILE]:
        capped.append((start, min(end, start + MAX_SNIPPET_LINES - 1), reason))
    return capped


def _snippet(lines: list[str], window: tuple[int, int, str]) -> RelevantSnippet:
    """Build one snippet; every line passes `scan_line` right here, just before
    it can be written."""
    start, end, reason = window
    width = len(str(end))
    shown: list[str] = []
    for number in range(start, end + 1):
        text = _clip_line(lines[number - 1])
        names = scan_line(text)
        if names:
            text = f'[line withheld: matches pattern "{names[0]}"]'
        shown.append(f"{number:>{width}}| {text}")
    return RelevantSnippet(start=start, end=end, reason=reason, lines=shown)


def _header(cand: _Candidate) -> str:
    why = "; ".join(cand.reasons) or "selected"
    out = f"## {cand.path} -- {why} (score {cand.score})"
    if cand.same_as:
        names = ", ".join(cand.same_as[:_MAX_SAME_AS])
        more = len(cand.same_as) - _MAX_SAME_AS
        out += f"\n(same content: {names}{f', +{more} more' if more > 0 else ''})"
    return out


def _snippet_text(snippet: RelevantSnippet) -> str:
    return f"-- lines {snippet.start}-{snippet.end}: {snippet.reason}\n" + "\n".join(
        snippet.lines
    )


def _size(text: str) -> int:
    return len(text.encode("utf-8"))


def select_relevant_source(
    data: ReportData, tokens: int = TOKENS_DEFAULT, focus: str = ""
) -> RelevantSource:
    """Select and format L4. Deterministic; reads only the files it keeps."""
    cap = tokens * BYTES_PER_TOKEN
    result = RelevantSource(tokens=tokens, bytes_cap=cap)
    room = cap - WRAPPER_BYTES - _FOOTER_RESERVE
    if room < _size(TITLE) + 1:
        return result

    candidates = _merge_duplicates(_collect(data, focus), data)
    used = _size(TITLE) + 1  # the title and its newline
    chosen: list[tuple[_Candidate, list[str]]] = []

    # Pass 1: headers, in score order. A file is read only when its header fits.
    # پاس اول: هدرها به ترتیب امتیاز؛ فایل فقط وقتی هدرش جا شود خوانده می‌شود.
    for index, cand in enumerate(candidates):
        block = _header(cand)
        if len(chosen) >= MAX_FILES or used + _size(block) + 1 > room:
            result.omitted_files = len(candidates) - index
            break
        lines = _read_lines(data.project_root, cand.path)
        if lines is None:
            result.unreadable_files += 1
            continue
        chosen.append((cand, lines))
        used += _size(block) + 1

    # Pass 2: snippets, in score order, whole where they fit, trimmed when only
    # part fits, dropped below three lines.
    # پاس دوم: snippetها به ترتیب امتیاز؛ کامل، یا کوتاه‌شده، یا حذف.
    per_file: dict[str, list[RelevantSnippet]] = {cand.path: [] for cand, _ in chosen}
    for cand, lines in chosen:
        for window in _windows(cand, len(lines)):
            fitted = _fit(_snippet(lines, window), room - used)
            if fitted is None:
                result.omitted_snippets += 1
                continue
            used += _size(_snippet_text(fitted)) + 1
            per_file[cand.path].append(fitted)
            result.withheld_lines += sum(
                1 for s in fitted.lines if "[line withheld:" in s
            )

    parts = [TITLE]
    for cand, _ in chosen:
        parts.append(_header(cand))
        parts.extend(_snippet_text(snip) for snip in per_file[cand.path])
        result.files.append(
            RelevantFile(
                path=cand.path,
                why=list(cand.reasons),
                score=cand.score,
                same_as=list(cand.same_as),
                snippets=per_file[cand.path],
            )
        )
    if result.omitted_files or result.omitted_snippets:
        parts.append(
            f"(+{result.omitted_files} more file(s) not shown, "
            f"{result.omitted_snippets} snippet(s) omitted)"
        )
    result.text = "\n".join(parts)
    result.bytes_used = _size(result.text) + WRAPPER_BYTES
    return result


def _fit(snippet: RelevantSnippet, room: int) -> RelevantSnippet | None:
    """The snippet if it fits in `room` bytes (with its separator), else its
    longest prefix that does (at least three lines), else None."""
    total = len(snippet.lines)
    for count in range(total, 0, -1):
        if count < total and count < _MIN_TRIMMED_LINES:
            break
        trial = RelevantSnippet(
            start=snippet.start,
            end=snippet.start + count - 1,
            reason=snippet.reason + (" (trimmed)" if count < total else ""),
            lines=snippet.lines[:count],
        )
        if _size(_snippet_text(trial)) + 1 <= room:
            return trial
    return None


_EMPTY_NOTE = "(the budget is too small to show any file)"


def relevant_source_text(rs: RelevantSource) -> str:
    """The text every renderer shows: the canonical block, or a note when the
    budget was too small for a single header."""
    return rs.text or _EMPTY_NOTE


def relevant_source_payload(rs: RelevantSource) -> dict[str, Any]:
    """The JSON form: the budget (as D-QC6 requires), the text the budget
    applies to, and an index of what it shows. The index is metadata about the
    text, not a second copy of the source."""
    return {
        "budget": {
            "tokens": rs.tokens,
            "bytes_cap": rs.bytes_cap,
            "bytes_used": rs.bytes_used,
            "bytes_per_token": BYTES_PER_TOKEN,
            "wrapper_bytes": WRAPPER_BYTES,
        },
        "text": rs.text,
        "files": [
            {
                "path": f.path,
                "why": f.why,
                "score": f.score,
                "same_as": f.same_as,
                "snippets": [
                    {"start": s.start, "end": s.end, "reason": s.reason}
                    for s in f.snippets
                ],
            }
            for f in rs.files
        ],
        "omitted_files": rs.omitted_files,
        "omitted_snippets": rs.omitted_snippets,
        "withheld_lines": rs.withheld_lines,
        "unreadable_files": rs.unreadable_files,
    }
