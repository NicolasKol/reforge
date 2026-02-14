"""
Test fixtures for join_oracles_to_ghidra_decompile.

All fixtures are pure-Python: no real binaries, no Docker, no external
tools.  They provide minimal valid data structures matching the schemas
from upstream workers.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import pytest

# ═══════════════════════════════════════════════════════════════════════════════
# Canonical test SHA-256
# ═══════════════════════════════════════════════════════════════════════════════

TEST_SHA256 = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"


# ═══════════════════════════════════════════════════════════════════════════════
# Build receipt
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def build_receipt() -> dict:
    return {
        "builder": {
            "name": "builder",
            "version": "v2",
            "profile_id": "gcc-O0O1O2O3",
            "lock_text_hash": "abc",
        },
        "job": {
            "job_id": "job-42",
            "name": "math_recurse",
            "created_at": "2025-01-01T00:00:00Z",
            "finished_at": "2025-01-01T00:01:00Z",
            "status": "COMPLETE",
        },
        "builds": [
            {
                "optimization": "O0",
                "variant": "stripped",
                "status": "SUCCESS",
                "flags": ["-O0"],
                "artifact": {
                    "path_rel": "O0/stripped/math_recurse",
                    "sha256": TEST_SHA256,
                    "size_bytes": 12345,
                    "elf": {"type": "EXEC", "arch": "x86_64", "build_id": "deadbeef"},
                    "debug_presence": {"has_debug_sections": False},
                },
            },
            {
                "optimization": "O3",
                "variant": "stripped",
                "status": "SUCCESS",
                "flags": ["-O3"],
                "artifact": {
                    "path_rel": "O3/stripped/math_recurse",
                    "sha256": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
                    "size_bytes": 9876,
                },
            },
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Oracle DWARF outputs
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def oracle_report() -> dict:
    return {
        "package_name": "oracle_dwarf",
        "oracle_version": "v0",
        "schema_version": "0.2",
        "profile_id": "linux-x86_64-gcc-O0O1",
        "binary_path": "/build/math_recurse",
        "binary_sha256": TEST_SHA256,
        "build_id": "deadbeef",
        "verdict": "ACCEPT",
        "reasons": [],
        "function_counts": {"total": 4, "accept": 2, "warn": 1, "reject": 1},
        "timestamp": "2025-01-01T00:02:00Z",
    }


@pytest.fixture
def oracle_functions() -> dict:
    """Four DWARF functions: 2 ACCEPT, 1 WARN, 1 REJECT."""
    return {
        "package_name": "oracle_dwarf",
        "oracle_version": "v0",
        "schema_version": "0.2",
        "profile_id": "linux-x86_64-gcc-O0O1",
        "binary_path": "/build/math_recurse",
        "binary_sha256": TEST_SHA256,
        "functions": [
            {
                "function_id": "cu0:0x100",
                "die_offset": "0x100",
                "cu_offset": "0x0",
                "name": "add",
                "linkage_name": None,
                "decl_file": "/src/math.c",
                "decl_line": 5,
                "decl_column": 1,
                "comp_dir": "/build",
                "cu_id": "cu0",
                "ranges": [{"low": "0x401000", "high": "0x401030"}],
                "dominant_file": "/src/math.c",
                "dominant_file_ratio": 1.0,
                "n_line_rows": 8,
                "line_rows": [
                    {"file": "/src/math.c", "line": 5, "count": 3},
                    {"file": "/src/math.c", "line": 6, "count": 5},
                ],
                "file_row_counts": {"/src/math.c": 8},
                "verdict": "ACCEPT",
                "reasons": [],
                "source_extract": None,
                "source_ready": "NO",
            },
            {
                "function_id": "cu0:0x200",
                "die_offset": "0x200",
                "cu_offset": "0x0",
                "name": "multiply",
                "linkage_name": None,
                "decl_file": "/src/math.c",
                "decl_line": 12,
                "decl_column": 1,
                "comp_dir": "/build",
                "cu_id": "cu0",
                "ranges": [{"low": "0x401030", "high": "0x401080"}],
                "dominant_file": "/src/math.c",
                "dominant_file_ratio": 1.0,
                "n_line_rows": 10,
                "line_rows": [
                    {"file": "/src/math.c", "line": 12, "count": 5},
                    {"file": "/src/math.c", "line": 13, "count": 5},
                ],
                "file_row_counts": {"/src/math.c": 10},
                "verdict": "ACCEPT",
                "reasons": [],
                "source_extract": None,
                "source_ready": "NO",
            },
            {
                "function_id": "cu0:0x300",
                "die_offset": "0x300",
                "cu_offset": "0x0",
                "name": "helper",
                "linkage_name": None,
                "decl_file": "/src/math.c",
                "decl_line": 20,
                "decl_column": 1,
                "comp_dir": "/build",
                "cu_id": "cu0",
                "ranges": [
                    {"low": "0x401080", "high": "0x4010a0"},
                    {"low": "0x4010c0", "high": "0x4010e0"},
                ],
                "dominant_file": "/src/math.c",
                "dominant_file_ratio": 0.8,
                "n_line_rows": 6,
                "line_rows": [
                    {"file": "/src/math.c", "line": 20, "count": 3},
                    {"file": "/src/util.h", "line": 5, "count": 3},
                ],
                "file_row_counts": {"/src/math.c": 3, "/src/util.h": 3},
                "verdict": "WARN",
                "reasons": ["MULTI_FILE_RANGE"],
                "source_extract": None,
                "source_ready": "NO",
            },
            {
                "function_id": "cu0:0x400",
                "die_offset": "0x400",
                "cu_offset": "0x0",
                "name": None,
                "linkage_name": None,
                "decl_file": None,
                "decl_line": None,
                "decl_column": None,
                "comp_dir": "/build",
                "cu_id": "cu0",
                "ranges": [],
                "dominant_file": None,
                "dominant_file_ratio": 0.0,
                "n_line_rows": 0,
                "line_rows": [],
                "file_row_counts": {},
                "verdict": "REJECT",
                "reasons": ["MISSING_RANGE"],
                "source_extract": None,
                "source_ready": "NO",
            },
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Alignment outputs
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def alignment_report() -> dict:
    return {
        "package_name": "join_dwarf_ts",
        "joiner_version": "v0",
        "schema_version": "0.1",
        "profile_id": "join-dwarf-ts-v0",
        "binary_sha256": TEST_SHA256,
        "build_id": "deadbeef",
        "dwarf_profile_id": "linux-x86_64-gcc-O0O1",
        "ts_profile_id": "oracle-ts-v0",
        "tu_hashes": {"math.c.i": "hash123"},
        "pair_counts": {"match": 2, "ambiguous": 1, "no_match": 0, "non_target": 1},
        "reason_counts": {"UNIQUE_BEST": 2, "NEAR_TIE": 1},
        "thresholds": {"overlap_threshold": 0.7, "epsilon": 0.02, "min_overlap_lines": 1},
        "excluded_path_prefixes": ["/usr/include"],
        "timestamp": "2025-01-01T00:03:00Z",
    }


@pytest.fixture
def alignment_pairs() -> dict:
    return {
        "package_name": "join_dwarf_ts",
        "joiner_version": "v0",
        "schema_version": "0.1",
        "profile_id": "join-dwarf-ts-v0",
        "binary_sha256": TEST_SHA256,
        "build_id": "deadbeef",
        "dwarf_profile_id": "linux-x86_64-gcc-O0O1",
        "ts_profile_id": "oracle-ts-v0",
        "pairs": [
            {
                "dwarf_function_id": "cu0:0x100",
                "dwarf_function_name": "add",
                "dwarf_verdict": "ACCEPT",
                "decl_file": "/src/math.c",
                "decl_line": 5,
                "decl_column": 1,
                "comp_dir": "/build",
                "best_ts_func_id": "math.c.i:10:50:hash_add",
                "best_tu_path": "math.c.i",
                "best_ts_function_name": "add",
                "overlap_count": 8,
                "total_count": 8,
                "overlap_ratio": 1.0,
                "gap_count": 0,
                "verdict": "MATCH",
                "reasons": ["UNIQUE_BEST"],
                "candidates": [
                    {
                        "ts_func_id": "math.c.i:10:50:hash_add",
                        "tu_path": "math.c.i",
                        "function_name": "add",
                        "context_hash": "ctx1",
                        "overlap_count": 8,
                        "overlap_ratio": 1.0,
                        "gap_count": 0,
                    },
                ],
            },
            {
                "dwarf_function_id": "cu0:0x200",
                "dwarf_function_name": "multiply",
                "dwarf_verdict": "ACCEPT",
                "decl_file": "/src/math.c",
                "decl_line": 12,
                "decl_column": 1,
                "comp_dir": "/build",
                "best_ts_func_id": "math.c.i:55:100:hash_mul",
                "best_tu_path": "math.c.i",
                "best_ts_function_name": "multiply",
                "overlap_count": 10,
                "total_count": 10,
                "overlap_ratio": 1.0,
                "gap_count": 0,
                "verdict": "MATCH",
                "reasons": ["UNIQUE_BEST"],
                "candidates": [
                    {
                        "ts_func_id": "math.c.i:55:100:hash_mul",
                        "tu_path": "math.c.i",
                        "function_name": "multiply",
                        "context_hash": "ctx2",
                        "overlap_count": 10,
                        "overlap_ratio": 1.0,
                        "gap_count": 0,
                    },
                ],
            },
            {
                "dwarf_function_id": "cu0:0x300",
                "dwarf_function_name": "helper",
                "dwarf_verdict": "WARN",
                "decl_file": "/src/math.c",
                "decl_line": 20,
                "decl_column": 1,
                "comp_dir": "/build",
                "best_ts_func_id": "math.c.i:105:150:hash_helper",
                "best_tu_path": "math.c.i",
                "best_ts_function_name": "helper",
                "overlap_count": 4,
                "total_count": 6,
                "overlap_ratio": 0.666,
                "gap_count": 2,
                "verdict": "AMBIGUOUS",
                "reasons": ["NEAR_TIE", "MULTI_FILE_RANGE_PROPAGATED"],
                "candidates": [
                    {
                        "ts_func_id": "math.c.i:105:150:hash_helper",
                        "tu_path": "math.c.i",
                        "function_name": "helper",
                        "context_hash": "ctx3",
                        "overlap_count": 4,
                        "overlap_ratio": 0.666,
                        "gap_count": 2,
                    },
                    {
                        "ts_func_id": "math.c.i:155:180:hash_helper2",
                        "tu_path": "math.c.i",
                        "function_name": "helper",
                        "context_hash": "ctx3",
                        "overlap_count": 3,
                        "overlap_ratio": 0.5,
                        "gap_count": 1,
                    },
                ],
            },
        ],
        "non_targets": [
            {
                "dwarf_function_id": "cu0:0x400",
                "name": None,
                "dwarf_verdict": "REJECT",
                "dwarf_reasons": ["MISSING_RANGE"],
                "decl_file": None,
                "decl_line": None,
                "decl_column": None,
                "comp_dir": "/build",
            },
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Ghidra outputs
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def ghidra_report() -> dict:
    return {
        "package_name": "analyzer_ghidra_decompile",
        "analyzer_version": "v1",
        "schema_version": "1.0",
        "profile_id": "ghidra-default",
        "binary_sha256": TEST_SHA256,
        "binary_path": "/stripped/math_recurse",
        "ghidra_version": "11.2",
        "java_version": "17",
        "binary_verdict": "ACCEPT",
        "reasons": [],
        "function_counts": {
            "n_functions_total": 5,
            "n_functions_ok": 3,
            "n_functions_warn": 1,
            "n_functions_fail": 0,
            "n_thunks": 0,
            "n_imports": 0,
            "n_externals": 1,
            "n_plt_or_stub": 0,
            "n_init_fini_aux": 1,
            "n_compiler_aux": 0,
            "n_decompile_fail": 0,
        },
        "timestamp": "2025-01-01T00:04:00Z",
    }


def _ghidra_func_id(sha: str, entry_va: int) -> str:
    return f"{sha}:{entry_va}"


@pytest.fixture
def ghidra_functions() -> List[dict]:
    """Five Ghidra functions with known body ranges."""
    sha = TEST_SHA256
    return [
        {
            "binary_id": sha,
            "function_id": _ghidra_func_id(sha, 0x401000),
            "entry_va": 0x401000,
            "entry_hex": "0x401000",
            "name": "FUN_00401000",
            "namespace": None,
            "body_start_va": 0x401000,
            "body_end_va": 0x401030,
            "size_bytes": 0x30,
            "is_external_block": False,
            "is_thunk": False,
            "is_import": False,
            "section_hint": ".text",
            "decompile_status": "OK",
            "c_raw": "int FUN_00401000(int a, int b) {\n  return a + b;\n}\n",
            "warnings": [],
            "warnings_raw": [],
            "verdict": "OK",
            "is_plt_or_stub": False,
            "is_init_fini_aux": False,
            "is_compiler_aux": False,
            "is_library_like": False,
            "asm_insn_count": 5,
            "c_line_count": 3,
            "insn_to_c_ratio": 1.67,
            "temp_var_count": 0,
            "fat_function_flag": False,
        },
        {
            "binary_id": sha,
            "function_id": _ghidra_func_id(sha, 0x401030),
            "entry_va": 0x401030,
            "entry_hex": "0x401030",
            "name": "FUN_00401030",
            "namespace": None,
            "body_start_va": 0x401030,
            "body_end_va": 0x401085,
            "size_bytes": 0x55,
            "is_external_block": False,
            "is_thunk": False,
            "is_import": False,
            "section_hint": ".text",
            "decompile_status": "OK",
            "c_raw": "int FUN_00401030(int a, int b) {\n  int result = 0;\n  for(int i=0; i<b; i++) {\n    result += a;\n  }\n  return result;\n}\n",
            "warnings": [],
            "warnings_raw": [],
            "verdict": "OK",
            "is_plt_or_stub": False,
            "is_init_fini_aux": False,
            "is_compiler_aux": False,
            "is_library_like": False,
            "asm_insn_count": 12,
            "c_line_count": 7,
            "insn_to_c_ratio": 1.71,
            "temp_var_count": 1,
            "fat_function_flag": False,
        },
        {
            # Ghidra func that partially overlaps DWARF "helper" (fragmented)
            "binary_id": sha,
            "function_id": _ghidra_func_id(sha, 0x401080),
            "entry_va": 0x401080,
            "entry_hex": "0x401080",
            "name": "FUN_00401080",
            "namespace": None,
            "body_start_va": 0x401080,
            "body_end_va": 0x4010f0,
            "size_bytes": 0x70,
            "is_external_block": False,
            "is_thunk": False,
            "is_import": False,
            "section_hint": ".text",
            "decompile_status": "OK",
            "c_raw": "void FUN_00401080(void) {\n  goto LAB_1;\nLAB_1:\n  return;\n}\n",
            "warnings": ["UNREACHABLE_BLOCKS_REMOVED"],
            "warnings_raw": ["Removed unreachable block"],
            "verdict": "WARN",
            "is_plt_or_stub": False,
            "is_init_fini_aux": False,
            "is_compiler_aux": False,
            "is_library_like": False,
            "asm_insn_count": 15,
            "c_line_count": 5,
            "insn_to_c_ratio": 3.0,
            "temp_var_count": 2,
            "fat_function_flag": False,
        },
        {
            # External function (no body range)
            "binary_id": sha,
            "function_id": _ghidra_func_id(sha, 0x0),
            "entry_va": 0x0,
            "entry_hex": "0x0",
            "name": "printf",
            "namespace": None,
            "body_start_va": None,
            "body_end_va": None,
            "size_bytes": None,
            "is_external_block": True,
            "is_thunk": False,
            "is_import": True,
            "section_hint": None,
            "decompile_status": "FAIL",
            "c_raw": "",
            "warnings": [],
            "warnings_raw": [],
            "verdict": "FAIL",
            "is_plt_or_stub": False,
            "is_init_fini_aux": False,
            "is_compiler_aux": False,
            "is_library_like": True,
            "asm_insn_count": 0,
            "c_line_count": 0,
            "insn_to_c_ratio": 0.0,
            "temp_var_count": 0,
            "fat_function_flag": False,
        },
        {
            # Aux function
            "binary_id": sha,
            "function_id": _ghidra_func_id(sha, 0x400800),
            "entry_va": 0x400800,
            "entry_hex": "0x400800",
            "name": "frame_dummy",
            "namespace": None,
            "body_start_va": 0x400800,
            "body_end_va": 0x400820,
            "size_bytes": 0x20,
            "is_external_block": False,
            "is_thunk": False,
            "is_import": False,
            "section_hint": ".text",
            "decompile_status": "OK",
            "c_raw": "void frame_dummy(void) { return; }\n",
            "warnings": [],
            "warnings_raw": [],
            "verdict": "OK",
            "is_plt_or_stub": False,
            "is_init_fini_aux": False,
            "is_compiler_aux": True,
            "is_library_like": True,
            "asm_insn_count": 3,
            "c_line_count": 1,
            "insn_to_c_ratio": 3.0,
            "temp_var_count": 0,
            "fat_function_flag": False,
        },
    ]


@pytest.fixture
def ghidra_variables() -> List[dict]:
    sha = TEST_SHA256
    return [
        {
            "binary_id": sha,
            "function_id": _ghidra_func_id(sha, 0x401030),
            "entry_va": 0x401030,
            "var_id": f"{_ghidra_func_id(sha, 0x401030)}:LOCAL:stack:off:-0x10:sig1",
            "var_kind": "LOCAL",
            "name": "result",
            "type_str": "int",
            "size_bytes": 4,
            "storage_class": "STACK",
            "storage_key": "stack:off:-0x10",
            "stack_offset": -16,
            "register_name": None,
            "addr_va": None,
            "is_temp_singleton": False,
            "access_sites": [0x401035, 0x401040],
            "access_sites_truncated": False,
            "access_sig": "abcd1234abcd1234",
        },
        {
            "binary_id": sha,
            "function_id": _ghidra_func_id(sha, 0x401080),
            "entry_va": 0x401080,
            "var_id": f"{_ghidra_func_id(sha, 0x401080)}:TEMP:uniq:uVar1:sig2",
            "var_kind": "TEMP",
            "name": "uVar1",
            "type_str": "undefined4",
            "size_bytes": 4,
            "storage_class": "UNIQUE",
            "storage_key": "uniq:uVar1",
            "stack_offset": None,
            "register_name": None,
            "addr_va": None,
            "is_temp_singleton": True,
            "access_sites": [0x401085],
            "access_sites_truncated": False,
            "access_sig": "ef561234ef561234",
        },
    ]


@pytest.fixture
def ghidra_cfg() -> List[dict]:
    sha = TEST_SHA256
    return [
        {
            "binary_id": sha,
            "function_id": _ghidra_func_id(sha, 0x401000),
            "entry_va": 0x401000,
            "bb_count": 1,
            "edge_count": 0,
            "cyclomatic": 1,
            "has_indirect_jumps": False,
            "unresolved_indirect_jump_count": 0,
            "cfg_completeness": "HIGH",
            "blocks": [{"block_id": 0, "start_va": 0x401000, "end_va": 0x401030, "succ": []}],
        },
        {
            "binary_id": sha,
            "function_id": _ghidra_func_id(sha, 0x401030),
            "entry_va": 0x401030,
            "bb_count": 3,
            "edge_count": 3,
            "cyclomatic": 2,
            "has_indirect_jumps": False,
            "unresolved_indirect_jump_count": 0,
            "cfg_completeness": "HIGH",
            "blocks": [
                {"block_id": 0, "start_va": 0x401030, "end_va": 0x401040, "succ": [1]},
                {"block_id": 1, "start_va": 0x401040, "end_va": 0x401060, "succ": [1, 2]},
                {"block_id": 2, "start_va": 0x401060, "end_va": 0x401085, "succ": []},
            ],
        },
        {
            "binary_id": sha,
            "function_id": _ghidra_func_id(sha, 0x401080),
            "entry_va": 0x401080,
            "bb_count": 2,
            "edge_count": 1,
            "cyclomatic": 1,
            "has_indirect_jumps": False,
            "unresolved_indirect_jump_count": 0,
            "cfg_completeness": "MEDIUM",
            "blocks": [
                {"block_id": 0, "start_va": 0x401080, "end_va": 0x4010b0, "succ": [1]},
                {"block_id": 1, "start_va": 0x4010b0, "end_va": 0x4010f0, "succ": []},
            ],
        },
    ]


@pytest.fixture
def ghidra_calls() -> List[dict]:
    sha = TEST_SHA256
    return [
        {
            "binary_id": sha,
            "caller_function_id": _ghidra_func_id(sha, 0x401030),
            "caller_entry_va": 0x401030,
            "callsite_va": 0x401050,
            "callsite_hex": "0x401050",
            "call_kind": "DIRECT",
            "callee_entry_va": 0x401000,
            "callee_name": "FUN_00401000",
            "is_external_target": False,
            "is_import_proxy_target": False,
        },
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# Filesystem helpers — write fixtures to temp dirs
# ═══════════════════════════════════════════════════════════════════════════════

def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


@pytest.fixture
def fixture_dirs(
    tmp_path: Path,
    build_receipt,
    oracle_report,
    oracle_functions,
    alignment_report,
    alignment_pairs,
    ghidra_report,
    ghidra_functions,
    ghidra_variables,
    ghidra_cfg,
    ghidra_calls,
) -> Dict[str, Path]:
    """Write all fixtures to a temp directory tree and return paths."""
    base = tmp_path / "math_recurse" / "O0" / "stripped"

    # Receipt is at test_case level
    receipt_path = tmp_path / "math_recurse" / "build_receipt.json"
    _write_json(receipt_path, build_receipt)

    # Oracle
    oracle_dir = base / "oracle"
    _write_json(oracle_dir / "oracle_report.json", oracle_report)
    _write_json(oracle_dir / "oracle_functions.json", oracle_functions)

    # Alignment
    align_dir = base / "join_dwarf_ts"
    _write_json(align_dir / "alignment_report.json", alignment_report)
    _write_json(align_dir / "alignment_pairs.json", alignment_pairs)

    # Ghidra
    ghidra_dir = base / "ghidra_decompile"
    _write_json(ghidra_dir / "report.json", ghidra_report)
    _write_jsonl(ghidra_dir / "functions.jsonl", ghidra_functions)
    _write_jsonl(ghidra_dir / "variables.jsonl", ghidra_variables)
    _write_jsonl(ghidra_dir / "cfg.jsonl", ghidra_cfg)
    _write_jsonl(ghidra_dir / "calls.jsonl", ghidra_calls)

    # Output dir
    output_dir = base / "join_oracles_ghidra"

    return {
        "receipt_path": receipt_path,
        "oracle_dir": oracle_dir,
        "alignment_dir": align_dir,
        "ghidra_dir": ghidra_dir,
        "output_dir": output_dir,
        "tmp_path": tmp_path,
    }
