# sarand

[![CI](https://github.com/msoleimani62/sarand/actions/workflows/ci.yml/badge.svg)](https://github.com/msoleimani62/sarand/actions/workflows/ci.yml)

**A cross-platform CLI that scans any project, detects its architecture, runs its tests, and generates a single AI-ready intelligence report.**

Point it at any directory — Python, Rust, Go, Node.js, C++, Java, or a mix — and it produces one Markdown/JSON/text/HTML/SARIF/PDF file containing the project tree, full source, test results, health score, and an AI-oriented summary. Built to run *before* you hand a codebase to an AI coding assistant.

**یک ابزار خط‌فرمان چندسکویی که هر پروژه‌ای را اسکن می‌کند، معماری‌اش را تشخیص می‌دهد، تست‌هایش را اجرا می‌کند و یک گزارش هوشمند و آماده برای هوش مصنوعی تولید می‌کند.**

آن را روی هر دایرکتوری اجرا کن — پایتون، Rust، Go، Node.js یا ترکیبی از این‌ها — و یک فایل Markdown/JSON/متنی تولید می‌شود که شامل درخت پروژه، سورس کامل، نتایج تست، امتیاز سلامت، و یک خلاصه‌ی مخصوص هوش مصنوعی است. برای اجرا *قبل از* دادن کدبیس به هر دستیار برنامه‌نویسی هوش مصنوعی ساخته شده.

---

## Architecture · معماری

Hybrid Rust + Python. The CPU-heavy part (walking the whole tree, counting lines, hashing files for duplicate detection) is a Rust crate exposed via [PyO3](https://pyo3.rs)/[maturin](https://www.maturin.rs). Everything that changes often — language analyzers, output renderers, health scoring, the CLI — is plain Python, loosely coupled and independently testable.

هیبرید Rust + پایتون. بخش سنگین محاسباتی (پیمایش کل درخت، شمارش خط، هش کردن فایل‌ها برای تشخیص تکراری) یک crate از جنس Rust است که از طریق PyO3/maturin به پایتون صادر می‌شود. هرچیزی که زیاد تغییر می‌کند — آنالایزرهای زبان، رندررهای خروجی، امتیازدهی سلامت، خود CLI — پایتون خالص است، کم‌وابسته و به‌صورت مستقل قابل‌تست.

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
    ├── core/                    ← health score, AI summary
    ├── renderers/               ← one file per output format
    └── cli.py
```

## Install · نصب

Requires a Rust toolchain (for the fast path) and Python ≥ 3.10.

نیازمند زنجیره‌ابزار Rust (برای مسیر سریع) و پایتون ≥ ۳.۱۰ است.

### Recommended: pipx (globally available, no manual venv/PATH management)

`pipx` builds sarand into its own isolated environment and puts the
`sarand` command on your PATH automatically — no `source activate`, no
editing `.zshrc`.

`pipx` sarand را در محیط ایزوله‌ی خودش می‌سازد و دستور `sarand` را
خودکار به PATH اضافه می‌کند — بدون `source activate`، بدون ویرایش دستی
`.zshrc`.

```bash
pipx install ~/sarand
sarand --version
```

**Upgrading after pulling new sarand source:** a plain `pipx install`
does not automatically refresh an already-installed copy. Use
`install.sh` (in the repo root) instead of a raw `pipx install` from
the second install onward — it checks whether a previous pipx
installation exists, removes it first (printing what it's doing), then
builds and installs the current source fresh:

**آپدیت بعد از دریافت سورس جدید sarand:** یک `pipx install` ساده
نصب قبلی را خودکار تازه نمی‌کند. از دومین نصب به بعد به‌جای
`pipx install` خام از `install.sh` (در ریشه‌ی ریپو) استفاده کن — بررسی
می‌کند که آیا نصب قبلی pipx وجود دارد، اول آن را حذف می‌کند (و اعلام
می‌کند)، سپس نسخه‌ی فعلی سورس را از نو می‌سازد و نصب می‌کند:

```bash
./install.sh
```

If `pipx` itself isn't installed yet:

```bash
pip install pipx --break-system-packages
pipx ensurepath
```

(`pipx ensurepath` adds pipx's own bin directory to PATH — restart your
shell, or `source ~/.zshrc`/`~/.bashrc`, afterward.)

### Alternative: development venv (editable, for working on sarand itself)

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
```

Re-running against the same project replaces its previous report at
that output path automatically (and says so) — reports never pile up
under the same filename.

اجرای مجدد روی همان پروژه، گزارش قبلی‌اش در همان مسیر خروجی را خودکار
جایگزین می‌کند (و اعلامش می‌کند) — گزارش‌ها زیر یک نام فایل روی هم
انباشته نمی‌شوند.

| Flag | Meaning |
|---|---|
| `--project, -p PATH` | Project root (default: current directory) |
| `--output-dir, -d PATH` | Where to write the report |
| `--output-name, -o NAME` | Report filename (default: `sarand-<project>-report.<ext>`) |
| `--set-output-dir PATH` | Persist PATH as the default output dir and exit |
| `--format, -f {markdown,json,text,html,pdf,sarif}` | Output format |
| `--skip-tests` | Skip running tests |
| `--quality` | Run lint/format checks per detected language |
| `--security` | Run security/vulnerability checks per detected language |
| `--cache` | Skip re-scanning TODOs/secrets in files unchanged since the last `--cache` run (opt-in) |
| `--clear-cache` | Delete the incremental-scan cache for this project and exit |
| `--doctor` | Run environment diagnostics (Rust core, per-language toolchains, PDF engines) and exit |
| `--no-source` | Don't embed source file contents |
| `--no-health` | Skip health-score calculation |
| `--verbose, -v` / `--debug` | Logging verbosity |

## Persisted config · کانفیگ پایدار

`sarand --set-output-dir <path>` writes to an OS-appropriate config file, so every future run (without `-d`) drops the report there:

- Linux: `$XDG_CONFIG_HOME/sarand/config.json` or `~/.config/sarand/config.json`
- macOS: `~/Library/Application Support/sarand/config.json`
- Windows: `%APPDATA%\sarand\config.json`

## Writing a plugin analyzer · نوشتن یک آنالایزر پلاگین

Add support for a new language without touching sarand's source: implement the `LanguageAnalyzer` protocol (`matches`, `entry_points`, `run_tests`, `run_quality`) in your own package, and register it under the `sarand.analyzers` entry-point group:

```toml
# in your plugin's pyproject.toml
[project.entry-points."sarand.analyzers"]
zig = "sarand_zig_plugin:ZigAnalyzer"
```

sarand discovers and runs it automatically, concurrently with every other matching analyzer.

## Current scope · دامنه‌ی فعلی

Implemented: Python/Rust/Go/Node.js/C++/Java analyzers (tests + quality + security checks), Markdown/JSON/text/HTML/SARIF renderers, PDF export (via an installed `wkhtmltopdf`/`weasyprint`), secret detection and exclusion, an opt-in incremental scan cache, `sarand --doctor`, and CI across Linux/macOS/Windows. Not yet implemented: Zig/Dart/Ruby/PHP/Lua/Swift/C# analyzers, and packaging beyond pipx (Docker/AUR/Homebrew/deb-rpm/standalone binary) — added only as actually needed, per `AGENTS.md`'s roadmap.

پیاده‌سازی‌شده: آنالایزرهای Python/Rust/Go/Node.js/C++/Java (تست + کیفیت + امنیت)، رندررهای Markdown/JSON/متن/HTML/SARIF، خروجی PDF (از طریق `wkhtmltopdf`/`weasyprint` نصب‌شده)، تشخیص و حذف secret، کش افزایشی اختیاری، `sarand --doctor`، و CI روی لینوکس/مک/ویندوز. هنوز نیست: آنالایزرهای Zig/Dart/Ruby/PHP/Lua/Swift/C#، و پکیجینگ فراتر از pipx (Docker/AUR/Homebrew/deb-rpm/باینری مستقل) — طبق نقشه‌راه `AGENTS.md` فقط در صورت نیاز واقعی اضافه می‌شوند.

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
