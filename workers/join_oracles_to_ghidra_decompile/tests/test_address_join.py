"""Tests for core.address_join — Stage 3."""
from __future__ import annotations

import pytest

from join_oracles_to_ghidra_decompile.core.address_join import (
    JoinResult,
    join_dwarf_to_ghidra,
)
from join_oracles_to_ghidra_decompile.core.function_table import (
    DwarfFunctionRow,
    GhidraFunctionRow,
    IntervalEntry,
    build_dwarf_function_table,
    build_ghidra_function_table,
)
from join_oracles_to_ghidra_decompile.policy.profile import (
    JoinOraclesGhidraProfile,
)
from join_oracles_to_ghidra_decompile.tests.conftest import TEST_SHA256


@pytest.fixture
def profile():
    return JoinOraclesGhidraProfile.v1()


@pytest.fixture
def tables(oracle_functions, alignment_pairs, ghidra_functions, ghidra_cfg, ghidra_variables):
    dwarf_table = build_dwarf_function_table(oracle_functions, alignment_pairs)
    ghidra_table, interval_index = build_ghidra_function_table(
        ghidra_functions, ghidra_cfg, ghidra_variables,
    )
    return dwarf_table, ghidra_table, interval_index


class TestAddressJoin:
    """Primary address-overlap join."""

    def test_result_count(self, tables, profile):
        dt, gt, idx = tables
        results = join_dwarf_to_ghidra(dt, gt, idx, profile)
        # 4 DWARF functions → 4 results
        assert len(results) == 4

    def test_exact_overlap_joined_strong(self, tables, profile):
        """add: DWARF [0x401000, 0x401030) == Ghidra [0x401000, 0x401030)."""
        dt, gt, idx = tables
        results = join_dwarf_to_ghidra(dt, gt, idx, profile)

        by_fid = {r.dwarf.function_id: r for r in results}
        r = by_fid["cu0:0x100"]
        assert r.match_kind == "JOINED_STRONG"
        assert r.pc_overlap_ratio == pytest.approx(1.0)
        assert r.ghidra_entry_va == 0x401000

    def test_partial_overlap_joined(self, tables, profile):
        """multiply: DWARF [0x401030, 0x401080) overlaps Ghidra [0x401030, 0x401085)."""
        dt, gt, idx = tables
        results = join_dwarf_to_ghidra(dt, gt, idx, profile)

        by_fid = {r.dwarf.function_id: r for r in results}
        r = by_fid["cu0:0x200"]
        # Overlap = 0x401080 - 0x401030 = 0x50 = 80 bytes
        # DWARF range = 0x401080 - 0x401030 = 0x50 = 80 bytes
        # Ratio = 80/80 = 1.0 (Ghidra extends past, but overlap covers full DWARF)
        assert r.match_kind == "JOINED_STRONG"
        assert r.ghidra_entry_va == 0x401030

    def test_no_range_not_fabricated(self, tables, profile):
        """REJECT function with no ranges → NO_RANGE, no ghidra join."""
        dt, gt, idx = tables
        results = join_dwarf_to_ghidra(dt, gt, idx, profile)

        by_fid = {r.dwarf.function_id: r for r in results}
        r = by_fid["cu0:0x400"]
        assert r.match_kind == "NO_RANGE"
        assert r.ghidra_func_id is None
        assert r.ghidra_entry_va is None

    def test_fragmented_dwarf_ranges(self, tables, profile):
        """helper: two DWARF ranges overlapping one Ghidra function."""
        dt, gt, idx = tables
        results = join_dwarf_to_ghidra(dt, gt, idx, profile)

        by_fid = {r.dwarf.function_id: r for r in results}
        r = by_fid["cu0:0x300"]
        # Ghidra func at 0x401080 with body [0x401080, 0x4010f0)
        # DWARF ranges: [0x401080, 0x4010a0) and [0x4010c0, 0x4010e0)
        # Overlap1 = [0x401080, 0x4010a0) = 0x20 = 32 bytes
        # Overlap2 = [0x4010c0, 0x4010e0) = 0x20 = 32 bytes
        # Total = 64 bytes, DWARF total = 64 bytes → ratio = 1.0
        assert r.match_kind == "JOINED_STRONG"
        assert r.pc_overlap_bytes == 64
        assert r.ghidra_entry_va == 0x401080


