# Baseline ساختاری: مقایسه‌ی دو عکس لحظه‌ای ساختار

وضعیت: کتابخانه و خط فرمان (قطعه‌های S1 و S2 از R14-D1، `docs/R14D1_PLAN.md`). این صفحه قرارداد
است: snapshot چیست، یک مقایسه چه چیزی را می‌تواند ادعا کند، چه چیزی را ادعا نمی‌کند، و خط فرمان
چگونه از آن استفاده می‌کند.

baseline ساختاری **مستقل از baseline یافته‌ها** است. آنچه پروژه از آن ساخته شده را مقایسه می‌کند
(فایل‌ها، symbolها، relationها، importها، چرخه‌ها، نقطه‌های ورود)؛ هیچ یافته‌ای نمی‌سازد یا
تغییر نمی‌دهد و هیچ کد یافته‌ها آن را import نمی‌کند.

## پرسش و دو طرف

`compare_structures(old, new)` یک مرجع (`old`) را با وضعیت فعلی (`new`) مقایسه می‌کند. هر طرف
یک `Reference` است که `read_reference` از JSON خوانده‌شده می‌سازد:

- یک **snapshot**: شیء `structure` گزارش در یک پوشه‌ی کوچک (پایین)، یا
- یک **گزارش JSON** که کلید `structure` دارد.

`read_reference` روی ورودی بد خطا نمی‌دهد؛ مرجعی برمی‌گرداند که علت بی‌استفاده‌بودنش را می‌گوید، تا
مقایسه به‌جای «مقایسه‌ی هیچ و گفتن بدون تغییر» همین را اعلام کند.

## پوشه‌ی snapshot

| کلید | معنا |
|---|---|
| `kind` | `sarand-structure-snapshot` |
| `snapshot_format` | `1` |
| `structure_schema`، `language` | از structure کپی می‌شود و با آن سنجیده می‌شود |
| `fingerprint_basis` | مثلاً `fp1/python-3.14`؛ با structure سنجیده می‌شود |
| `settings` | `excluded_secret_files` (مسیرهای مرتب) و `max_file_size`: آنچه محتوای snapshot را عوض می‌کند |
| `structure` | همان `structure` گزارش |
| `digest` | `sha256:` همه‌ی موارد بالا در JSON استاندارد |

snapshot زمان و نام ماشین ندارد: همان پروژه با همان کد همیشه همان بایت‌ها را می‌نویسد
(`snapshot_text`). تغییر یک بایت digest را خراب می‌کند و مرجع `invalid` می‌شود.

## حکم‌ها

حکم، اولین فیلد پاسخ است. اولین موردی که برقرار باشد برنده است؛ واقعیت‌های مربوط به موارد
پایین‌تر در `reasons`، `fingerprints_comparable` و `uncertain_paths` می‌مانند.

| حکم | کی | چه چیزی مقایسه می‌شود |
|---|---|---|
| `invalid` | یک طرف snapshot قابل‌استفاده نیست: شیء نیست، کلید `structure` ندارد، digest نمی‌خواند، بخشی گم است، پوشه با structure خودش ناسازگار است | هیچ چیز |
| `incompatible` | یک طرف درست‌ساخت است ولی schema، قالب snapshot یا زبانی دارد که این نسخه مقایسه نمی‌کند (`SUPPORTED_SCHEMAS` برابر `4`)، یا دو طرف فرق دارند | هیچ چیز |
| `partial` | دست‌کم یک مسیر نامطمئن، یا دو سقف اندازه‌ی فایل که هر دو معلوم‌اند و فرق دارند | همه چیز؛ آنچه به مسیر نامطمئن وابسته است `uncertain` است |
| `ids_only` | بنیان بصمت‌ها فرق دارد یا نیست (نسخه‌ی minor دیگر پایتون) | symbolها فقط با شناسه؛ هیچ `content_changed` ادعا نمی‌شود |
| `comparable` | هیچ‌کدام از موارد بالا | همه چیز |

schema تازه‌ای که builder شروع به نوشتن آن کند باید همراه با مقایسه به `SUPPORTED_SCHEMAS`
اضافه شود؛ تا آن موقع `incompatible` است و یک آزمون فهرست پشتیبانی‌شده را به schemaی که builder
امروز می‌نویسد گره می‌زند.

## نبودِ داده حذف نیست

یک مسیر **نامطمئن** است وقتی تغییرِ مرتبط با آن را نتوان تغییر واقعی خواند:

- فایل در یکی از snapshotها `full` نیست (`partial`، `failed`، `skipped_size`)؛
- مسیر در استثنای secret یک snapshot هست و در دیگری نیست.

