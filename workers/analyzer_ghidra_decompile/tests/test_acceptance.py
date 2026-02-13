"""
Acceptance tests for analyzer_ghidra_decompile (§13).

These tests use synthetic raw JSONL fixtures (no Ghidra required).
They verify the Python processing pipeline: parsing, schema validation,
verdicts, noise classification, determinism, and output contracts.
"""
import json
from pathlib import Path

import pytest

from analyzer_ghidra_decompile.core.call_processor import process_calls
from analyzer_ghidra_decompile.core.cfg_processor import compute_cfg_completeness, process_cfg
from analyzer_ghidra_decompile.core.function_processor import (
    compute_fat_function_flag,
    compute_inline_likely,
    compute_proxy_metrics,
    is_temp_name,
    map_warnings,
    normalize_address,
)
from analyzer_ghidra_decompile.core.raw_parser import parse_raw_jsonl
from analyzer_ghidra_decompile.core.variable_processor import (
    build_var_id,
    classify_var_kind,
    compute_access_sig,
    compute_storage_key,
    is_temp_singleton,
    process_variables,
)
from analyzer_ghidra_decompile.io.schema import (
    GhidraCallEntry,
    GhidraCfgEntry,
    GhidraFunctionEntry,
    GhidraReport,
    GhidraVariableEntry,
)
from analyzer_ghidra_decompile.io.writer import write_outputs
from analyzer_ghidra_decompile.policy.noise import classify_noise
from analyzer_ghidra_decompile.policy.profile import Profile
from analyzer_ghidra_decompile.policy.verdict import (
    DecompileStatus,
    FunctionVerdict,
    gate_binary,
    judge_function,
)
from analyzer_ghidra_decompile.tests.conftest import write_fixture_jsonl


# ═══════════════════════════════════════════════════════════════════════════════
# §13.1 — Raw parser
# ═══════════════════════════════════════════════════════════════════════════════

