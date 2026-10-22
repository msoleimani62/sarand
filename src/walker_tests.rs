use super::{scan, scan_report, without_root, ScanProblems};
use std::fs;
use std::path::Path;
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

#[test]
fn a_clean_tree_reports_no_problems() {
    let root = temp_dir("walker-clean");

    fs::write(root.join("a.rs"), "fn a() {}\n").expect("file must be writable");

    let report = scan_report(&root, &[], 524_288, 5000);

    assert_eq!(report.records.len(), 1);
    assert_eq!(report.problems.skipped, 0);
    assert!(report.problems.samples.is_empty());

    remove_tree(&root);
}

#[test]
fn only_the_first_few_problem_messages_are_kept() {
    let mut problems = ScanProblems::default();

    for index in 0..12 {
        problems.record(format!("problem {index}"));
    }

    assert_eq!(problems.skipped, 12);
    assert_eq!(problems.samples.len(), 5);
    assert_eq!(problems.samples[0], "problem 0");
}

#[test]
fn messages_do_not_contain_the_absolute_scan_root() {
    let root = Path::new("/home/someone/project");

    let message = without_root(
        root,
        "IO error for operation on /home/someone/project/locked: denied",
    );

    assert_eq!(message, "IO error for operation on ./locked: denied");
    assert_eq!(without_root(Path::new("/"), "keep /as/is"), "keep /as/is");
}

#[cfg(unix)]
#[test]
fn reports_an_unreadable_directory_instead_of_hiding_it() {
    use std::os::unix::fs::PermissionsExt;

    let root = temp_dir("walker-unreadable");
    let locked = root.join("locked");

    fs::create_dir(&locked).expect("directory must be creatable");
    fs::write(locked.join("secret.rs"), "fn s() {}\n").expect("file must be writable");
    fs::write(root.join("open.rs"), "fn o() {}\n").expect("file must be writable");
    fs::set_permissions(&locked, fs::Permissions::from_mode(0o000))
        .expect("permissions must be changeable");

    // Root (and some containers) can read anything, which makes this scenario
    // impossible to build; restore and stop in that case.
    if fs::read_dir(&locked).is_ok() {
        fs::set_permissions(&locked, fs::Permissions::from_mode(0o755))
            .expect("permissions must be restorable");
        remove_tree(&root);
        return;
    }

    let report = scan_report(&root, &[], 524_288, 5000);

    fs::set_permissions(&locked, fs::Permissions::from_mode(0o755))
        .expect("permissions must be restorable");

    assert!(report
        .records
        .iter()
        .any(|record| record.rel_path == "open.rs"));
    assert!(report.problems.skipped >= 1);
    assert!(report
        .problems
        .samples
        .iter()
        .any(|sample| sample.contains("locked")));
    let root_text = root.to_string_lossy().to_string();
    assert!(report
        .problems
        .samples
        .iter()
        .all(|sample| !sample.contains(&root_text)));

    remove_tree(&root);
}

#[test]
fn does_not_apply_the_users_global_gitignore() {
    let config_home = temp_dir("walker-global-config");
    let root = temp_dir("walker-global-ignore");

    fs::create_dir_all(config_home.join("git")).expect("directory must be creatable");
    fs::write(config_home.join("git").join("ignore"), "*.machine-local\n")
        .expect("global ignore must be writable");
    fs::write(root.join("notes.machine-local"), "kept\n").expect("file must be writable");
    fs::write(root.join("kept.rs"), "fn k() {}\n").expect("file must be writable");

    // The `ignore` crate reads the global file from $XDG_CONFIG_HOME/git/ignore
    // (unless `core.excludesFile` points elsewhere, as it may on a developer machine).
    let previous = std::env::var_os("XDG_CONFIG_HOME");
    std::env::set_var("XDG_CONFIG_HOME", &config_home);
    let records = scan(&root, &[], 524_288, 5000);
    match previous {
        Some(value) => std::env::set_var("XDG_CONFIG_HOME", value),
        None => std::env::remove_var("XDG_CONFIG_HOME"),
    }

    assert!(records.iter().any(|record| record.rel_path == "kept.rs"));
    assert!(records
        .iter()
        .any(|record| record.rel_path == "notes.machine-local"));

    remove_tree(&config_home);
    remove_tree(&root);
}
