# گزارش تکمیل R13

گزارش مبتنی بر شواهد، معنای confidence و یکپارچگی ریسک: مرحله‌های A تا H، همه با
ترمینال و CI خود مالک تأیید شده‌اند (جدول پایین). مرحله‌ی H همین گزارش، مقایسه‌ی
fixture واقعی، `tests/test_ramz_real_fixture.py` و مستندات است.

## A. خلاصه‌ی اجرایی

گزارش‌های سرند می‌توانستند چیزهایی بگویند که شواهد پشتشان نبود. R13 هرکدام را در
منشأ خودش، به ترتیب، رفع و با تست قفل کرد.

| مشکل (تأییدشده) | گزارش چه می‌گفت | حالا چه می‌گوید |
|---|---|---|
| known issue عمومی | «Compilation or lint errors were detected.» وقتی فقط linterهای workflow، YAML و Markdown شکست خورده بودند | ابزار شکست‌خورده و دسته‌اش (`lint_failure`، `security_finding_detected`، `dependency_policy_failure`، ...) با علت و شناسه‌ی پایدار |
| confidence | «confidence 100%» حتی وقتی هیچ چکی خواسته نشده بود | پوشش اجرا `executed / requested`، وقتی چیزی خواسته نشده «not available»، و یادداشت اینکه کامل‌بودن یا درستیِ تحلیل را نمی‌سنجد |
| شکست ابزار امنیتی | «Security tool reported issues.» برای timeout، نقض licence و advisory به یک شکل | یافته‌ی امنیتی، نقض سیاست وابستگی و شکست ابزار سه چیزند؛ advisory نتیجه‌ی ابزار است و applicability برابر `unknown` |
| skipped، inconclusive، unavailable | health، ریسک‌ها و رندرها متفاوت می‌خواندند | یک برداشت (`core/check_states.py`) همه‌جا، با جدول رسمی |
| marker | هر کامنت `BUG` یک marker بود و فقط اولین marker هر خط | همه‌ی markerها پیدا و طبقه‌بندی می‌شوند؛ فقط TODO یا FIXME نوشته‌شده به‌شکل کار امتیاز دارد |
| یک مشکل در چند جا | یک شرط هم شکست بحرانی health، هم known issue و هم خط Quick Context | یک شناسه‌ی پایدار؛ Quick Context آن را یک بار نشان می‌دهد |
| قالب‌هایی که با هم نمی‌خوانند | شمار error و warning متفاوت، بدون failures و advisory در HTML، وضعیت فقط در Markdown | یک مجموعه فهرست (`core/report_views.py`)، همان واقعیت‌ها در Markdown، HTML، JSON، SARIF و text |

فرضیه‌هایی که درست درنیامدند: اینکه چیدمان lock در fixture ی Ramz فرق دارد (پس گرفته
شد: نسبت رندر است و diff کاری فقط ۵ خط)، و اینکه timeout در گروه تست باید از نسبت
امتیاز بیرون بماند (مالک رد کرد: امتیاز را بالا می‌برد؛ چک در مخرج می‌ماند و امتیاز
نمی‌گیرد).

## B. تغییرات معماری

| ماژول | مرحله | نقش |
|---|---|---|
| `core/failures.py` و جدول‌های `constants.py` | A | طبقه‌بندی نتیجه‌ی چک با ابزار و شواهد؛ known issueها |
| `core/check_states.py` | B، D | تنها برداشت از وضعیت یک چک |
| `core/execution_coverage.py` | B | پوشش اجرا، شکاف‌ها و گروه‌ها |
| `core/advisories.py` | C | advisory از خروجی cargo audit و cargo deny |
| `core/markers.py` | E | دسته‌ی marker و تنها تعریف actionable |
| `core/finding_identity.py` | F | شناسه‌ی پایدار یافته (`<kind>:<12 hex>`) |
| `core/report_views.py` | G | فهرست‌هایی که همه‌ی رندرها مشترک دارند |

