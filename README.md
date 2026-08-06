# sarand

**A cross-platform CLI that scans any project, detects its architecture, runs its tests, and generates a single AI-ready intelligence report.**

Point it at any directory — Python, Rust, Go, Node.js, or a mix — and it produces one Markdown/JSON/text file containing the project tree, full source, test results, health score, and an AI-oriented summary. Built to run *before* you hand a codebase to an AI coding assistant.

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

```bash
pip install maturin --break-system-packages
cd sarand
maturin develop --release   # compiles the Rust core, installs sarand editable
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
```

| Flag | Meaning |
|---|---|
| `--project, -p PATH` | Project root (default: current directory) |
| `--output-dir, -d PATH` | Where to write the report |
| `--output-name, -o NAME` | Report filename (default: `sarand-<project>-report.<ext>`) |
| `--set-output-dir PATH` | Persist PATH as the default output dir and exit |
| `--format, -f {markdown,json,text}` | Output format |
| `--skip-tests` | Skip running tests |
| `--quality` | Run lint/format checks per detected language |
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

This is a from-scratch architectural rebuild (Phase 1–3 of the roadmap). Built-in language analyzers: **Python, Rust, Go, Node.js**. Security scanning (`--security`), the HTML dashboard, PDF/SARIF renderers, and the incremental-scan cache are deliberately not yet implemented — they're real next phases, not silent gaps.

این یک بازسازی معماری از صفر است (فاز ۱ تا ۳ نقشه‌راه). آنالایزرهای داخلی: **پایتون، Rust، Go، Node.js**. اسکن امنیتی (`--security`)، داشبورد HTML، رندررهای PDF/SARIF، و کش اسکن افزایشی عمداً هنوز پیاده‌سازی نشده‌اند — این‌ها فازهای بعدی واقعی هستند، نه یک نقص پنهان.

## Uninstall · حذف نصب

```bash
pip uninstall sarand --break-system-packages
rm -rf ~/.config/sarand   # remove persisted config (Linux)
```

## Troubleshooting

**`externally-managed-environment` error even after activating the venv:**
Some venvs created by `uv venv` intentionally ship without `pip` (uv manages
packages itself). Install it once with:
~/.venv/bin/python -m ensurepip --upgrade
Then `pip install <pkg>` works normally inside that venv from then on.
