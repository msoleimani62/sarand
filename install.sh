#!/usr/bin/env bash
# sarand installer / upgrader.
#
# Run from anywhere -- it locates itself via its own script path, not
# the current working directory. It replaces a previous pipx installation
# with a fresh build of the current source tree (a plain `pipx install`
# can leave a stale snapshot, since pipx installs are not editable).
#
# The old installation is only *set aside* while the new one is built,
# never deleted up front: the build needs the network (it downloads
# `maturin` and the dependencies) and a Rust toolchain, and either can
# fail. If every attempt fails, the previous installation is restored
# exactly as it was, so a failed upgrade never leaves you without sarand.
# Only after a successful build is the old copy removed.
#
# Tuning (environment variables):
#   SARAND_INSTALL_ATTEMPTS      build attempts before giving up (default 3)
#   SARAND_INSTALL_RETRY_DELAY   seconds between attempts (default 5)
#
# نصب‌کننده/به‌روزرسان sarand. از هر جایی اجرا شود کار می‌کند -- خودش را
# از روی مسیر اسکریپت پیدا می‌کند، نه دایرکتوری فعلی. نصب قبلی pipx را با
# یک build تازه از سورس فعلی جایگزین می‌کند (یک `pipx install` ساده ممکن
# است snapshot قدیمی نگه دارد، چون نصب‌های pipx به‌طور پیش‌فرض editable
# نیستند).
#
# نصب قدیمی فقط *کنار گذاشته می‌شود* تا نسخه‌ی جدید ساخته شود و هیچ‌وقت
# از اول پاک نمی‌شود: build به شبکه (دانلود `maturin` و وابستگی‌ها) و یک
# زنجیره‌ابزار Rust نیاز دارد و هر دو می‌توانند شکست بخورند. اگر همه‌ی
# تلاش‌ها شکست بخورند، نصب قبلی دقیقاً همان‌طور که بود برمی‌گردد، پس یک
# به‌روزرسانی ناموفق هرگز تو را بدون sarand رها نمی‌کند. فقط بعد از یک build
# موفق، نسخه‌ی قدیمی حذف می‌شود.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPX_HOME_DIR="${PIPX_HOME:-$HOME/.local/share/pipx}"
PIPX_VENV_DIR="$PIPX_HOME_DIR/venvs/sarand"
BACKUP_DIR="$PIPX_HOME_DIR/.sarand-previous-venv"
ATTEMPTS="${SARAND_INSTALL_ATTEMPTS:-3}"
RETRY_DELAY="${SARAND_INSTALL_RETRY_DELAY:-5}"
# What this script has done to the pipx venv so far -- what an interrupt or a
# failed build has to undo:
#   idle   nothing touched yet (an existing install is left exactly alone)
#   aside  the previous install was moved to $BACKUP_DIR
#   fresh  there was no previous install; a build may have left a partial venv
# آنچه این اسکریپت تا اینجا با venv ی pipx کرده -- چیزی که یک وقفه یا build
# ناموفق باید برگرداند:
#   idle   هنوز به چیزی دست نزده (نصب موجود دقیقاً دست‌نخورده می‌ماند)
#   aside  نصب قبلی به $BACKUP_DIR منتقل شده
#   fresh  نصب قبلی نبوده؛ ممکن است build یک venv ناقص به‌جا گذاشته باشد
STATE=idle

# Slow mobile networks are the usual cause of a failed build; give both
# pip and uv (pipx can use either) a generous timeout.
# شبکه‌ی کند موبایل علت معمول شکست build است؛ به pip و uv (pipx می‌تواند
# از هر دو استفاده کند) timeout سخاوتمندانه می‌دهیم.
export PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT:-180}"
export UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-180}"

# Undo what this run changed. Safe to call at any point: in the `idle` state
# it does nothing, so it can never delete an install it has not set aside.
# هر چه این اجرا عوض کرده را برمی‌گرداند. در هر لحظه امن است: در حالت `idle`
# کاری نمی‌کند، پس هرگز نصبی را که کنار نگذاشته پاک نمی‌کند.
restore_previous() {
    case "$STATE" in
        aside)
            rm -rf "$PIPX_VENV_DIR"
            mv "$BACKUP_DIR" "$PIPX_VENV_DIR"
            echo "==> The previous installation was restored -- nothing was lost."
            ;;
        fresh)
            rm -rf "$PIPX_VENV_DIR"
            ;;
    esac
    STATE=idle
}

# Ctrl-C (or a terminated shell) in the middle of a slow build must not
# leave the old installation set aside and sarand missing.
# Ctrl-C (یا بسته‌شدن شل) وسط یک build کند نباید نصب قدیمی را کنار گذاشته و
# sarand را ناپدید کند.
interrupted() {
    echo "==> Interrupted." >&2
    restore_previous >&2
    exit 130
}

