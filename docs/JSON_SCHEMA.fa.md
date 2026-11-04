# شمای گزارش JSON

`sarand --format json` یک شیء JSON می‌نویسد. این صفحه همه‌ی کلیدهای سطح بالا، فیلدهای شیءهای تو در تو و آنچه یک اسکریپت می‌تواند به آن تکیه کند را فهرست می‌کند. نسخه‌ی فعلی پایین است؛ یک تست این صفحه و کد را هم‌گام نگه می‌دارد، پس کلیدی که در کد هست ولی اینجا نیست build را می‌شکند.

نسخه‌ی فعلی: **1.1**

## سیاست سازگاری

- `schema_version` به‌شکل `MAJOR.MINOR` و اولین کلید است. جدا از نسخه‌ی خود برنامه شماره‌گذاری می‌شود.
- **افزودن** کلید یا فیلد، MINOR را بالا می‌برد (از 1.0 به 1.1). خواننده باید کلیدهای ناشناس را نادیده بگیرد.
- **حذف یا تغییر نام** کلید یا فیلد، تغییر نوع، یا تغییر معنی، MAJOR را بالا می‌برد و CHANGELOG آن را می‌گوید.
- کلید اختیاری وقتی قابلیتش به کار نمی‌آید **غایب** است، نه `null`. تنها `null` همان `health` با `--no-health` است.
- متن آزاد زیر پوشش نیست: `raw_output`، `content`، `details`، `tool_versions` و عبارت‌بندی `reason`، `summary` و `ai_summary` بدون افزایش نسخه می‌توانند عوض شوند. شناسه‌ی قاعده‌ها (`rule_id`)، مقادیری مثل `severity` و کلیدهای همین صفحه زیر پوشش‌اند.
- این صفحه درباره‌ی گزارش JSON است. SARIF استاندارد خودش را دارد و برای Markdown، HTML و text هیچ وعده‌ی پایداری نیست.

## کلیدهای سطح بالا

