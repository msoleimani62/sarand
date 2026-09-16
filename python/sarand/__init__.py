"""sarand -- cross-platform AI project intelligence CLI."""

from __future__ import annotations

from importlib import metadata

# BUG FIX: __version__ used to be a hardcoded literal that lived
# separately from the one in pyproject.toml, so bumping the release
# version required remembering to edit two files -- and cli.py's
# `--version` flag had a *third* hardcoded copy, still stuck at "0.1.0"
# after a bump to 0.1.1. Reading the installed package's own metadata
# makes pyproject.toml the single source of truth; nothing else needs
# to be touched on a version bump. The except clause only fires for an
# editable/uninstalled checkout with no metadata yet (e.g. running
# straight from a git clone before `pip install -e .`).
#
# اصلاح باگ: __version__ قبلاً یک مقدار ثابت جدا از pyproject.toml بود،
# پس هر بار افزایش نسخه باید یادت می‌ماند دو فایل را ویرایش کنی -- و
# فلگ `--version` در cli.py هم یک نسخه‌ی ثابتِ *سومی* داشت که بعد از
# ارتقا به 0.1.1 همچنان روی "0.1.0" مانده بود. خواندن متادیتای خودِ
# پکیج نصب‌شده، pyproject.toml را تنها منبع حقیقت می‌کند؛ با ارتقای
# نسخه دیگر نیازی به دست‌زدن به جای دیگری نیست. بلاک except فقط برای
# حالتی است که پروژه هنوز نصب/editable نشده (مثلاً اجرای مستقیم از یک
# git clone پیش از `pip install -e .`) و متادیتایی موجود نیست.
try:
    __version__ = metadata.version("sarand")
except metadata.PackageNotFoundError:
    __version__ = "0.0.0+unknown"
