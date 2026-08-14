#!/usr/bin/env bash
# sarand installer / upgrader.
#
# Run from anywhere -- it locates itself via its own script path, not
# the current working directory. Checks whether a previous pipx
# installation exists; if so, removes it first (with clear messages)
# before building and installing the current source tree. This is
# what makes re-running this script after pulling new sarand code
# actually pick up the changes -- a plain `pipx install` without first
# uninstalling can leave a stale snapshot from whenever it was last
# run, since pipx installs are not editable by default.
#
# نصب‌کننده/به‌روزرسان sarand. از هر جایی اجرا شود کار می‌کند -- خودش را
# از روی مسیر اسکریپت پیدا می‌کند، نه دایرکتوری فعلی. بررسی می‌کند که
# نصب قبلی pipx وجود دارد یا نه؛ اگر دارد، اول آن را حذف می‌کند (با
# پیام‌های واضح) پیش از ساخت و نصب نسخه‌ی فعلی سورس. همین چیزی است که
# باعث می‌شود اجرای دوباره‌ی این اسکریپت بعد از دریافت کد جدید sarand
# واقعاً تغییرات را اعمال کند -- یک `pipx install` ساده بدون uninstall
# اول، ممکن است snapshot قدیمی از آخرین باری که اجرا شده را نگه دارد،
# چون نصب‌های pipx به‌طور پیش‌فرض editable نیستند.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPX_VENV_DIR="$HOME/.local/share/pipx/venvs/sarand"

echo "==> sarand installer/upgrader"
echo "==> Source: $SCRIPT_DIR"

if ! command -v pipx >/dev/null 2>&1; then
    echo "==> pipx not found."
    echo "    Install it first: pip install pipx --break-system-packages && pipx ensurepath"
    exit 1
fi

if pipx list --short 2>/dev/null | grep -q '^sarand '; then
    echo "==> Previous pipx installation found -- removing it first..."
    if ! pipx uninstall sarand; then
        # pipx itself can fail to read a previous install's metadata
        # (a known pipx bug: "Unknown metadata version X. Perhaps it
        # was installed with a later version of pipx" -- pipx's own
        # internal venv bookkeeping got corrupted, not a sarand issue).
        # `pipx uninstall` hits the same read and fails the same way,
        # so fall back to removing the venv directory directly.
        # خودِ pipx می‌تواند در خواندن متادیتای نصب قبلی شکست بخورد (یک
        # باگ شناخته‌شده‌ی pipx: خرابی بوکیپینگ داخلی venv، نه مشکلی از
        # sarand). چون `pipx uninstall` هم به همان خواندن برمی‌خورد و
        # به همان شکل شکست می‌خورد، به حذف مستقیم پوشه‌ی venv برمی‌گردیم.
        echo "==> pipx uninstall failed (likely corrupted pipx metadata, see"
        echo "    https://github.com/pypa/pipx/issues/1619) -- removing the"
        echo "    venv directory directly instead: $PIPX_VENV_DIR"
        rm -rf "$PIPX_VENV_DIR"
    fi
    echo "==> Previous installation removed."
elif [ -d "$PIPX_VENV_DIR" ]; then
    # A venv directory can exist on disk without `pipx list` showing it
    # at all, for the same corrupted-metadata reason above -- pipx
    # silently omits entries it can't parse rather than erroring on
    # `list`. Left alone, `pipx install` would hit the same broken
    # metadata and fail with the cryptic "Unknown metadata version" error.
    # یک پوشه‌ی venv می‌تواند روی دیسک باشد بدون این‌که `pipx list` اصلاً
    # نشانش دهد، به همان دلیل خرابی متادیتا -- pipx ورودی‌هایی را که
    # نمی‌تواند parse کند بی‌صدا از `list` حذف می‌کند، نه این‌که خطا بدهد.
    echo "==> Found a stale pipx venv directory not tracked by 'pipx list'"
    echo "    (likely corrupted pipx metadata) -- removing it directly: $PIPX_VENV_DIR"
    rm -rf "$PIPX_VENV_DIR"
elif command -v sarand >/dev/null 2>&1; then
    echo "==> A 'sarand' command exists on PATH but wasn't installed via pipx"
    echo "    ($(command -v sarand)). Not touching it automatically -- if this"
    echo "    is a stale dev-venv install, remove it manually first."
else
    echo "==> No previous installation found."
fi

echo "==> Building and installing the current version..."
pipx install "$SCRIPT_DIR"

echo "==> Done."
sarand --version
