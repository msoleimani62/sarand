# sarand report — hybrid-project

**Generated:** 2026-01-01 12:00:00  
**Host:** kali  
**Project:** `<PROJECT_ROOT>`  

This report is generated for AI analysis and contains project metadata, test results and source files.

---

## Detected Project

- **Primary language:** Python
- **All detected languages:** Python, Rust, Go
- **Project type:** workspace
- **Build system:** pip + cargo + go mod
- **Markers found:** `pyproject.toml`, `Cargo.toml`, `go.mod`
- **Scan engine:** Rust core (native)
- **Entry points:** `src/main.py`, `src/lib.rs`, `cmd/server/main.go`
- **Assembly dialects:** x86 (NASM): 2 file(s), ARM: 1 file(s)

---

## Environment

| Fact | Value |
|------|-------|
| Python | Python 3.14.6 |
| Rust core | compiled and loaded |
| OS | Linux |
| Architecture | aarch64 |
| CPU | 8-core |
| Memory | 6.0 GiB total / 2.1 GiB free |
| Disk | 41.2 GiB free |
| Hostname | kali |

### Detected tools

| Tool | Version |
|------|---------|
| ruff | 0.8.0 |
| cargo | 1.83.0 |
| go | 1.23.0 |

## Git

- **Branch:** main
- **Commit:** 1e99b0ce56c28c2472531bf4683ca8d93899b1f9
- **Dirty:** True
- **Ahead / Behind:** 1 / 0

### Status
```text
M src/main.py
?? scratch.py
```

### Recent commits
```text
1e99b0c style: format health module
bd88701 fix health tooling score
```

### Untracked files

- `scratch/untracked-0.tmp`
- `scratch/untracked-1.tmp`
- `scratch/untracked-2.tmp`
- `scratch/untracked-3.tmp`
- `scratch/untracked-4.tmp`
- `scratch/untracked-5.tmp`
- `scratch/untracked-6.tmp`
- `scratch/untracked-7.tmp`
- `scratch/untracked-8.tmp`
- `scratch/untracked-9.tmp`
- `scratch/untracked-10.tmp`
- `scratch/untracked-11.tmp`
- `scratch/untracked-12.tmp`
- `scratch/untracked-13.tmp`
- `scratch/untracked-14.tmp`
- `scratch/untracked-15.tmp`
- `scratch/untracked-16.tmp`
- `scratch/untracked-17.tmp`
- `scratch/untracked-18.tmp`
- `scratch/untracked-19.tmp`
- `scratch/untracked-20.tmp`
- `scratch/untracked-21.tmp`
- `scratch/untracked-22.tmp`
- `scratch/untracked-23.tmp`
- `scratch/untracked-24.tmp`
- `scratch/untracked-25.tmp`
- `scratch/untracked-26.tmp`
- `scratch/untracked-27.tmp`
- `scratch/untracked-28.tmp`
- `scratch/untracked-29.tmp`
- `scratch/untracked-30.tmp`
- `scratch/untracked-31.tmp`
- `scratch/untracked-32.tmp`
- `scratch/untracked-33.tmp`
- `scratch/untracked-34.tmp`
- `scratch/untracked-35.tmp`
- `scratch/untracked-36.tmp`
- `scratch/untracked-37.tmp`
- `scratch/untracked-38.tmp`
- `scratch/untracked-39.tmp`
- `scratch/untracked-40.tmp`
- `scratch/untracked-41.tmp`
- `scratch/untracked-42.tmp`
- `scratch/untracked-43.tmp`
- `scratch/untracked-44.tmp`
- `scratch/untracked-45.tmp`
- `scratch/untracked-46.tmp`
- `scratch/untracked-47.tmp`
- `scratch/untracked-48.tmp`
- `scratch/untracked-49.tmp`

## Health Score

**Score:** 76.0 / 100.0  **Grade:** C

**Check coverage:** 9 ran, 1 skipped (tool not installed) -- confidence 90%

