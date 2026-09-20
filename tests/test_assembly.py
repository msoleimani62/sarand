"""Tests for assembly detection: file discovery, dialect classification,
project detection and report rendering."""

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from _helpers import write
from sarand.analyzers.assembly_analyzer import AssemblyAnalyzer
from sarand.analyzers.registry import discover_analyzers
from sarand.core.ai_summary import generate_ai_summary
from sarand.discovery.assembly import (
    UNIDENTIFIED,
    assembly_entry_points,
    classify,
    has_assembly_sources,
    scan_assembly,
)
from sarand.discovery.project_detector import detect_project
from sarand.models.results import (
    EnvironmentInfo,
    GitSnapshot,
    ProjectDetection,
    ProjectStats,
    ReportData,
)
from sarand.renderers import json_renderer, markdown, text

_SAMPLES = {
    "x86-64 / NASM": (
        "boot.asm",
        """\
bits 64
section .text
global _start
_start:
    mov rax, 60
    xor rdi, rdi
    syscall
section .data
msg db 'hi', 10
len equ $ - msg
""",
    ),
    "x86 (32-bit) / NASM": (
        "hello.nasm",
        """\
section .data
msg db 'Hello', 0xa
section .text
global _start
_start:
    mov eax, 4
    mov ebx, 1
    mov ecx, msg
    mov edx, 6
    int 0x80
""",
    ),
    "x86 (16-bit) / NASM": (
        "boot.asm",
        """\
bits 16
org 0x7c00
start:
    mov ax, 0
    mov ds, ax
    hlt
times 510-($-$$) db 0
dw 0xaa55
""",
    ),
    "x86 (32-bit) / Intel syntax": (
        "x.asm",
        """\
mov eax, 1
mov ebx, 2
add eax, ebx
sub eax, 1
""",
    ),
    "x86-64 / GNU as, AT&T": (
        "start.s",
        """\
.globl _start
.text
_start:
    movq $60, %rax
    xorq %rdi, %rdi
    syscall
""",
    ),
    "x86 (32-bit) / GNU as, AT&T": (
        "start.S",
        """\
.globl _start
.text
_start:
    movl $1, %eax
    xorl %ebx, %ebx
    int $0x80
""",
    ),
    "x86-64 / GNU as, Intel": (
        "k.s",
        """\
.intel_syntax noprefix
.globl main
main:
    mov rax, qword ptr [rbp-8]
    ret
""",
    ),
    "x86 (32-bit) / MASM/TASM": (
        "prog.asm",
        """\
.386
.model flat, stdcall
.code
main proc
    invoke ExitProcess, 0
main endp
end main
""",
    ),
    "x86 (32-bit) / FASM": (
        "a.fasm",
        """\
format PE console
entry start
section '.text' code readable executable
start:
    invoke ExitProcess, 0
use32
""",
    ),
    "ARM / A32/T32": (
        "start.s",
        """\
.syntax unified
.thumb
.global _start
_start:
    push {r4, lr}
    ldr r0, =msg
    mov r1, #1
    bl printf
    pop {r4, pc}
    bx lr
""",
    ),
    "AArch64 / A64": (
        "start.s",
        """\
.global _start
_start:
    stp x29, x30, [sp, #-16]!
    mov x0, #0
    adrp x1, msg
    bl main
    ldp x29, x30, [sp], #16
    ret
""",
    ),
    "RISC-V": (
        "start.S",
        """\
.section .text
.globl _start
_start:
    li a0, 0
    addi sp, sp, -16
    sd ra, 8(sp)
    ecall
""",
    ),
    "MIPS": (
        "m.s",
        """\
.set noreorder
.text
main:
    addiu $sp, $sp, -8
    lw $t0, 0($a0)
    jr $ra
    nop
""",
    ),
    "PowerPC": (
        "p.s",
        """\
.machine ppc
main:
    mflr 0
    stwu 1, -16(1)
    lwz 3, 8(1)
    blr
""",
    ),
    "6502": (
        "game.a65",
        """\
.org $8000
reset:
    sei
    lda #$00
    sta $2000
    ldx #$ff
    txs
    jsr init
    rts
""",
    ),
    "Z80": (
        "z.z80",
        """\
    org 0x8000
    ld a, 5
    ld hl, buffer
loop:
    djnz loop
    halt
""",
    ),
    "AVR": (
        "blink.asm",
        """\
.include "m328Pdef.inc"
.org 0x0000
    rjmp reset
reset:
    ldi r16, 0xFF
    out DDRB, r16
    sbi PORTB, 5
    rjmp reset
""",
    ),
    "Motorola 68000": (
        "m.s",
        """\
start:
    move.l #$1000, d0
    lea buffer, a0
    move.w d0, (a0)
    jsr sub
    rts
""",
    ),
    "8051": (
        "c.a51",
        """\
ORG 0000H
    mov A, #05h
    mov R0, #10
loop: djnz R0, loop
    setb P1.0
    acall delay
    sjmp $
""",
    ),
}


@pytest.mark.parametrize("label", sorted(_SAMPLES))
def test_each_dialect_is_identified(label: str) -> None:
    filename, source = _SAMPLES[label]

    assert classify(source, Path(filename).suffix).label == label


def test_text_that_is_not_assembly_is_left_unidentified() -> None:
    assert classify("", ".s") == UNIDENTIFIED
    assert classify("just some prose with the word move in it\n", ".asm") == (
        UNIDENTIFIED
    )
    assert classify("int main(void) { return 0; }\n", ".s") == UNIDENTIFIED


