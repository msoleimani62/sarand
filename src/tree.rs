//! ASCII project tree renderer -- a direct port of the original
//! Python `build_tree()` algorithm, so the visual output is identical.
//!
//! رندر درخت متنی پروژه -- پورت مستقیم الگوریتم پایتونی `build_tree()`
//! تا خروجی بصری کاملاً یکسان بماند.

use std::path::Path;

pub fn build_tree_text(
    root: &Path,
    ignore_dirs: &[String],
    max_depth: usize,
    max_entries: usize,
) -> String {
    let root_name = root
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_else(|| root.to_string_lossy().to_string());

    let mut lines = vec![format!("{}/", root_name)];
    walk(root, "", 0, max_depth, max_entries, ignore_dirs, &mut lines);
    lines.join("\n")
}

fn walk(
    dir: &Path,
    prefix: &str,
    depth: usize,
    max_depth: usize,
    max_entries: usize,
    ignore_dirs: &[String],
    lines: &mut Vec<String>,
) {
    if depth >= max_depth {
        return;
    }

    let mut entries: Vec<_> = match std::fs::read_dir(dir) {
        Ok(rd) => rd
            .filter_map(|e| e.ok())
            .filter(|e| {
                let name = e.file_name().to_string_lossy().to_string();
                !ignore_dirs.iter().any(|d| d == &name)
            })
            .collect(),
        Err(_) => return,
    };

    // Files after directories is NOT the rule -- original sorts by
    // (is_file, name.lower()) so directories come first, matching
    // Python's `key=lambda item: (item.is_file(), item.name.lower())`.
    // ترتیب اصلی: (فایل‌بودن، نام حروف‌کوچک) یعنی پوشه‌ها اول می‌آیند.
    entries.sort_by(|a, b| {
        let a_is_file = a.path().is_file();
        let b_is_file = b.path().is_file();
        (a_is_file, a.file_name().to_string_lossy().to_lowercase())
            .cmp(&(b_is_file, b.file_name().to_string_lossy().to_lowercase()))
    });

    let hidden = entries.len().saturating_sub(max_entries);
    entries.truncate(max_entries);

    let total = entries.len();
    for (index, entry) in entries.iter().enumerate() {
        let is_last = index == total - 1 && hidden == 0;
        let connector = if is_last { "└── " } else { "├── " };
        let path = entry.path();
        let is_dir = path.is_dir();
        let suffix = if is_dir { "/" } else { "" };
        let name = entry.file_name().to_string_lossy().to_string();
        lines.push(format!("{prefix}{connector}{name}{suffix}"));

        if is_dir {
            let extension = if is_last { "    " } else { "│   " };
            walk(
                &path,
                &format!("{prefix}{extension}"),
                depth + 1,
                max_depth,
                max_entries,
                ignore_dirs,
                lines,
            );
        }
    }

    if hidden > 0 {
        lines.push(format!("{prefix}└── ... ({hidden} more entries hidden)"));
    }
}

#[cfg(test)]
#[path = "tree_tests.rs"]
mod tests;
