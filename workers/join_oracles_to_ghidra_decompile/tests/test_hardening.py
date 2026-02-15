"""
test_hardening — Pre-experiment hardening tests.

Exercises edge cases and invariants identified in the academic review
that are not covered by the existing test suite.  All tests use the
existing conftest fixtures or minimal synthetic extensions — no new
external dependencies.

Fix packet A5 from the pre-experiment hardening plan.
"""
from __future__ import annotations

import copy
from typing import Dict, List

import pytest

from join_oracles_to_ghidra_decompile.core.address_join import (
    join_dwarf_to_ghidra,
)
from join_oracles_to_ghidra_decompile.core.diagnostics import (
    build_joined_function_rows,
    _classify_aux,
)
from join_oracles_to_ghidra_decompile.core.function_table import (
    build_dwarf_function_table,
    build_ghidra_function_table,
    apply_eligibility,
    IntervalEntry,
)
from join_oracles_to_ghidra_decompile.core.invariants import (
    check_invariants,
)
from join_oracles_to_ghidra_decompile.io.schema import JoinedFunctionRow
from join_oracles_to_ghidra_decompile.policy.profile import (
    JoinOraclesGhidraProfile,
)

from .conftest import TEST_SHA256


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _make_profile() -> JoinOraclesGhidraProfile:
    return JoinOraclesGhidraProfile.v1()


def _make_ghidra_func(
    entry_va: int,
    body_start: int,
    body_end: int,
    *,
    name: str = "FUN",
    is_thunk: bool = False,
    is_external: bool = False,
    warnings: list | None = None,
) -> dict:
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
        "size_bytes": body_end - body_start,
        "is_external_block": is_external,
        "is_thunk": is_thunk,
        "is_import": False,
        "section_hint": ".text",
        "decompile_status": "OK",
        "c_raw": f"void {name}(void) {{ return; }}\n",
        "warnings": warnings or [],
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


# ═══════════════════════════════════════════════════════════════════════════════
# Test 1 — Image-base rebasing + address join
# ═══════════════════════════════════════════════════════════════════════════════

class TestImageBaseRebasing:
    """Verify that Ghidra image_base rebasing produces correct join results."""

    def test_rebase_aligns_overlap(
        self, oracle_functions, alignment_pairs,
    ):
        """DWARF func at 0x401000-0x401030, Ghidra at 0x501000-0x501030
        with image_base=0x100000 should rebase to 0x401000 and join."""
        image_base = 0x100000
        ghidra_funcs = [
            _make_ghidra_func(0x501000, 0x501000, 0x501030, name="FUN_rebased"),
        ]
        ghidra_cfg: list = []
        ghidra_vars: list = []

        ghidra_table, interval_index = build_ghidra_function_table(
            ghidra_funcs, ghidra_cfg, ghidra_vars,
            image_base=image_base,
        )

        # After rebasing, the Ghidra function should be at 0x401000
        assert len(interval_index) == 1
        assert interval_index[0].body_start == 0x401000
        assert interval_index[0].body_end == 0x401030

        # Build DWARF table and join
        profile = _make_profile()
        dwarf_table = build_dwarf_function_table(oracle_functions, alignment_pairs)
        apply_eligibility(dwarf_table, profile.aux_function_names)

        results = join_dwarf_to_ghidra(
            dwarf_table, ghidra_table, interval_index, profile,
        )

        # "add" function at 0x401000-0x401030 should get JOINED_STRONG
        add_result = next(r for r in results if r.dwarf.name == "add")
        assert add_result.match_kind == "JOINED_STRONG"
        assert add_result.pc_overlap_ratio == 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# Test 2 — Many-to-one / FAT_FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