class TestAddressJoinEdgeCases:
    """Edge cases for the join logic."""

    def test_no_ghidra_functions(self, profile):
        """Empty Ghidra table → all NO_MATCH."""
        dwarf_table = {
            "f1": DwarfFunctionRow(
                function_id="f1",
                ranges=[(0x1000, 0x2000)],
                total_range_bytes=0x1000,
                has_range=True,
                low_pc=0x1000,
                high_pc=0x2000,
                oracle_verdict="ACCEPT",
            ),
        }
        results = join_dwarf_to_ghidra(dwarf_table, {}, [], profile)
        assert len(results) == 1
        assert results[0].match_kind == "NO_MATCH"

    def test_near_tie_multi_match(self, profile):
        """Two Ghidra funcs with very similar overlap → MULTI_MATCH."""
        dwarf_table = {
            "f1": DwarfFunctionRow(
                function_id="f1",
                ranges=[(0x1000, 0x1100)],
                total_range_bytes=0x100,
                has_range=True,
                low_pc=0x1000,
                high_pc=0x1100,
                oracle_verdict="ACCEPT",
            ),
        }
        ghidra_table = {
            "g1": GhidraFunctionRow(
                function_id="g1",
                entry_va=0x1000,
                body_start_va=0x1000,
                body_end_va=0x1080,
                has_body_range=True,
            ),
            "g2": GhidraFunctionRow(
                function_id="g2",
                entry_va=0x1080,
                body_start_va=0x1080,
                body_end_va=0x1100,
                has_body_range=True,
            ),
        }
        interval_index = [
            IntervalEntry(body_start=0x1000, body_end=0x1080, function_id="g1"),
            IntervalEntry(body_start=0x1080, body_end=0x1100, function_id="g2"),
        ]

        # g1 overlap = 0x80 = 128 bytes; g2 overlap = 0x80 = 128 bytes
        # (but actually g2 = 0x1100 - 0x1080 = 0x80 = 128 bytes too)
        # Wait: g1 covers [1000, 1080) → overlap with [1000, 1100) = [1000, 1080) = 128
        #       g2 covers [1080, 1100) → overlap with [1000, 1100) = [1080, 1100) = 128
        # They are equal → near-tie → MULTI_MATCH
        results = join_dwarf_to_ghidra(
            dwarf_table, ghidra_table, interval_index, profile,
        )
        assert len(results) == 1

        # Both have 128 bytes — definitely a near-tie
        r = results[0]
        assert r.match_kind == "MULTI_MATCH"
        assert r.n_near_ties >= 1

    def test_weak_overlap(self, profile):
        """Small overlap → JOINED_WEAK."""
        dwarf_table = {
            "f1": DwarfFunctionRow(
                function_id="f1",
                ranges=[(0x1000, 0x1100)],
                total_range_bytes=0x100,
                has_range=True,
                low_pc=0x1000,
                high_pc=0x1100,
                oracle_verdict="ACCEPT",
            ),
        }
        ghidra_table = {
            "g1": GhidraFunctionRow(
                function_id="g1",
                entry_va=0x1050,
                body_start_va=0x1050,
                body_end_va=0x10e0,  # overlap = [0x1050, 0x1100) = 0xB0 = 176
                has_body_range=True,
                # But DWARF is 0x100 = 256 bytes, so ratio = 176/256 ≈ 0.6875
            ),
        }
        interval_index = [
            IntervalEntry(body_start=0x1050, body_end=0x10e0, function_id="g1"),
        ]
        results = join_dwarf_to_ghidra(
            dwarf_table, ghidra_table, interval_index, profile,
        )
        r = results[0]
        # 176/256 ≈ 0.6875 → between 0.3 and 0.9 → JOINED_WEAK
        assert r.match_kind == "JOINED_WEAK"

    def test_below_weak_threshold(self, profile):
        """Very small overlap → NO_MATCH."""
        dwarf_table = {
            "f1": DwarfFunctionRow(
                function_id="f1",
                ranges=[(0x1000, 0x2000)],
                total_range_bytes=0x1000,
                has_range=True,
                low_pc=0x1000,
                high_pc=0x2000,
                oracle_verdict="ACCEPT",
            ),
        }
        ghidra_table = {
            "g1": GhidraFunctionRow(
                function_id="g1",
                entry_va=0x1F00,
                body_start_va=0x1F00,
                body_end_va=0x2100,
                has_body_range=True,
                # Overlap = [0x1F00, 0x2000) = 256 bytes
                # DWARF = 0x1000 = 4096 bytes → ratio = 256/4096 = 0.0625
            ),
        }
        interval_index = [
            IntervalEntry(body_start=0x1F00, body_end=0x2100, function_id="g1"),
        ]
        results = join_dwarf_to_ghidra(
            dwarf_table, ghidra_table, interval_index, profile,
        )
        r = results[0]
        assert r.match_kind == "NO_MATCH"
