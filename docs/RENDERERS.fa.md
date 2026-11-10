# هماهنگی رندرها

Markdown، HTML، JSON، SARIF و text نمایش‌های متفاوتِ **یک** مدل‌اند. می‌توانند آن را
متفاوت رسم کنند، ولی نباید چیزهای متفاوت بگویند. فهرست‌هایی که همه لازم دارند
(errorها و warningها، ردیف‌های شکست، ردیف‌های advisory، وضعیت هر چک) یک بار در
`core/report_views.py` تعیین می‌شوند و رندر فقط شیوه‌ی نمایش را انتخاب می‌کند. هیچ
رندری واقعیتی را دوباره حساب نمی‌کند.

## هر قالب چه چیزی دارد

| فیلد | Markdown | HTML | JSON | SARIF | Text |
|---|---|---|---|---|---|
| امتیاز و نمره‌ی سلامت | بله | بله | بله | `runs[0].properties.sarand.health` | بله |
| پوشش اجرا (و مبنای آن) | بله | بله | بله | `...health.executionCoverage`، `checksRequested`، `checksExecuted`، `coverageByGroup` | یک خط |
| شکاف‌های پوشش (چه چیزی اجرا نشد و چرا) | بله | بله | بله | `...health.coverageGaps` | یک خط |
| وضعیت هر چک | `[PASS]` `[FAIL]` `[SKIP]` ... | badge | `state` در هر result | `...checkStates` | خیر |
| شکست‌های طبقه‌بندی‌شده با شناسه | جدول | جدول | `failures[].id` | `...failures` | شمارش |
| شکست‌های بحرانی | بله | بله | `health.critical_failures`، `critical_ids` | `...health.criticalFindingIds` | خیر |
| Known issues | فهرست | فهرست | `known_issues`، `known_issue_ids` | `...knownIssueIds` | خیر |
| شناسه، بسته، نسخه و نوع advisory | جدول | جدول | `advisories` | یک result برای هر advisory؛ `ruleId` همان شناسه‌ی advisory | شمارش |
| severity (فقط اگر ابزار چاپ کرده) | ستون | ستون | `severity` | `properties.severity` | خیر |
| applicability (همیشه `unknown`) | ستون | ستون | `applicability` | `properties.applicability` | در خط شمارش |
| منبع advisory (کدام ابزارها گزارش کردند) | ستون | ستون | `sources` | `properties.reportedBy` | خیر |
| هویت یافته‌ی advisory | شناسه‌اش | شناسه‌اش | شناسه، بسته، نسخه | `partialFingerprints.sarandFindingId/v1` | خیر |
| errorها و warningهای ابزارها | فهرست | جدول | داخل هر result | resultهای `tool-output/...` | خیر |

SARIF فیلد بومی برای وضعیت چک‌ها و پوشش ندارد؛ پس در property bag زیر کلید
`sarand` نگه داشته می‌شوند. استاندارد اجازه می‌دهد و چیزی از معنای هیچ result را
تغییر نمی‌دهد. سطح‌ها از استاندارد پیروی می‌کنند (`note`، `warning`، `error`):
advisory از نوع vulnerability یا unsound که ابزار گزارش کرده `warning` است،
اعلان نگهداری `note`، و هیچ‌کدام برای تمیزتر دیده‌شدن بالا یا پایین نمی‌رود.

## یک واقعیت، یک شمارش

- **خطوط advisory دوبار فهرست نمی‌شوند.** خطوط بی‌نام `Warning:   unsound` در
  `cargo audit` و سرِ `error[vulnerability]` / `warning[unmaintained]` در
  `cargo deny` را خود advisory نمایندگی می‌کند. زیر «Errors detected»،
  «Warnings detected» و resultهای `tool-output` در SARIF تکرار نمی‌شوند و یک جمله
  می‌گوید چند خط ادغام شد. خروجی خود چک همچنان همه‌چیز را کامل نشان می‌دهد. خط فقط
  وقتی ادغام می‌شود که همان چک دست‌کم یک advisory تولید کرده باشد؛ بقیه‌ی خطوط آن
  ابزارها (نقض license، `error: 5 vulnerabilities found!`، crate تکراری) می‌مانند.
- **Quick Context همان را می‌شمارد.** «tools reported N error(s) and M
  warning(s)» از همان فهرست‌ها می‌آید و یک خط جدا شمار advisoryها را می‌دهد.
- **چکی که اجرا نشد known issue نیست.** timeout یا ابزار گم‌شده حکمی نداده
  (`unavailable`، به `docs/CHECK_STATES.fa.md` نگاه کنید)، پس «ابزاری که شکست
  خورده» نیست و دیگر در `known_issues` یا میان یافته‌های بحرانیِ Quick Context
  نمی‌آید. با علتش (مثلاً `tool_not_found`) در `failures`، شکاف‌های پوشش و
  ریسک‌ها می‌ماند.
- **JSON** خروجی کامل هر چک را نگه می‌دارد (شاهد است) و در هر result فیلد `state`
  گرفت؛ `health.checks_inconclusive` همیشه حاضر است.

## پوشش داده نشده

HTML جدول‌های هر component در گزارش workspace را متفاوت از Markdown رسم نمی‌کند، و
قالب text عمداً خلاصه است (برای فهرست‌ها به گزارش کامل ارجاع می‌دهد). مقایسه‌ی
قبل/بعد روی Ramz به گزارش نهایی R13 مربوط است.