class TestManyToOne:
    """Verify that multiple DWARF functions mapping to one Ghidra func
    trigger fat_function_multi_dwarf."""

    def test_fat_function_flag(self, alignment_pairs):
        """Two DWARF funcs both inside one large Ghidra function."""
        # Create oracle functions with two functions in the same range
        oracle_functions = {
            "package_name": "oracle_dwarf",
            "oracle_version": "v0",
            "schema_version": "0.2",
            "binary_sha256": TEST_SHA256,
            "functions": [
                {
                    "function_id": "cu0:0x100",
                    "name": "func_a",
                    "linkage_name": None,
                    "decl_file": "/src/a.c",
                    "decl_line": 1,
                    "decl_column": 1,
                    "comp_dir": "/build",
                    "cu_id": "cu0",
                    "ranges": [{"low": "0x401000", "high": "0x401020"}],
                    "verdict": "ACCEPT",
                    "reasons": [],
                    "dominant_file": "/src/a.c",
                    "dominant_file_ratio": 1.0,
                    "n_line_rows": 4,
                    "line_rows": [],
                    "file_row_counts": {},
                },
                {
                    "function_id": "cu0:0x200",
                    "name": "func_b",
                    "linkage_name": None,
                    "decl_file": "/src/a.c",
                    "decl_line": 10,
                    "decl_column": 1,
                    "comp_dir": "/build",
                    "cu_id": "cu0",
                    "ranges": [{"low": "0x401020", "high": "0x401040"}],
                    "verdict": "ACCEPT",
                    "reasons": [],
                    "dominant_file": "/src/a.c",
                    "dominant_file_ratio": 1.0,
                    "n_line_rows": 4,
                    "line_rows": [],
                    "file_row_counts": {},
                },
            ],
        }

        # Single large Ghidra function covering both DWARF ranges
        ghidra_funcs = [
            _make_ghidra_func(0x401000, 0x401000, 0x401040, name="FUN_big"),
        ]

        profile = _make_profile()
        dwarf_table = build_dwarf_function_table(oracle_functions, alignment_pairs)
        apply_eligibility(dwarf_table, profile.aux_function_names)

        ghidra_table, interval_index = build_ghidra_function_table(
            ghidra_funcs, [], [],
        )

        results = join_dwarf_to_ghidra(
            dwarf_table, ghidra_table, interval_index, profile,
        )

        from join_oracles_to_ghidra_decompile.core.build_context import (
            BuildContext,
        )
        ctx = BuildContext(
            binary_sha256=TEST_SHA256,
            job_id="test",
            test_case="test",
            opt="O0",
            variant="stripped",
            builder_profile_id="test",
            ghidra_binary_sha256=TEST_SHA256,
            ghidra_variant="stripped",
        )
        rows = build_joined_function_rows(results, ctx, profile)

        # Both rows should map to the same Ghidra function
        joined = [r for r in rows if r.ghidra_func_id is not None]
        assert len(joined) == 2

        ghidra_ids = {r.ghidra_func_id for r in joined}
        assert len(ghidra_ids) == 1  # same Ghidra function

        for r in joined:
            assert r.fat_function_multi_dwarf is True
            assert r.n_dwarf_funcs_per_ghidra_func == 2


# ═══════════════════════════════════════════════════════════════════════════════
# Tests 3-4 — Near-tie epsilon
# ═══════════════════════════════════════════════════════════════════════════════

