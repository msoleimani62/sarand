# sarand

[![CI](https://github.com/msoleimani62/sarand/actions/workflows/ci.yml/badge.svg)](https://github.com/msoleimani62/sarand/actions/workflows/ci.yml)

**A cross-platform CLI that scans any project, detects its architecture, runs its tests, and generates a single AI-ready intelligence report.**

Point it at any directory — Python, Rust, Go, Node.js, C++, Java, or a mix — and it produces one Markdown/JSON/text/HTML/SARIF/PDF file containing the project tree, full source, test results, health score, and an AI-oriented summary. Built to run *before* you hand a codebase to an AI coding assistant.

**یک ابزار خط‌فرمان چندسکویی که هر پروژه‌ای را اسکن می‌کند، معماری‌اش را تشخیص می‌دهد، تست‌هایش را اجرا می‌کند و یک گزارش هوشمند و آماده برای هوش مصنوعی تولید می‌کند.**

آن را روی هر دایرکتوری اجرا کن — پایتون، Rust، Go، Node.js یا ترکیبی از این‌ها — و یک فایل Markdown/JSON/متنی تولید می‌شود که شامل درخت پروژه، سورس کامل، نتایج تست، امتیاز سلامت، و یک خلاصه‌ی مخصوص هوش مصنوعی است. برای اجرا *قبل از* دادن کدبیس به هر دستیار برنامه‌نویسی هوش مصنوعی ساخته شده.

---

## Table of contents · فهرست

- [Architecture · معماری](#architecture--معماری)
- [Install · نصب](#install--نصب)
- [Usage · استفاده](#usage--استفاده)
- [Persisted config · کانفیگ پایدار](#persisted-config--کانفیگ-پایدار)
- [Pasting a large report into a chat · پیست گزارش بزرگ در چت](#pasting-a-large-report-into-a-chat-with-no-file-upload--پیست-گزارش-بزرگ-در-چتی-بدون-آپلود-فایل)
- [Device storage & environment audit · بازرسی فضای دستگاه](#device-storage--environment-audit--بازرسی-فضای-ذخیره‌سازی-و-محیط-دستگاه)
- [Writing a plugin analyzer · نوشتن یک آنالایزر پلاگین](#writing-a-plugin-analyzer--نوشتن-یک-آنالایزر-پلاگین)
- [Current scope · دامنه‌ی فعلی](#current-scope--دامنهی-فعلی)
- [Uninstall · حذف نصب](#uninstall--حذف-نصب)

---

## Architecture · معماری

Hybrid Rust + Python. The CPU-heavy part (walking the whole tree, counting lines, hashing files for duplicate detection) is a Rust crate exposed via [PyO3](https://pyo3.rs)/[maturin](https://www.maturin.rs). Everything that changes often — language analyzers, output renderers, health scoring, the CLI, and the RC (report-communication) subsystem — is plain Python, loosely coupled and independently testable.

هیبرید Rust + پایتون. بخش سنگین محاسباتی (پیمایش کل درخت، شمارش خط، هش کردن فایل‌ها برای تشخیص تکراری) یک crate از جنس Rust است که از طریق PyO3/maturin به پایتون صادر می‌شود. هرچیزی که زیاد تغییر می‌کند — آنالایزرهای زبان، رندررهای خروجی، امتیازدهی سلامت، خود CLI، و زیرسیستم RC (ارتباط گزارش) — پایتون خالص است، کم‌وابسته و به‌صورت مستقل قابل‌تست.

If the Rust extension isn't compiled for your platform, sarand automatically falls back to an equivalent pure-Python scanner — slower, but functionally identical. Nothing breaks.

اگر پسوند Rust برای پلتفرمت کامپایل نشده باشد، sarand خودکار به یک اسکنر معادل خالص‌پایتونی برمی‌گردد — کندتر، ولی از نظر عملکردی یکسان. چیزی نمی‌شکند.

```
sarand/
├── Cargo.toml, src/*.rs        ← Rust core (compiles to sarand._core)
└── python/sarand/
    ├── rust_bridge.py          ← the one place that decides Rust-or-fallback
    ├── discovery/              ← project/language detection
    ├── analyzers/              ← one file per language, pluggable via entry_points
    ├── scanners/                ← git, environment, stats, tree, TODOs
    ├── core/                    ← health score, AI summary, secrets
    ├── renderers/               ← one file per output format
    ├── rc/                      ← report-communication (chunked paste) subsystem
    └── cli.py
```

## Install · نصب

Requires a Rust toolchain (for the fast path) and Python ≥ 3.10.

نیازمند زنجیره‌ابزار Rust (برای مسیر سریع) و پایتون ≥ ۳.۱۰ است.

### Recommended: pipx (globally available, no manual venv/PATH management)

`pipx` builds sarand into its own isolated environment and puts the `sarand` command on your PATH automatically — no `source activate`, no editing `.zshrc`.

`pipx` sarand را در محیط ایزوله‌ی خودش می‌سازد و دستور `sarand` را خودکار به PATH اضافه می‌کند — بدون `source activate`، بدون ویرایش دستی `.zshrc`.

```bash
pipx install ~/sarand
sarand --version
```

**Upgrading after pulling new sarand source:** a plain `pipx install` does not automatically refresh an already-installed copy. Use `install.sh` (in the repo root) instead of a raw `pipx install` from the second install onward — it checks whether a previous pipx installation exists, removes it first (printing what it's doing), then builds and installs the current source fresh:

**آپدیت بعد از دریافت سورس جدید sarand:** یک `pipx install` ساده نصب قبلی را خودکار تازه نمی‌کند. از دومین نصب به بعد به‌جای `pipx install` خام از `install.sh` (در ریشه‌ی ریپو) استفاده کن — بررسی می‌کند که آیا نصب قبلی pipx وجود دارد، اول آن را حذف می‌کند (و اعلامش می‌کند)، سپس نسخه‌ی فعلی سورس را از نو می‌سازد و نصب می‌کند:

```bash
./install.sh
```

If `pipx` itself isn't installed yet:

اگر خودِ `pipx` هنوز نصب نشده:

```bash
pip install pipx --break-system-packages
pipx ensurepath
```

(`pipx ensurepath` adds pipx's own bin directory to PATH — restart your shell, or `source ~/.zshrc`/`~/.bashrc`, afterward.)

(`pipx ensurepath` دایرکتوری bin خود pipx را به PATH اضافه می‌کند — بعدش شل را ری‌استارت کن یا `source ~/.zshrc`/`~/.bashrc` بزن.)

### Arch Linux: AUR

### آرچ‌لینوکس: AUR

If the `sarand` package has been published to the AUR, install it with any AUR helper:

اگر پکیج `sarand` روی AUR منتشر شده باشد، با هر AUR helperای نصبش کن:

```bash
yay -S sarand
# or, without a helper · یا بدون هلپر:
git clone https://aur.archlinux.org/sarand.git
cd sarand
makepkg -si
```

This builds the same Rust extension as the pipx path, using `rust` and `python-maturin` as build dependencies — no manual venv/PATH steps either way.

این هم دقیقاً همان extension راستی مسیر pipx را می‌سازد، با `rust` و `python-maturin` به‌عنوان وابستگی‌های build — اینجا هم بدون هیچ مرحله‌ی دستی venv/PATH.

### Alternative: development venv (editable, for working on sarand itself)

### جایگزین: venv توسعه (editable، برای کار کردن روی خود sarand)

```bash
pip install maturin --break-system-packages
cd sarand
maturin develop --release
```

If `maturin develop` fails to compile on your platform (rare, but can happen on some Termux/aarch64 toolchains), install without it — sarand will run on the pure-Python fallback:

اگر `maturin develop` روی پلتفرمت کامپایل نشد (نادر، ولی ممکن است روی برخی زنجیره‌ابزار Termux/aarch64 پیش بیاید)، بدون آن نصب کن — sarand روی fallback خالص‌پایتونی اجرا می‌شود:

```bash
pip install -e . --break-system-packages
```

## Usage · استفاده

```bash
sarand                                   # analyse the current directory
sarand --project ~/myproject --quality   # explicit path + lint/format checks
sarand --skip-tests --format json -o report.json
sarand --set-output-dir ~/ai-reports     # persist output location, once
sarand --cache                           # skip re-scanning unchanged files (opt-in)
sarand --doctor                          # environment diagnostics
sarand --full                            # everything on, nothing truncated -- the most complete report possible
```

`--full` is shorthand for "give me the absolute maximum": it turns on `--quality` and `--security`, and removes the file-size/tree-depth/tree-entry truncation limits entirely, so nothing gets skipped or cut short. An explicit `--max-depth`/`--max-entries`/`--max-file-size` you also pass still wins over `--full`'s defaults.

`--full` مخفف «حداکثر مطلق بده» است: `--quality` و `--security` را روشن می‌کند، و محدودیت‌های اندازه‌فایل/عمق‌درخت/تعداد‌ورودی‌های‌درخت را کاملاً حذف می‌کند تا چیزی رد یا کوتاه نشود. اگر خودت هم `--max-depth`/`--max-entries`/`--max-file-size` صریح بدهی، همچنان بر پیش‌فرض‌های `--full` اولویت دارد.

Re-running against the same project replaces its previous report at that output path automatically (and says so) — reports never pile up under the same filename.

اجرای مجدد روی همان پروژه، گزارش قبلی‌اش در همان مسیر خروجی را خودکار جایگزین می‌کند (و اعلامش می‌کند) — گزارش‌ها زیر یک نام فایل روی هم انباشته نمی‌شوند.

| Flag · پرچم | Meaning · معنی |
|---|---|
| `--project, -p PATH` | Project root (default: current directory) · ریشه‌ی پروژه (پیش‌فرض: دایرکتوری فعلی) |
| `--output-dir, -d PATH` | Where to write the report · مسیر خروجی گزارش |
| `--output-name, -o NAME` | Report filename (default: `sarand-<project>-report.<ext>`) · نام فایل گزارش |
| `--set-output-dir PATH` | Persist PATH as the default output dir and exit · مسیر خروجی پیش‌فرض را ذخیره و خارج شو |
| `--format, -f {markdown,json,text,html,pdf,sarif}` | Output format · فرمت خروجی |
| `--skip-tests` | Skip running tests · صرف‌نظر از اجرای تست‌ها |
| `--quality` | Run lint/format checks per detected language · بررسی lint/format برای هر زبان تشخیص‌داده‌شده |
| `--security` | Run security/vulnerability checks per detected language · بررسی امنیتی/آسیب‌پذیری |
| `--full` | Maximum completeness: `--quality` + `--security` + no truncation limits · حداکثر کامل بودن |
| `--cache` | Skip re-scanning TODOs/secrets in files unchanged since the last `--cache` run (opt-in) · صرف‌نظر از اسکن مجدد فایل‌های بدون‌تغییر |
| `--clear-cache` | Delete the incremental-scan cache for this project and exit · حذف کش اسکن افزایشی |
| `--doctor` | Run environment diagnostics (Rust core, per-language toolchains, PDF engines) and exit · تشخیص محیط |
| `--no-source` | Don't embed source file contents · عدم embed کردن سورس |
| `--no-health` | Skip health-score calculation · صرف‌نظر از محاسبه‌ی امتیاز سلامت |
| `--verbose, -v` / `--debug` | Logging verbosity · سطح جزئیات لاگ |

## Persisted config · کانفیگ پایدار

`sarand --set-output-dir <path>` writes to an OS-appropriate config file, so every future run (without `-d`) drops the report there:

`sarand --set-output-dir <path>` یک فایل کانفیگ متناسب با سیستم‌عامل می‌نویسد، تا هر اجرای بعدی (بدون `-d`) گزارش را همان‌جا بگذارد:

- Linux: `$XDG_CONFIG_HOME/sarand/config.json` or `~/.config/sarand/config.json`
- macOS: `~/Library/Application Support/sarand/config.json`
- Windows: `%APPDATA%\sarand\config.json`

## Pasting a large report into a chat with no file upload · پیست گزارش بزرگ در چتی بدون آپلود فایل

`python3 -m sarand.rc.command` (the RC subsystem) splits any file (typically a `sarand --full` report) into paste-sized chunks wrapped in an integrity-checked protocol envelope (`SARAND RC START/CHUNK/END`, each with a `session_id`, `chunk_hash`, and a final `report_hash` an AI receiver can verify before treating the transfer as complete), and walks you through them one at a time, with resumable state (next/back/history/jump-to-block) across separate invocations. On a terminal that supports the OSC52 escape sequence (Termux included) each chunk is copied straight to the system clipboard with no external clipboard tool and no graphical session needed — the only thing that works on a non-rooted Android phone with no X11/Wayland.

`python3 -m sarand.rc.command` (زیرسیستم RC) هر فایلی (معمولاً یک گزارش `sarand --full`) را به تکه‌های اندازه‌مناسب پیست می‌شکند، هرکدام داخل یک قاب پروتکل صحت‌سنج (`SARAND RC START/CHUNK/END`، با `session_id`، `chunk_hash`، و یک `report_hash` نهایی که یک AI گیرنده می‌تواند قبل از کامل دانستن انتقال verify کند)، و یکی‌یکی طی‌شان می‌کند، با وضعیت قابل‌ازسرگیری بین اجراهای جدا. روی ترمینالی که OSC52 را پشتیبانی می‌کند (از جمله Termux) هر تکه مستقیم در کلیپ‌بورد سیستم کپی می‌شود، بدون ابزار کلیپ‌بورد خارجی و بدون نشست گرافیکی — تنها چیزی که روی گوشی اندروید بدون روت و بدون X11/Wayland کار می‌کند.

```bash
sarand --full -d /tmp/reports
python3 -m sarand.rc.command --source /tmp/reports/sarand-*-report.md
# paste the chunk, then run again with no flags for the next one:
python3 -m sarand.rc.command --source /tmp/reports/sarand-*-report.md
```

State lives under `.sarand-rc/` (namespaced per source file). Useful commands:

وضعیت زیر `.sarand-rc/` نگهداری می‌شود (جداگانه برای هر فایل منبع). دستورات کاربردی:

| Command · دستور | Effect · اثر |
|---|---|
| *(no flags)* | Emit next unsent chunk · ارسال تکه‌ی بعدی |
| `--info, -i` | Show session/progress status · نمایش وضعیت نشست |
| `--back, -b` | Re-emit the previous block · بازارسال بلاک قبلی |
| `--back-run, -br` | Re-emit the previous history entry · بازارسال آخرین ارسال |
| `-n N` | Jump to block N · پرش به بلاک N |
| `--chunk, -c N` | Emit chunk N of the current block · ارسال تکه‌ی N از بلاک فعلی |
| `--reset` / `--clean` | Delete state and start a fresh session · پاک‌کردن وضعیت و شروع نشست تازه |

## Device storage & environment audit · بازرسی فضای ذخیره‌سازی و محیط دستگاه

`python3 -m sarand.device_report.command` is a separate, read-only tool ported from a standalone bash script into sarand proper: it scans your whole device (not a single project) for space hogs, duplicate files, stale files, build-artifact caches, package-manager footprints, and Android/Termux/Kali/proot environment details, and writes one Markdown report. It never deletes, moves, modifies, chmods, chowns, or installs anything — evidence for a cleanup decision, not an automated cleanup.

`python3 -m sarand.device_report.command` ابزاری جدا و فقط‌خواندنی است که از یک اسکریپت مستقل بش به خودِ sarand پورت شده: کل دستگاهت را (نه یک پروژه‌ی خاص) برای فضاخورهای بزرگ، فایل‌های تکراری، فایل‌های قدیمی، کش‌های build artifact، ردپای package managerها، و جزئیات محیط Android/Termux/Kali/proot اسکن می‌کند و یک گزارش Markdown می‌نویسد. هیچ‌وقت چیزی را حذف، جابه‌جا، تغییر، chmod، chown، یا نصب نمی‌کند — شاهد برای تصمیم پاک‌سازی است، نه خودِ پاک‌سازی خودکار.

```bash
python3 -m sarand.device_report.command
python3 -m sarand.device_report.command --full -o ~/device-report.md
python3 -m sarand.device_report.command -r ~/Projects -x ~/Projects/big-archive --old-days 90
```

| Flag | Effect · اثر |
|---|---|
| `-o, --output PATH` | Output report path · مسیر خروجی گزارش |
| `-r, --root DIR` | Extra scan root, repeatable (default: `$HOME` + `/sdcard` if present) · روت اضافه، تکرارپذیر |
| `-x, --exclude PATH` | Exclude a path from every scan, repeatable · حذف یک مسیر از همه‌ی اسکن‌ها |
| `-q, --quick` | Skip duplicate and stale-file scans (the two slowest) · رد کردن اسکن تکراری‌ها و فایل‌های قدیمی |
| `--full` | Always run duplicate/stale scans (overrides `--quick`) and remove the `--top` row cap so every match is listed · همیشه اسکن تکراری/قدیمی را اجرا کن و سقف ردیف `--top` را حذف کن |
| `-n, --top N` | Rows per top-space table (default 30; `--full` makes this unlimited unless set explicitly) · تعداد ردیف در جدول‌های فضا |
| `-d, --old-days N` | Stale-file threshold in days (default 180) · آستانه‌ی روز برای فایل قدیمی |
| `-m, --min-file-size MB` | Minimum size for the large-files section (default 50) · حداقل اندازه برای بخش فایل‌های بزرگ |
| `-u, --dup-min-size MB` | Minimum size considered for duplicate scanning (default 5) · حداقل اندازه برای اسکن تکراری‌ها |
| `-D, --max-depth N` | Maximum scan depth, 0 = unlimited (default) · حداکثر عمق اسکن |
| `--min-top-space MB` | Minimum size for a row in the Executive Summary's Top Space Users table, 0 = no filter (default 1.0) · حداقل اندازه برای ردیف جدول Top Space Users |
| `--expand-aggregates` | List every `__pycache__`/`.mypy_cache`/`.pytest_cache`/`.ruff_cache` instance individually instead of one aggregated line per pattern (`--full` implies this) · لیست تک‌تک نمونه‌های کش به‌جای یک خط تجمیعی |
| `--summary-only` | Only render sections 1 and 12 -- all scanning still happens (for an accurate summary), but per-section detail is omitted; mutually exclusive with `--full` · فقط بخش‌های ۱ و ۱۲ را رندر کن |

A real run against a full development machine produced a 5+ MiB report — almost entirely thousands of individually-listed `__pycache__`-style cache directories, plus KB-sized entries cluttering the summary table, neither of which added anything to a cleanup decision. `--min-top-space` and the default aggregation behavior above exist specifically to fix that; `--summary-only` is for repeat runs (e.g. handing the report to an AI repeatedly) where only the Executive Summary is actually read.

یک اجرای واقعی روی یک ماشین توسعه‌ی کامل گزارشی ۵+ مگابایتی تولید کرد — تقریباً تماماً هزاران پوشه‌ی کش شبیه `__pycache__` که تک‌تک لیست شده بودند، به‌علاوه موارد چند-کیلوبایتیِ شلوغ‌کننده‌ی جدول خلاصه، که هیچ‌کدام به تصمیم پاک‌سازی چیزی اضافه نمی‌کردند. `--min-top-space` و رفتار پیش‌فرض تجمیع بالا دقیقاً برای رفع همین ساخته شدند؛ `--summary-only` برای اجراهای مکرر (مثلاً دادن گزارش به یک هوش مصنوعی به‌طور مکرر) است که فقط Executive Summary واقعاً خوانده می‌شود.

**Not yet implemented:** directory-level duplicate detection (comparing whole directory *trees* for overlapping content, not just individual files ≥5 MB) — flagged as valuable but scoped out of this pass for its own design/performance review, since a naive version would mean hashing every file in every candidate directory.

**هنوز پیاده‌سازی نشده:** تشخیص تکراری در سطح دایرکتوری (مقایسه‌ی کل *درخت* پوشه‌ها برای محتوای هم‌پوشان، نه فقط فایل‌های تکی ≥۵ مگابایت) — به‌عنوان چیزی ارزشمند علامت‌گذاری شده ولی از این دور بیرون گذاشته شد تا بازبینی طراحی/عملکرد جداگانه‌ی خودش را داشته باشد، چون نسخه‌ی ساده‌اش یعنی هش‌کردن هر فایل در هر دایرکتوری کاندید.

Every filesystem-sizing, walking, and hashing operation (`du`, `find -printf`, `numfmt`, `sha256sum` in the original bash version) is pure Python stdlib here instead — `os.walk`/`hashlib` behave identically across glibc, musl, BusyBox (Termux's default), and Toybox (stock Android) userlands, where GNU-specific flags on those external tools do not. Only genuinely platform-specific data (package-manager listings, `getprop`, `git status`, the system mount table) still shells out to the real tool and skips cleanly when it's absent, exactly like every sarand language analyzer.

هر عملیات اندازه‌گیری، پیمایش، و هش‌کردن فایل‌سیستم (`du`، `find -printf`، `numfmt`، `sha256sum` در نسخه‌ی بش) اینجا پایتون خالص stdlib است -- `os.walk`/`hashlib` روی محیط‌های glibc، musl، BusyBox (پیش‌فرض Termux)، و Toybox (اندروید خام) یکسان رفتار می‌کنند، جایی که فلگ‌های مخصوص GNU آن ابزارهای بیرونی یکسان رفتار نمی‌کنند. فقط داده‌ی واقعاً مخصوصِ پلتفرم (فهرست package manager، `getprop`، `git status`، جدول mount سیستم) همچنان به ابزار واقعی متکی است و در نبودش تمیز رد می‌شود، دقیقاً مثل هر آنالایزر زبانِ sarand.

## Writing a plugin analyzer · نوشتن یک آنالایزر پلاگین

Add support for a new language without touching sarand's source: implement the `LanguageAnalyzer` protocol (`matches`, `entry_points`, `run_tests`, `run_quality`) in your own package, and register it under the `sarand.analyzers` entry-point group:

اضافه‌کردن پشتیبانی یک زبان جدید بدون دست‌زدن به سورس sarand: پروتکل `LanguageAnalyzer` (`matches`, `entry_points`, `run_tests`, `run_quality`) را در پکیج خودت پیاده کن، و آن را زیر گروه entry-point با نام `sarand.analyzers` ثبت کن:

```toml
# in your plugin's pyproject.toml
[project.entry-points."sarand.analyzers"]
zig = "sarand_zig_plugin:ZigAnalyzer"
```

sarand discovers and runs it automatically, concurrently with every other matching analyzer.

sarand آن را خودکار پیدا و اجرا می‌کند، به‌صورت هم‌زمان با هر آنالایزر دیگری که مطابقت دارد.

## Current scope · دامنه‌ی فعلی

Implemented: Python/Rust/Go/Node.js/C++/Java analyzers (tests + quality + security checks), Markdown/JSON/text/HTML/SARIF renderers, PDF export (via an installed `wkhtmltopdf`/`weasyprint`), secret detection and exclusion, an opt-in incremental scan cache, `sarand --doctor`, an RC (report-communication) subsystem for chunked/pasted transfer to AI chats, and CI across Linux/macOS/Windows. Not yet implemented: Zig/Dart/Ruby/PHP/Lua/Swift/C# analyzers, and packaging beyond pipx (Docker/AUR/Homebrew/deb-rpm/standalone binary) — added only as actually needed, per `AGENTS.md`'s roadmap.

پیاده‌سازی‌شده: آنالایزرهای Python/Rust/Go/Node.js/C++/Java (تست + کیفیت + امنیت)، رندررهای Markdown/JSON/متن/HTML/SARIF، خروجی PDF (از طریق `wkhtmltopdf`/`weasyprint` نصب‌شده)، تشخیص و حذف secret، کش افزایشی اختیاری، `sarand --doctor`، زیرسیستم RC برای انتقال تکه‌ای/پیستی به چت‌های هوش مصنوعی، و CI روی لینوکس/مک/ویندوز. هنوز نیست: آنالایزرهای Zig/Dart/Ruby/PHP/Lua/Swift/C#، و پکیجینگ فراتر از pipx (Docker/AUR/Homebrew/deb-rpm/باینری مستقل) — طبق نقشه‌راه `AGENTS.md` فقط در صورت نیاز واقعی اضافه می‌شوند.

## Uninstall · حذف نصب

If installed via pipx:

اگر با pipx نصب شده:

```bash
pipx uninstall sarand
rm -rf ~/.config/sarand
```

If installed via the development venv (`pip install -e .` / `maturin develop`):

اگر با venv توسعه نصب شده:

```bash
pip uninstall sarand --break-system-packages
rm -rf ~/.config/sarand
```