| کلید | نوع | حضور | معنی |
|---|---|---|---|
| `schema_version` | رشته | همیشه | نسخه‌ی این شمای JSON به‌شکل `MAJOR.MINOR` (سیاست پایین را ببینید). همیشه اولین کلید. |
| `project_root` | رشته | همیشه | مسیر مطلق پروژه‌ی اسکن‌شده. |
| `quick_context` | شیء | همیشه | خلاصه‌ی کوتاه و محدودی که گزارش با آن شروع می‌شود (فیلدها پایین). |
| `architecture` | شیء | همیشه | اجزا، workspaceها، نقاط ورود و آیتم‌های Compose و Kubernetes که از همین گزارش خوانده شده‌اند (فیلدها پایین). |
| `risks` | شیء | همیشه | ریسک‌های قاعده‌محور، هرکدام با شواهد و محدودیتش، و قاعده‌هایی که ارزیابی‌شدنی نبودند (فیلدها پایین). |
| `generated_at` | رشته | همیشه | زمان ساخت گزارش به‌صورت ISO 8601. |
| `used_rust_core` | بولی | همیشه | اینکه موتور اسکن Rust استفاده شده یا نه. |
| `detection` | شیء | همیشه | زبان‌ها، سیستم ساخت و نقاط ورودِ شناسایی‌شده (فیلدها پایین). |
| `environment` | شیء | همیشه | ماشین و نسخه‌ی ابزارهایی که اسکن روی آن اجرا شده (فیلدها پایین). |
| `git` | شیء | همیشه | وضعیت مخزن؛ بیرون از مخزن `branch` برابر `(unavailable)` است (فیلدها پایین). |
| `stats` | شیء | همیشه | آمار فایل، خط و اندازه (فیلدها پایین). |
| `todos` | آرایه | همیشه | نشانه‌های TODO و مانند آن؛ هرکدام با `path`، `line_number`، `kind` و `content`. |
| `test_results` | آرایه | همیشه | نتیجه‌ی اجرای تست‌ها (شیء نتیجه، فیلدها پایین). با رد شدن تست‌ها خالی است. |
| `quality_results` | آرایه | همیشه | نتیجه‌ی linterها و type checkerها (شیء نتیجه). |
| `security_results` | آرایه | همیشه | نتیجه‌ی ابزارهای امنیتی (شیء نتیجه). |
| `health` | شیء یا null | همیشه | امتیاز سلامت (فیلدها پایین)؛ با `--no-health` برابر `null`. |
| `known_issues` | آرایه‌ی رشته‌ها | همیشه | مشکلاتی که خود اسکن دیده است. |
| `ai_summary` | رشته | همیشه | خلاصه‌ی ساده‌زبان برای خواننده‌ی هوش مصنوعی. |
| `suggested_reading_order` | آرایه‌ی رشته‌ها | همیشه | همه‌ی فایل‌های شامل‌شده، مهم‌ترین اول. Quick Context ده‌تای اول را نشان می‌دهد. |
| `included_files` | آرایه‌ی رشته‌ها | همیشه | مسیرهای نسبی به پروژه که محتوایشان ممکن است نمایش داده شود. |
| `skipped_files` | آرایه‌ی جفت‌ها | همیشه | `[path, reason]` برای فایل‌هایی که کنار گذاشته شدند. |
| `excluded_secret_files` | آرایه‌ی رشته‌ها | همیشه | مسیرهایی که چون شبیه راز هستند یا راز دارند کنار گذاشته شدند. فقط مسیر، هرگز محتوا. |
| `secret_findings` | آرایه | همیشه | موردهای مطابق با الگوی راز: `path`، `line_number`، `pattern_name`، `is_test_fixture`. هرگز مقدار. |
| `todos_suppressed` | عدد صحیح | فقط وقتی نشانه‌ای حذف شده | تعداد نشانه‌هایی که یک استثنا حذف کرده است. |
| `failures` | آرایه | فقط وقتی چکی شکست خورده | هر چک شکست‌خورده، طبقه‌بندی‌شده: ابزار، گروه، دسته، علت، موضوع، کد خروج، یک خلاصه‌ی خنثی و برچسب شواهد (فیلدها پایین). دسته می‌گوید شکست از چه نوعی است، نه اینکه پروژه آسیب‌پذیر است. |
| `relevant_source` | شیء | فقط با `--relevant-source` | زیرمجموعه‌ی کد منبع مرتبط: `budget`، `text`، نمایه‌ی `files` و شمارنده‌ها (فیلدها پایین). |
| `scan_skipped` | عدد صحیح | فقط وقتی اسکن مسیری را نتوانسته بخواند | تعداد مسیرهایی که اسکن نتوانست بخواند. |
| `scan_skipped_samples` | آرایه‌ی رشته‌ها | همراه `scan_skipped` | چند نمونه از آن مسیرها. |
| `workspace` | شیء | فقط وقتی workspace شناسایی شده | workspace شناسایی‌شده: نوع و اعضای آن. |
| `workspaces` | آرایه | فقط با بیش از یک workspace | همه‌ی workspaceها؛ اولی برابر `workspace` است. |
| `package_results` | آرایه | فقط وقتی بسته‌ها چک‌های خودشان را اجرا کرده‌اند | خلاصه‌ی چک‌ها به‌تفکیک بسته. |
| `kubernetes` | شیء | فقط وقتی Helm یا Kustomize شناسایی شده | چارت‌های Helm، overlayهای Kustomize و در صورت وجود مانیفست‌های خام. |
| `compose` | شیء | فقط وقتی فایل Compose شناسایی شده | `files`: فایل‌های Compose با سرویس‌هایشان. |
| `makefile` | شیء | فقط وقتی Makefile شناسایی شده | `files` و `total_files` مربوط به Makefileها و targetهایشان. |
| `monorepo_tools` | آرایه | فقط وقتی تنظیمات Turborepo یا Nx پیدا شده | taskهای اعلام‌شده‌ی Turborepo و Nx که ایستا خوانده شده‌اند. |
| `components` | شیء | فقط برای پروژه‌ی ترکیبی | `components`، `links`، `total_components`، `total_links`. |
| `source_files` | آرایه | مگر با `--no-source` | `{path, size, content}` برای هر فایل شامل‌شده. |

## شیءهای تو در تو

فیلدهای شیءهای نام‌برده‌شده، به همان ترتیبی که نوشته می‌شوند.

