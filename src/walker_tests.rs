use super::scan;
use std::fs;
use std::time::{SystemTime, UNIX_EPOCH};

fn temp_dir(name: &str) -> std::path::PathBuf {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("system clock must be after UNIX epoch")
        .as_nanos();

    let path = std::env::temp_dir().join(format!("sarand-rust-test-{nonce}-{name}"));
    fs::create_dir_all(&path).expect("test directory must be creatable");
    path
}

fn remove_tree(path: &std::path::Path) {
    fs::remove_dir_all(path).expect("test directory must be removable");
}

fn find_record<'a>(records: &'a [super::FileRecord], path: &str) -> &'a super::FileRecord {
    records
        .iter()
        .find(|record| record.rel_path == path)
        .expect("expected file record must exist")
}

#[test]
fn scans_regular_files_and_metadata() {
    let root = temp_dir("walker-basic");

    fs::create_dir(root.join("src")).expect("directory must be creatable");
    fs::write(root.join("src").join("main.rs"), "fn main() {}\n")
        .expect("source file must be writable");

    let records = scan(&root, &[], 524_288, 5000);
    let record = find_record(&records, "src/main.rs");

    assert_eq!(record.rel_path, "src/main.rs");
    assert_eq!(record.extension, ".rs");
    assert_eq!(record.total_lines, 1);
    assert_eq!(record.code_lines, 1);
    assert_eq!(record.comment_lines, 0);
    assert_eq!(record.blank_lines, 0);
    assert!(!record.is_binary);
    assert!(!record.is_symlink);
    assert!(!record.is_broken_symlink);
    assert!(record.content_hash.is_some());

    remove_tree(&root);
}

#[test]
fn skips_gitignored_files() {
    let root = temp_dir("walker-gitignore");

    fs::write(root.join(".gitignore"), "ignored.txt\n").expect("gitignore must be writable");
    fs::write(root.join("ignored.txt"), "ignored\n").expect("ignored file must be writable");
    fs::write(root.join("kept.txt"), "kept\n").expect("kept file must be writable");

    let records = scan(&root, &[], 524_288, 5000);

    assert!(records.iter().any(|record| record.rel_path == "kept.txt"));
    assert!(!records
        .iter()
        .any(|record| record.rel_path == "ignored.txt"));

    remove_tree(&root);
}

#[test]
fn skips_configured_directories() {
    let root = temp_dir("walker-ignore");

    fs::create_dir(root.join("target")).expect("directory must be creatable");
    fs::write(root.join("target").join("artifact"), "ignored\n").expect("file must be writable");
    fs::write(root.join("kept.txt"), "kept\n").expect("file must be writable");

    let ignore = vec!["target".to_string()];
    let records = scan(&root, &ignore, 524_288, 5000);

    assert!(records.iter().any(|record| record.rel_path == "kept.txt"));
    assert!(!records
        .iter()
        .any(|record| record.rel_path.starts_with("target/")));

    remove_tree(&root);
}

#[test]
fn does_not_hash_files_above_size_limit() {
    let root = temp_dir("walker-hash-limit");

    fs::write(root.join("small.txt"), "small\n").expect("file must be writable");

    let records = scan(&root, &[], 1, 5000);
    let record = find_record(&records, "small.txt");

    assert!(record.content_hash.is_none());

    remove_tree(&root);
}

#[test]
fn respects_hash_file_limit() {
    let root = temp_dir("walker-hash-count");

    for index in 0..8 {
        fs::write(
            root.join(format!("file-{index}.txt")),
            format!("content-{index}\n"),
        )
        .expect("file must be writable");
    }

    let records = scan(&root, &[], 524_288, 2);
    let hashed = records
        .iter()
        .filter(|record| record.content_hash.is_some())
        .count();

    assert!(hashed <= 2);

    remove_tree(&root);
}

#[test]
fn detects_binary_files() {
    let root = temp_dir("walker-binary");

    fs::write(root.join("data.bin"), b"abc\0def").expect("binary file must be writable");

    let records = scan(&root, &[], 524_288, 5000);
    let record = find_record(&records, "data.bin");

    assert!(record.is_binary);
    assert_eq!(record.total_lines, 0);
    assert_eq!(record.code_lines, 0);
    assert_eq!(record.comment_lines, 0);
    assert_eq!(record.blank_lines, 0);
    assert!(record.content_hash.is_none());

    remove_tree(&root);
}