مدل‌ها: `Failure`، `CoverageGap`، `Advisory`؛ `HealthScore` فیلدهای پوشش و
`critical_ids` گرفت؛ `ReportData` فیلدهای `failures`، `advisories`، `known_issue_ids`؛
`TodoItem` فیلد `category`. شمای JSON از `1.0` تا `1.6` (فقط افزودنی؛ تاریخچه‌ی نسخه
در `docs/JSON_SCHEMA.fa.md`).

## C. مشخصات confidence و پوشش

به `docs/EXECUTION_COVERAGE.fa.md` نگاه کنید. خلاصه: `execution_coverage = executed /
requested`؛ executed یعنی وضعیت `passed` یا `failed`؛ skipped، inconclusive،
unavailable و unknown اجرا‌شده نیستند؛ وقتی چیزی خواسته نشده `null` و «not available»
است، هرگز ۱۰۰٪ نیست. **تصمیم نام فیلد:** گزینه‌ی ۱ از دستور (افزودنی). فیلد جدید
`execution_coverage` است. `confidence` قدیمی با همان حساب دقیق قبلی می‌ماند، چون بررسی
کد ثابت کرد هم‌ارز نیست (kind را فقط در مخرج یکتا می‌کرد و timeout را اجراشده می‌شمرد)؛
منسوخ است، در هیچ گزارشی نشان داده نمی‌شود و پیش از شمای 2.0 حذف نمی‌شود.

## D. مشخصات طبقه‌بندی امنیتی

به `docs/SECURITY_EVIDENCE.fa.md` نگاه کنید. ابزاری که نتوانست اجرا شود (timeout، پیدا
نشد) حکمی نداده و «یافته» نیست. advisory شناخته‌شده با شناسه، بسته، نسخه، نوع،
نسخه‌های رفع، شدت (فقط وقتی ابزار چاپ کرده) و منبع‌ها نگه داشته می‌شود. نقض سیاست
وابستگی (licence، ban، source در cargo deny) آسیب‌پذیری نیست. applicability برای هر
advisory برابر `unknown` است: سرند تحلیل reachability نمی‌کند و برچسب «قابل سوءاستفاده»
یا «بی‌ربط» وجود ندارد. آسیب‌پذیری تأییدشده شواهدی می‌خواهد که سرند جمع نمی‌کند.

## E. یکپارچگی یافته‌ها

به `docs/FINDINGS.fa.md` (هویت و تکرار) و `docs/MARKERS.fa.md` نگاه کنید. هویت از
فیلدهای ساختاریافته می‌آید، نه از جمله؛ شرطی که هم شکست بحرانی health و هم known issue
است یک شناسه دارد و در Quick Context یک بار شمرده می‌شود؛ یافته‌هایی که شبیه‌اند ولی
فرق دارند شناسه‌ی جدا می‌مانند.

## F. شواهد تست

روی ترمینال مالک و در CI، مرحله‌به‌مرحله:

| مرحله | commit | pytest (پاس، skip) | اجرای CI |
|---|---|---|---|
| A | `3eee120` | 1436، 10 | 41802738433 |
| B | `cde9271` | 1466، 10 | سبز (همه‌ی jobها) |
| C | `66a66a7` | 1501، 10 | 42521818749 |
| D | `7d0f5c3` | 1529، 10 | 42572508443 |
| E | `83f9f3e` | 1559، 10 | 42585275296 |
| F | `1c198b5` | 1578، 10 | 42694571943 |
| G | `01bd0c6` | 1602، 10 | 42746997234 |
| H | `cb6c19e` | 1608، 10 | 42778552059 |

هر کدام ruff lint و format، mypy، bandit، markdownlint، مجموعه‌ی کامل روی Ubuntu
(پایتون 3.11، 3.12، 3.14، 3.15)، macOS و Windows، Clippy، تست‌های Rust، cargo deny،
gitleaks و jobهای ابزار واقعی را گذراند. در هیچ مرحله شکستی باقی نماند.

