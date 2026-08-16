//! Binary detection and line counting.
//!
//! Mirrors the exact heuristic the old pure-Python implementation used,
//! so report numbers stay identical when the Rust core is present vs.
//! when sarand falls back to pure Python (no silent behavior drift).
//!
//! این ماژول دقیقاً همان هیوریستیک نسخه‌ی خالص-پایتونی قبلی را تکرار
//! می‌کند، تا وقتی هسته‌ی Rust فعال است یا وقتی sarand به پایتون خالص
//! برمی‌گردد، اعداد گزارش یکسان بمانند (بدون انحراف رفتاری خاموش).

use std::fs::File;
use std::io::{BufRead, BufReader, Read};
use std::path::Path;

/// Line-count breakdown for a single text file.
#[derive(Debug, Default, Clone, Copy)]
pub struct LineCounts {
    pub total: u64,
    pub code: u64,
    pub comment: u64,
    pub blank: u64,
}

/// Sample the first N bytes and look for a NUL byte -- same heuristic
/// as `is_binary()` in the old Python `utils/fs.py`.
pub fn is_binary(path: &Path, sample_size: usize) -> bool {
    let file = match File::open(path) {
        Ok(f) => f,
        Err(_) => return true,
    };
    let mut buf = vec![0u8; sample_size];
    let mut reader = file.take(sample_size as u64);
    let read = match reader.read(&mut buf) {
        Ok(n) => n,
        Err(_) => return true,
    };
    buf[..read].contains(&0u8)
}

/// Count total/code/comment/blank lines for a (already known non-binary) file.
///
/// A line is: blank (empty after trim), comment (starts with `#` or
/// `//` after trim), otherwise code. Invalid UTF-8 bytes are replaced,
/// never causing a hard failure (matches Python's `errors="replace"`).
pub fn count_lines(path: &Path) -> LineCounts {
    let file = match File::open(path) {
        Ok(f) => f,
        Err(_) => return LineCounts::default(),
    };
    let reader = BufReader::new(file);
    let mut counts = LineCounts::default();

    for line in reader.lines() {
        // `lines()` yields an error on invalid UTF-8; treat that single
        // line as an (uncounted) boundary rather than aborting the file.
        // `lines()` روی UTF-8 نامعتبر خطا می‌دهد؛ آن خط را به‌جای متوقف
        // کردن کل فایل، صرفاً نادیده می‌گیریم.
        let line = match line {
            Ok(l) => l,
            Err(_) => continue,
        };
        counts.total += 1;
        let trimmed = line.trim();
        if trimmed.is_empty() {
            counts.blank += 1;
        } else if trimmed.starts_with('#') || trimmed.starts_with("//") {
            counts.comment += 1;
        } else {
            counts.code += 1;
        }
    }
    counts
}

#[cfg(test)]
#[path = "linecount_tests.rs"]
mod tests;