هر مورد افزوده، حذف یا تغییرکرده که به مسیر نامطمئن وابسته باشد با وضعیت `uncertain` و علت گزارش
می‌شود، هرگز افزوده یا حذف. بسته‌های خارجی که دیگر import نمی‌شوند هم تا وقتی مسیر نامطمئنی هست
`uncertain` هستند، چون ممکن است importی که از آن‌ها استفاده می‌کرد اصلاً خوانده نشده باشد.

## چه چیزی مقایسه می‌شود و هویتش چیست

| بخش | هویت | وضعیت‌ها |
|---|---|---|
| فایل‌ها | مسیر | `added`، `removed`، `changed` (فیلدهای `content`، `completeness`، `language`)، `uncertain` |
| ماژول‌ها | نام و root | `added`، `removed`، `changed` (`path`، `is_package`، `is_namespace`)، `uncertain` |
| symbolها | کلاس‌های تطبیق `identity.py` | `content_changed`، `content_unknown`، `moved`، `ambiguous`، `added`، `removed`، `uncertain` |
| relationها | نوع، مبدأ و مقصد تطبیق‌خورده | `added`، `removed`، `changed`، `uncertain` |
| یال‌های import | نوع، ماژول واردکننده، نام درخواستی | `added`، `removed`، `changed`، `uncertain` |
| چرخه‌ها | مجموعه‌ی مرتب ماژول‌ها | `added`، `removed`، `changed` (پرچم eager)، `uncertain` |
| نقطه‌های ورود | نوع، نام، مقصد | `added`، `removed`، `changed`، `uncertain` |
| بسته‌های خارجی | نام | `added`، `removed`، `changed`، `uncertain` |

موارد بدون تغییر شمرده می‌شوند و فهرست نمی‌شوند. خط و ستون سورس شاهد است و هرگز بخشی از هویت
نیست.

- **محتوا هویت نیست.** symbolی با همان شناسه و بصمت دیگر `content_changed` است؛ هرگز «حذف به‌علاوه‌ی
  افزودن» گزارش نمی‌شود. symbol جابه‌جاشده `moved` است (تطبیق `probable`)؛ symbol تغییرنام‌یافته
  یک جفت بی‌همتاست، مطابق `docs/R14A_ADR_STRUCTURAL_IDENTITY.md`. تغییر صرفاً قالب‌بندی هش فایل را
  عوض می‌کند و هیچ symbolی را نه.
- **relationها دنبال symbolهایشان می‌روند.** relationی که symbol مبدأ یا مقصدش حذف یا افزوده شده در
  `removed_with_symbol` یا `added_with_symbol` شمرده می‌شود و دوباره فهرست نمی‌شود. relationی که به
  symbol `ambiguous` یا symbol در فایل نامطمئن می‌خورد با علت `uncertain` فهرست می‌شود، چون هیچ
  کلیدی برایش قابل‌اعتماد نیست. relation بین symbolهای تطبیق‌خورده با نوع و شناسه‌های تطبیق‌خورده
  مقایسه می‌شود؛ تغییر confidence، روش حل، پرچم یا تعداد نقطه‌ها `changed` است.

## قطعیت و ایمنی

دو مرجع یکسان همان بایت‌ها را می‌دهند (`to_json`)، هر ترتیبی که عناصر داخلشان داشته باشند. مقایسه
هیچ‌کدام از دو ورودی را تغییر نمی‌دهد. `compare_structures` فقط دو مرجع را می‌خواند: بدون فایل،
بدون شبکه، بدون ساعت.

## خط فرمان

هر دو گزینه به `--structure` نیاز دارند (بدون آن اجرا رد می‌شود).

| گزینه | کار |
|---|---|
| `--structure-baseline PATH` | ساختار این اجرا را با مرجع در `PATH` (snapshot، یا گزارش JSON که `structure` دارد) مقایسه می‌کند و آنچه تغییر کرده را به گزارش می‌افزاید. |
| `--structure-snapshot PATH` | ساختار این اجرا را به‌صورت snapshot در `PATH` می‌نویسد. |
| `--replace-structure-snapshot` | به `--structure-snapshot` اجازه‌ی جایگزینی فایل موجود را می‌دهد. |

- **شکست زودهنگام.** baselineی که نیست، خوانده نمی‌شود، snapshot یا گزارش نیست، قالب snapshot یا
  schema ساختار دیگری دارد، یا digest اشتباه دارد خطایی است که نام فایل و علت را می‌گوید؛ همین‌طور
  مقصد snapshot که دایرکتوری است، symbolic link است، در دایرکتوری ناموجود است، یا فایل موجودی است
  بدون `--replace-structure-snapshot`. این پیش از هر کاری بررسی می‌شود: نه اسکن، نه گزارش. کد خروج برای baseline نامعتبر ۴ و برای مقصد snapshotِ غیرقابل استفاده ۱ است.