- **پاس‌شده:** عددهای بالا.
- **Skip:** ۱۰ تست با شرط skip خودشان؛ در R13 بررسی نشدند.
- **اجرا نشده:** اعتبارسنجی SARIF با schema رسمی (در repo validator نیست و sandbox
  شبکه ندارد؛ SARIF ساختاری بررسی می‌شود)؛ به‌روزرسانی زنده‌ی پایگاه advisory.
- **Blocked:** هیچ.

## G. مقایسه‌ی رندرها

ماتریس اینکه هر قالب چه چیزی دارد در `docs/RENDERERS.fa.md` است.

## H. وضعیت git

مرحله‌های A تا H کامیت‌های `main` هستند (جدول بالا). commit انتشار که پس از این گزارش
می‌آید بخشی از R13 نیست.

## I. ریسک‌های باقی‌مانده

| ریسک | شاهد | اقدام بعدی |
|---|---|---|
| دستور دقیق اجرای تاریخیِ Ramz معلوم نیست | در تاریخچه‌ی shell مالک چنین دستوری نیست؛ flagها از روی گزارش استنباط شده (تست، quality، security، source) | لازم نیست: هر دو گزارش همان ۱۲ چک، ۳۹ فایل و ۳۶ فایل واردشده را دارند |
| پایگاه advisory ممکن است بین دو اجرا فرق کند | commit آن برای اجرای تاریخی ثبت نشده | لازم نیست: هر دو اجرا ۵ vulnerability و ۱۳ warning می‌دهند |
| ۸ marker سرکوب‌شده ۱۱ شد | اسکنر جدید همه‌ی markerهای یک خط را گزارش می‌کند (R13-E)؛ سه‌تای اضافه تک‌تک شمرده نشدند | تأیید با اجرای اسکنر قدیم و جدید روی Ramz |
| reachability advisoryها سنجیده نمی‌شود | بخش J، قسمت آخر | قابلیت جداگانه‌ی reachability اگر خواسته شد |
| SARIF فقط ساختاری اعتبارسنجی می‌شود | validator در دسترس نبود | افزودن validator در CI وقتی نسخه‌ی pin‌شده انتخاب شد |
| `core/relevant_source.py` هنوز همه‌ی انواع marker را وزن می‌دهد | در R13-E ثبت شد، تغییر نکرد | جدا تصمیم‌گیری شود |
| `report_generation_failure` در واژگان هست ولی چیزی آن را تولید نمی‌کند | R13-A | از یک شکست واقعی تولید شود یا حذف شود |
| همان ابزار که در دو component با یک برچسب شکست بخورد یک شناسه دارد | `docs/FINDINGS.fa.md` | اگر مسئله شد component به شناسه اضافه شود |

## J. مقایسه‌ی قبل و بعد روی fixture واقعی (Ramz)

**ورودی‌ها، تأییدشده.** گزارش تاریخی: `sarand-ramz-report-historical.md`، SHA-256
`4c6a0622147205b481ad4b3844d332036b75c5e1ccfe0456995d10926583c32d` (با digest ثبت‌شده
یکی است)، ساخته‌شده در 2026-11-01 با سرند `160c589`. مخزن: Ramz
`7252b1ca8fea9dc59ebfa082998d0da307cb4eb1` (تگ `v0.3.2`) با تغییر `Cargo.lock`؛
`Cargo.lock` کامیت‌شده به‌علاوه‌ی patch ثبت‌شده SHA-256
`906a1bd8198f58f2bcab13db40f3cfde647fb2ec1510a2f58e243d56ad920b87` می‌دهد که working
copy پیش و پس از اجرای جدید همان را داشت. گزارش‌های جدید: سرند `01bd0c6`،
`sarand --full`، در 2026-11-10 (cargo 1.97.1، rustc 1.97.1، cargo-audit 0.22.2،
cargo-deny 0.20.2، Python 3.14.6)، SHA-256 فایل Markdown
`1ae1a238bd6d1714c75facdd93e07363d06c9fa8d4cf732a855462306a4c4792`، JSON
`2967fabf14ceb3055a692cd2a0d2b0c76a2e9d1bc1104e566fcfe0cf4d210b07`، SARIF
`81b49d25e968cd5312de20636b7284053e3050bfd1e4d5f3e643b7e5fa81d98e`. مقایسه از حالت
دقیق تاریخی مخزن استفاده می‌کند؛ مقایسه‌ی همان مخزن با همان چک‌هاست، نه بازتولید
بایت‌به‌بایت (کد متفاوت سرند خودِ هدف مقایسه است).