main() {
    trap interrupted INT TERM

    echo "==> sarand installer/upgrader"
    echo "==> Source: $SCRIPT_DIR"

    if ! command -v pipx >/dev/null 2>&1; then
        echo "==> pipx not found."
        echo "    Install it first: pip install pipx --break-system-packages && pipx ensurepath"
        exit 1
    fi

    # Set the previous installation aside. Moving the directory works even
    # when pipx cannot read its metadata (a known pipx bug, see
    # https://github.com/pypa/pipx/issues/1619), where `pipx uninstall` fails.
    # نصب قبلی را کنار می‌گذاریم. جابه‌جاکردن پوشه حتی وقتی pipx نتواند
    # متادیتایش را بخواند کار می‌کند (باگ شناخته‌شده‌ی pipx) که
    # `pipx uninstall` آنجا شکست می‌خورد.
    if [ -e "$PIPX_VENV_DIR" ]; then
        echo "==> Previous installation found -- setting it aside while the new one is built..."
        rm -rf "$BACKUP_DIR"
        mv "$PIPX_VENV_DIR" "$BACKUP_DIR"
        STATE=aside
    else
        if command -v sarand >/dev/null 2>&1; then
            echo "==> A 'sarand' command exists on PATH but wasn't installed via pipx"
            echo "    ($(command -v sarand)). Not touching it automatically -- if this"
            echo "    is a stale dev-venv install, remove it manually first."
        else
            echo "==> No previous installation found."
        fi
        STATE=fresh
    fi

    echo "==> Building and installing the current version..."
    attempt=1
    until pipx install "$SCRIPT_DIR"; do
        # pipx cleans up after itself, but make sure no half-built venv stays.
        rm -rf "$PIPX_VENV_DIR"
        if [ "$attempt" -ge "$ATTEMPTS" ]; then
            echo "==> The build failed $ATTEMPTS time(s)." >&2
            echo "    Likely causes: no/slow network (it downloads maturin and the" >&2
            echo "    dependencies) or no Rust toolchain (https://rustup.rs)." >&2
            restore_previous >&2
            exit 1
        fi
        attempt=$((attempt + 1))
        echo "==> Build failed -- retrying in ${RETRY_DELAY}s (attempt $attempt of $ATTEMPTS)..."
        sleep "$RETRY_DELAY"
    done

    trap - INT TERM
    rm -rf "$BACKUP_DIR"
    STATE=idle
    echo "==> Done."
    verify_installed
}

# Report what was just installed -- by asking the pipx copy directly, not
# whatever `sarand` happens to come first on PATH -- and say so if a different
# copy shadows it. Without this, a stale development virtualenv earlier on PATH
# makes `sarand --version` print the OLD version right after a successful
# install, which looks like a failed upgrade.
# آنچه تازه نصب شد را گزارش می‌کند -- با پرسیدن مستقیم از نسخه‌ی pipx، نه هر
# `sarand` ی که اول PATH باشد -- و اگر نسخه‌ی دیگری روی آن سایه انداخته باشد
# همین را می‌گوید. بدون این، یک virtualenv توسعه‌ی کهنه‌ی جلوتر در PATH باعث
# می‌شود `sarand --version` درست بعد از یک نصب موفق نسخه‌ی *قدیمی* را نشان بدهد،
# که شبیه به‌روزرسانی ناموفق به نظر می‌رسد.
verify_installed() {
    local bin_dir="${PIPX_BIN_DIR:-$HOME/.local/bin}"
    local installed="$bin_dir/sarand"
    local installed_version="" first_on_path="" shadow_version=""

    if [ -x "$installed" ]; then
        installed_version="$("$installed" --version 2>/dev/null | head -n 1 || true)"
        echo "==> Installed: ${installed_version:-version unknown}  ($installed)"
    else
        echo "==> Installed, but $installed was not found: run 'pipx ensurepath' and open a new shell."
        return 0
    fi

    first_on_path="$(command -v sarand 2>/dev/null || true)"
    if [ -z "$first_on_path" ]; then
        echo "==> 'sarand' is not on PATH yet: run 'pipx ensurepath' and open a new shell."
    elif [ "$first_on_path" != "$installed" ]; then
        shadow_version="$("$first_on_path" --version 2>/dev/null | head -n 1 || true)"
        echo "==> WARNING: another 'sarand' comes first on PATH and shadows the one just installed:"
        echo "      running now : $first_on_path (${shadow_version:-version unknown})"
        echo "      just installed: $installed (${installed_version:-version unknown})"
        echo "    Deactivate the virtualenv that provides it (or remove it), then run 'hash -r'."
    fi
}

# `SARAND_INSTALL_SOURCE_ONLY=1 . install.sh` defines the functions without
# installing anything -- that is how the tests exercise the restore logic.
# `SARAND_INSTALL_SOURCE_ONLY=1 . install.sh` فقط تابع‌ها را تعریف می‌کند و
# چیزی نصب نمی‌کند -- تست‌ها منطق برگرداندن را همین‌طور امتحان می‌کنند.
if [ "${SARAND_INSTALL_SOURCE_ONLY:-}" != "1" ]; then
    main "$@"
fi