- **`quick_context`**: `project`, `primary_language`, `languages`, `project_type`, `build_system`, `components`, `frameworks_declared`, `frameworks_declared_total`, `structure`, `total_files`, `total_loc`, `tests`, `quality`, `security`, `health`, `critical_findings`, `risks`, `reading_order`. `frameworks_declared` حداکثر ۸ مورد `{name, label, scope, manifest}` دارد؛ `frameworks_declared_total` شمار واقعی است.
- **`architecture`**: `components`, `workspaces`, `entry_points`, `compose`, `kubernetes`. پنج فهرست از خط‌های کوتاه متن ساده.
- **`risks`**: `risks`, `rules_not_evaluated`. `risks` فهرستی از `{rule_id, category, severity, evidence_refs, reason, limitations}` است؛ `severity` یکی از `high`، `warning` یا `info` است؛ `rules_not_evaluated` شناسه‌ی قاعده‌هایی است که داده‌شان غایب بود.
- **`relevant_source`**: `budget`, `text`, `files`, `omitted_files`, `omitted_snippets`, `withheld_lines`, `unreadable_files`. `budget` شامل `{tokens, bytes_cap, bytes_used, bytes_per_token, wrapper_bytes}` است؛ `files` نمایه‌ای از `{path, why, score, same_as, snippets}` است، نه نسخه‌ی دوم کد.
- **`detection`**: `languages`, `primary_language`, `project_type`, `build_system`, `markers_found`, `entry_points`, `details`.
- **`environment`**: `python`, `rust_core`, `os_name`, `architecture`, `cpu_summary`, `memory_summary`, `disk_free`, `hostname`, `tool_versions`.
- **`git`**: `branch`, `commit`, `status`, `log`, `diff`, `dirty`, `ahead`, `behind`, `tags`, `stashes`, `untracked`.
- **`stats`**: `total_files`, `total_loc`, `code_lines`, `comment_lines`, `blank_lines`, `files_by_extension`, `largest_directories`, `largest_files`, `duplicate_files`, `broken_symlinks`, `temporary_files`, `unused_cache_files`, `empty_files`, `executable_scripts`, `hidden_files`, `binary_files`. `largest_files` فهرست `[path, bytes]` و `duplicate_files` فهرست `[hash, [paths]]` است.
- **`health`**: `score`, `max_score`, `grade`, `breakdown`, `recommendations`, `critical_failures`, `checks_run`, `checks_skipped`, `confidence`, `checks_inconclusive`. `confidence` بین ۰ و ۱ است و می‌گوید چند چک اجرا شده، نه اینکه کد چقدر خوب است.
- **`result`**: `kind`, `returncode`, `summary`, `raw_output`, `warnings`, `errors`, `duration_seconds`, `skipped`, `skip_reason`, `inconclusive_reason`. شیء داخل `test_results`، `quality_results` و `security_results`؛ `inconclusive_reason` فقط وقتی مقدار دارد می‌آید.
- **`kubernetes`**: `helm_charts`، `kustomize_overlays` و، فقط وقتی مانیفست خام پیدا شده، `manifests` و `total_manifest_files`.
- **`failures`**: `tool`، `group`، `category`، `cause`، `subject`، `returncode`، `summary`، `signals`. `group` یکی از `test`، `quality` یا `security` است. `category` یکی از `compilation_failure`، `test_failure`، `lint_failure`، `security_tool_failure`، `security_finding_detected`، `configuration_failure`، `dependency_policy_failure`، `report_generation_failure` (رزرو، هنوز تولید نمی‌شود) یا `unknown_tool_failure` است. `cause` یکی از `exit_code`، `timeout`، `tool_not_found` یا `os_error` است؛ فقط `exit_code` یعنی خود ابزار اجرا شد و با کد غیرصفر خارج شد. `signals` برچسب شواهدی است که دسته را تعیین کرده، نه خروجی خام. یک چک شکست‌خورده می‌تواند چند ورودی بدهد (cargo deny در یک اجرا هم advisory و هم نقض سیاست گزارش می‌کند).

## تاریخچه‌ی نسخه

- **1.1** (R13-A): کلید اختیاری `failures` اضافه شد. عبارت‌بندی `known_issues` عوض شد: جمله‌ی کلی «Compilation or lint errors were detected.» دیگر وجود ندارد، چون روی یک گزارش واقعی از `cargo audit` و `cargo deny` می‌آمد، نه از کامپایلر یا linter. اسکریپت‌هایی که این جمله را می‌خواندند باید `failures[].category` را بخوانند. دو جمله‌ی قدیمی («One or more source files contain syntax errors.» و «A required Python dependency is missing.») بدون تغییرند.
- **1.0**: اولین نسخه‌ی مستند.