| معیار (دستور ۱۱٫۵) | قبل (`160c589`) | بعد (`01bd0c6`) |
|---|---|---|
| عبارت عمومی وقتی هیچ compiler شکست نخورده | ۳ بار، هم known issue هم یافته‌ی بحرانی Quick Context | ۰ بار در Markdown، JSON و SARIF |
| شکست ابزارهای غیر compiler | طبقه‌بندی نشده | `actionlint`، `yamllint`، `markdownlint`: `lint_failure` هرکدام با شناسه |
| confidence یا پوشش | «confidence 100%» | «execution coverage 100% (12 of 12 requested checks ran to a verdict)» با یادداشت اینکه یقین تحلیلی نیست |
| markerهای BUG تاریخی | ۸ ردیف `BUG` بدون دسته | همان ۸ ردیف با دسته‌ی `historical`: «0 actionable, 8 historical»؛ امتیاز code در health بدون تغییر (15.0) |
| شکست ابزار امنیتی، سیاست licence، آسیب‌پذیری | یک خط: «Security tool reported issues.» | دو خط: یافته‌ی امنیتی از cargo audit و cargo deny («a tool result; exploitability is not assessed») و نقض سیاست وابستگی («not a vulnerability») |
| advisoryها | فهرست نمی‌شدند (فقط ۱۳ خط `Warning:` و سر `error[...]`) | ۱۸ مورد با شناسه: ۵ vulnerability، ۱۰ unsound، ۳ unmaintained؛ شدتی چاپ نشده؛ applicability برابر `unknown` |
| errorها و warningها | ۱۲ error و ۳۷ warning | ۴ و ۲۴، با ۲۱ خط ابزار که در advisoryها ادغام شد (12 + 37 = 4 + 24 + 21) |
| شکست‌های بحرانی health و ریسک‌ها | ۱ شکست بحرانی؛ Quick Context ۲ نشان می‌داد | ۲ شکست بحرانی، هرکدام یک بار در Quick Context؛ ریسک می‌گوید هر دو همان چک‌های امنیتی شکست‌خورده را بازگو می‌کنند |
| شمارها در قالب‌ها | قابل مقایسه نبود | Markdown، JSON و SARIF: ۱۸ advisory، ۲۸ مورد tool-output، ۶ شکست با شناسه‌های یکسان، ۱۲ وضعیت چک، پوشش ۱۲ از ۱۲ |
| امتیاز سلامت | 76.0 (C): tests 25، quality 10، security 5، git 6، code 15، tooling 15 | 76.0 (C): همان تفکیک |

امتیاز تغییر نکرد چون R13 هیچ وزن یا واقعیتِ امتیازدار را عوض نکرد: همان چک‌ها اجرا
شدند و همان‌ها شکست خوردند. quality برابر 10.0 است چون ۳ از ۶ چک quality پاس شدند
(20 × 3/6)؛ security برابر 5.0 است چون یک چک امنیتی شکست خورد.

**ادعاهایی که تأیید نشدند.** دستور دقیق اجرای تاریخی (استنباط شده)؛ commit پایگاه
advisory در اجرای تاریخی؛ سه marker اضافه‌ی سرکوب‌شده؛ هر reachability از advisoryها
توسط سرند (عمداً).

**شواهد دستیِ reachability (بخشی از خروجی سرند نیست).** از سورس Ramz در `7252b1c` و
`Cargo.lock` آن؛ متن advisory همان است که cargo audit در fixture چاپ کرده، از شبکه
تازه نشد و سورس crateهای وابسته خوانده نشد.

