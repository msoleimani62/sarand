"""Quick Context: the compact, deterministic L2 layer of the report
(backlog item 12, "AI-Oriented Context").

Context layers (model-agnostic, no per-model presets -- the backlog
says not to build those without evidence):

- L0 full report -- everything, unchanged
- L1 project summary -- the existing "AI Summary" section
- **L2 Quick Context -- this module**, a short section at the very top
- L3/L4 architecture/risks and relevant source subset -- not built

Evidence-first audit (run on a real report: sarand scanning itself,
1.6 MB, ~410K tokens by the 4-chars-per-token rule of thumb, plus the
golden fixtures):

1. The existing "AI Summary" (L1) is orientation only: languages, type,
   file counts, git state, health score. It has **no test/quality/
   security status, no critical findings, no risks, no components**.
   Those facts exist elsewhere in the report, behind Environment, Git
   and the TODO table (which is unbounded under `--full`), so a reader
   that truncates or skims cannot rely on seeing them.
2. The "Suggested reading order" was misleading on the real report:
   its first 40 entries were 33 alphabetically-ordered analyzer
   plugins (each bucket kept scan order and the substrings
   "analyzers"/"scanners" -- names from sarand's own layout --
   promoted files), and even after sorting by depth the first 10 held
   four docs files and a test file while `cli.py` never appeared.
   Fixed in `suggest_reading_order`: shallow paths first, test files
   never promoted, docs after the entry points, and the two
   sarand-specific substrings removed.
3. Frameworks, "important risks" in an inferential sense and an
   architecture graph are **not** in the report data, so Quick Context
   does not invent them (the backlog: "exact fields must be based on
   current report data"). Everything below is read from existing
   `ReportData` fields; nothing is guessed.

Properties:

- **Deterministic:** a pure function of `ReportData` -- no clock, no
  environment, no randomness, stable ordering everywhere.
- **Does not touch analysis:** it only reads `ReportData`; it adds no
  finding, changes no score and no other section.
- **Bounded:** every list is capped, every string clipped to 120
  characters, dropped items are counted as "(+N more)". Worst case is
  about 6 KiB (~1.5K tokens) for any project; a typical report's block
  is 1-2 KiB (~250-500 tokens). A test pins the worst case.
- **Preserves what matters:** failed checks, health critical failures,
  known issues, tool errors/warnings counts, secret-pattern counts
  (never paths or content), skipped checks and git drift all surface
  here, so skimming only this block still shows what is wrong.

Not covered: frameworks, an inferred risk model, L3/L4, HTML/text
renderers (Markdown and JSON carry it).

Quick Context: لایه‌ی فشرده و قطعیِ L2 گزارش (آیتم ۱۲ backlog).

ممیزی روی یک گزارش واقعی (sarand روی خودش، ۱٫۶ مگابایت، حدود ۴۱۰ هزار
توکن) نشان داد: (۱) «AI Summary» فقط جهت‌یابی است و وضعیت تست/کیفیت/
امنیت، یافته‌های بحرانی، ریسک‌ها و اجزا را ندارد؛ این‌ها پشت Environment،
Git و جدول TODO (که با `--full` نامحدود است) هستند. (۲) «ترتیب مطالعه»
گمراه‌کننده بود: ۴۰ مورد اولش ۳۳ پلاگین آنالایزر بود و `cli.py` و
ماژول‌های `core/` هرگز نمی‌آمدند. (۳) فریمورک‌ها و مدل استنتاجیِ ریسک
در داده‌ی گزارش نیستند و ساخته نمی‌شوند.

ویژگی‌ها: قطعی (تابع محضِ `ReportData`)، بدون دست‌زدن به تحلیل، محدود
(سقف هر فهرست، هر رشته ۱۲۰ نویسه، بدترین حالت حدود ۶ KiB ≈ ۱٫۵ هزار
توکن؛ حالت معمول ۱ تا ۲ KiB) و حافظ آنچه مهم است.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sarand.models.results import CommandResult, ReportData

_CLIP = 120
_MAX_COMPONENTS = 8
_MAX_STRUCTURE = 12
_MAX_CHECKS = 12
_MAX_CRITICAL = 5
_MAX_KNOWN = 5
_MAX_NAMES = 6
_READING_ORDER_LEN = 10

# One top-level entry of the rendered project tree ("├── name/").
# یک ورودی سطح‌بالای درخت پروژه.
_TOP_LEVEL = re.compile(r"^[├└]── (.+)$")


@dataclass
class QuickContext:
    """The L2 block. Plain data, JSON-serialisable via `asdict`."""

    project: str = ""
    primary_language: str = ""
    languages: list[str] = field(default_factory=list)
    project_type: str = ""
    build_system: str = ""
    components: list[str] = field(default_factory=list)
    structure: list[str] = field(default_factory=list)
    total_files: int = 0
    total_loc: int = 0
    tests: list[str] = field(default_factory=list)
    quality: list[str] = field(default_factory=list)
    security: list[str] = field(default_factory=list)
    health: str = ""
    critical_findings: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    reading_order: list[str] = field(default_factory=list)


def _clip(text: str, limit: int = _CLIP) -> str:
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _capped(items: list[str], limit: int) -> list[str]:
    if len(items) <= limit:
        return items
    return [*items[:limit], f"(+{len(items) - limit} more)"]


def _status(result: CommandResult) -> str:
    if result.skipped:
        return "skipped"
    return "passed" if result.passed else "failed"


def _checks(results: list[CommandResult]) -> list[str]:
    return _capped([f"{_clip(r.kind, 60)}: {_status(r)}" for r in results], _MAX_CHECKS)


def _names(results: list[CommandResult], wanted: str) -> list[str]:
    return [_clip(r.kind, 60) for r in results if _status(r) == wanted]


def _component_labels(data: ReportData) -> list[str]:
    info = data.components
    if info is None:
        return []
    labels = [
        _clip(f"{c.path} ({c.role}{', ' + c.kind if c.kind else ''})", 80)
        for c in info.components
        if c.role == "application"
    ] + [
        _clip(f"{c.path} ({c.role}{', ' + c.kind if c.kind else ''})", 80)
        for c in info.components
        if c.role != "application"
    ]
    return _capped(labels, _MAX_COMPONENTS)


def _top_level(tree_text: str) -> list[str]:
    """Top-level directories of the project tree, plus a count of the
    top-level files (dotfiles and manifests are noise here; the reading
    order and Detected Project already name the ones that matter)."""
    matches = (_TOP_LEVEL.match(line) for line in tree_text.splitlines())
    names = [m.group(1) for m in matches if m]
    dirs = [_clip(n, 60) for n in names if n.endswith("/")]
    files = len(names) - len(dirs)
    result = _capped(dirs, _MAX_STRUCTURE)
    if files:
        result.append(f"({files} top-level file(s))")
    return result


def _name_list(names: list[str]) -> str:
    """First few names, with a "(+N more)" tail."""
    shown = ", ".join(names[:_MAX_NAMES])
    extra = len(names) - _MAX_NAMES
    return f"{shown} (+{extra} more)" if extra > 0 else shown


def _risks(data: ReportData, all_results: list[CommandResult]) -> list[str]:
    risks: list[str] = []
    failed = _names(all_results, "failed")
    if failed:
        risks.append(f"{len(failed)} check(s) failed: {_name_list(failed)}")
    skipped = _names(all_results, "skipped")
    if skipped:
        risks.append(
            f"{len(skipped)} check(s) skipped, so the score does not reflect "
            f"them: {_name_list(skipped)}"
        )
    errors = sum(len(r.errors) for r in all_results)
    warnings = sum(len(r.warnings) for r in all_results)
    if errors or warnings:
        risks.append(f"tools reported {errors} error(s) and {warnings} warning(s)")
    if data.secret_findings:
        risks.append(
            f"{len(data.secret_findings)} potential secret(s) found; "
            "affected files are excluded from the report"
        )
    if data.excluded_secret_files:
        risks.append(
            f"{len(data.excluded_secret_files)} credential-shaped file(s) "
            "excluded from the report"
        )
    if data.git.dirty:
        risks.append("working tree has uncommitted changes")
    if data.git.behind:
        risks.append(f"branch is {data.git.behind} commit(s) behind its upstream")
    return risks


def build_quick_context(data: ReportData) -> QuickContext:
    """Build the Quick Context block from a finished `ReportData`.
    Pure and deterministic; never mutates `data`.
    """
    detection = data.detection
    all_results = [*data.test_results, *data.quality_results, *data.security_results]

    critical: list[str] = []
    if data.health is not None:
        critical.extend(_clip(c) for c in data.health.critical_failures[:_MAX_CRITICAL])
        hidden = len(data.health.critical_failures) - _MAX_CRITICAL
        if hidden > 0:
            critical.append(f"(+{hidden} more critical failure(s))")
    critical.extend(_clip(k) for k in data.known_issues[:_MAX_KNOWN])
    hidden_known = len(data.known_issues) - _MAX_KNOWN
    if hidden_known > 0:
        critical.append(f"(+{hidden_known} more known issue(s))")

    health = ""
    if data.health is not None:
        health = (
            f"{data.health.score}/{data.health.max_score} (grade {data.health.grade}), "
            f"confidence {round(data.health.confidence * 100)}%"
        )

    return QuickContext(
        project=_clip(data.project_root.name, 60),
        primary_language=_clip(detection.primary_language, 40),
        languages=[_clip(lang, 30) for lang in detection.languages[:10]],
        project_type=_clip(detection.project_type, 40),
        build_system=_clip(detection.build_system, 40),
        components=_component_labels(data),
        structure=_top_level(data.tree_text),
        total_files=data.stats.total_files,
        total_loc=data.stats.total_loc,
        tests=_checks(data.test_results),
        quality=_checks(data.quality_results),
        security=_checks(data.security_results),
        health=health,
        critical_findings=critical,
        risks=_risks(data, all_results),
        reading_order=[
            _clip(p, 80) for p in data.suggested_reading_order[:_READING_ORDER_LEN]
        ],
    )
