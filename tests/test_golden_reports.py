"""Golden / representative-report regression suite (AGENTS.md section 5.21).

Renders each fixture in ``_golden_fixtures.py`` through every text-based
renderer and compares the (normalized) output byte-for-byte against a
stored snapshot under ``golden/``. Structural regressions in analyzers,
report structure, health scoring, or source inclusion that pass the
existing "does the output contain X" tests can still change these
snapshots -- that's the point (see ``golden/README.md``).

Deliberately renderer-level, not scan-level: ``ReportData`` is built by
hand here, so every field is fixed in advance and the suite needs no
network access and no optional external tool (ruff/cargo/go/... are
never invoked). ``pdf.py`` is excluded on purpose -- it always shells
out to a real, optionally-installed tool and has no snapshot-able
in-process text output.

مجموعه‌تست رگرسیون golden / گزارش‌نمونه (بخش ۵.۲۱ AGENTS.md).

هر فیکسچر در ``_golden_fixtures.py`` را از هر رندرکننده‌ی متنی عبور
می‌دهد و خروجی (نرمال‌شده) را بایت‌به‌بایت با یک snapshot ذخیره‌شده زیر
``golden/`` مقایسه می‌کند. رگرسیون‌های ساختاری در آنالایزرها، ساختار
گزارش، امتیازدهی سلامت یا درج سورس -- حتی اگر از تست‌های موجودِ «آیا
خروجی شامل X هست» عبور کنند -- می‌توانند این snapshotها را تغییر دهند؛
دقیقاً همین هدف این مجموعه‌تست است (به ``golden/README.md`` نگاه کنید).

عمداً در سطح رندرکننده است، نه در سطح اسکن: ``ReportData`` اینجا
دستی ساخته می‌شود، پس هر فیلد از پیش ثابت است و این مجموعه‌تست نه به
دسترسی شبکه نیاز دارد و نه به هیچ ابزار بیرونیِ اختیاری (ruff/cargo/go/...
هرگز صدا زده نمی‌شوند). ``pdf.py`` عمداً کنار گذاشته شده -- همیشه به یک
ابزار واقعی و اختیاراً-نصب‌شده متکی است و خروجی متنیِ درون‌فرآیندیِ
قابل-snapshot ندارد.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import tempfile
from pathlib import Path

import pytest
from _golden_fixtures import FIXTURES
from sarand.renderers import html, json_renderer, markdown, sarif, text

GOLDEN_DIR = Path(__file__).parent / "golden"

# One (renderer, file extension) pair per snapshot-able format.
# یک جفت (رندرکننده، پسوند فایل) برای هر فرمت قابل-snapshot.
RENDERERS = {
    "md": markdown,
    "json": json_renderer,
    "txt": text,
    "sarif.json": sarif,
    "html": html,
}

# Set SARAND_UPDATE_GOLDEN=1 to (re)write the stored snapshots instead of
# comparing against them -- use only after confirming the new output is
# correct, and review the diff before committing.
# برای (باز)نوشتن snapshotهای ذخیره‌شده به‌جای مقایسه با آن‌ها،
# SARAND_UPDATE_GOLDEN=1 را ست کنید -- فقط بعد از اطمینان از درستیِ خروجیِ
# جدید استفاده کنید و پیش از commit کردن، diff را مرور کنید.
_UPDATE = os.environ.get("SARAND_UPDATE_GOLDEN") == "1"


def _normalize(rendered: str, root: Path) -> str:
    """Strip the non-deterministic values a renderer can embed: the
    fixture's own (random tempdir) absolute path and its URI form.
    ``root.name`` itself is made deterministic by the caller (a fixed
    subdirectory name, not the random tempdir's own name) so it needs
    no normalization here -- see ``_fixture_root``.

    مقادیر غیرقطعیِ ممکن در یک رندرکننده را حذف می‌کند: مسیر مطلقِ خودِ
    فیکسچر (که در یک tempdir تصادفی قرار دارد) و شکل URI آن. خودِ
    ``root.name`` توسط فراخواننده قطعی می‌شود (یک نام زیرپوشه‌ی ثابت، نه
    نام خودِ tempdir تصادفی) پس اینجا نیازی به نرمال‌سازی ندارد --
    ``_fixture_root`` را ببینید.
    """
    raw = str(root)

    # BUG FIX, real root cause (found via the full CI log, not guessed
    # this time -- see AGENTS.md 5.32): this function used to replace
    # the plain absolute path FIRST and the `file://` URI SECOND. On
    # Linux `raw` ("/tmp/.../hybrid-project") is a literal substring of
    # `root.as_uri()` ("file:///tmp/.../hybrid-project/") -- both use
    # forward slashes -- so the plain-path replace *accidentally*
    # already consumed the path portion inside the URI, leaving a
    # half-normalized "file://<PROJECT_ROOT>/" behind; the dedicated
    # URI-matching step that ran after found nothing left to match, so
    # it was silently a no-op. That accidental leftover is exactly what
    # got captured into the golden files back in section 5.21. On
    # Windows, `raw` uses backslashes and `.as_uri()` always uses
    # forward slashes, so the plain-path replace never touches the URI
    # at all -- it survives fully intact down to the dedicated
    # URI-matching step, which *does* fire there and produces a
    # different, fully-normalized "<PROJECT_ROOT_URI>/" with no
    # "file://" left in front of it. Two platforms, two different
    # amounts of normalization applied to the exact same field, purely
    # because of replace-order -- not a Windows bug at all. Fixed by
    # doing the URI match FIRST, unconditionally, so both platforms
    # produce the same "<PROJECT_ROOT_URI>/" every time; the golden
    # sarif.json files were regenerated to match (see 5.32).
    #
    # اصلاح باگ، علت ریشه‌ای واقعی (از روی لاگ کاملِ CI پیدا شد، این‌بار
    # حدس نیست -- به AGENTS.md بخش ۵.۳۲ نگاه کنید): این تابع قبلاً اول
    # مسیر مطلق ساده را جایگزین می‌کرد و بعد URI با پیشوند `file://` را.
    # روی لینوکس، `raw` ("/tmp/.../hybrid-project") زیررشته‌ی عینیِ
    # `root.as_uri()` ("file:///tmp/.../hybrid-project/") است -- هر دو
    # از اسلش رو-به-جلو استفاده می‌کنند -- پس جایگزینیِ مسیرِ ساده
    # *تصادفاً* بخش مسیرِ داخل URI را از قبل مصرف می‌کرد و یک
    # "file://<PROJECT_ROOT>/" نیمه‌نرمال‌شده باقی می‌گذاشت؛ گامِ
    # اختصاصیِ تطبیقِ URI که بعدش اجرا می‌شد چیزی برای تطبیق پیدا
    # نمی‌کرد، پس خاموشانه بی‌اثر بود. همان باقیمانده‌ی تصادفی دقیقاً
    # همان چیزی است که در بخش ۵.۲۱ در golden fileها ضبط شد. روی ویندوز،
    # `raw` از بک‌اسلش استفاده می‌کند و `.as_uri()` همیشه از اسلش
    # رو-به-جلو، پس جایگزینیِ مسیرِ ساده اصلاً به URI دست نمی‌زند -- تا
    # گامِ اختصاصیِ تطبیقِ URI کاملاً دست‌نخورده باقی می‌ماند، که *آنجا*
    # واقعاً شلیک می‌کند و یک "<PROJECT_ROOT_URI>/" کاملاً نرمال‌شده و
    # بدون هیچ "file://" جلویش تولید می‌کند. دو سیستم‌عامل، دو مقدار
    # متفاوت از نرمال‌سازی روی دقیقاً همان فیلد، فقط به‌خاطر ترتیبِ
    # replace -- نه اصلاً باگی مخصوص ویندوز. با انجامِ تطبیقِ URI
    # *اول*، بدون قید و شرط، اصلاح شد تا هر دو سیستم‌عامل همیشه همان
    # "<PROJECT_ROOT_URI>/" را تولید کنند؛ فایل‌های golden sarif.json هم
    # برای تطبیق بازتولید شدند (به ۵.۳۲ نگاه کنید).
    uri_pattern = re.compile(
        re.escape("file://") + r".*?" + re.escape(root.name) + r"/?",
        re.IGNORECASE,
    )
    out = uri_pattern.sub("<PROJECT_ROOT_URI>/", rendered)

    out = out.replace(raw, "<PROJECT_ROOT>")
    # Windows also JSON-escapes any backslash left in `raw` (e.g.
    # "C:\Users\...\hybrid-project" -> `\\` in a JSON string) for the
    # plain (non-URI) `project_root` field in json_renderer.py -- try
    # that form too. A no-op on Linux/macOS (no backslashes to begin
    # with).
    # ویندوز هر بک‌اسلشِ باقی‌مانده در `raw` را هم برای فیلدِ ساده‌ی
    # (غیر-URI) `project_root` در json_renderer.py به‌صورت JSON
    # escape می‌کند (مثلاً "C:\Users\...\hybrid-project" به `\\` در یک
    # رشته‌ی JSON) -- این شکل را هم امتحان کن. روی لینوکس/مک بی‌اثر است
    # (از اول بک‌اسلشی وجود ندارد).
    escaped = raw.replace("\\", "\\\\")
    if escaped != raw:
        out = out.replace(escaped, "<PROJECT_ROOT>")
    return out


def _fixture_root(tmp: str, fixture_name: str) -> Path:
    """A subdirectory with a fixed, fixture-specific name inside the
    (randomly named) tempdir -- so ``project_root.name`` (embedded
    as-is by every renderer's title/header) is deterministic too,
    without needing its own normalization rule.

    زیرپوشه‌ای با نامی ثابت و مخصوص فیکسچر درون tempdir (که نامش تصادفی
    است) -- تا ``project_root.name`` (که عیناً در تیتر/سربرگ هر
    رندرکننده جاسازی می‌شود) هم بدون نیاز به قاعده‌ی نرمال‌سازیِ
    جداگانه، قطعی باشد.
    """
    root = Path(tmp) / f"{fixture_name}-project"
    root.mkdir()
    return root


def _golden_path(fixture_name: str, ext: str) -> Path:
    return GOLDEN_DIR / f"{fixture_name}.{ext}"


def _json_diff_message(actual: object, expected: object) -> str:
    """A real, complete unified diff for a failed JSON/SARIF
    comparison, instead of relying on pytest's own dict-repr
    truncation (which on a large nested dict shows only a short head
    and tail of each side -- exactly what made three rounds of
    Windows-only sarif.json CI failures hard to diagnose from the
    GitHub Actions summary box alone: the actual differing field was
    never visible, only a few characters near the end of a huge repr).
    Pretty-printed with sorted keys so the diff lines up field by
    field regardless of insertion order.

    یک unified diffِ واقعی و کامل برای یک مقایسه‌ی JSON/SARIF ناموفق،
    به‌جای تکیه بر truncationِ خودِ pytest روی repr دیکشنری (که روی
    یک دیکشنریِ تودرتوی بزرگ فقط یک سر و ته کوتاه از هر طرف را نشان
    می‌دهد -- دقیقاً همان چیزی که سه دور شکست CI مخصوص sarif.json در
    ویندوز را از روی باکس خلاصه‌ی GitHub Actions سخت‌تشخیص کرد: فیلد
    واقعاً متفاوت هرگز دیده نمی‌شد، فقط چند کاراکتر نزدیک انتهای یک
    repr غول‌پیکر). با کلیدهای مرتب‌شده pretty-print شده تا diff
    صرف‌نظر از ترتیب درج، فیلد به فیلد هم‌تراز شود.
    """
    actual_lines = json.dumps(actual, indent=2, sort_keys=True).splitlines()
    expected_lines = json.dumps(expected, indent=2, sort_keys=True).splitlines()
    diff = difflib.unified_diff(
        expected_lines, actual_lines, fromfile="expected (golden)", tofile="actual"
    )
    return "\n".join(diff)


@pytest.mark.parametrize("fixture_name", sorted(FIXTURES))
@pytest.mark.parametrize("ext", sorted(RENDERERS))
def test_renderer_output_matches_golden_snapshot(fixture_name: str, ext: str) -> None:
    renderer = RENDERERS[ext]
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture_root(tmp, fixture_name)
        data = FIXTURES[fixture_name](root)
        rendered = renderer.render(data, include_source=True, full_output=False)
        normalized = _normalize(rendered, root)

        # JSON/SARIF: compare parsed structures, not raw bytes -- dict key
        # order is already deterministic (insertion order) but this also
        # gives a much clearer pytest diff on failure than a giant string.
        # JSON/SARIF: ساختار پارس‌شده مقایسه می‌شود، نه بایت خام -- ترتیب
        # کلید دیکشنری همین الان هم قطعی است (ترتیب درج) اما این کار روی
        # شکست، یک diff بسیار خواناتر از یک رشته‌ی غول‌پیکر به pytest می‌دهد.
        is_json_like = ext in ("json", "sarif.json")

        golden_path = _golden_path(fixture_name, ext)
        if _UPDATE:
            golden_path.parent.mkdir(parents=True, exist_ok=True)
            golden_path.write_text(normalized, encoding="utf-8")
            return

        assert golden_path.exists(), (
            f"No golden snapshot at {golden_path}. Run once with "
            "SARAND_UPDATE_GOLDEN=1 to create it, then review the diff."
        )
        expected = golden_path.read_text(encoding="utf-8")

        if is_json_like:
            actual_obj = json.loads(normalized)
            expected_obj = json.loads(expected)
            assert actual_obj == expected_obj, _json_diff_message(
                actual_obj, expected_obj
            )
        else:
            assert normalized == expected


def test_every_fixture_has_a_golden_snapshot_for_every_format() -> None:
    """Guard against a fixture or renderer being added without ever
    running with SARAND_UPDATE_GOLDEN=1 -- silently skipped coverage
    would defeat the point of this suite.

    نگهبان در برابر افزوده‌شدن یک فیکسچر یا رندرکننده بدون اجرای حتی یک
    بار با SARAND_UPDATE_GOLDEN=1 -- پوشش خاموش‌رد-شده هدف این
    مجموعه‌تست را بی‌اثر می‌کند.
    """
    missing = [
        str(_golden_path(fixture_name, ext))
        for fixture_name in FIXTURES
        for ext in RENDERERS
        if not _golden_path(fixture_name, ext).exists()
    ]
    assert not missing, f"Missing golden snapshot(s): {missing}"