- **ترتیب.** مقایسه از مرجع به همان صورت پیش از اجرا استفاده می‌کند. snapshot آخر نوشته می‌شود،
  فقط پس از موفقیت گزارش؛ با PDF ناموفق (خروج ۱) هیچ snapshotی نوشته نمی‌شود. می‌توان یک مسیر را به
  هر دو گزینه داد: اجرا با فایل قدیمی مقایسه می‌کند، سپس آن را جایگزین می‌کند (قدیمی با نام
  `PATH.prev` می‌ماند).
- **نوشتن امن.** snapshot در یک فایل موقتِ کنار مقصد آماده می‌شود، روی دیسک نوشته می‌شود، دوباره
  خوانده و راستی‌آزمایی می‌شود (باید snapshot قابل‌استفاده با همان digest مورد نظر باشد) و بعد
  rename می‌شود. شکست مقصد را همان‌طور که بود می‌گذارد و فایل موقتی باقی نمی‌ماند. جایگزینی یک نسل
  قبلی را با نام `PATH.prev` نگه می‌دارد؛ برای بازگرداندن، آن را دوباره rename کنید. مجوز فایل موجود
  حفظ می‌شود، وگرنه پیش‌فرض umask اعمال می‌شود.
- **نتیجه کجا می‌رود.** JSON: شیء `structure_comparison` (شمای گزارش 1.11، `docs/JSON_SCHEMA.fa.md`).
  Markdown و HTML: بخش «Structure changes» (حکم، علت‌ها، شمارش هر بخش، مسیرهای نامطمئن، تا ۴۰ تغییر
  فهرست‌شده). text: یک خط. SARIF: هیچ. مقایسه فقط اطلاعاتی است: هرگز کد خروج را عوض نمی‌کند و
  هرگز یافته نمی‌سازد.

```text
sarand --structure --structure-snapshot structure.json          # اولین اجرا: نوشتن مرجع
sarand --structure --structure-baseline structure.json          # بعداً: چه تغییر کرده؟
sarand --structure --structure-baseline structure.json \
       --structure-snapshot structure.json --replace-structure-snapshot   # مقایسه، سپس به‌روزرسانی
```

## محدودیت‌ها

- relationی که مقصدش حل نشده در payload نام مقصد پایدار ندارد؛ پس چند مقصد حل‌نشده‌ی یک مبدأ و
  نوع، یک کلید هستند.
- ماژول تغییرنام‌یافته یک ماژول حذف‌شده به‌علاوه‌ی یک ماژول افزوده است؛ importهایش دنبالش می‌آیند.
- با `ids_only` گزارش نمی‌تواند تغییر محتوا را از نبودِ تغییر تشخیص دهد؛ چنین symbolهایی
  `content_unknown` هستند.
- snapshot کل payload ساختار است: برای sarand حدود ۱۱٫۶ مگابایت (۵٬۰۷۸ symbol). در sandbox
  (x86، پایتون ۳٫۱۲) یک مقایسه‌ی دو snapshot چنین ۰٫۳ تا ۰٫۶ ثانیه طول کشید. اعداد گوشی در قطعه‌ی P
  اندازه‌گیری می‌شود.
- فقط Python مقایسه می‌شود. زبان دیگر `incompatible` است.

## استفاده (کتابخانه)

```python
from sarand.structure.snapshot import make_snapshot, read_reference
from sarand.structure.compare import compare_structures

old = read_reference(make_snapshot(old_structure_payload))
new = read_reference(make_snapshot(new_structure_payload))
result = compare_structures(old, new)
print(result.verdict)
print(result.to_json())
```

## آزمون‌ها

`tests/test_structure_compare.py` این موارد را می‌پوشاند: snapshotهای یکسان، هر وضعیت، هر حکم و هر
راهی که یک snapshot بی‌استفاده می‌شود، digest و نبودِ زمان، استقلال خروجی از ترتیب ورودی، و اینکه
هیچ چیز در ورودی‌ها تغییر نمی‌کند. `tests/test_structure_baseline_cli.py` فایل‌های snapshot (یا
کامل یا هیچ، هرگز بی‌اجازه روی فایل، نسل قبلی، مجوزها، خواندنی که exception نمی‌دهد) و دستور
(ردها، شمای JSON و قالب‌های دیگر، اجرا بدون گزینه‌ها) را می‌پوشاند.
