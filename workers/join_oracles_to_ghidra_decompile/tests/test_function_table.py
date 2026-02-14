"""Tests for core.function_table — Stages 1 + 2."""
from __future__ import annotations

from join_oracles_to_ghidra_decompile.core.function_table import (
    DwarfFunctionRow,
    GhidraFunctionRow,
    build_dwarf_function_table,
    build_ghidra_function_table,
)
from join_oracles_to_ghidra_decompile.tests.conftest import TEST_SHA256


class TestDwarfFunctionTable:
    """Stage 1: DWARF function table construction."""

    def test_table_size(self, oracle_functions, alignment_pairs):
        table = build_dwarf_function_table(oracle_functions, alignment_pairs)
        assert len(table) == 4  # 2 ACCEPT + 1 WARN + 1 REJECT

    def test_accept_function_ranges_parsed(self, oracle_functions, alignment_pairs):
        table = build_dwarf_function_table(oracle_functions, alignment_pairs)
        row = table["cu0:0x100"]

        assert isinstance(row, DwarfFunctionRow)
        assert row.has_range is True
        assert row.low_pc == 0x401000
        assert row.high_pc == 0x401030
        assert row.total_range_bytes == 0x30

    def test_reject_no_range(self, oracle_functions, alignment_pairs):
        table = build_dwarf_function_table(oracle_functions, alignment_pairs)
        row = table["cu0:0x400"]

        assert row.has_range is False
        assert row.oracle_verdict == "REJECT"
        assert row.is_non_target is True

    def test_alignment_match_evidence(self, oracle_functions, alignment_pairs):
        table = build_dwarf_function_table(oracle_functions, alignment_pairs)
        row = table["cu0:0x100"]

        assert row.align_verdict == "MATCH"
        assert row.align_overlap_ratio == 1.0
        assert row.align_n_candidates == 1
        assert row.quality_weight == 1.0  # 1.0 / 1

    def test_alignment_ambiguous(self, oracle_functions, alignment_pairs):
        table = build_dwarf_function_table(oracle_functions, alignment_pairs)
        row = table["cu0:0x300"]

        assert row.align_verdict == "AMBIGUOUS"
        assert row.align_n_candidates == 2
        assert row.quality_weight == 0.0  # Not MATCH → 0

    def test_fragmented_ranges(self, oracle_functions, alignment_pairs):
        table = build_dwarf_function_table(oracle_functions, alignment_pairs)
        row = table["cu0:0x300"]

        # Two ranges: [0x401080, 0x4010a0) and [0x4010c0, 0x4010e0)
        assert len(row.ranges) == 2
        assert row.total_range_bytes == 0x20 + 0x20  # 32 + 32 = 64

    def test_name_normalization(self, oracle_functions, alignment_pairs):
        table = build_dwarf_function_table(oracle_functions, alignment_pairs)
        assert table["cu0:0x100"].name_norm == "add"
        assert table["cu0:0x200"].name_norm == "multiply"
        assert table["cu0:0x400"].name_norm is None  # name was None

    def test_all_functions_preserved(self, oracle_functions, alignment_pairs):
        """All DWARF functions including REJECT must be in the table."""
        table = build_dwarf_function_table(oracle_functions, alignment_pairs)
        verdicts = {r.oracle_verdict for r in table.values()}
        assert "ACCEPT" in verdicts
        assert "WARN" in verdicts
        assert "REJECT" in verdicts


class TestGhidraFunctionTable:
    """Stage 2: Ghidra function table construction."""

    def test_table_size(self, ghidra_functions, ghidra_cfg, ghidra_variables):
        table, idx = build_ghidra_function_table(
            ghidra_functions, ghidra_cfg, ghidra_variables,
        )
        assert len(table) == 5

    def test_interval_index_excludes_no_body(
        self, ghidra_functions, ghidra_cfg, ghidra_variables,
    ):
        """External func with body_start_va=None should not be in index."""
        table, idx = build_ghidra_function_table(
            ghidra_functions, ghidra_cfg, ghidra_variables,
        )
        # 4 functions have body ranges, 1 external does not
        assert len(idx) == 4

    def test_interval_index_sorted(
        self, ghidra_functions, ghidra_cfg, ghidra_variables,
    ):
        _, idx = build_ghidra_function_table(
            ghidra_functions, ghidra_cfg, ghidra_variables,
        )
        starts = [e.body_start for e in idx]
        assert starts == sorted(starts)

    def test_cfg_merge(self, ghidra_functions, ghidra_cfg, ghidra_variables):
        table, _ = build_ghidra_function_table(
            ghidra_functions, ghidra_cfg, ghidra_variables,
        )
        sha = TEST_SHA256
        fid = f"{sha}:{0x401030}"
        row = table[fid]
        assert row.bb_count == 3
        assert row.edge_count == 3
        assert row.cfg_completeness == "HIGH"

    def test_goto_count(self, ghidra_functions, ghidra_cfg, ghidra_variables):
        table, _ = build_ghidra_function_table(
            ghidra_functions, ghidra_cfg, ghidra_variables,
        )
        sha = TEST_SHA256
        # FUN_00401080 has "goto LAB_1" in its c_raw
        fid = f"{sha}:{0x401080}"
        row = table[fid]
        assert row.goto_count == 1
        assert row.goto_density > 0

    def test_variable_stats(self, ghidra_functions, ghidra_cfg, ghidra_variables):
        table, _ = build_ghidra_function_table(
            ghidra_functions, ghidra_cfg, ghidra_variables,
        )
        sha = TEST_SHA256
        fid = f"{sha}:{0x401080}"
        row = table[fid]
        # One TEMP variable with type "undefined4"
        assert row.total_vars_in_func == 1
        assert row.placeholder_type_rate == 1.0  # 1 placeholder / 1 total