# --- file discovery ----------------------------------------------------


def test_sources_are_found_in_the_root_and_conventional_directories() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert has_assembly_sources(root) is False

        write(root / "src" / "boot.S", "nop\n")
        assert has_assembly_sources(root) is True


def test_nested_or_vendored_assembly_does_not_make_an_assembly_project() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "third_party" / "lib" / "x.s", "nop\n")
        write(root / "src" / "deep" / "y.asm", "nop\n")
        write(root / "notes.txt", "mov eax, 1\n")

        assert has_assembly_sources(root) is False


def test_the_uppercase_s_extension_counts() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "entry.S", ".globl _start\n_start:\n")

        assert has_assembly_sources(root) is True


def test_profile_counts_dialects_most_common_first() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "a.asm", _SAMPLES["x86-64 / NASM"][1])
        write(root / "b.asm", _SAMPLES["x86-64 / NASM"][1])
        write(root / "asm" / "c.s", _SAMPLES["AArch64 / A64"][1])

        profile = scan_assembly(root)

    assert profile is not None
    assert profile.summary() == "x86-64 / NASM x2, AArch64 / A64 x1"
    assert set(profile.files) == {"a.asm", "b.asm", "asm/c.s"}


def test_entry_points_are_files_declaring_a_start_symbol_with_forward_slashes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "src" / "boot.S", ".globl _start\n_start:\n    nop\n")
        write(root / "src" / "helper.s", "helper:\n    ret\n")

        assert assembly_entry_points(root) == ["src/boot.S"]


def test_a_conventional_entry_file_name_counts_even_without_a_declaration() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "boot.asm", "nop\n")

        assert assembly_entry_points(root) == ["boot.asm"]


def test_a_huge_file_is_only_read_up_to_the_limit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "big.s", ".globl main\n" + "nop\n" * 500_000)

        profile = scan_assembly(root)

    assert profile is not None
    assert list(profile.files) == ["big.s"]


# --- analyzer contract -------------------------------------------------


def test_the_analyzer_matches_and_runs_nothing() -> None:
    analyzer = AssemblyAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert analyzer.matches(root) is False
        write(root / "boot.asm", "nop\n")

        assert analyzer.matches(root) is True
        assert asyncio.run(analyzer.run_tests(root)) is None
        assert asyncio.run(analyzer.run_quality(root)) == []
        assert asyncio.run(analyzer.run_security(root)) == []


def test_the_registry_includes_the_assembly_analyzer() -> None:
    assert "Assembly" in {a.name for a in discover_analyzers()}


# --- project detection -------------------------------------------------


def test_an_assembly_only_project_is_recognized() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "boot.asm", _SAMPLES["x86 (16-bit) / NASM"][1])

        result = detect_project(root)

    assert result.is_recognized
    assert result.languages == ["Assembly"]
    assert result.primary_language == "Assembly"
    assert result.details == {"Assembly": "x86 (16-bit) / NASM x1"}
    assert result.markers_found == ["boot.asm"]


def test_assembly_next_to_a_real_build_system_does_not_take_over() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "CMakeLists.txt", "cmake_minimum_required(VERSION 3.10)\n")
        write(root / "src" / "start.s", _SAMPLES["AArch64 / A64"][1])

        result = detect_project(root)

    assert result.primary_language == "C/C++"
    assert result.languages == ["C/C++", "Assembly"]
    assert result.details["Assembly"] == "AArch64 / A64 x1"


def test_a_makefile_project_is_assembly_only_without_other_sources() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "Makefile", "all:\n\tnasm -f elf64 boot.asm\n")
        write(root / "boot.asm", _SAMPLES["x86-64 / NASM"][1])
        assert detect_project(root).primary_language == "Assembly"

        write(root / "main.c", "int main(void) { return 0; }\n")
        assert detect_project(root).primary_language == "Generic"


def test_projects_without_assembly_get_no_details() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "pyproject.toml", "[project]\nname='x'\n")

        assert detect_project(root).details == {}


# --- rendering ---------------------------------------------------------


def _report(root: Path) -> ReportData:
    return ReportData(
        project_root=root,
        generated_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        environment=EnvironmentInfo(python="Python 3.13.0"),
        git=GitSnapshot(branch="main", commit="abc123"),
        stats=ProjectStats(total_files=1, total_loc=1, files_by_extension={".asm": 1}),
        detection=ProjectDetection(
            languages=["Assembly"],
            primary_language="Assembly",
            project_type="low-level / assembly program",
            build_system="assembler (project-specific)",
            markers_found=["boot.asm"],
            entry_points=["boot.asm"],
            details={"Assembly": "x86-64 / NASM x2, AArch64 / A64 x1"},
        ),
        used_rust_core=False,
        tree_text="x/",
        included_files=[],
    )


def test_every_renderer_shows_the_dialect_breakdown() -> None:
    expected = "x86-64 / NASM x2, AArch64 / A64 x1"
    with tempfile.TemporaryDirectory() as tmp:
        data = _report(Path(tmp))

        assert f"- **Assembly:** {expected}" in markdown.render(data)
        assert f"Assembly: {expected}" in text.render(data)
        assert f"Assembly: {expected}" in generate_ai_summary(data)
        payload = json.loads(json_renderer.render(data))
        assert payload["detection"]["details"] == {"Assembly": expected}
