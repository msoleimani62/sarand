//! Parallel, .gitignore-aware directory walk that produces a flat
//! per-file record list. This is the single most expensive part of a
//! sarand run on a large repository, which is exactly why it lives
//! here instead of in Python.
//!
//! پیمایش موازی درخت فایل با احترام واقعی به .gitignore، که یک لیست
//! تخت از رکورد هر فایل تولید می‌کند. این پرهزینه‌ترین بخش یک اجرای
//! sarand روی یک ریپوی بزرگ است -- دقیقاً همان دلیلی که اینجا (نه در
//! پایتون) پیاده‌سازی شده.

use ignore::WalkBuilder;
use rayon::prelude::*;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};

use crate::hasher::hash_file;
use crate::linecount::{count_lines, is_binary};

/// Everything Python needs to know about one file, computed in Rust.
#[derive(Debug, Clone)]
pub struct FileRecord {
    pub rel_path: String,
    pub size: u64,
    pub is_symlink: bool,
    pub is_broken_symlink: bool,
    pub is_hidden: bool,
    pub is_binary: bool,
    pub is_executable: bool,
    pub extension: String,
    pub total_lines: u64,
    pub code_lines: u64,
    pub comment_lines: u64,
    pub blank_lines: u64,
    pub content_hash: Option<String>,
}

/// Walk `root`, skipping directories named in `ignore_dirs` *and*
/// anything `.gitignore`/`.ignore`/global-git-excludes would skip
/// (via the `ignore` crate -- this is real .gitignore support, which
/// the old pure-Python walker never had).
///
/// Args:
///   root: absolute project root.
///   ignore_dirs: directory *names* (not paths) to always prune, e.g. "target", "node_modules".
///   hash_max_bytes: only hash files at or under this size (duplicate detection).
///   max_hash_files: hard cap on total files hashed, to bound work on huge repos.
pub fn scan(
    root: &Path,
    ignore_dirs: &[String],
    hash_max_bytes: u64,
    max_hash_files: usize,
) -> Vec<FileRecord> {
    // Collect candidate file paths first (single-threaded walk, but
    // fast: it is just directory traversal, no file I/O yet).
    // جمع‌آوری مسیرهای کاندید در یک پیمایش تک‌رشته‌ای (سریع، چون فقط
    // پیمایش دایرکتوری است، هنوز I/O روی فایل انجام نشده).
    let mut builder = WalkBuilder::new(root);
    builder
        .hidden(false) // we decide hidden-handling ourselves, per-file
        .git_ignore(true)
        .git_global(true)
        .git_exclude(true)
        .parents(true);

    let candidates: Vec<PathBuf> = builder
        .build()
        .filter_map(|entry| entry.ok())
        .filter(|entry| {
            // Prune directories that match the caller-supplied ignore list.
            // حذف دایرکتوری‌هایی که با لیست نادیده‌ی فراخوان مطابقت دارند.
            !entry
                .path()
                .components()
                .any(|c| ignore_dirs.iter().any(|d| c.as_os_str() == d.as_str()))
        })
        .filter(|entry| entry.file_type().map(|t| t.is_file() || is_symlink(entry.path())).unwrap_or(false))
        .map(|entry| entry.into_path())
        .collect();

    let hashed_count = AtomicUsize::new(0);

    // Fan the expensive per-file work (stat, binary sniff, line count,
    // hash) out across all cores.
    // پخش کار پرهزینه‌ی هر فایل (stat، تشخیص باینری، شمارش خط، هش)
    // روی تمام هسته‌ها.
    candidates
        .par_iter()
        .filter_map(|path| build_record(root, path, hash_max_bytes, max_hash_files, &hashed_count))
        .collect()
}

fn is_symlink(path: &Path) -> bool {
    path.symlink_metadata().map(|m| m.file_type().is_symlink()).unwrap_or(false)
}

fn build_record(
    root: &Path,
    path: &Path,
    hash_max_bytes: u64,
    max_hash_files: usize,
    hashed_count: &AtomicUsize,
) -> Option<FileRecord> {
    let rel_path = path.strip_prefix(root).ok()?.to_string_lossy().replace('\\', "/");
    let file_name = path.file_name()?.to_string_lossy();
    let is_hidden = file_name.starts_with('.');

    let symlink_meta = path.symlink_metadata().ok()?;
    let is_link = symlink_meta.file_type().is_symlink();

    if is_link {
        let broken = std::fs::metadata(path).is_err();
        return Some(FileRecord {
            rel_path,
            size: 0,
            is_symlink: true,
            is_broken_symlink: broken,
            is_hidden,
            is_binary: false,
            is_executable: false,
            extension: String::new(),
            total_lines: 0,
            code_lines: 0,
            comment_lines: 0,
            blank_lines: 0,
            content_hash: None,
        });
    }

    let meta = std::fs::metadata(path).ok()?;
    let size = meta.len();
    let extension = path
        .extension()
        .map(|e| format!(".{}", e.to_string_lossy().to_lowercase()))
        .unwrap_or_default();

    #[cfg(unix)]
    let is_executable = {
        use std::os::unix::fs::PermissionsExt;
        meta.permissions().mode() & 0o111 != 0
    };
    #[cfg(not(unix))]
    let is_executable = false;

    let binary = is_binary(path, 8192);

    let (total_lines, code_lines, comment_lines, blank_lines) = if binary {
        (0, 0, 0, 0)
    } else {
        let counts = count_lines(path);
        (counts.total, counts.code, counts.comment, counts.blank)
    };

    let content_hash = if !binary && size > 0 && size <= hash_max_bytes {
        if hashed_count.fetch_add(1, Ordering::Relaxed) < max_hash_files {
            hash_file(path)
        } else {
            None
        }
    } else {
        None
    };

    Some(FileRecord {
        rel_path,
        size,
        is_symlink: false,
        is_broken_symlink: false,
        is_hidden,
        is_binary: binary,
        is_executable,
        extension,
        total_lines,
        code_lines,
        comment_lines,
        blank_lines,
        content_hash,
    })
}