class TestNearTieEpsilon:
    """Verify near-tie detection with different overlap sizes."""

    def _make_dwarf_and_ghidra(
        self,
        dwarf_range: tuple,
        ghidra_ranges: list,
        alignment_pairs,
    ):
        """Helper: one DWARF func, N Ghidra funcs."""
        oracle_functions = {
            "package_name": "oracle_dwarf",
            "oracle_version": "v0",
            "schema_version": "0.2",
            "binary_sha256": TEST_SHA256,
            "functions": [
                {
                    "function_id": "cu0:0x100",
                    "name": "target",
                    "linkage_name": None,
                    "decl_file": "/src/t.c",
                    "decl_line": 1,
                    "decl_column": 1,
                    "comp_dir": "/build",
                    "cu_id": "cu0",
                    "ranges": [{"low": hex(dwarf_range[0]), "high": hex(dwarf_range[1])}],
                    "verdict": "ACCEPT",
                    "reasons": [],
                    "dominant_file": "/src/t.c",
                    "dominant_file_ratio": 1.0,
                    "n_line_rows": 4,
                    "line_rows": [],
                    "file_row_counts": {},
                },
            ],
        }
        ghidra_funcs = [
            _make_ghidra_func(r[0], r[0], r[1], name=f"FUN_{i}")
            for i, r in enumerate(ghidra_ranges)
        ]

        profile = _make_profile()
        dwarf_table = build_dwarf_function_table(oracle_functions, alignment_pairs)
        apply_eligibility(dwarf_table, profile.aux_function_names)
        ghidra_table, interval_index = build_ghidra_function_table(
            ghidra_funcs, [], [],
        )
        return dwarf_table, ghidra_table, interval_index, profile

    def test_tiny_function_no_false_tie(self, alignment_pairs):
        """10-byte DWARF func, two Ghidra candidates: 10 and 9 bytes overlap.
        Epsilon = 5% of 10 = 0.5 bytes. Diff = 1 > 0.5 → NOT a near-tie."""
        # DWARF: [0x1000, 0x100A)  = 10 bytes
        # Ghidra A: [0x1000, 0x100A)  overlaps 10/10
        # Ghidra B: [0x1001, 0x100A)  overlaps 9/10
        dwarf_table, ghidra_table, idx, profile = self._make_dwarf_and_ghidra(
            (0x1000, 0x100A),
            [(0x1000, 0x100A), (0x1001, 0x100A)],
            alignment_pairs,
        )
        results = join_dwarf_to_ghidra(dwarf_table, ghidra_table, idx, profile)
        r = results[0]
        assert r.match_kind == "JOINED_STRONG"
        assert r.n_near_ties == 0

    def test_near_tie_triggers_multi_match(self, alignment_pairs):
        """100-byte DWARF func, two Ghidra candidates: 100 and 96 bytes.
        Epsilon = 5% of 100 = 5.0 bytes. Diff = 4 <= 5 → near-tie → MULTI_MATCH."""
        # DWARF: [0x2000, 0x2064)  = 100 bytes
        # Ghidra A: [0x2000, 0x2064)  overlaps 100/100
        # Ghidra B: [0x2004, 0x2064)  overlaps 96/100
        dwarf_table, ghidra_table, idx, profile = self._make_dwarf_and_ghidra(
            (0x2000, 0x2064),
            [(0x2000, 0x2064), (0x2004, 0x2064)],
            alignment_pairs,
        )
        results = join_dwarf_to_ghidra(dwarf_table, ghidra_table, idx, profile)
        r = results[0]
        assert r.match_kind == "MULTI_MATCH"
        assert r.n_near_ties >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Test 5 — None ghidra_name safety (exercises Fix A3)
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoneGhidraName:
    """Verify that _classify_aux handles None name without crash."""

    def test_classify_aux_with_none_name(self):
        """Calling _classify_aux with None must not crash."""
        result = _classify_aux(None, ("frame_dummy", "_init")) #type: ignore
        assert result is False

    def test_classify_aux_with_empty_string(self):
        """Empty string should not match aux names."""
        result = _classify_aux("", ("frame_dummy", "_init"))
        assert result is False

    def test_classify_aux_with_actual_aux(self):
        """Known aux name should match."""
        result = _classify_aux("frame_dummy", ("frame_dummy", "_init"))
        assert result is True


# ═══════════════════════════════════════════════════════════════════════════════
# Test 6 — Invariant: QW formula consistency (exercises Fix A4)
# ═══════════════════════════════════════════════════════════════════════════════

class TestInvariantQualityWeight:
    """Verify the new quality_weight formula invariant check."""

    def _make_row(self, **overrides) -> JoinedFunctionRow:
        defaults = dict(
            binary_sha256=TEST_SHA256,
            job_id="test",
            test_case="test",
            opt="O0",
            variant="stripped",
            builder_profile_id="test",
            ghidra_binary_sha256=TEST_SHA256,
            ghidra_variant="stripped",
            dwarf_function_id="cu0:0x100",
            dwarf_function_name="func",
            dwarf_function_name_norm="func",
            decl_file="/src/a.c",
            decl_line=1,
            decl_column=1,
            low_pc=0x401000,
            high_pc=0x401030,
            dwarf_total_range_bytes=48,
            dwarf_oracle_verdict="ACCEPT",
            align_verdict="MATCH",
            align_overlap_ratio=1.0,
            align_gap_count=0,
            align_n_candidates=1,
            quality_weight=1.0,
            align_reason_tags=["UNIQUE_BEST"],
            ghidra_match_kind="JOINED_STRONG",
            ghidra_func_id="g1",
            ghidra_entry_va=0x401000,
            ghidra_name="FUN",
            decompile_status="OK",
            cfg_completeness="HIGH",
            bb_count=1,
            edge_count=0,
            warning_tags=[],
            goto_count=0,
            loc_decompiled=3,
            temp_var_count=0,
            placeholder_type_rate=0.0,
            pc_overlap_bytes=48,
            pc_overlap_ratio=1.0,
            n_near_ties=0,
            join_warnings=[],
            is_high_confidence=True,
            is_aux_function=False,
            is_import_proxy=False,
            is_external_block=False,
            is_non_target=False,
            is_thunk=False,
            eligible_for_join=True,
            eligible_for_gold=True,
            exclusion_reason=None,
            confidence_tier="GOLD",
            hc_reject_reason=None,
            upstream_collapse_reason=None,
            decompiler_quality_flags=[],
        )
        defaults.update(overrides)
        return JoinedFunctionRow(**defaults) #type: ignore

    def test_correct_qw_passes(self):
        """Row with qw = overlap_ratio / n_candidates should pass."""
        row = self._make_row(
            align_overlap_ratio=0.8,
            align_n_candidates=2,
            quality_weight=0.4,  # 0.8 / 2
        )
        violations = check_invariants([row])
        qw_violations = [v for v in violations if v["check"] == "qw_formula"]
        assert len(qw_violations) == 0

    def test_corrupt_qw_detected(self):
        """Row with wrong qw should produce a violation."""
        row = self._make_row(
            align_overlap_ratio=0.8,
            align_n_candidates=2,
            quality_weight=0.9,  # wrong: should be 0.4
        )
        violations = check_invariants([row])
        qw_violations = [v for v in violations if v["check"] == "qw_formula"]
        assert len(qw_violations) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Test 7 — Invariant: match_kind / ratio consistency (exercises Fix A4)