| Category | Points |
|----------|--------|
| Tests | 18.0 |
| Quality | 15.0 |
| Security | 12.0 |
| Git | 10.0 |
| Code | 11.0 |
| Tooling | 10.0 |

### Critical failures

- 1 potential secret was found in tracked source

### Recommendations

- Fix the failing cargo test
- Rotate the leaked credential

## AI Summary

```text
This is a hybrid Python/Rust/Go workspace with one failing test.
```

## Suggested reading order

1. `src/module_0.py`
2. `src/module_1.py`
3. `src/module_2.py`
4. `src/module_3.py`
5. `src/module_4.py`
6. `src/module_5.py`
7. `src/module_6.py`
8. `src/module_7.py`
9. `src/module_8.py`
10. `src/module_9.py`
11. `src/module_10.py`
12. `src/module_11.py`
13. `src/module_12.py`
14. `src/module_13.py`
15. `src/module_14.py`
16. `src/module_15.py`
17. `src/module_16.py`
18. `src/module_17.py`
19. `src/module_18.py`
20. `src/module_19.py`
21. `src/module_20.py`
22. `src/module_21.py`
23. `src/module_22.py`
24. `src/module_23.py`
25. `src/module_24.py`
26. `src/module_25.py`
27. `src/module_26.py`
28. `src/module_27.py`
29. `src/module_28.py`
30. `src/module_29.py`
31. `src/module_30.py`
32. `src/module_31.py`
33. `src/module_32.py`
34. `src/module_33.py`
35. `src/module_34.py`
36. `src/module_35.py`
37. `src/module_36.py`
38. `src/module_37.py`
39. `src/module_38.py`
40. `src/module_39.py`

## Project statistics

- Total files: **196**
- By extension: .ext0 (12), .ext1 (11), .ext2 (10), .ext3 (9), .ext4 (8), .ext5 (7), .ext6 (6), .ext7 (5), .ext8 (4), .ext9 (3)
- LOC: **12000** (code 9800 / comment 1500 / blank 700)
- Binary files: 2 · Hidden files: 3
- Empty files: 1 · Broken symlinks: 1
- Temporary files: 1 · Cache-like: 1

### Largest files

| Path | Size |
|------|------|
| `big/file-0.bin` | 1.0 KiB |
| `big/file-1.bin` | 2.0 KiB |
| `big/file-2.bin` | 3.0 KiB |
| `big/file-3.bin` | 4.0 KiB |
| `big/file-4.bin` | 5.0 KiB |
| `big/file-5.bin` | 6.0 KiB |
| `big/file-6.bin` | 7.0 KiB |
| `big/file-7.bin` | 8.0 KiB |
| `big/file-8.bin` | 9.0 KiB |
| `big/file-9.bin` | 10.0 KiB |
| `big/file-10.bin` | 11.0 KiB |
| `big/file-11.bin` | 12.0 KiB |
| `big/file-12.bin` | 13.0 KiB |
| `big/file-13.bin` | 14.0 KiB |
| `big/file-14.bin` | 15.0 KiB |

## TODO / FIXME markers

