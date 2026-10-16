"""Secret detection: never let a credential end up inside a generated
report. Two independent layers, per AGENTS.md §4.10:

1. Filename-based exclusion -- a file that merely *looks* like a
   credential (id_rsa, .env, a service-account JSON, ...) is dropped
   from the report entirely, regardless of extension, before its
   contents are ever read for embedding.
2. Content-based scanning -- a lightweight, dependency-free regex scan
   over files that *were* included, catching a hardcoded secret sitting
   inside an otherwise ordinary source file (e.g. an AWS key pasted
   into a .py config module). Findings report the location and pattern
   name only -- never the matched value itself, so the finding can't
   leak the very thing it's warning about.

Both layers run unconditionally (not gated behind --security) because
this is a safety rule, not an optional quality check -- see AGENTS.md
§7, priority 1.

Whether a finding counts against the health score is *not* decided here
by guessing from the path. A project lists its deliberate fake
credentials in `.sarand.toml` (`[secrets] fixture_paths`, see
core/secrets_config.py) and `mark_fixture_findings` applies that list.

دو لایه‌ی مستقل، طبق §4.10 در AGENTS.md: (۱) حذف بر اساس نام فایل،
(۲) اسکن محتوایی regex روی فایل‌هایی که وارد گزارش شده‌اند. یافته‌ها فقط
مکان و نام الگو را نگه می‌دارند، هرگز مقدار را. اینکه یک یافته روی امتیاز
سلامت اثر بگذارد یا نه با حدس از مسیر تعیین نمی‌شود؛ پروژه اعتبارنامه‌های
جعلی عمدی‌اش را در `.sarand.toml` (`[secrets] fixture_paths`) فهرست می‌کند.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from fnmatch import fnmatchcase
from pathlib import Path

from sarand.constants import SECRET_FILENAME_PATTERNS, SECRET_PATH_PATTERNS
from sarand.models.results import SecretFinding
from sarand.utils.logging import get_logger

logger = get_logger("secrets")

_FILENAME_RE = [re.compile(p, re.IGNORECASE) for p in SECRET_FILENAME_PATTERNS]
_PATH_RE = [re.compile(p, re.IGNORECASE) for p in SECRET_PATH_PATTERNS]

# Bump whenever a rule's *logic* (a validator, a threshold) changes without
# its regex text changing, so core/cache.py invalidates stale caches.
# هر وقت منطق یک قانون (validator یا آستانه) بدون تغییر متن regex عوض شد،
# این عدد را زیاد کنید تا core/cache.py کش‌های کهنه را باطل کند.
RULES_VERSION = 2

# Lines shorter than this cannot hold any credential the rules know about.
# خطوط کوتاه‌تر از این نمی‌توانند اعتبارنامه‌ای از نوع شناخته‌شده داشته باشند.
_MIN_LINE_LENGTH = 16

# --- Value validators --------------------------------------------------
# A regex alone is too eager for the two "assignment" style rules and for
# URLs; these small checks cut the obvious placeholders without needing a
# dependency. Linear time, no regex.
# فقط regex برای قوانین «انتساب» و URL بیش‌ازحد حریص است؛ این بررسی‌های
# کوچک placeholderهای واضح را حذف می‌کنند، بدون وابستگی، در زمان خطی.

_PLACEHOLDER_MARKERS = (
    "example",
    "changeme",
    "placeholder",
    "redacted",
    "dummy",
    "your_",
    "your-",
    "insert",
    "replace",
    "todo",
    "fixme",
    "xxxx",
    "****",
    "....",
    "<",
    ">",
    "${",
    "{{",
    "%(",
    "%s",
)
_COMMON_URL_PASSWORDS = frozenset(
    {"pass", "password", "passwd", "secret", "user", "admin", "root", "test", "token"}
)


def shannon_entropy(value: str) -> float:
    """Shannon entropy of `value` in bits per character (0.0 when empty)."""
    if not value:
        return 0.0
    total = len(value)
    return -sum(
        (count / total) * math.log2(count / total) for count in Counter(value).values()
    )


def is_placeholder(value: str) -> bool:
    """True for values that are obviously not a real credential."""
    lowered = value.lower()
    if any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
        return True
    return len(set(value)) <= 2


def _looks_random(value: str, minimum_entropy: float = 3.0) -> bool:
    if is_placeholder(value):
        return False
    if not any(ch.isdigit() or ch.isupper() for ch in value):
        return False
    return shannon_entropy(value) >= minimum_entropy


def _password_assignment_ok(match: re.Match[str]) -> bool:
    return _looks_random(match.group("value"))


def _url_password_ok(match: re.Match[str]) -> bool:
    password = match.group("password")
    if is_placeholder(password):
        return False
    return password.lower() not in _COMMON_URL_PASSWORDS


def _openai_key_ok(match: re.Match[str]) -> bool:
    return shannon_entropy(match.group(0)) >= 3.5


@dataclass(frozen=True)
class _Rule:
    """One content rule.

    `needles` are lowercase literals; a line is only handed to the regex when
    it contains at least one of them (a cheap pre-filter that keeps the scan
    fast on ordinary source). `validator` may veto a regex match.

    `needles` رشته‌های ثابت حروف‌کوچک‌اند؛ خط فقط وقتی به regex می‌رسد که
    دست‌کم یکی از آن‌ها را داشته باشد (پیش‌فیلتر ارزان). `validator` می‌تواند
    یک تطابق regex را رد کند.
    """

    name: str
    regex: re.Pattern[str]
    needles: tuple[str, ...]
    validator: Callable[[re.Match[str]], bool] | None = None


# Every pattern is linear-time on adversarial input: no nested quantifiers,
# and every "run of characters then a literal" shape has a lookbehind so the
# match can only start at the beginning of a run (otherwise "eyJ" * 30000
# would be quadratic). tests/test_secrets.py pins this with 100k-char inputs.
# هر الگو روی ورودی خصمانه زمان خطی دارد: بدون کوانتیفایر تودرتو، و هر شکل
# «دنباله‌ی کاراکتر سپس literal» یک lookbehind دارد تا تطابق فقط از ابتدای
# دنباله شروع شود.
_RULES: tuple[_Rule, ...] = (
    _Rule(
        "AWS Access Key ID",
        re.compile(r"(?<![A-Z0-9])AKIA[0-9A-Z]{16}(?![A-Z0-9])"),
        ("akia",),
    ),
    _Rule(
        "AWS Temporary Key ID",
        re.compile(r"(?<![A-Z0-9])ASIA[0-9A-Z]{16}(?![A-Z0-9])"),
        ("asia",),
    ),
    _Rule(
        "Private Key Block",
        re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----"),
        ("private key",),
    ),
    _Rule(
        "Slack Token",
        re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}"),
        ("xox",),
    ),
    _Rule(
        "GitHub Token",
        re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
        ("ghp_", "gho_", "ghu_", "ghs_", "ghr_"),
    ),
    _Rule(
        "GitHub Fine-grained Token",
        re.compile(r"github_pat_[A-Za-z0-9_]{22,}"),
        ("github_pat_",),
    ),
    _Rule(
        "Anthropic API Key",
        re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
        ("sk-ant-",),
    ),
    _Rule(
        "OpenAI API Key",
        re.compile(
            r"(?<![A-Za-z0-9])sk-(?!ant-)(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{32,}"
        ),
        ("sk-",),
        _openai_key_ok,
    ),
    _Rule(
        "Google API Key",
        re.compile(r"(?<![A-Za-z0-9_\-])AIza[0-9A-Za-z_\-]{35}(?![0-9A-Za-z_\-])"),
        ("aiza",),
    ),
    _Rule(
        "Stripe Live Key",
        re.compile(r"(?<![A-Za-z0-9])[sr]k_live_[0-9A-Za-z]{16,}"),
        ("_live_",),
    ),
    _Rule(
        "PyPI Token",
        re.compile(r"pypi-AgEI[A-Za-z0-9_\-]{50,}"),
        ("pypi-agei",),
    ),
    _Rule(
        "npm Token",
        re.compile(r"(?<![A-Za-z0-9])npm_[A-Za-z0-9]{36}(?![A-Za-z0-9])"),
        ("npm_",),
    ),
    _Rule(
        "JSON Web Token",
        re.compile(
            r"(?<![A-Za-z0-9_\-])eyJ[A-Za-z0-9_\-]{10,}"
            r"\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"
        ),
        ("eyj",),
    ),
    _Rule(
        "Credentials in URL",
        re.compile(
            r"(?<![A-Za-z0-9+.\-])[A-Za-z][A-Za-z0-9+.\-]*://"
            r"(?P<user>[^\s:/@'\"<>]+):(?P<password>[^\s@/'\"<>]{3,})"
            r"@(?P<host>[^\s/'\"<>]+)"
        ),
        ("://",),
        _url_password_ok,
    ),
    _Rule(
        "Generic API Key Assignment",
        re.compile(
            r"(?i)(?:api[_-]?key|secret[_-]?key|access[_-]?token)"
            r"\s*[:=]\s*[\"'][A-Za-z0-9_\-]{16,}[\"']"
        ),
        (
            "api_key",
            "api-key",
            "apikey",
            "secret_key",
            "secret-key",
            "secretkey",
            "access_token",
            "access-token",
            "accesstoken",
        ),
    ),
    _Rule(
        "Hardcoded Password Assignment",
        re.compile(
            r"(?i)(?<![A-Za-z0-9])(?:password|passwd|pwd|secret|token)"
            r"[A-Za-z0-9_]{0,24}[\"']?\s*[:=]\s*[\"'](?P<value>[^\"'\s]{12,})[\"']"
        ),
        ("password", "passwd", "pwd", "secret", "token"),
        _password_assignment_ok,
    ),
)

# One credential on one line should read as one finding: the password rule is
# a catch-all, so any more specific rule that matched the same line wins
# (e.g. a PyPI token assigned to a variable called TOKEN).
# یک اعتبارنامه روی یک خط باید یک یافته باشد: قانون password فراگیر است، پس
# هر قانون خاص‌تری که روی همان خط تطابق داشته باشد مقدم است (مثلاً توکن PyPI
# که به متغیری به نام TOKEN داده شده).
_CATCH_ALL_RULE = "Hardcoded Password Assignment"


# One alternation of every rule's needles: ordinary source lines contain none
# of them, so a single pass over the lowered line rejects almost every line
# before any per-rule work happens.
# یک alternation از همه‌ی needleهای قانون‌ها: خطوط معمولی هیچ‌کدام را ندارند،
# پس یک گذر روی خط، تقریباً همه‌ی خطوط را پیش از کار هر قانون رد می‌کند.
_ANY_NEEDLE = re.compile(
    "|".join(
        re.escape(needle)
        for needle in sorted(
            {needle for rule in _RULES for needle in rule.needles},
            key=len,
            reverse=True,
        )
    )
)


def looks_like_secret_filename(name: str) -> bool:
    """Return True if a bare filename (not full path) looks credential-shaped."""
    return any(pattern.search(name) for pattern in _FILENAME_RE)


def looks_like_secret_path(path: str) -> bool:
    """Return True if a project-relative path looks credential-shaped.

    Applies the bare-name patterns to the last component and the
    path-suffix patterns (e.g. `.docker/config.json`, `.aws/credentials`)
    to the whole POSIX-style path.

    الگوهای نام فایل روی آخرین مؤلفه و الگوهای پسوند مسیر (مثل
    `.docker/config.json`) روی کل مسیر به‌سبک POSIX اعمال می‌شوند.
    """
    posix = path.replace("\\", "/")
    name = posix.rsplit("/", 1)[-1]
    if looks_like_secret_filename(name):
        return True
    return any(pattern.search(posix) for pattern in _PATH_RE)


def content_pattern_names() -> list[str]:
    """Public accessor for the content-scan pattern names.

    Exists so other modules don't reach into the private rule table.
    """
    return [rule.name for rule in _RULES]


def content_rule_signatures() -> list[str]:
    """One stable string per rule (name + regex text) plus the rules version.

    core/cache.py hashes these so that changing a rule invalidates every
    cache -- a cache must never silently miss a finding a rule change would
    have caught in unchanged files.

    core/cache.py این رشته‌ها را هش می‌کند تا تغییر یک قانون همه‌ی کش‌ها را
    باطل کند.
    """
    return [f"rules-v{RULES_VERSION}"] + [
        f"{rule.name}={rule.regex.pattern}" for rule in _RULES
    ]


def scan_line(line: str) -> list[str]:
    """Names of every rule that matches one line (never the matched value)."""
    if len(line) < _MIN_LINE_LENGTH:
        return []
    lowered = line.lower()
    if _ANY_NEEDLE.search(lowered) is None:
        return []
    names: list[str] = []
    for rule in _RULES:
        if not any(needle in lowered for needle in rule.needles):
            continue
        for match in rule.regex.finditer(line):
            if rule.validator is None or rule.validator(match):
                names.append(rule.name)
                break
    if _CATCH_ALL_RULE in names and len(names) > 1:
        names.remove(_CATCH_ALL_RULE)
    return names


def scan_for_secrets(root: Path, included_files: list[Path]) -> list[SecretFinding]:
    """Scan already-included files' content for hardcoded-secret patterns.

    Args:
        root: Project root.
        included_files: Relative paths of files that passed the
            filename-exclusion layer and will be embedded in the report.

    Returns:
        Findings with location + pattern name only, never the matched value.
        `is_test_fixture` is always False here: whether a path is a
        deliberate fixture is a project decision applied afterwards by
        `mark_fixture_findings`, not a guess made while scanning.
    """
    findings: list[SecretFinding] = []
    for rel in included_files:
        path = root / rel
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                for lineno, line in enumerate(fh, start=1):
                    for pattern_name in scan_line(line):
                        findings.append(
                            SecretFinding(
                                path=str(rel),
                                line_number=lineno,
                                pattern_name=pattern_name,
                            )
                        )
        except OSError:
            continue

    if findings:
        logger.warning("Found %d potential secret(s) in included files", len(findings))
    return findings


def matches_fixture_path(path: str, fixture_paths: Sequence[str]) -> bool:
    """True when the POSIX-style `path` matches any `fixture_paths` glob.

    Semantics are `fnmatch` (case-sensitive; `*` also crosses `/`).
    معنای glob همان `fnmatch` است (حساس به حروف؛ `*` از `/` هم می‌گذرد).
    """
    posix = path.replace("\\", "/")
    return any(fnmatchcase(posix, pattern) for pattern in fixture_paths)


def mark_fixture_findings(
    findings: Iterable[SecretFinding], fixture_paths: Sequence[str]
) -> list[SecretFinding]:
    """Return `findings` with `is_test_fixture` set from the project allowlist.

    The flag is *recomputed* for every finding (not OR-ed with the old
    value), so a finding reloaded from an older cache cannot keep a stale
    "fixture" mark after the allowlist changed.

    پرچم برای هر یافته از نو محاسبه می‌شود (نه OR با مقدار قبلی)، پس
    یافته‌ای که از کش قدیمی برمی‌گردد نمی‌تواند علامت «fixture» کهنه نگه دارد.
    """
    return [
        replace(f, is_test_fixture=matches_fixture_path(f.path, fixture_paths))
        for f in findings
    ]


def exclude_flagged_files(
    included: list[Path],
    excluded: list[Path],
    findings: list[SecretFinding],
) -> tuple[list[Path], list[Path]]:
    """Move any file with a content-level finding out of `included`.

    A finding on its own is just a warning; this is the step that turns
    it into an actual guarantee. A file whose content matched a secret
    pattern must never have its full source embedded in the report --
    otherwise the "finding" would flag the exact secret sitting three
    sections below it in the same document.

    یک finding به‌تنهایی فقط یک هشدار است؛ این تابع همان مرحله‌ای است که
    آن را به یک تضمین واقعی تبدیل می‌کند. فایلی که محتوایش با یک الگوی
    secret مطابقت داشته هرگز نباید سورس کاملش در گزارش embed شود --
    وگرنه همان "finding" دقیقاً همان secretای را که چند بخش پایین‌تر در
    همان سند نشسته، پرچم‌گذاری کرده بود.

    Args:
        included: Files currently slated for full-source embedding.
        excluded: Files already excluded (filename-based, §4.10).
        findings: Result of scan_for_secrets() over `included`.

    Returns:
        (new_included, new_excluded) with flagged files moved across.
    """
    flagged = {Path(f.path) for f in findings}
    if not flagged:
        return included, excluded

    new_included = [p for p in included if p not in flagged]
    new_excluded = sorted(set(excluded) | flagged)
    return new_included, new_excluded


def exclude_paths(
    included: list[Path], excluded: list[Path], paths: Iterable[Path]
) -> tuple[list[Path], list[Path]]:
    """Move the given paths out of `included`, but only those actually in it.

    Used for files another engine (gitleaks) flagged. Unlike
    `exclude_flagged_files` it ignores paths that are not slated for
    embedding (gitleaks also reports files that exist only in git history),
    so the "excluded" list never names files the report would not have
    contained anyway.

    برای فایل‌هایی که موتور دیگری (gitleaks) پرچم زده. مسیرهایی که قرار
    نبوده embed شوند (مثلاً فقط در تاریخچه‌ی گیت هستند) نادیده گرفته
    می‌شوند.
    """
    flagged = set(paths) & set(included)
    if not flagged:
        return included, excluded

    new_included = [p for p in included if p not in flagged]
    new_excluded = sorted(set(excluded) | flagged)
    return new_included, new_excluded
