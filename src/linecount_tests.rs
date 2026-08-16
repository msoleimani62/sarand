use super::{count_lines, is_binary};
use std::fs;
use std::time::{SystemTime, UNIX_EPOCH};

fn temp_path(name: &str) -> std::path::PathBuf {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("system clock must be after UNIX epoch")
        .as_nanos();

    std::env::temp_dir().join(format!("sarand-rust-test-{nonce}-{name}"))
}

#[test]
fn counts_code_comment_and_blank_lines() {
    let path = temp_path("lines.txt");

    fs::write(
        &path,
        "fn main() {\n\n// comment\n# comment\nlet value = 42;\n  \n}\n",
    )
    .expect("test file must be writable");

    let counts = count_lines(&path);

    assert_eq!(counts.total, 7);
    assert_eq!(counts.code, 3);
    assert_eq!(counts.comment, 2);
    assert_eq!(counts.blank, 2);

    fs::remove_file(path).expect("test file must be removable");
}

#[test]
fn trims_whitespace_before_classification() {
    let path = temp_path("whitespace.txt");

    fs::write(&path, "   \n   // comment\n   # comment\n   code\n")
        .expect("test file must be writable");

    let counts = count_lines(&path);

    assert_eq!(counts.total, 4);
    assert_eq!(counts.code, 1);
    assert_eq!(counts.comment, 2);
    assert_eq!(counts.blank, 1);

    fs::remove_file(path).expect("test file must be removable");
}

#[test]
fn invalid_utf8_does_not_abort_counting() {
    let path = temp_path("invalid-utf8.txt");

    fs::write(&path, b"valid\n\xff\nvalid\n").expect("test file must be writable");

    let counts = count_lines(&path);

    assert_eq!(counts.total, 2);
    assert_eq!(counts.code, 2);

    fs::remove_file(path).expect("test file must be removable");
}

#[test]
fn detects_nul_as_binary() {
    let path = temp_path("binary.bin");

    fs::write(&path, b"abc\0def").expect("test file must be writable");

    assert!(is_binary(&path, 8192));

    fs::remove_file(path).expect("test file must be removable");
}

#[test]
fn ignores_nul_after_sample_boundary() {
    let path = temp_path("sample-boundary.bin");

    let mut data = vec![b'a'; 16];
    data.push(0);

    fs::write(&path, &data).expect("test file must be writable");

    assert!(!is_binary(&path, 16));

    fs::remove_file(path).expect("test file must be removable");
}

#[test]
fn missing_file_is_binary() {
    let path = temp_path("missing.bin");

    assert!(is_binary(&path, 8192));
    assert_eq!(count_lines(&path).total, 0);
}