| Advisory | شاهد در سورس Ramz | نتیجه |
|---|---|---|
| RUSTSEC-2026-0391 (zstd، context بازاستفاده‌شده) | `zstd::stream::Decoder::new` و `Encoder::new` در هر فراخوانی در `backends-age/src/lib.rs`؛ هیچ context میان فراخوانی‌ها نگه داشته نمی‌شود | شاهدی از بازاستفاده‌ی context نیست؛ ثابت نشده |
| RUSTSEC-2026-0403 (zstd-safe، decompress استریمی frame قدیمی) | `Decoder` استریمی استفاده می‌شود؛ feature ی `legacy` در zstd بررسی نشد | نامعلوم |
| RUSTSEC-2026-0398 (zstd-safe، `Seekable::decompress`) | در سورس API ی seekable استفاده نشده | استفاده‌ی مستقیم پیدا نشد |
| RUSTSEC-2026-0410 (zstd-sys، WebAssembly) | targetهای انتشار Linux، macOS، Windows و Android‌اند؛ هیچ‌کدام WebAssembly نیست | برای targetهای منتشرشده غیرقابل‌اعمال؛ برای buildهای دیگر ثابت نشده |
| RUSTSEC-2026-0385 (ctutils) | از طریق `hybrid-array` و `module-lattice` (وابستگی `ml-kem`) می‌رسد؛ توابع constant-time استفاده‌شده بررسی نشد | نامعلوم |

## K. تصمیم وزن امتیاز سلامت

**وزن‌های اصلی حفظ شد**، چون هیچ جریمه‌ی نامتناسبی نشان داده نشد. روی fixture ی Ramz
امتیاز پیش و پس 76.0 است؛ security برای هر چک امنیتیِ شکست‌خورده 5.0 از 15 و quality
برابر 10.0 از 20 برای ۳ پاس از ۶ است. اینکه شکستِ فقط-سیاست همان امتیاز امنیتی
advisory را کم می‌کند ویژگی طراحی است که این fixture نمی‌تواند جدایش کند (هر دو با هم
هستند)، پس هیچ اندازه‌گیری تغییر را پشتیبانی نمی‌کند. هر پیشنهاد اول یک مقایسه‌ی
ترکیبی از آن دو حالت می‌خواهد.

## معیارهای پذیرش

| # | وضعیت | شاهد |
|---|---|---|
| 1 | VERIFIED | مرحله‌ی A؛ اجرای واقعی هیچ ادعای compilation ندارد |
| 2، 3 | VERIFIED | مرحله‌های A و C |
| 4، 5 | VERIFIED | مرحله‌ی C: applicability برابر `unknown`، بدون ادعای exploitability |
| 6، 7 | VERIFIED | مرحله‌ی B و `docs/EXECUTION_COVERAGE.fa.md` |
| 8، 19 | VERIFIED | مرحله‌ی D و `docs/CHECK_STATES.fa.md` |
| 9، 10 | VERIFIED | مرحله‌ی E |
| 11، 12 | VERIFIED | مرحله‌ی F |
| 13 | VERIFIED | مرحله‌ی G و اجرای واقعی (J) |
| 14 | VERIFIED | تست‌های هر مرحله و تست‌های fixture واقعی مرحله‌ی H |
| 15 | VERIFIED | مجموعه‌ی کامل در هر مرحله سبز بود؛ تغییرات رفتار در `CHANGELOG.md` فهرست شده |
| 16 | VERIFIED | بخش F: همه‌ی gateها در هر مرحله، از جمله H، اجرا شدند |
| 17 | VERIFIED | هر تحویل hash-guard داشت و روی tree تغییرکرده رد می‌شد |
| 18 | با بازبینی | ادعاها محدود به چیزی‌اند که بخش‌های F و J نشان می‌دهند |
| 20 | با محدودیت‌های J VERIFIED | حالت دقیق مخزن؛ flagهای دقیق استنباطی |
| 21 | VERIFIED | بخش C |
| 22 | NOT APPLICABLE | هیچ وزنی تغییر نکرد (بخش K) |
| 23 | VERIFIED | هر مرحله پس از تأیید مرحله‌ی قبل شروع شد |