| File | Line | Kind | Content |
|------|------|------|---------|
| `src/todo_0.py` | 1 | TODO | `item 0` |
| `src/todo_1.py` | 2 | TODO | `item 1` |
| `src/todo_2.py` | 3 | TODO | `item 2` |
| `src/todo_3.py` | 4 | TODO | `item 3` |
| `src/todo_4.py` | 5 | TODO | `item 4` |
| `src/todo_5.py` | 6 | TODO | `item 5` |
| `src/todo_6.py` | 7 | TODO | `item 6` |
| `src/todo_7.py` | 8 | TODO | `item 7` |
| `src/todo_8.py` | 9 | TODO | `item 8` |
| `src/todo_9.py` | 10 | TODO | `item 9` |
| `src/todo_10.py` | 11 | TODO | `item 10` |
| `src/todo_11.py` | 12 | TODO | `item 11` |
| `src/todo_12.py` | 13 | TODO | `item 12` |
| `src/todo_13.py` | 14 | TODO | `item 13` |
| `src/todo_14.py` | 15 | TODO | `item 14` |
| `src/todo_15.py` | 16 | TODO | `item 15` |
| `src/todo_16.py` | 17 | TODO | `item 16` |
| `src/todo_17.py` | 18 | TODO | `item 17` |
| `src/todo_18.py` | 19 | TODO | `item 18` |
| `src/todo_19.py` | 20 | TODO | `item 19` |
| `src/todo_20.py` | 21 | TODO | `item 20` |
| `src/todo_21.py` | 22 | TODO | `item 21` |
| `src/todo_22.py` | 23 | TODO | `item 22` |
| `src/todo_23.py` | 24 | TODO | `item 23` |
| `src/todo_24.py` | 25 | TODO | `item 24` |
| `src/todo_25.py` | 26 | TODO | `item 25` |
| `src/todo_26.py` | 27 | TODO | `item 26` |
| `src/todo_27.py` | 28 | TODO | `item 27` |
| `src/todo_28.py` | 29 | TODO | `item 28` |
| `src/todo_29.py` | 30 | TODO | `item 29` |
| `src/todo_30.py` | 31 | TODO | `item 30` |
| `src/todo_31.py` | 32 | TODO | `item 31` |
| `src/todo_32.py` | 33 | TODO | `item 32` |
| `src/todo_33.py` | 34 | TODO | `item 33` |
| `src/todo_34.py` | 35 | TODO | `item 34` |
| `src/todo_35.py` | 36 | TODO | `item 35` |
| `src/todo_36.py` | 37 | TODO | `item 36` |
| `src/todo_37.py` | 38 | TODO | `item 37` |
| `src/todo_38.py` | 39 | TODO | `item 38` |
| `src/todo_39.py` | 40 | TODO | `item 39` |
| `src/todo_40.py` | 41 | TODO | `item 40` |
| `src/todo_41.py` | 42 | TODO | `item 41` |
| `src/todo_42.py` | 43 | TODO | `item 42` |
| `src/todo_43.py` | 44 | TODO | `item 43` |
| `src/todo_44.py` | 45 | TODO | `item 44` |
| `src/todo_45.py` | 46 | TODO | `item 45` |
| `src/todo_46.py` | 47 | TODO | `item 46` |
| `src/todo_47.py` | 48 | TODO | `item 47` |
| `src/todo_48.py` | 49 | TODO | `item 48` |
| `src/todo_49.py` | 50 | TODO | `item 49` |
| `src/todo_50.py` | 51 | TODO | `item 50` |
| `src/todo_51.py` | 52 | TODO | `item 51` |
| `src/todo_52.py` | 53 | TODO | `item 52` |
| `src/todo_53.py` | 54 | TODO | `item 53` |
| `src/todo_54.py` | 55 | TODO | `item 54` |
| `src/todo_55.py` | 56 | TODO | `item 55` |
| `src/todo_56.py` | 57 | TODO | `item 56` |
| `src/todo_57.py` | 58 | TODO | `item 57` |
| `src/todo_58.py` | 59 | TODO | `item 58` |
| `src/todo_59.py` | 60 | TODO | `item 59` |
| `src/todo_60.py` | 61 | TODO | `item 60` |
| `src/todo_61.py` | 62 | TODO | `item 61` |
| `src/todo_62.py` | 63 | TODO | `item 62` |
| `src/todo_63.py` | 64 | TODO | `item 63` |
| `src/todo_64.py` | 65 | TODO | `item 64` |
| `src/todo_65.py` | 66 | TODO | `item 65` |
| `src/todo_66.py` | 67 | TODO | `item 66` |
| `src/todo_67.py` | 68 | TODO | `item 67` |
| `src/todo_68.py` | 69 | TODO | `item 68` |
| `src/todo_69.py` | 70 | TODO | `item 69` |
| `src/todo_70.py` | 71 | TODO | `item 70` |
| `src/todo_71.py` | 72 | TODO | `item 71` |
| `src/todo_72.py` | 73 | TODO | `item 72` |
| `src/todo_73.py` | 74 | TODO | `item 73` |
| `src/todo_74.py` | 75 | TODO | `item 74` |
| `src/todo_75.py` | 76 | TODO | `item 75` |
| `src/todo_76.py` | 77 | TODO | `item 76` |
| `src/todo_77.py` | 78 | TODO | `item 77` |
| `src/todo_78.py` | 79 | TODO | `item 78` |
| `src/todo_79.py` | 80 | TODO | `item 79` |
| `src/todo_80.py` | 81 | TODO | `item 80` |
| `src/todo_81.py` | 82 | TODO | `item 81` |
| `src/todo_82.py` | 83 | TODO | `item 82` |
| `src/todo_83.py` | 84 | TODO | `item 83` |
| `src/todo_84.py` | 85 | TODO | `item 84` |
| `src/todo_85.py` | 86 | TODO | `item 85` |
| `src/todo_86.py` | 87 | TODO | `item 86` |
| `src/todo_87.py` | 88 | TODO | `item 87` |
| `src/todo_88.py` | 89 | TODO | `item 88` |
| `src/todo_89.py` | 90 | TODO | `item 89` |
| `src/todo_90.py` | 91 | TODO | `item 90` |
| `src/todo_91.py` | 92 | TODO | `item 91` |
| `src/todo_92.py` | 93 | TODO | `item 92` |
| `src/todo_93.py` | 94 | TODO | `item 93` |
| `src/todo_94.py` | 95 | TODO | `item 94` |
| `src/todo_95.py` | 96 | TODO | `item 95` |
| `src/todo_96.py` | 97 | TODO | `item 96` |
| `src/todo_97.py` | 98 | TODO | `item 97` |
| `src/todo_98.py` | 99 | TODO | `item 98` |
| `src/todo_99.py` | 100 | TODO | `item 99` |
| ... | ... | ... | (3 more) |

