//! PyO3 entry point. Everything exposed here becomes importable from
//! Python as `sarand._core`. Keep this file thin -- it only translates
//! between Rust structs and Python dicts; all real logic lives in the
//! other modules (walker, tree, linecount, hasher).
//!
//! نقطه‌ورود PyO3. هرچه اینجا صادر شود از پایتون به‌صورت `sarand._core`
//! قابل ایمپورت است. این فایل عمداً نازک نگه داشته شده -- فقط بین
//! ساختارهای Rust و دیکشنری‌های پایتون ترجمه می‌کند؛ منطق واقعی در
//! بقیه‌ی ماژول‌ها (walker، tree، linecount، hasher) است.

mod hasher;
mod linecount;
mod tree;
mod walker;

use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::path::PathBuf;

use walker::FileRecord;

fn record_to_dict<'py>(py: Python<'py>, record: &FileRecord) -> PyResult<Bound<'py, PyDict>> {
    // Use the current PyO3 Bound API for dictionary creation.
    // استفاده از API فعلی Bound در PyO3 برای ساخت دیکشنری.
    let dict = PyDict::new(py);
    dict.set_item("rel_path", &record.rel_path)?;
    dict.set_item("size", record.size)?;
    dict.set_item("is_symlink", record.is_symlink)?;
    dict.set_item("is_broken_symlink", record.is_broken_symlink)?;
    dict.set_item("is_hidden", record.is_hidden)?;
    dict.set_item("is_binary", record.is_binary)?;
    dict.set_item("is_executable", record.is_executable)?;
    dict.set_item("extension", &record.extension)?;
    dict.set_item("total_lines", record.total_lines)?;
    dict.set_item("code_lines", record.code_lines)?;
    dict.set_item("comment_lines", record.comment_lines)?;
    dict.set_item("blank_lines", record.blank_lines)?;
    dict.set_item("content_hash", record.content_hash.clone())?;
    Ok(dict)
}

/// Scan `root` and return one dict per file (see `record_to_dict` for
/// the field list). This single call replaces what used to be a
/// separate Python `os.walk` + per-file loop for every file in the
/// project -- the expensive part of a sarand run.
// PyO3's generated wrapper can trigger this Clippy false positive.
// تبدیل ایجادشده توسط wrapper ماکروی PyO3 می‌تواند این false positive را ایجاد کند.
#[allow(clippy::useless_conversion)]
#[pyfunction]
#[pyo3(signature = (root, ignore_dirs, hash_max_bytes=524_288, max_hash_files=5000))]
fn scan_project(
    py: Python<'_>,
    root: String,
    ignore_dirs: Vec<String>,
    hash_max_bytes: u64,
    max_hash_files: usize,
) -> PyResult<Vec<Py<PyAny>>> {
    let root_path = PathBuf::from(root);

    // Python::allow_threads was renamed to Python::detach in pyo3 0.26
    // (part of the GIL-terminology cleanup for free-threaded Python).
    // Python::allow_threads در pyo3 0.26 به Python::detach تغییر نام
    // داد (بخشی از پاک‌سازی نام‌گذاری GIL برای پایتون free-threaded).
    let records =
        py.detach(|| walker::scan(&root_path, &ignore_dirs, hash_max_bytes, max_hash_files));

    records
        .iter()
        .map(|record| record_to_dict(py, record).map(|dict| dict.into_any().unbind()))
        .collect()
}

/// Build the ASCII project tree text (same format as the old
/// pure-Python `build_tree()`).
// Same PyO3 wrapper false positive as `scan_project`.
// همان false positive wrapper مربوط به PyO3 مانند `scan_project`.
#[allow(clippy::useless_conversion)]
#[pyfunction]
#[pyo3(signature = (root, ignore_dirs, max_depth=8, max_entries=100))]
fn build_tree_text(
    root: String,
    ignore_dirs: Vec<String>,
    max_depth: usize,
    max_entries: usize,
) -> PyResult<String> {
    let root_path = PathBuf::from(root);
    Ok(tree::build_tree_text(
        &root_path,
        &ignore_dirs,
        max_depth,
        max_entries,
    ))
}

/// Hash a single file's contents using SHA-256 and return hexadecimal output.
/// Returns `None` when the file cannot be read.
#[pyfunction]
fn hash_file(path: String) -> Option<String> {
    hasher::hash_file(&PathBuf::from(path))
}

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(scan_project, m)?)?;
    m.add_function(wrap_pyfunction!(build_tree_text, m)?)?;
    m.add_function(wrap_pyfunction!(hash_file, m)?)?;
    Ok(())
}
