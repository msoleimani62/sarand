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
