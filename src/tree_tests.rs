use super::build_tree_text;
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

#[test]
fn renders_directories_before_files() {
    let root = temp_dir("tree-order");

    fs::create_dir(root.join("z_dir")).expect("directory must be creatable");
    fs::create_dir(root.join("a_dir")).expect("directory must be creatable");
    fs::write(root.join("z_file"), b"").expect("file must be writable");
    fs::write(root.join("a_file"), b"").expect("file must be writable");

    let output = build_tree_text(&root, &[], 8, 100);

    let expected = format!(
        "{}/\n├── a_dir/\n├── z_dir/\n├── a_file\n└── z_file",
        root.file_name()
            .expect("root must have a name")
            .to_string_lossy()
    );

    assert_eq!(output, expected);

    remove_tree(&root);
}

#[test]
fn respects_ignored_directories() {
    let root = temp_dir("tree-ignore");

    fs::create_dir(root.join("target")).expect("directory must be creatable");
    fs::create_dir(root.join("src")).expect("directory must be creatable");
    fs::write(root.join("target").join("ignored.txt"), b"").expect("file must be writable");
    fs::write(root.join("src").join("main.rs"), b"").expect("file must be writable");

    let ignore = vec!["target".to_string()];
    let output = build_tree_text(&root, &ignore, 8, 100);

    assert!(!output.contains("target"));
    assert!(output.contains("src/"));
    assert!(output.contains("main.rs"));

    remove_tree(&root);
}

#[test]
fn respects_max_depth() {
    let root = temp_dir("tree-depth");

    fs::create_dir_all(root.join("a").join("b").join("c"))
        .expect("nested directories must be creatable");

    let output = build_tree_text(&root, &[], 1, 100);

    assert!(output.contains("a/"));
    assert!(!output.contains("b/"));
    assert!(!output.contains("c/"));

    remove_tree(&root);
}

#[test]
fn reports_hidden_entries_when_max_entries_is_exceeded() {
    let root = temp_dir("tree-limit");

    fs::write(root.join("a"), b"").expect("file must be writable");
    fs::write(root.join("b"), b"").expect("file must be writable");
    fs::write(root.join("c"), b"").expect("file must be writable");

    let output = build_tree_text(&root, &[], 8, 2);

    assert!(output.contains("1 more entries hidden"));

    remove_tree(&root);
}
