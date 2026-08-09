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

echo "==> sarand installer/upgrader"
echo "==> Source: $SCRIPT_DIR"

if ! command -v pipx >/dev/null 2>&1; then
    echo "==> pipx not found."
    echo "    Install it first: pip install pipx --break-system-packages && pipx ensurepath"
    exit 1
fi

if pipx list --short 2>/dev/null | grep -q '^sarand '; then
    echo "==> Previous pipx installation found -- removing it first..."
    pipx uninstall sarand
    echo "==> Previous installation removed."
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