#[cfg(unix)]
#[test]
fn records_symlinks_without_following_them() {
    use std::os::unix::fs::symlink;

    let root = temp_dir("walker-symlink");

    fs::write(root.join("target.txt"), "target\n").expect("target file must be writable");
    symlink(root.join("target.txt"), root.join("link.txt")).expect("symlink must be creatable");

    let records = scan(&root, &[], 524_288, 5000);
    let record = find_record(&records, "link.txt");

    assert!(record.is_symlink);
    assert!(!record.is_broken_symlink);
    assert_eq!(record.size, 0);
    assert!(record.content_hash.is_none());

    remove_tree(&root);
}

#[cfg(unix)]
#[test]
fn detects_broken_symlinks() {
    use std::os::unix::fs::symlink;

    let root = temp_dir("walker-broken-symlink");

    symlink(root.join("missing.txt"), root.join("broken.txt")).expect("symlink must be creatable");

    let records = scan(&root, &[], 524_288, 5000);
    let record = find_record(&records, "broken.txt");

    assert!(record.is_symlink);
    assert!(record.is_broken_symlink);
    assert!(record.content_hash.is_none());

    remove_tree(&root);
}

#[test]
fn keeps_files_when_the_root_sits_under_an_ignored_directory_name() {
    let base = temp_dir("walker-ancestor");
    let root = base.join("build").join("proj");

    fs::create_dir_all(root.join("src")).expect("directory must be creatable");
    fs::write(root.join("src").join("a.rs"), "fn a() {}\n").expect("file must be writable");

    let ignore = vec!["build".to_string(), "target".to_string()];
    let records = scan(&root, &ignore, 524_288, 5000);

    assert!(records.iter().any(|record| record.rel_path == "src/a.rs"));

    remove_tree(&base);
}

#[test]
fn prunes_ignored_directories_but_keeps_same_named_files_and_dot_github() {
    let root = temp_dir("walker-prune");

    fs::create_dir_all(root.join("src").join("build")).expect("directory must be creatable");
    fs::create_dir_all(root.join(".github").join("workflows"))
        .expect("directory must be creatable");
    fs::write(root.join("src").join("build").join("gen.rs"), "x\n").expect("file must be writable");
    fs::write(
        root.join(".github").join("workflows").join("ci.yml"),
        "on: push\n",
    )
    .expect("file must be writable");
    fs::write(root.join("dist"), "a plain file\n").expect("file must be writable");
    fs::write(root.join("kept.rs"), "fn k() {}\n").expect("file must be writable");

    let ignore = vec!["build".to_string(), "dist".to_string()];
    let records = scan(&root, &ignore, 524_288, 5000);

    assert!(records.iter().any(|record| record.rel_path == "kept.rs"));
    assert!(records.iter().any(|record| record.rel_path == "dist"));
    assert!(records
        .iter()
        .any(|record| record.rel_path == ".github/workflows/ci.yml"));
    assert!(!records
        .iter()
        .any(|record| record.rel_path.starts_with("src/build/")));

    remove_tree(&root);
}

#[cfg(unix)]
#[test]
fn prunes_symlinks_to_directories_that_are_named_like_ignored_ones() {
    use std::os::unix::fs::symlink;

    let root = temp_dir("walker-symlink-prune");

    fs::create_dir(root.join("real")).expect("directory must be creatable");
    fs::write(root.join("real").join("a.txt"), "a\n").expect("file must be writable");
    symlink(root.join("real"), root.join("node_modules")).expect("symlink must be creatable");

    let ignore = vec!["node_modules".to_string()];
    let records = scan(&root, &ignore, 524_288, 5000);

    assert!(records.iter().any(|record| record.rel_path == "real/a.txt"));
    assert!(!records
        .iter()
        .any(|record| record.rel_path == "node_modules"));

    remove_tree(&root);
}
