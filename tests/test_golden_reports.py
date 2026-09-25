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
    out = rendered.replace(raw, "<PROJECT_ROOT>")
    # BUG FIX: on Windows `raw` contains backslashes (e.g.
    # "C:\Users\...\hybrid-project"), and json_renderer.py/sarif.py
    # embed it inside a JSON string, where json.dumps escapes every
    # backslash as `\\`. The plain replace above only ever matches the
    # single-backslash form, so it silently did nothing to the json/
    # sarif.json outputs on Windows -- the real (un-normalized) path
    # leaked into the "normalized" text and could never match a
    # snapshot captured on Linux. Also try the JSON-escaped form.
    #
    # اصلاح باگ: روی ویندوز `raw` بک‌اسلش دارد (مثلاً
    # "C:\Users\...\hybrid-project")، و json_renderer.py/sarif.py آن
    # را داخل یک رشته‌ی JSON جا می‌دهند، جایی که json.dumps هر بک‌اسلش
    # را به‌صورت `\\` escape می‌کند. replace ساده‌ی بالا فقط با شکل
    # تک-بک‌اسلش تطبیق پیدا می‌کند، پس روی خروجی json/sarif.json در
    # ویندوز خاموشانه هیچ کاری نمی‌کرد -- مسیر واقعی (نرمال‌نشده) به
    # متنِ «نرمال‌شده» نشت می‌کرد و هرگز نمی‌توانست با snapshotی که روی
    # لینوکس گرفته شده مطابقت کند. شکل escape‌شده‌ی JSON را هم امتحان
    # می‌کند.
    escaped = raw.replace("\\", "\\\\")
    if escaped != raw:
        out = out.replace(escaped, "<PROJECT_ROOT>")
    # BUG FIX: `out.replace(root.as_uri() + "/", ...)` (an exact string
    # match) kept failing on Windows CI even after the fix above --
    # `sarif.py`'s `originalUriBaseIds.PROJECTROOT.uri` is the only
    # absolute-path-derived field left unmatched. Root cause not fully
    # pinned down (Windows `Path.as_uri()` drive-letter casing is the
    # leading theory, but unconfirmed from the truncated CI summary),
    # so this replaces the exact-match with a pattern match instead of
    # guessing at the exact mechanism: any `file://...` URI ending in
    # this fixture's own (unique, known) directory name, case-
    # insensitive, regardless of how the drive letter/prefix is cased
    # or formatted. Safe because sarif.py has exactly one such field
    # and this fixture's directory name never collides with anything
    # else in the rendered output.
    #
    # اصلاح باگ: `out.replace(root.as_uri() + "/", ...)` (یک تطبیق
    # رشته‌ای دقیق) حتی بعد از اصلاح بالا هم روی CI ویندوز مدام
    # fail می‌شد -- فیلد `originalUriBaseIds.PROJECTROOT.uri` در
    # `sarif.py` تنها فیلد وابسته به مسیر مطلقِ باقی‌مانده‌ی
    # تطبیق‌نیافته است. علت ریشه‌ای کاملاً مشخص نشده (شکِ اصلی روی
    # حساسیت به بزرگی/کوچکیِ حرف درایو در `Path.as_uri()` ویندوز
    # است، ولی از روی خلاصه‌ی بریده‌شده‌ی CI تأیید نشده)، پس به‌جای
    # حدس‌زدنِ مکانیزم دقیق، تطبیقِ دقیقِ رشته‌ای با یک تطبیقِ الگو
    # جایگزین شده: هر URI به‌شکل `file://...` که به نام دایرکتوریِ
    # خودِ این فیکسچر (منحصربه‌فرد و شناخته‌شده) ختم شود، بدون
    # حساسیت به بزرگی/کوچکیِ حروف، صرف‌نظر از اینکه حرف درایو/پیشوند
    # چطور نوشته یا فرمت شده. امن است چون sarif.py دقیقاً یک چنین
    # فیلدی دارد و نام دایرکتوریِ این فیکسچر با هیچ‌چیز دیگری در
    # خروجیِ رندرشده تداخل ندارد.
    uri_pattern = re.compile(
        re.escape("file://") + r".*?" + re.escape(root.name) + r"/?",
        re.IGNORECASE,
    )
    out = uri_pattern.sub("<PROJECT_ROOT_URI>/", out)
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
            assert json.loads(normalized) == json.loads(expected)
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