class TestGhidraImageBaseRebase:
    """Verify that build_ghidra_function_table subtracts image_base from VAs."""

    IMAGE_BASE = 0x100000

    def _make_func(self, entry_va, body_start, body_end, name="FUN"):
        sha = TEST_SHA256
        return {
            "binary_id": sha,
            "function_id": f"{sha}:{entry_va}",
            "entry_va": entry_va,
            "entry_hex": hex(entry_va),
            "name": name,
            "namespace": None,
            "body_start_va": body_start,
            "body_end_va": body_end,
            "size_bytes": body_end - body_start if body_end and body_start else None,
            "is_external_block": False,
            "is_thunk": False,
            "is_import": False,
            "section_hint": ".text",
            "decompile_status": "OK",
            "c_raw": "void f(void){}\n",
            "warnings": [],
            "warnings_raw": [],
            "verdict": "OK",
            "is_plt_or_stub": False,
            "is_init_fini_aux": False,
            "is_compiler_aux": False,
            "is_library_like": False,
            "asm_insn_count": 5,
            "c_line_count": 1,
            "insn_to_c_ratio": 5.0,
            "temp_var_count": 0,
            "fat_function_flag": False,
        }

    def test_rebase_subtracts_image_base(self):
        """entry_va, body_start_va, body_end_va should all be rebased."""
        raw_entry = 0x100000 + 0x1159
        raw_start = 0x100000 + 0x1159
        raw_end   = 0x100000 + 0x119E
        funcs = [self._make_func(raw_entry, raw_start, raw_end, "array_sum")]

        table, idx = build_ghidra_function_table(
            funcs, [], [], image_base=self.IMAGE_BASE,
        )

        fid = f"{TEST_SHA256}:{raw_entry}"
        row = table[fid]
        assert row.entry_va == 0x1159
        assert row.body_start_va == 0x1159
        assert row.body_end_va == 0x119E

    def test_rebase_interval_index(self):
        """Interval index entries should use rebased addresses."""
        raw_start = 0x100000 + 0x1159
        raw_end   = 0x100000 + 0x119E
        funcs = [self._make_func(raw_start, raw_start, raw_end)]

        _, idx = build_ghidra_function_table(
            funcs, [], [], image_base=self.IMAGE_BASE,
        )

        assert len(idx) == 1
        assert idx[0].body_start == 0x1159
        assert idx[0].body_end == 0x119E

    def test_zero_image_base_is_noop(self):
        """image_base=0 must leave addresses unchanged."""
        entry = 0x1159
        funcs = [self._make_func(entry, entry, 0x119E)]

        table, idx = build_ghidra_function_table(
            funcs, [], [], image_base=0,
        )

        fid = f"{TEST_SHA256}:{entry}"
        assert table[fid].entry_va == 0x1159
        assert idx[0].body_start == 0x1159

    def test_default_image_base_is_zero(self):
        """Omitting image_base should default to 0 (no rebase)."""
        entry = 0x401000
        funcs = [self._make_func(entry, entry, 0x401030)]

        table, _ = build_ghidra_function_table(funcs, [], [])

        fid = f"{TEST_SHA256}:{entry}"
        assert table[fid].entry_va == 0x401000

    def test_external_func_no_body_rebased(self):
        """External func with body=None: entry_va still rebased, no crash."""
        raw_entry = 0x100000
        funcs = [{
            "binary_id": TEST_SHA256,
            "function_id": f"{TEST_SHA256}:{raw_entry}",
            "entry_va": raw_entry,
            "entry_hex": hex(raw_entry),
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
        }]

        table, idx = build_ghidra_function_table(
            funcs, [], [], image_base=self.IMAGE_BASE,
        )

        fid = f"{TEST_SHA256}:{raw_entry}"
        assert table[fid].entry_va == 0  # 0x100000 - 0x100000
        assert table[fid].body_start_va is None  # still None
        assert len(idx) == 0  # no body → no interval entry
