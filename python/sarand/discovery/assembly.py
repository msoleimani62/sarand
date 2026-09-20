"""Assembly language detection: which files are assembly, and which dialect
(architecture + assembler syntax) each one is written in.

"Assembly" is not one language. `mov eax, 1` is NASM/Intel x86, `movl $1,
%eax` is GNU as/AT&T x86, `mov x0, #1` is AArch64 and `li a0, 1` is
RISC-V -- four different programs to a reader, an assembler or an AI
assistant. sarand therefore reports the *dialect* of every assembly file
and a per-dialect summary for the project, not just "Assembly".

Classification is a transparent heuristic, not a parser: each dialect has a
handful of weighted patterns (its own register names, directives and
mnemonics), the best score wins, and a file that scores too low is reported
as an unidentified dialect instead of a guess. Only the first 64 KiB of a
file is read, and only the project root plus a few conventional first-level
directories are searched, so vendored or unrelated nested files never make
a project "an assembly project".

Assembly is a single language to sarand's analyzers, but its dialects cover:
x86 (NASM/Intel, GNU as AT&T, GNU as Intel, MASM/TASM, FASM), ARM (A32/T32),
AArch64, RISC-V, MIPS, PowerPC, 6502, Z80, AVR, Motorola 68000 and 8051.

زبان اسمبلی یک زبان واحد نیست. `mov eax, 1` اسمبلی NASM/Intel روی x86 است،
`movl $1, %eax` اسمبلی GNU as/AT&T روی x86، `mov x0, #1` اسمبلی AArch64 و
`li a0, 1` اسمبلی RISC-V -- برای خواننده، اسمبلر یا دستیار هوش مصنوعی چهار
برنامه‌ی متفاوت. پس sarand *گویش* هر فایل اسمبلی و یک خلاصه‌ی هر گویش برای
پروژه را گزارش می‌کند، نه فقط «Assembly».

طبقه‌بندی یک heuristic شفاف است، نه parser: هر گویش چند الگوی وزن‌دار دارد
(نام رجیسترها، دستورهای راهنما و mnemonic های خودش)، بهترین امتیاز برنده
می‌شود و فایلی که امتیاز کمی بگیرد به‌جای حدس به‌عنوان «گویش ناشناخته»
گزارش می‌شود. فقط ۶۴ کیلوبایت اول هر فایل خوانده می‌شود و فقط ریشه‌ی پروژه
و چند پوشه‌ی قراردادی سطح اول جست‌وجو می‌شوند، تا فایل‌های vendored یا
نامرتبط تو در تو پروژه را «پروژه‌ی اسمبلی» نکنند.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ASM_SUFFIXES = frozenset(
    {
        ".asm",
        ".s",  # also matches ".S" (lower-cased): GNU as with the C preprocessor
        ".nasm",
        ".yasm",
        ".masm",
        ".fasm",
        ".a51",
        ".a65",
        ".a86",
        ".z80",
    }
)
# First-level directories searched in addition to the project root.
# پوشه‌های سطح اول که علاوه بر ریشه‌ی پروژه جست‌وجو می‌شوند.
_SHALLOW_DIRS = ("asm", "src", "boot", "kernel", "firmware")
_MAX_FILES = 300
_READ_LIMIT = 64 * 1024
_MIN_SCORE = 4
_MAX_HITS_PER_PATTERN = 3

_ENTRY_NAMES = (
    "start.s",
    "boot.s",
    "boot.asm",
    "main.s",
    "main.asm",
    "crt0.s",
    "_start.s",
    "src/start.s",
    "src/boot.s",
    "src/boot.asm",
    "src/main.s",
    "src/main.asm",
)
_ENTRY_DECLARATION = re.compile(
    r"^\s*(?:\.globl|\.global|global|public)\s+(?:_start|main|_main|reset_handler)\b",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class Dialect:
    arch: str
    syntax: str

    @property
    def label(self) -> str:
        if not self.syntax:
            return self.arch
        return f"{self.arch} / {self.syntax}"


UNIDENTIFIED = Dialect("Unidentified", "")


@dataclass(frozen=True)
class _Signature:
    arch: str
    syntax: str
    patterns: tuple[tuple[str, int], ...]
    suffix_hints: tuple[str, ...] = ()
    # Patterns that count toward the score but do not by themselves prove
    # the dialect (plain Intel-style `mov eax, 1` is NASM, MASM and others).
    # الگوهایی که در امتیاز حساب می‌شوند ولی به‌تنهایی گویش را ثابت نمی‌کنند
    # (`mov eax, 1` به سبک Intel در NASM، MASM و بقیه هست).
    generic_patterns: tuple[tuple[str, int], ...] = ()


_X86_REGISTERS = r"(?:e|r)?(?:ax|bx|cx|dx|si|di|sp|bp)|[abcd][lh]|r(?:8|9|1[0-5])[dwb]?"

_SIGNATURES: tuple[_Signature, ...] = (
    _Signature(
        "x86",
        "GNU as, AT&T",
        (
            (rf"%(?:{_X86_REGISTERS})\b", 3),
            (
                (
                    r"\b(?:mov|push|pop|add|sub|lea|cmp|xor|call|ret|test|and|or|inc|dec)"
                    r"[bwlq]\b"
                ),
                2,
            ),
            (r"\$0x[0-9a-f]+|\$-?\d+\s*,\s*%", 1),
        ),
    ),
    _Signature(
        "x86",
        "GNU as, Intel",
        ((r"^\s*\.intel_syntax\b", 6), (r"\b(?:byte|word|dword|qword) ptr\b", 1)),
    ),
    _Signature(
        "x86",
        "NASM",
        (
            (r"^\s*section\s+\.(?:text|data|bss|rodata)\b", 3),
            (r"^\s*global\s+[\w.$@]+", 2),
            (r"^\s*bits\s+(?:16|32|64)\b", 4),
            (r"^\s*%(?:macro|endmacro|define|include|ifdef|ifndef|if|endif)\b", 2),
            (r"\b(?:resb|resw|resd|resq|equ)\b", 1),
        ),
        (".nasm", ".yasm"),
        (
            (
                (
                    rf"^\s*(?:mov|lea|add|sub|cmp|xor|and|or|test)\s+"
                    rf"(?:(?:byte|word|dword|qword)\s+)?\[?(?:{_X86_REGISTERS})\b"
                ),
                2,
            ),
        ),
    ),
    _Signature(
        "x86",
        "MASM/TASM",
        (
            (r"^\s*\.(?:386|486|586|686|model|code|stack|const|xmm)\b", 3),
            (r"\b\w+\s+proc\b", 2),
            (r"\bendp\b", 3),
            (r"\b(?:invoke|includelib)\b", 3),
            (r"\b(?:offset|addr)\s+\w+", 1),
            (r"^\s*end\s+\w+\s*$", 1),
        ),
        (".masm",),
    ),
    _Signature(
        "x86",
        "FASM",
        (
            (r"^\s*format\s+(?:PE|ELF|MZ|COFF|binary)", 5),
            (r"\buse(?:16|32|64)\b", 3),
            (r"^\s*entry\s+\w+", 2),
            (r"^\s*section\s+'[.\w]+'", 3),
            (r"^\s*(?:macro|struc)\b.*\{", 2),
        ),
        (".fasm",),
    ),
    _Signature(
        "ARM",
        "A32/T32",
        (
            (
                r"^\s*\.(?:arm|thumb|thumb_func|syntax\s+unified|fpu|cpu\s+cortex-m)\b",
                3,
            ),
            (r"\bbx\s+lr\b", 3),
            (r"\b(?:push|pop|ldm\w*|stm\w*)\s+\{", 2),
            (
                (
                    r"\b(?:mov|ldr|str|add|sub|cmp|orr|eor|and|bl|blx|movs|adds|subs)\s+"
                    r"(?:r(?:1[0-5]|\d)|sp|lr|pc)\b"
                ),
                2,
            ),
            (r"\bldr\s+r\d+\s*,\s*=", 2),
        ),
    ),
    _Signature(
        "AArch64",
        "A64",
        (
            (r"\b(?:stp|ldp)\s+[xw]\d+", 3),
            (r"\badrp\b", 3),
            (
                (
                    r"\b(?:mov|ldr|str|add|sub|cmp|orr|eor|and|bl|blr|cbz|cbnz|movz|movk)"
                    r"\s+[xw](?:[12]?\d|30)\b"
                ),
                2,
            ),
            (r"\.arch\s+armv8", 3),
            (r"\bsvc\s+#0\b", 2),
            (r"\b(?:x29|x30)\b", 2),
        ),
    ),
    _Signature(
        "RISC-V",
        "",
        (
            (
                (
                    r"\b(?:addi|lui|auipc|jalr?|sd|ld|lw|sw|beq|bne|blt|bge|li|la|mv)\s+"
                    r"(?:zero|ra|sp|gp|tp|[ast]\d+|x\d+)\b"
                ),
                3,
            ),
            (r"^\s*\.option\s+(?:rvc|norvc|push|pop|relax|norelax)\b", 3),
            (r"\b(?:ecall|ebreak)\b", 2),
        ),
    ),
    _Signature(
        "MIPS",
        "",
        (
            (r"\$(?:zero|at|v[01]|a[0-3]|t\d|s[0-7]|k[01]|gp|sp|fp|ra)\b", 3),
            (r"^\s*\.set\s+(?:noreorder|reorder|noat|at)\b", 3),
            (r"\b(?:addiu|lui|ori|jal|jr|syscall|sll)\b", 1),
        ),
    ),
    _Signature(
        "PowerPC",
        "",
        (
            (r"\b(?:mflr|mtlr|stwu|lwz|stw|blr|bctr|mtctr|lis|addis)\b", 3),
            (r"^\s*\.machine\s+\w*ppc\w*", 3),
        ),
    ),
    _Signature(
        "6502",
        "",
        (
            (r"\b(?:lda|sta|ldx|ldy|stx|sty|jsr|rts|inx|iny|dex|dey|pha|pla)\b", 2),
            (r"#\$[0-9a-f]{2}\b", 3),
            (r"^\s*\.org\s+\$", 2),
            (r"\b(?:sei|cli|clc|sec|adc|sbc|bne|beq|bcc|bcs)\b", 1),
        ),
        (".a65",),
    ),
    _Signature(
        "Z80",
        "",
        (
            (r"\bld\s+(?:a|b|c|d|e|h|l|hl|de|bc|sp|ix|iy)\s*,", 3),
            (r"\b(?:djnz|halt|ldir|lddr|exx|otir|inir)\b", 3),
            (r"\bcall\s+(?:nz|z|nc|c)\s*,", 2),
            (r"\bex\s+af\s*,", 3),
        ),
        (".z80",),
    ),
    _Signature(
        "AVR",
        "",
        (
            (r"\.include\s+\"[a-z0-9]+def\.inc\"", 5),
            (r"\bldi\s+r(?:1[6-9]|2\d|3[01])\b", 3),
            (r"\b(?:rjmp|rcall|sbi|cbi|sbrs|sbrc|reti|cpi|brne|breq)\b", 2),
        ),
    ),
    _Signature(
        "Motorola 68000",
        "",
        (
            (r"\b(?:move|add|sub|cmp|clr|tst|lea|movea)\.[bwl]\b", 3),
            (r"\b(?:jsr|rts|bra|dbra|trap\s+#\d+)\b", 1),
            (r"\b[da][0-7]\b", 1),
        ),
    ),
    _Signature(
        "8051",
        "",
        (
            (r"\b(?:movx|movc|acall|lcall|sjmp|setb|jnb|jbc)\b", 3),
            (r"\bmov\s+(?:a|r[0-7]|dptr|p[0-3])\s*,", 2),
            (r"\bdjnz\s+r[0-7]\b", 2),
        ),
        (".a51",),
    ),
)

_SUFFIX_BONUS = 5


def _x86_architecture(text: str) -> str:
    if re.search(
        r"\bbits\s+64\b|\buse64\b|\b(?:r[abcd]x|r[sd]i|r[sb]p|r(?:8|9|1[0-5]))\b",
        text,
        re.IGNORECASE,
    ):
        return "x86-64"
    if re.search(r"\bbits\s+16\b|\buse16\b|\borg\s+0?x?7c00h?\b", text, re.IGNORECASE):
        return "x86 (16-bit)"
    if re.search(
        r"\b(?:e[abcd]x|e[sd]i|e[sb]p)\b|\bbits\s+32\b|\buse32\b|\.386\b",
        text,
        re.IGNORECASE,
    ):
        return "x86 (32-bit)"
    return "x86"


def _score(patterns: tuple[tuple[str, int], ...], text: str) -> int:
    return sum(
        min(
            len(re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)),
            _MAX_HITS_PER_PATTERN,
        )
        * weight
        for pattern, weight in patterns
    )


def classify(text: str, suffix: str = "") -> Dialect:
    """Best-matching dialect of one assembly source, or UNIDENTIFIED."""
    lowered_suffix = suffix.lower()
    best: tuple[int, int, _Signature] | None = None  # (total, distinctive, sig)
    for signature in _SIGNATURES:
        distinctive = _score(signature.patterns, text)
        if lowered_suffix in signature.suffix_hints:
            distinctive += _SUFFIX_BONUS
        total = distinctive + _score(signature.generic_patterns, text)
        if best is None or total > best[0]:
            best = (total, distinctive, signature)
    if best is None or best[0] < _MIN_SCORE:
        return UNIDENTIFIED
    _total, distinctive, signature = best
    arch = _x86_architecture(text) if signature.arch == "x86" else signature.arch
    syntax = signature.syntax
    if signature.generic_patterns and distinctive == 0:
        syntax = "Intel syntax"
    return Dialect(arch, syntax)


def _candidate_files(root: Path) -> list[Path]:
    """Assembly-looking files in the root and the conventional first-level
    directories, in a stable order, capped at `_MAX_FILES`."""
    directories = [root, *(root / name for name in _SHALLOW_DIRS)]
    files: list[Path] = []
    for directory in directories:
        try:
            entries = sorted(directory.iterdir())
        except OSError:
            continue
        for path in entries:
            try:
                is_source = path.is_file() and path.suffix.lower() in ASM_SUFFIXES
            except OSError:
                continue
            if is_source:
                files.append(path)
            if len(files) >= _MAX_FILES:
                return files
    return files


def has_assembly_sources(root: Path) -> bool:
    """Cheap existence check for the analyzer's `matches`."""
    return bool(_candidate_files(root))


