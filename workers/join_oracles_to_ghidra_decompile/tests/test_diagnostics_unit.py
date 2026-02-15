"""Unit tests for diagnostics decision functions.

Tests _decompiler_quality_flags, _assign_confidence_tier,
_detect_upstream_collapse, and _build_collision_summary in isolation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import pytest

from join_oracles_to_ghidra_decompile.core.diagnostics import (
    _assign_confidence_tier,
    _build_collision_summary,
    _decompiler_quality_flags,
    _detect_upstream_collapse,
)
from join_oracles_to_ghidra_decompile.io.schema import JoinedFunctionRow


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

_FATAL = ("DECOMPILE_TIMEOUT", "UNRESOLVED_INDIRECT_JUMP")

SHA = "a" * 64


@dataclass
class _FakeDwarfRow:
    """Minimal stub matching the duck-typed interface of _detect_upstream_collapse."""

    has_range: bool = True
    is_non_target: bool = False
    oracle_verdict: str = "ACCEPT"
    align_verdict: Optional[str] = "MATCH"


def _row(**kw) -> JoinedFunctionRow:
    """Build a minimal JoinedFunctionRow with sensible defaults."""
    defaults = dict(
        binary_sha256=SHA,
        job_id="j1",
        test_case="tc",
        opt="O0",
        variant="stripped",
        builder_profile_id="p1",
        dwarf_function_id="cu0:0x100",
    )
    defaults.update(kw)
    return JoinedFunctionRow(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# TestDecompilerQualityFlags
# ═══════════════════════════════════════════════════════════════════════════════

class TestDecompilerQualityFlags:
    """Tests for _decompiler_quality_flags."""

    def test_clean_function_no_flags(self):
        flags = _decompiler_quality_flags(
            cfg_completeness="HIGH",
            warning_tags=[],
            goto_count=0,
            loc_decompiled=100,
            placeholder_type_rate=0.0,
            fatal_warnings=_FATAL,
        )
        assert flags == []

    def test_cfg_low(self):
        flags = _decompiler_quality_flags(
            cfg_completeness="LOW",
            warning_tags=[],
            goto_count=0,
            loc_decompiled=100,
            placeholder_type_rate=0.0,
            fatal_warnings=_FATAL,
        )
        assert flags == ["CFG_LOW"]

    def test_fatal_warning(self):
        flags = _decompiler_quality_flags(
            cfg_completeness="HIGH",
            warning_tags=["DECOMPILE_TIMEOUT"],
            goto_count=0,
            loc_decompiled=100,
            placeholder_type_rate=0.0,
            fatal_warnings=_FATAL,
        )
        assert flags == ["FATAL_WARNING"]

    def test_high_goto_density(self):
        flags = _decompiler_quality_flags(
            cfg_completeness="HIGH",
            warning_tags=[],
            goto_count=20,
            loc_decompiled=100,
            placeholder_type_rate=0.0,
            fatal_warnings=_FATAL,
        )
        assert flags == ["HIGH_GOTO_DENSITY"]

    def test_high_placeholder_types(self):
        flags = _decompiler_quality_flags(
            cfg_completeness="HIGH",
            warning_tags=[],
            goto_count=0,
            loc_decompiled=100,
            placeholder_type_rate=0.5,
            fatal_warnings=_FATAL,
        )
        assert flags == ["HIGH_PLACEHOLDER_TYPES"]

    def test_multiple_flags(self):
        flags = _decompiler_quality_flags(
            cfg_completeness="LOW",
            warning_tags=["UNRESOLVED_INDIRECT_JUMP"],
            goto_count=50,
            loc_decompiled=100,
            placeholder_type_rate=0.9,
            fatal_warnings=_FATAL,
        )
        assert set(flags) == {
            "CFG_LOW",
            "FATAL_WARNING",
            "HIGH_GOTO_DENSITY",
            "HIGH_PLACEHOLDER_TYPES",
        }

    def test_non_fatal_warning_not_flagged(self):
        flags = _decompiler_quality_flags(
            cfg_completeness="HIGH",
            warning_tags=["UNREACHABLE_BLOCKS_REMOVED"],
            goto_count=0,
            loc_decompiled=100,
            placeholder_type_rate=0.0,
            fatal_warnings=_FATAL,
        )
        assert flags == []

    def test_goto_boundary_not_triggered(self):
        """Exactly at threshold (0.1) should NOT trigger."""
        flags = _decompiler_quality_flags(
            cfg_completeness="HIGH",
            warning_tags=[],
            goto_count=10,
            loc_decompiled=100,
            placeholder_type_rate=0.0,
            fatal_warnings=_FATAL,
        )
        assert "HIGH_GOTO_DENSITY" not in flags


# ═══════════════════════════════════════════════════════════════════════════════
# TestAssignConfidenceTier
# ═══════════════════════════════════════════════════════════════════════════════

class TestAssignConfidenceTier:
    """Tests for _assign_confidence_tier."""

    def test_gold(self):
        assert _assign_confidence_tier(hc=True, match_kind="JOINED_STRONG", eligible_for_gold=True) == "GOLD"

    def test_gold_overrides_ineligible(self):
        """HC=True forces GOLD even if eligible_for_gold were somehow False."""
        assert _assign_confidence_tier(hc=True, match_kind="JOINED_STRONG", eligible_for_gold=False) == "GOLD"

    def test_silver(self):
        assert _assign_confidence_tier(hc=False, match_kind="JOINED_STRONG", eligible_for_gold=True) == "SILVER"

    def test_bronze_strong_not_gold_eligible(self):
        assert _assign_confidence_tier(hc=False, match_kind="JOINED_STRONG", eligible_for_gold=False) == "BRONZE"

    def test_bronze_weak(self):
        assert _assign_confidence_tier(hc=False, match_kind="JOINED_WEAK", eligible_for_gold=False) == "BRONZE"

    def test_bronze_weak_gold_eligible(self):
        """JOINED_WEAK + gold-eligible is still BRONZE (not SILVER)."""
        assert _assign_confidence_tier(hc=False, match_kind="JOINED_WEAK", eligible_for_gold=True) == "BRONZE"

    def test_empty_no_match(self):
        assert _assign_confidence_tier(hc=False, match_kind="NO_MATCH", eligible_for_gold=False) == ""

    def test_empty_no_range(self):
        assert _assign_confidence_tier(hc=False, match_kind="NO_RANGE", eligible_for_gold=False) == ""

    def test_empty_multi_match(self):
        assert _assign_confidence_tier(hc=False, match_kind="MULTI_MATCH", eligible_for_gold=False) == ""


# ═══════════════════════════════════════════════════════════════════════════════
# TestDetectUpstreamCollapse
# ═══════════════════════════════════════════════════════════════════════════════

class TestDetectUpstreamCollapse:
    """Tests for _detect_upstream_collapse."""

    def test_no_collapse(self):
        assert _detect_upstream_collapse(_FakeDwarfRow()) is None

    def test_no_dwarf_range(self):
        assert _detect_upstream_collapse(_FakeDwarfRow(has_range=False)) == "NO_DWARF_RANGE"

    def test_alignment_non_target(self):
        assert _detect_upstream_collapse(_FakeDwarfRow(is_non_target=True)) == "ALIGNMENT_NON_TARGET"

    def test_dwarf_oracle_reject(self):
        assert _detect_upstream_collapse(_FakeDwarfRow(oracle_verdict="REJECT")) == "DWARF_ORACLE_REJECT"

    def test_alignment_disappear(self):
        assert _detect_upstream_collapse(_FakeDwarfRow(align_verdict="DISAPPEAR")) == "ALIGNMENT_DISAPPEAR"

    def test_priority_no_range_wins(self):
        """NO_DWARF_RANGE is checked first, even if other flags also set."""
        row = _FakeDwarfRow(has_range=False, is_non_target=True, oracle_verdict="REJECT")
        assert _detect_upstream_collapse(row) == "NO_DWARF_RANGE"

    def test_priority_non_target_over_reject(self):
        row = _FakeDwarfRow(is_non_target=True, oracle_verdict="REJECT")
        assert _detect_upstream_collapse(row) == "ALIGNMENT_NON_TARGET"


# ═══════════════════════════════════════════════════════════════════════════════
# TestBuildCollisionSummary
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuildCollisionSummary:
    """Tests for _build_collision_summary."""

    def test_no_collisions(self):
        rows = [
            _row(dwarf_function_id="d1", ghidra_func_id="g1"),
            _row(dwarf_function_id="d2", ghidra_func_id="g2"),
        ]
        cs = _build_collision_summary(rows)
        assert cs.n_unique_ghidra_funcs_matched == 2
        assert cs.n_ghidra_funcs_with_multi_dwarf == 0
        assert cs.max_dwarf_per_ghidra == 1
        assert cs.top_collisions == []

    def test_many_to_one(self):
        rows = [
            _row(dwarf_function_id="d1", ghidra_func_id="g1"),
            _row(dwarf_function_id="d2", ghidra_func_id="g1"),
            _row(dwarf_function_id="d3", ghidra_func_id="g1"),
            _row(dwarf_function_id="d4", ghidra_func_id="g2"),
        ]
        cs = _build_collision_summary(rows)
        assert cs.n_unique_ghidra_funcs_matched == 2
        assert cs.n_ghidra_funcs_with_multi_dwarf == 1
        assert cs.max_dwarf_per_ghidra == 3
        assert len(cs.top_collisions) == 1
        assert cs.top_collisions[0]["ghidra_func_id"] == "g1"
        assert cs.top_collisions[0]["n_dwarf"] == 3

    def test_no_ghidra_match(self):
        rows = [
            _row(dwarf_function_id="d1", ghidra_func_id=None),
            _row(dwarf_function_id="d2", ghidra_func_id=None),
        ]
        cs = _build_collision_summary(rows)
        assert cs.n_unique_ghidra_funcs_matched == 0
        assert cs.max_dwarf_per_ghidra == 0

    def test_top_n_limit(self):
        """Only top_n collisions are returned."""
        rows = []
        for g_idx in range(10):
            for d_idx in range(g_idx + 2):
                rows.append(_row(
                    dwarf_function_id=f"d_{g_idx}_{d_idx}",
                    ghidra_func_id=f"g{g_idx}",
                ))
        cs = _build_collision_summary(rows, top_n=3)
        assert len(cs.top_collisions) == 3
        # Sorted descending by count
        counts = [c["n_dwarf"] for c in cs.top_collisions]
        assert counts == sorted(counts, reverse=True)
