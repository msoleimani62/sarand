use super::hash_file;
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
fn hashes_known_content() {
    let path = temp_path("known.txt");
    fs::write(&path, b"hello world").expect("test file must be writable");

    let digest = hash_file(&path);

    assert_eq!(
        digest.as_deref(),
        Some("b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9")
    );

    fs::remove_file(path).expect("test file must be removable");
}

#[test]
fn hashes_empty_file() {
    let path = temp_path("empty.txt");
    fs::write(&path, b"").expect("test file must be writable");

    let digest = hash_file(&path);

    assert_eq!(
        digest.as_deref(),
        Some("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
    );

    fs::remove_file(path).expect("test file must be removable");
}

#[test]
fn returns_none_for_missing_file() {
    let path = temp_path("missing.txt");

    assert_eq!(hash_file(&path), None);
}
