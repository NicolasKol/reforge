"""
Test fixtures for analyzer_ghidra_decompile.

Provides a synthetic raw JSONL fixture (embedded, no Ghidra required)
and helper factories for test data.
"""
import json
import tempfile
from pathlib import Path
from typing import List

import pytest


# ── Synthetic raw JSONL fixture ──────────────────────────────────────

def _make_raw_function(
    entry_va: int,
    name: str,
    c_raw: str | None = "int main(void) { return 0; }",
    error: str | None = None,
    is_external_block: bool = False,
    is_thunk: bool = False,
    is_import: bool = False,
    section_hint: str = ".text",
    namespace: str | None = None,
    insn_count: int = 10,
    size_bytes: int = 50,
    warnings_raw: list | None = None,
    variables: list | None = None,
    blocks: list | None = None,
    calls: list | None = None,
) -> dict:
    """Build a minimal raw function record dict."""
    return {
        "_type": "function",
        "entry_hex": hex(entry_va),
        "entry_va": entry_va,
        "name": name,
        "namespace": namespace,
        "is_external_block": is_external_block,
        "is_thunk": is_thunk,
        "is_import": is_import,
        "body_start_va": entry_va,
        "body_end_va": entry_va + size_bytes - 1,
        "size_bytes": size_bytes,
        "section_hint": section_hint,
        "insn_count": insn_count,
        "c_raw": c_raw,
        "error": error,
        "warnings_raw": warnings_raw or [],
        "variables": variables or [
            {
                "name": "param_1",
                "is_param": True,
                "size_bytes": 8,
                "type_str": "long",
                "storage_class": "REGISTER",
                "storage_key": "reg:RDI",
                "stack_offset": None,
                "register_name": "RDI",
                "addr_va": None,
                "access_sites": [entry_va + 2, entry_va + 10],
                "access_sites_truncated": False,
            },
            {
                "name": "local_c",
                "is_param": False,
                "size_bytes": 4,
                "type_str": "int",
                "storage_class": "STACK",
                "storage_key": "stack:off:-0x10",
                "stack_offset": -16,
                "register_name": None,
                "addr_va": None,
                "access_sites": [entry_va + 5],
                "access_sites_truncated": False,
            },
        ],
        "blocks": blocks or [
            {
                "block_id": 0,
                "start_va": entry_va,
                "end_va": entry_va + 20,
                "succ_va": [entry_va + 21],
            },
            {
                "block_id": 1,
                "start_va": entry_va + 21,
                "end_va": entry_va + size_bytes - 1,
                "succ_va": [],
            },
        ],
        "calls": calls or [],
    }


def _make_raw_summary(
    total: int = 5,
    ok: int = 4,
    fail: int = 1,
) -> dict:
    return {
        "_type": "summary",
        "ghidra_version": "12.0.3",
        "java_version": "21.0.10",
        "program_name": "test_binary",
        "program_arch": "x86",
        "total_functions": total,
        "decompile_ok": ok,
        "decompile_fail": fail,
        "analysis_options": "default",
    }


def write_fixture_jsonl(
    tmp_dir: Path,
    functions: list | None = None,
    summary: dict | None = None,
    filename: str = "raw.jsonl",
) -> Path:
    """Write a fixture raw JSONL file and return its path."""
    if functions is None:
        functions = [
            _make_raw_function(0x101000, "main",
                c_raw="int main(int argc, char **argv) {\n  return 0;\n}\n",
                insn_count=15, size_bytes=80,
                calls=[{
                    "callsite_va": 0x101010,
                    "callsite_hex": "0x101010",
                    "call_kind": "DIRECT",
                    "callee_entry_va": 0x101100,
                    "callee_name": "helper",
                    "is_external_target": False,
                    "is_import_proxy_target": False,
                }]),
            _make_raw_function(0x101100, "helper",
                c_raw="void helper(int x) {\n  x = x + 1;\n}\n",
                insn_count=8, size_bytes=40),
            _make_raw_function(0x101200, "_init",
                c_raw="void _init(void) { return; }\n",
                insn_count=3, size_bytes=10, section_hint=".init"),
            _make_raw_function(0x101300, "printf",
                c_raw=None, error=None,
                is_external_block=True, is_thunk=True, is_import=True,
                section_hint=".plt", insn_count=0, size_bytes=16),
            _make_raw_function(0x101400, "fail_func",
                c_raw=None, error="Decompile timed out",
                insn_count=50, size_bytes=200),
        ]

    if summary is None:
        ok_count = sum(1 for f in functions if f.get("c_raw") is not None)
        fail_count = len(functions) - ok_count
        summary = _make_raw_summary(
            total=len(functions), ok=ok_count, fail=fail_count,
        )

    out_path = tmp_dir / filename
    with open(out_path, "w", encoding="utf-8") as fp:
        for func in functions:
            fp.write(json.dumps(func, sort_keys=True) + "\n")
        fp.write(json.dumps(summary, sort_keys=True) + "\n")

    return out_path


# ── Minimal ELF fixture ──────────────────────────────────────────────

def write_minimal_elf(tmp_dir: Path, filename: str = "test.elf") -> Path:
    """
    Write a minimal valid ELF binary (just the header).

    This is enough to pass magic-byte validation but not full Ghidra import.
    """
    # Minimal ELF64 header (64 bytes)
    elf_header = bytearray(64)
    # Magic
    elf_header[0:4] = b"\x7fELF"
    # Class: 64-bit
    elf_header[4] = 2
    # Data: little-endian
    elf_header[5] = 1
    # Version
    elf_header[6] = 1
    # OS/ABI
    elf_header[7] = 0
    # Type: ET_EXEC
    elf_header[16] = 2
    elf_header[17] = 0
    # Machine: EM_X86_64 = 0x3E
    elf_header[18] = 0x3E
    elf_header[19] = 0
    # Version
    elf_header[20] = 1
    # ELF header size
    elf_header[52] = 64
    elf_header[53] = 0

    out_path = tmp_dir / filename
    out_path.write_bytes(bytes(elf_header))
    return out_path


# ── Pytest fixtures ──────────────────────────────────────────────────

@pytest.fixture
def tmp_output_dir(tmp_path: Path) -> Path:
    """Temporary output directory."""
    d = tmp_path / "output"
    d.mkdir()
    return d


@pytest.fixture
def fixture_raw_jsonl(tmp_path: Path) -> Path:
    """A synthetic raw JSONL file with 5 functions + summary."""
    return write_fixture_jsonl(tmp_path)


@pytest.fixture
def fixture_elf(tmp_path: Path) -> Path:
    """A minimal valid ELF binary."""
    return write_minimal_elf(tmp_path)