# ═══════════════════════════════════════════════════════════════════════════════

class TestInvariantMatchKindRatio:
    """Verify the new match_kind/ratio consistency invariant check."""

    def _make_row(self, **overrides) -> JoinedFunctionRow:
        defaults = dict(
            binary_sha256=TEST_SHA256,
            job_id="test",
            test_case="test",
            opt="O0",
            variant="stripped",
            builder_profile_id="test",
            ghidra_binary_sha256=TEST_SHA256,
            ghidra_variant="stripped",
            dwarf_function_id="cu0:0x100",
            dwarf_function_name="func",
            dwarf_function_name_norm="func",
            decl_file="/src/a.c",
            decl_line=1,
            decl_column=1,
            low_pc=0x401000,
            high_pc=0x401030,
            dwarf_total_range_bytes=48,
            dwarf_oracle_verdict="ACCEPT",
            align_verdict="MATCH",
            align_overlap_ratio=1.0,
            align_gap_count=0,
            align_n_candidates=1,
            quality_weight=1.0,
            align_reason_tags=["UNIQUE_BEST"],
            ghidra_match_kind="JOINED_STRONG",
            ghidra_func_id="g1",
            ghidra_entry_va=0x401000,
            ghidra_name="FUN",
            decompile_status="OK",
            cfg_completeness="HIGH",
            bb_count=1,
            edge_count=0,
            warning_tags=[],
            goto_count=0,
            loc_decompiled=3,
            temp_var_count=0,
            placeholder_type_rate=0.0,
            pc_overlap_bytes=48,
            pc_overlap_ratio=1.0,
            n_near_ties=0,
            join_warnings=[],
            is_high_confidence=True,
            is_aux_function=False,
            is_import_proxy=False,
            is_external_block=False,
            is_non_target=False,
            is_thunk=False,
            eligible_for_join=True,
            eligible_for_gold=True,
            exclusion_reason=None,
            confidence_tier="GOLD",
            hc_reject_reason=None,
            upstream_collapse_reason=None,
            decompiler_quality_flags=[],
        )
        defaults.update(overrides)
        return JoinedFunctionRow(**defaults) #type: ignore

    def test_consistent_strong_passes(self):
        """JOINED_STRONG with ratio >= 0.9 should pass."""
        row = self._make_row(
            ghidra_match_kind="JOINED_STRONG",
            pc_overlap_ratio=0.95,
        )
        violations = check_invariants([row])
        mk_violations = [v for v in violations if v["check"] == "match_kind_ratio"]
        assert len(mk_violations) == 0

    def test_strong_with_low_ratio_detected(self):
        """JOINED_STRONG but ratio 0.5 should produce a violation."""
        row = self._make_row(
            ghidra_match_kind="JOINED_STRONG",
            pc_overlap_ratio=0.5,
        )
        violations = check_invariants([row])
        mk_violations = [v for v in violations if v["check"] == "match_kind_ratio"]
        assert len(mk_violations) == 1

    def test_weak_with_high_ratio_detected(self):
        """JOINED_WEAK but ratio 0.95 should produce a violation."""
        row = self._make_row(
            ghidra_match_kind="JOINED_WEAK",
            pc_overlap_ratio=0.95,
        )
        violations = check_invariants([row])
        mk_violations = [v for v in violations if v["check"] == "match_kind_ratio"]
        assert len(mk_violations) == 1
