//! Parallel, .gitignore-aware directory walk that produces a flat
//! per-file record list. This is the single most expensive part of a
//! sarand run on a large repository, which is exactly why it lives
//! here instead of in Python.
//!
//! پیمایش موازی درخت فایل با احترام واقعی به .gitignore، که یک لیست
//! تخت از رکورد هر فایل تولید می‌کند. این پرهزینه‌ترین بخش یک اجرای
//! sarand روی یک ریپوی بزرگ است -- دقیقاً همان دلیلی که اینجا (نه در
//! پایتون) پیاده‌سازی شده.

use ignore::{DirEntry, WalkBuilder};
use rayon::prelude::*;
use std::collections::HashSet;
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

/// How many entries could not be read, and the first few reasons. A directory
/// the process may not enter, or a file that vanished mid-scan, used to disappear
/// from the results without a trace; now it is counted and shown.
///
/// چند مسیر خوانده نشد و دلیل چند مورد اول. دایرکتوری ممنوع یا فایلی که وسط اسکن
/// ناپدید شده بود قبلاً بی‌صدا از نتیجه حذف می‌شد؛ حالا شمرده و نشان داده می‌شود.
#[derive(Debug, Default)]
pub struct ScanProblems {
    pub skipped: usize,
    pub samples: Vec<String>,
}

/// Only the first few messages are kept: a million unreadable files must not
/// become a million strings.
const MAX_SAMPLES: usize = 5;

impl ScanProblems {
    fn record(&mut self, message: String) {
        self.skipped += 1;
        if self.samples.len() < MAX_SAMPLES {
            self.samples.push(message);
        }
    }
}

/// The records plus what could not be read.
#[derive(Debug)]
pub struct ScanReport {
    pub records: Vec<FileRecord>,
    pub problems: ScanProblems,
}

/// Walk `root`, skipping directories named in `ignore_dirs` *and*
/// anything `.gitignore`/`.ignore`/global-git-excludes would skip
/// (via the `ignore` crate -- this is real .gitignore support, which
/// the old pure-Python walker never had).
///
/// Args:
///   root: absolute project root.
///   ignore_dirs: directory *names* (not paths) to always prune, e.g. "target", "node_modules".
///     A directory is pruned by its own name, at any depth *below* `root`; the
///     components of `root` itself (its ancestors) are never examined.
///   hash_max_bytes: only hash files at or under this size (duplicate detection).
///   max_hash_files: hard cap on total files hashed, to bound work on huge repos.
pub fn scan(
    root: &Path,
    ignore_dirs: &[String],
    hash_max_bytes: u64,
    max_hash_files: usize,
) -> Vec<FileRecord> {
    scan_report(root, ignore_dirs, hash_max_bytes, max_hash_files).records
}