## Test results

### pytest [PASS]

```text
120 passed
```

### cargo test [FAIL]

```text
1 failed, 40 passed
```

<details>
<summary>Full output</summary>

```text
test add ... FAILED
thread 'main' panicked
```

</details>


### go test [SKIP]

*Skipped:* go not installed

## Quality checks

### ruff [PASS]

```text
All checks passed!
```

### cargo clippy [FAIL]

```text
2 warnings
```

<details>
<summary>Full output</summary>

```text
warning: unused import
warning: needless clone
```

</details>


## Security checks

### bandit [PASS]

```text
No issues identified.
```

### gitleaks [FAIL]

```text
1 leak found
```

<details>
<summary>Full output</summary>

```text
1 leak found
```

</details>


## Known issues

- Compilation or lint errors were detected

## Warnings detected

- **ruff**: `line too long`
- **clippy**: `unused import`
- **clippy**: `needless clone`

## Errors detected

- **cargo test**: `add() off by one`
- **gitleaks**: `possible API key`

## Project tree

```text
hybrid-project/
├── src/
│   ├── main.py
│   └── lib.rs
└── README.md
```

## Included files (3 included / 1 skipped / 2 excluded for secret safety)

### Excluded (credential-shaped filenames, never read — AGENTS.md §4.10)

- `.env`

### Excluded (content matched a secret pattern — see findings below)

- `config/secrets.env`

### ⚠ Potential hardcoded secrets detected

Location and pattern only — matched values are never shown. The affected file(s) are excluded from source embedding above (see the exclusion lists). Review and rotate anything genuine, then remove it from source control.

| File | Line | Pattern |
|------|------|---------|
| `config/secrets.env` | 3 | AWS Secret Key |
| `tests/fixtures/dummy_key.py` | 1 | Generic API Key |

### Skipped (too large)

- `assets/huge.bin` (50.0 MiB)


### FILE: `src/main.py`

Size: 28.0 B

```python
def main():
    print("hi")

```

### FILE: `src/lib.rs`

Size: 48.0 B

```rust
pub fn add(a: i32, b: i32) -> i32 {
    a + b
}

```

### FILE: `README.md`

Size: 14.0 B

```markdown
# Hybrid demo

```