def _read(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            return handle.read(_READ_LIMIT).decode("utf-8", errors="replace")
    except OSError:
        return ""


@dataclass
class AssemblyProfile:
    """What the project's assembly files are written in."""

    files: dict[str, Dialect] = field(default_factory=dict)  # posix path -> dialect
    entry_points: list[str] = field(default_factory=list)

    @property
    def dialect_counts(self) -> Counter[Dialect]:
        return Counter(self.files.values())

    def summary(self) -> str:
        """`x86-64 (NASM) x3, AArch64 (A64) x2` -- most common first."""
        return ", ".join(
            f"{dialect.label} x{count}"
            for dialect, count in sorted(
                self.dialect_counts.items(), key=lambda item: (-item[1], item[0].label)
            )
        )


def scan_assembly(root: Path) -> AssemblyProfile | None:
    """Profile the project's assembly sources, or None if it has none."""
    candidates = _candidate_files(root)
    if not candidates:
        return None
    profile = AssemblyProfile()
    for path in candidates:
        relative = path.relative_to(root).as_posix()
        text = _read(path)
        profile.files[relative] = classify(text, path.suffix)
        if _ENTRY_DECLARATION.search(text) or relative in _ENTRY_NAMES:
            profile.entry_points.append(relative)
    return profile


def assembly_entry_points(root: Path) -> list[str]:
    """Files that declare `_start`/`main`/`reset_handler`, plus conventional
    entry file names that exist. Paths use forward slashes on every OS."""
    profile = scan_assembly(root)
    return sorted(set(profile.entry_points)) if profile else []