/// Same walk as [`scan`], but also reports every entry that could not be read
/// (see [`ScanProblems`]). Messages never contain the absolute scan root, because
/// a report is often shared.
///
/// همان پیمایش `scan` ولی هر مسیری را که خوانده نشد هم گزارش می‌کند. پیام‌ها هرگز
/// مسیر مطلق ریشه را ندارند، چون گزارش اغلب به اشتراک گذاشته می‌شود.
pub fn scan_report(
    root: &Path,
    ignore_dirs: &[String],
    hash_max_bytes: u64,
    max_hash_files: usize,
) -> ScanReport {
    // Collect candidate file paths first (single-threaded walk, but
    // fast: it is just directory traversal, no file I/O yet).
    // جمع‌آوری مسیرهای کاندید در یک پیمایش تک‌رشته‌ای (سریع، چون فقط
    // پیمایش دایرکتوری است، هنوز I/O روی فایل انجام نشده).
    // `filter_entry` needs a `'static` closure, so it owns a copy of the names.
    // `filter_entry` یک closure با طول عمر `'static` می‌خواهد، پس کپی نام‌ها را نگه می‌دارد.
    let pruned: HashSet<String> = ignore_dirs.iter().cloned().collect();
    let mut builder = WalkBuilder::new(root);
    builder
        .hidden(false) // we decide hidden-handling ourselves, per-file
        .git_ignore(true)
        .git_global(false) // the user's global ignore file differs per machine
        .git_exclude(true)
        .require_git(false)
        .parents(true)
        // Prune ignored directories *during* the walk, so they are never
        // entered (before: walked, then discarded).
        // دایرکتوری‌های نادیده را *در حین* پیمایش هرس می‌کند تا هرگز وارد نشود.
        .filter_entry(move |entry| !is_pruned_dir(entry, &pruned));

    let mut problems = ScanProblems::default();
    let mut candidates: Vec<PathBuf> = Vec::new();
    for entry in builder.build() {
        match entry {
            Ok(entry) => {
                let is_candidate = entry
                    .file_type()
                    .map(|t| t.is_file() || is_symlink(entry.path()))
                    .unwrap_or(false);
                if is_candidate {
                    candidates.push(entry.into_path());
                }
            }
            Err(error) => problems.record(without_root(root, &error.to_string())),
        }
    }

    let hashed_count = AtomicUsize::new(0);

    // Fan the expensive per-file work (stat, binary sniff, line count,
    // hash) out across all cores.
    // پخش کار پرهزینه‌ی هر فایل (stat، تشخیص باینری، شمارش خط، هش)
    // روی تمام هسته‌ها.
    let outcomes: Vec<Result<FileRecord, String>> = candidates
        .par_iter()
        .map(|path| build_record(root, path, hash_max_bytes, max_hash_files, &hashed_count))
        .collect();

    let mut records = Vec::with_capacity(outcomes.len());
    for outcome in outcomes {
        match outcome {
            Ok(record) => records.push(record),
            Err(message) => problems.record(message),
        }
    }
    ScanReport { records, problems }
}

/// `message` with every occurrence of the scan root replaced by `.`, so a report
/// does not reveal where on the machine the project lives.
///
/// پیام با جایگزینی هر ریشه‌ی اسکن با `.` تا گزارش محل پروژه روی دستگاه را فاش نکند.
fn without_root(root: &Path, message: &str) -> String {
    let root_text = root.to_string_lossy();
    if root_text.len() > 1 {
        message.replace(&*root_text, ".")
    } else {
        message.to_string()
    }
}

/// True for a *directory* below the walk root whose own name is in `pruned`
/// (a symlink that points to a directory counts, as it does for `os.walk`).
///
/// Only the entry's own name is compared, never the components of its path: the
/// path starts at the caller-chosen root, so matching it would drop every file
/// of a project that lives under, say, `/build` or `~/.cache`. Plain files are
/// never pruned (a file named `dist` is kept) and the root (depth 0) never is.
///
/// فقط نام خودِ دایرکتوری مقایسه می‌شود، نه اجزای مسیر؛ ریشه و فایل‌ها هرگز هرس نمی‌شوند.
fn is_pruned_dir(entry: &DirEntry, pruned: &HashSet<String>) -> bool {
    // Name first: it is free, the file-type checks may touch the disk.
    entry.depth() > 0
        && pruned.contains(&*entry.file_name().to_string_lossy())
        && entry
            .file_type()
            .is_some_and(|kind| kind.is_dir() || (kind.is_symlink() && entry.path().is_dir()))
}

fn is_symlink(path: &Path) -> bool {
    path.symlink_metadata()
        .map(|m| m.file_type().is_symlink())
        .unwrap_or(false)
}

fn build_record(
    root: &Path,
    path: &Path,
    hash_max_bytes: u64,
    max_hash_files: usize,
    hashed_count: &AtomicUsize,
) -> Result<FileRecord, String> {
    let rel_path = path
        .strip_prefix(root)
        .map_err(|_| "a path outside the scan root".to_string())?
        .to_string_lossy()
        .replace('\\', "/");
    let file_name = path
        .file_name()
        .ok_or_else(|| format!("{rel_path}: has no file name"))?
        .to_string_lossy();
    let is_hidden = file_name.starts_with('.');

    let symlink_meta = path
        .symlink_metadata()
        .map_err(|error| format!("{rel_path}: {error}"))?;
    let is_link = symlink_meta.file_type().is_symlink();

    if is_link {
        let broken = std::fs::metadata(path).is_err();
        return Ok(FileRecord {
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

    let meta = std::fs::metadata(path).map_err(|error| format!("{rel_path}: {error}"))?;
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

    Ok(FileRecord {
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

#[cfg(test)]
#[path = "walker_tests.rs"]
mod tests;
