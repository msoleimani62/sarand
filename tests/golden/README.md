# Golden report snapshots

Stored, byte-exact regression snapshots for `test_golden_reports.py`.
See AGENTS.md section 5.21 for the design rationale (why
renderer-level, why only two fixtures, what's deliberately deferred).

## What's here

- `hybrid.*` — a dense, multi-language fixture built in
  `../_golden_fixtures.py` (`build_hybrid_fixture`). Exercises every
  truncation limit, mixed pass/fail/skipped tool results, secrets,
  untracked files, etc.
- `minimal.*` — an almost-empty, unrecognized-project fixture
  (`build_minimal_fixture`). Exercises the "nothing found" / empty
  branch of every renderer.
- One file per (fixture, renderer) pair: `.md` (markdown), `.json`
  (json), `.txt` (text), `.sarif.json` (sarif), `.html` (html).

`renderers/pdf.py` is not covered here — it always shells out to a
real, optionally-installed tool (`wkhtmltopdf`/`weasyprint`) and has
no in-process text output to snapshot.

## Why this exists

Unit/integration tests mostly assert "the output contains X". That
catches a feature going missing, but not the report's overall
*shape* silently changing — a section moving, a truncation limit
drifting, a count going out of sync with the list it counts. This
suite renders two fixed `ReportData` fixtures through every renderer
and diffs the full output against a stored snapshot, so any such
change fails loudly here even if every existing "contains X" test
still passes.

## Updating a snapshot

Only do this after confirming, by reading the diff, that the new
output is *correct* — this suite has no opinion on that, it only
detects that something changed.

```bash
SARAND_UPDATE_GOLDEN=1 pytest tests/test_golden_reports.py
git diff tests/golden/
```

Review the diff like any other code change. If it's the intended
result of the analyzer/report-structure/health-scoring change you're
making, commit it alongside that change — never as an unrelated,
unexplained diff.

## Adding a new fixture or renderer

Add the fixture function to `FIXTURES` in `../_golden_fixtures.py`
(or the renderer to `RENDERERS` in `../test_golden_reports.py`), then
run the `SARAND_UPDATE_GOLDEN=1` command above once to create its
snapshots. `test_every_fixture_has_a_golden_snapshot_for_every_format`
fails loudly if this step is forgotten, so a new fixture/renderer can
never silently ship with zero golden coverage.

## Known gap (not yet done)

These fixtures are built directly from `ReportData` — they exercise
every renderer thoroughly, but never a real scan (analyzer detection,
tool execution, secret scanning, cache behavior). Real per-ecosystem
source-tree fixtures (Python/Rust/JS/Go/hybrid/infra/multi-language,
scanned end-to-end) are the natural next phase of this backlog item
and are deliberately out of scope here — see the "P0.1 golden reports"
entry in AGENTS.md section 5.21.

---

# اسنپ‌شات‌های golden report

اسنپ‌شات‌های رگرسیونِ ذخیره‌شده و بایت‌به‌بایت برای `test_golden_reports.py`.
برای دلیل طراحی (چرا در سطح رندرکننده، چرا فقط دو فیکسچر، چه چیزی عمداً
به بعد موکول شده) بخش ۵.۲۱ AGENTS.md را ببینید.

## اینجا چه چیزی هست

- `hybrid.*` — فیکسچری پرمحتوا و چندزبانه که در `../_golden_fixtures.py`
  ساخته شده (`build_hybrid_fixture`). هر سقف truncation، نتایج ترکیبیِ
  pass/fail/skipped، اسرار، فایل‌های untracked و غیره را آزمون می‌کند.
- `minimal.*` — فیکسچری تقریباً خالی و ناشناخته
  (`build_minimal_fixture`). شاخه‌ی «چیزی یافت نشد» / خالیِ هر
  رندرکننده را آزمون می‌کند.
- یک فایل به ازای هر جفت (فیکسچر، رندرکننده): `.md`، `.json`، `.txt`،
  `.sarif.json`، `.html`.

`renderers/pdf.py` اینجا پوشش داده نمی‌شود — همیشه به یک ابزار واقعی و
اختیاراً-نصب‌شده (`wkhtmltopdf`/`weasyprint`) متکی است و خروجی متنیِ
درون‌فرآیندیِ قابل-snapshot ندارد.

## چرا این وجود دارد

بیشتر تست‌های واحد/یکپارچگی فقط «خروجی شامل X هست» را بررسی می‌کنند.
این، گم‌شدن یک قابلیت را می‌گیرد، اما نه تغییر خاموشِ *شکل* کلی گزارش را
— جابه‌جایی یک بخش، رفتن سقف truncation، یا خارج‌شدن یک شمارنده از
هماهنگی با فهرستی که می‌شمارد. این مجموعه‌تست دو فیکسچر ثابت
`ReportData` را از هر رندرکننده عبور می‌دهد و کل خروجی را با یک
اسنپ‌شات ذخیره‌شده مقایسه می‌کند، پس هر چنین تغییری حتی اگر همه‌ی
تست‌های «شامل X هست» هم‌چنان قبول شوند، اینجا با صدای بلند شکست
می‌خورد.

## به‌روزرسانی یک اسنپ‌شات

فقط بعد از اینکه با خواندن diff مطمئن شدید خروجی جدید *درست* است این
کار را انجام دهید — این مجموعه‌تست هیچ نظری درباره‌ی درستی ندارد، فقط
تغییر را تشخیص می‌دهد.

```bash
SARAND_UPDATE_GOLDEN=1 pytest tests/test_golden_reports.py
git diff tests/golden/
```

diff را مثل هر تغییر کد دیگری مرور کنید. اگر نتیجه‌ی مورد انتظارِ
تغییری در آنالایزر/ساختار گزارش/امتیازدهی سلامت است که دارید انجام
می‌دهید، آن را همراه با همان تغییر commit کنید — هرگز به‌صورت diffِ
بی‌ربط و بی‌توضیح.

## افزودن فیکسچر یا رندرکننده‌ی جدید

تابع فیکسچر را به `FIXTURES` در `../_golden_fixtures.py` (یا
رندرکننده را به `RENDERERS` در `../test_golden_reports.py`) اضافه
کنید، سپس یک‌بار دستور `SARAND_UPDATE_GOLDEN=1` بالا را اجرا کنید تا
اسنپ‌شات‌هایش ساخته شود. `test_every_fixture_has_a_golden_snapshot_for_every_format`
اگر این مرحله فراموش شود با صدای بلند شکست می‌خورد، پس یک فیکسچر/رندرکننده‌ی
جدید هرگز نمی‌تواند خاموش و با صفر پوشش‌ golden منتشر شود.

## خلأ شناخته‌شده (هنوز انجام نشده)

این فیکسچرها مستقیماً از `ReportData` ساخته می‌شوند — هر رندرکننده را
کامل آزمون می‌کنند، اما هرگز یک اسکن واقعی را (تشخیص آنالایزر، اجرای
ابزار، اسکن اسرار، رفتار cache) آزمون نمی‌کنند. فیکسچرهای واقعیِ
درخت-سورس به‌ازای هر اکوسیستم (Python/Rust/JS/Go/hybrid/infra/چندزبانه،
اسکن‌شده سر تا ته) فاز طبیعیِ بعدیِ همین آیتم backlog هستند و عمداً
اینجا خارج از scope گذاشته شده‌اند — ورودی «P0.1 golden reports» در
بخش ۵.۲۱ AGENTS.md را ببینید.
