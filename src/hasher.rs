//! SHA-256 hashing for small-file duplicate detection.
//!
//! Only called for files under a caller-supplied size ceiling (mirrors
//! the 512 KiB limit the old Python `statistics.py` used) -- hashing
//! is intentionally not attempted on large or binary files.
//!
//! فقط برای فایل‌های زیر یک سقف اندازه‌ی مشخص‌شده توسط فراخوان صدا زده
//! می‌شود (مطابق محدودیت ۵۱۲ کیلوبایتی نسخه‌ی قدیمی پایتونی) -- هش
//! کردن عمداً روی فایل‌های بزرگ یا باینری انجام نمی‌شود.

use sha2::{Digest, Sha256};
use std::fs;
use std::path::Path;

/// Return the hex-encoded SHA-256 digest of a file's contents, or
/// `None` if the file could not be read.
pub fn hash_file(path: &Path) -> Option<String> {
    let bytes = fs::read(path).ok()?;
    let mut hasher = Sha256::new();
    hasher.update(&bytes);
    Some(hex::encode(hasher.finalize()))
}