class TestRawParser:
    """Test raw JSONL parsing."""

    def test_parse_fixture(self, fixture_raw_jsonl):
        """Fixture JSONL parses without error."""
        summary, functions = parse_raw_jsonl(fixture_raw_jsonl)
        assert summary.total_functions == 5
        assert len(functions) == 5

    def test_sorted_by_entry_va(self, fixture_raw_jsonl):
        """Functions are sorted by entry_va ascending (§11)."""
        _, functions = parse_raw_jsonl(fixture_raw_jsonl)
        entry_vas = [f.entry_va for f in functions]
        assert entry_vas == sorted(entry_vas)

    def test_summary_fields(self, fixture_raw_jsonl):
        """Summary has expected provenance fields."""
        summary, _ = parse_raw_jsonl(fixture_raw_jsonl)
        assert summary.ghidra_version == "12.0.3"
        assert summary.java_version == "21.0.10"

    def test_missing_file_raises(self, tmp_path):
        """Missing JSONL file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            parse_raw_jsonl(tmp_path / "nonexistent.jsonl")


# ═══════════════════════════════════════════════════════════════════════════════
# Address normalization
# ═══════════════════════════════════════════════════════════════════════════════

class TestAddressNormalization:
    def test_normalize_with_prefix(self):
        va, hex_str = normalize_address("0x00101159")
        assert va == 0x101159
        assert hex_str == "0x101159"

    def test_normalize_without_prefix(self):
        va, hex_str = normalize_address("00101159")
        assert va == 0x101159
        assert hex_str == "0x101159"

    def test_canonical_lowercase(self):
        _, hex_str = normalize_address("0x0010ABCD")
        assert hex_str == "0x10abcd"


# ═══════════════════════════════════════════════════════════════════════════════
# Warning mapping
# ═══════════════════════════════════════════════════════════════════════════════

class TestWarningMapping:
    def test_unknown_calling_convention(self):
        warnings, _ = map_warnings(
            None, None, ["Unknown calling convention: __stdcall"]
        )
        assert "UNKNOWN_CALLING_CONVENTION" in warnings

    def test_unreachable_blocks(self):
        warnings, _ = map_warnings(
            None, None, ["Removing unreachable block at 0x1234"]
        )
        assert "UNREACHABLE_BLOCKS_REMOVED" in warnings

    def test_fallback_bucket(self):
        warnings, _ = map_warnings(
            None, None, ["Some unknown Ghidra message"]
        )
        assert "DECOMPILER_INTERNAL_WARNING" in warnings

    def test_empty_warnings(self):
        warnings, raw = map_warnings(None, None, [])
        assert warnings == []
        assert raw == []

    def test_dedup(self):
        warnings, _ = map_warnings(None, None, [
            "Unknown calling convention: X",
            "Unknown calling convention: Y",
        ])
        assert warnings.count("UNKNOWN_CALLING_CONVENTION") == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Noise classification
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoiseClassification:
    def test_plt_stub(self):
        plt, init, comp, lib = classify_noise(
            "printf", ".plt", False, False, False
        )
        assert plt is True
        assert lib is True

    def test_init_fini(self):
        _, init, _, lib = classify_noise(
            "_init", ".init", False, False, False
        )
        assert init is True
        assert lib is True

    def test_compiler_aux(self):
        _, _, comp, lib = classify_noise(
            "frame_dummy", ".text", False, False, False
        )
        assert comp is True
        assert lib is True

    def test_normal_function(self):
        plt, init, comp, lib = classify_noise(
            "main", ".text", False, False, False
        )
        assert plt is False
        assert init is False
        assert comp is False
        assert lib is False

    def test_external_is_library(self):
        _, _, _, lib = classify_noise(
            "some_func", ".text", True, False, False
        )
        assert lib is True


# ═══════════════════════════════════════════════════════════════════════════════
# Variable processing
# ═══════════════════════════════════════════════════════════════════════════════

class TestVariableProcessing:
    def test_classify_param(self):
        assert classify_var_kind(True, "REGISTER", "param_1", None) == "PARAM"

    def test_classify_global_ref(self):
        assert classify_var_kind(False, "MEMORY", "g_var", 0x404000) == "GLOBAL_REF"

    def test_classify_temp(self):
        assert classify_var_kind(False, "UNIQUE", "uVar1", None) == "TEMP"

    def test_classify_local(self):
        assert classify_var_kind(False, "STACK", "local_c", None) == "LOCAL"

    def test_storage_key_stack(self):
        key = compute_storage_key("STACK", -16, None, None, "local_c")
        assert key == "stack:off:-0x10"

    def test_storage_key_register(self):
        key = compute_storage_key("REGISTER", None, "RDI", None, "param_1")
        assert key == "reg:RDI"

    def test_storage_key_memory(self):
        key = compute_storage_key("MEMORY", None, None, 0x404000, "g_var")
        assert key == "mem:0x404000"

    def test_storage_key_unique(self):
        key = compute_storage_key("UNIQUE", None, None, None, "uVar1")
        assert key == "uniq:uVar1"

    def test_storage_key_unknown(self):
        key = compute_storage_key("UNKNOWN", None, None, None, "mystery")
        assert key == "unk:mystery"

    def test_access_sig_deterministic(self):
        sig1 = compute_access_sig([100, 200, 300], "reg:RDI")
        sig2 = compute_access_sig([300, 100, 200], "reg:RDI")
        assert sig1 == sig2  # sorted internally
        assert len(sig1) == 16

    def test_access_sig_fallback(self):
        sig = compute_access_sig([], "reg:RDI")
        assert len(sig) == 16

    def test_var_id_format(self):
        vid = build_var_id("sha:123", "PARAM", "reg:RDI", "abc123")
        assert vid == "sha:123:PARAM:reg:RDI:abc123"

    def test_temp_singleton(self):
        assert is_temp_singleton("uVar1", "TEMP", "UNIQUE") is True
        assert is_temp_singleton("local_c", "LOCAL", "STACK") is False


# ═══════════════════════════════════════════════════════════════════════════════
# CFG processing
# ═══════════════════════════════════════════════════════════════════════════════

class TestCfgProcessing:
    def test_cfg_completeness_high(self):
        assert compute_cfg_completeness([]) == "HIGH"

    def test_cfg_completeness_medium(self):
        assert compute_cfg_completeness(["UNREACHABLE_BLOCKS_REMOVED"]) == "MEDIUM"

    def test_cfg_completeness_low(self):
        assert compute_cfg_completeness(["UNRESOLVED_INDIRECT_JUMP"]) == "LOW"

    def test_process_cfg_basic(self, fixture_raw_jsonl):
        _, functions = parse_raw_jsonl(fixture_raw_jsonl)
        func = functions[0]
        result = process_cfg(func.blocks, [])
        assert isinstance(result["bb_count"], int)
        assert isinstance(result["edge_count"], int)
        assert result["bb_count"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Proxy metrics
# ═══════════════════════════════════════════════════════════════════════════════

class TestProxyMetrics:
    def test_compute_proxy_metrics(self):
        m = compute_proxy_metrics("int main() {\n  return 0;\n}\n", 15, 3)
        assert m["asm_insn_count"] == 15
        assert m["c_line_count"] == 3
        assert m["insn_to_c_ratio"] == 5.0

    def test_temp_name_detection(self):
        assert is_temp_name("uVar1") is True
        assert is_temp_name("iVar23") is True
        assert is_temp_name("local_c") is False
        assert is_temp_name("param_1") is False

    def test_fat_function_flag(self):
        profile = Profile.v1()
        assert compute_fat_function_flag(
            1000, 10, 5, 2.0, 500, profile
        ) is True  # size > p90

        assert compute_fat_function_flag(
            100, 100, 5, 2.0, 500, profile
        ) is True  # bb > threshold

        assert compute_fat_function_flag(
            100, 10, 5, 2.0, 500, profile
        ) is False  # nothing exceeds


# ═══════════════════════════════════════════════════════════════════════════════
# Verdict
# ═══════════════════════════════════════════════════════════════════════════════

class TestVerdict:
    def test_binary_gate_accept(self):
        profile = Profile.v1()
        v, reasons = gate_binary(True, "EM_X86_64", None, None, None, profile)
        assert v.value == "ACCEPT"

    def test_binary_gate_reject_not_elf(self):
        profile = Profile.v1()
        v, reasons = gate_binary(False, None, None, "bad file", None, profile)
        assert v.value == "REJECT"
        assert "NOT_ELF" in reasons

    def test_binary_gate_warn_high_fail_rate(self):
        profile = Profile.v1()
        v, reasons = gate_binary(
            True, "EM_X86_64", None, None,
            {"total_functions": 10, "decompile_fail": 5},
            profile,
        )
        assert v.value == "WARN"
        assert "HIGH_DECOMPILE_FAIL_RATE" in reasons

    def test_function_verdict_ok(self):
        v, r = judge_function("OK", [], 0x100, 0x200, False)
        assert v == FunctionVerdict.OK

    def test_function_verdict_fail_no_decompile(self):
        v, r = judge_function("FAIL", [], 0x100, 0x200, False)
        assert v == FunctionVerdict.FAIL

    def test_function_verdict_fail_no_body(self):
        v, r = judge_function("OK", [], None, None, False)
        assert v == FunctionVerdict.FAIL

    def test_function_verdict_warn_noise(self):
        v, r = judge_function("OK", [], 0x100, 0x200, True)
        assert v == FunctionVerdict.WARN


# ═══════════════════════════════════════════════════════════════════════════════
# §13 — End-to-end acceptance (synthetic fixture)
# ═══════════════════════════════════════════════════════════════════════════════

class TestEndToEnd:
    """Full pipeline test using synthetic raw JSONL (no Ghidra needed)."""

    def _run_pipeline(self, fixture_raw_jsonl, fixture_elf, tmp_output_dir):
        """Run the processing pipeline on fixtures."""
        from analyzer_ghidra_decompile.runner import run_ghidra_decompile

        report, funcs, var_list, cfg_list, calls = run_ghidra_decompile(
            binary_path=str(fixture_elf),
            raw_jsonl_path=str(fixture_raw_jsonl),
            output_dir=tmp_output_dir,
        )
        return report, funcs, var_list, cfg_list, calls

    def test_report_exists(self, fixture_raw_jsonl, fixture_elf, tmp_output_dir):
        """§13.1: report.json exists and verdict != REJECT."""
        report, *_ = self._run_pipeline(
            fixture_raw_jsonl, fixture_elf, tmp_output_dir
        )
        assert (tmp_output_dir / "report.json").exists()
        assert report.binary_verdict != "REJECT"

    def test_functions_non_empty_sorted(
        self, fixture_raw_jsonl, fixture_elf, tmp_output_dir
    ):
        """§13.2: functions.jsonl non-empty and sorted by entry_va."""
        _, funcs, *_ = self._run_pipeline(
            fixture_raw_jsonl, fixture_elf, tmp_output_dir
        )
        assert len(funcs) > 0
        assert (tmp_output_dir / "functions.jsonl").exists()
        entry_vas = [f.entry_va for f in funcs]
        assert entry_vas == sorted(entry_vas)

    def test_function_records_valid(
        self, fixture_raw_jsonl, fixture_elf, tmp_output_dir
    ):
        """§13.3: Every function has valid function_id, entry_va, decompile_status, verdict."""
        _, funcs, *_ = self._run_pipeline(
            fixture_raw_jsonl, fixture_elf, tmp_output_dir
        )
        for f in funcs:
            assert f.function_id
            assert ":" in f.function_id
            assert isinstance(f.entry_va, int)
            assert f.decompile_status in ("OK", "FAIL")
            assert f.verdict in ("OK", "WARN", "FAIL")

    def test_variables_valid(
        self, fixture_raw_jsonl, fixture_elf, tmp_output_dir
    ):
        """§13.4: variables reference valid function_ids, have storage_key + access_sig."""
        _, funcs, var_list, *_ = self._run_pipeline(
            fixture_raw_jsonl, fixture_elf, tmp_output_dir
        )
        func_ids = {f.function_id for f in funcs}
        for v in var_list:
            assert v.function_id in func_ids
            assert v.storage_key
            assert v.access_sig
            assert len(v.access_sig) == 16

    def test_cfg_valid(
        self, fixture_raw_jsonl, fixture_elf, tmp_output_dir
    ):
        """§13.5: bb_count and edge_count are ints, block edges reference declared block_ids."""
        _, funcs, _, cfg_list, _ = self._run_pipeline(
            fixture_raw_jsonl, fixture_elf, tmp_output_dir
        )
        for cfg in cfg_list:
            assert isinstance(cfg.bb_count, int)
            assert isinstance(cfg.edge_count, int)
            block_ids = {b.block_id for b in cfg.blocks}
            for b in cfg.blocks:
                for s in b.succ:
                    assert s in block_ids

    def test_calls_sorted_valid(
        self, fixture_raw_jsonl, fixture_elf, tmp_output_dir
    ):
        """§13.6: calls sorted, caller ids valid."""
        _, funcs, _, _, calls = self._run_pipeline(
            fixture_raw_jsonl, fixture_elf, tmp_output_dir
        )
        func_ids = {f.function_id for f in funcs}
        for c in calls:
            assert c.caller_function_id in func_ids

        # Sorted by (caller_entry_va, callsite_va)
        if calls:
            keys = [(c.caller_entry_va, c.callsite_va) for c in calls]
            assert keys == sorted(keys)

    def test_all_output_files_exist(
        self, fixture_raw_jsonl, fixture_elf, tmp_output_dir
    ):
        """All five output files are created."""
        self._run_pipeline(fixture_raw_jsonl, fixture_elf, tmp_output_dir)
        expected = [
            "report.json",
            "functions.jsonl",
            "variables.jsonl",
            "cfg.jsonl",
            "calls.jsonl",
        ]
        for name in expected:
            assert (tmp_output_dir / name).exists(), f"Missing: {name}"

    def test_determinism(
        self, fixture_raw_jsonl, fixture_elf, tmp_path
    ):
        """§11: Processing same raw JSONL twice produces identical content."""
        from analyzer_ghidra_decompile.runner import run_ghidra_decompile

        dir1 = tmp_path / "run1"
        dir2 = tmp_path / "run2"

        run_ghidra_decompile(
            binary_path=str(fixture_elf),
            raw_jsonl_path=str(fixture_raw_jsonl),
            output_dir=dir1,
        )
        run_ghidra_decompile(
            binary_path=str(fixture_elf),
            raw_jsonl_path=str(fixture_raw_jsonl),
            output_dir=dir2,
        )

        # Compare all JSONL files (report.json has timestamp, so skip it)
        for name in ("functions.jsonl", "variables.jsonl", "cfg.jsonl", "calls.jsonl"):
            content1 = (dir1 / name).read_text()
            content2 = (dir2 / name).read_text()
            assert content1 == content2, f"Non-deterministic output in {name}"

    def test_noise_flags_set(
        self, fixture_raw_jsonl, fixture_elf, tmp_output_dir
    ):
        """Noise functions are correctly flagged."""
        _, funcs, *_ = self._run_pipeline(
            fixture_raw_jsonl, fixture_elf, tmp_output_dir
        )
        func_by_name = {f.name: f for f in funcs}

        # _init should be flagged as init_fini_aux
        if "_init" in func_by_name:
            assert func_by_name["_init"].is_init_fini_aux is True
            assert func_by_name["_init"].is_library_like is True

        # printf (plt stub) should be flagged
        if "printf" in func_by_name:
            assert func_by_name["printf"].is_plt_or_stub is True
            assert func_by_name["printf"].is_library_like is True

        # main should NOT be noise
        if "main" in func_by_name:
            assert func_by_name["main"].is_library_like is False

    def test_report_counts(
        self, fixture_raw_jsonl, fixture_elf, tmp_output_dir
    ):
        """Report summary counts are consistent."""
        report, funcs, *_ = self._run_pipeline(
            fixture_raw_jsonl, fixture_elf, tmp_output_dir
        )
        c = report.function_counts
        assert c.n_functions_total == len(funcs)
        assert c.n_functions_ok + c.n_functions_warn + c.n_functions_fail == c.n_functions_total
