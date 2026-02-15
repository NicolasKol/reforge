"""Tests for Phase 0 eligibility and shared noise lists."""
from __future__ import annotations

import pytest

from data.noise_lists import (
    ALL_AUX_NAMES,
    AUX_INIT_FINI_NAMES,
    COMPILER_AUX_NAMES,
    NOISE_LIST_VERSION,
    STUB_NAME_PREFIXES,
    normalize_glibc_name,
)
from join_oracles_to_ghidra_decompile.policy.eligibility import (
    EXCL_NO_RANGE,
    EXCL_NON_TARGET,
    classify_eligibility,
)
from join_oracles_to_ghidra_decompile.policy.verdict import (
    is_high_confidence,
)
from join_oracles_to_ghidra_decompile.core.invariants import (
    check_invariants,
    check_report_invariants,
)
from join_oracles_to_ghidra_decompile.io.schema import (
    ConfidenceFunnel,
    ExclusionSummary,
    JoinedFunctionRow,
    JoinReport,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Noise lists
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoiseLists:
    def test_version_bumped(self):
        assert NOISE_LIST_VERSION == "1.2"

    def test_all_aux_is_union(self):
        assert ALL_AUX_NAMES == AUX_INIT_FINI_NAMES | COMPILER_AUX_NAMES

    def test_glibc_normalization(self):
        assert normalize_glibc_name("__cxa_finalize@@GLIBC_2.17") == "__cxa_finalize"

    def test_no_glibc_suffix(self):
        assert normalize_glibc_name("_start") == "_start"

    def test_empty(self):
        assert normalize_glibc_name("") == ""

    def test_cxa_finalize_in_compiler_aux(self):
        """Post-normalization, __cxa_finalize must be in COMPILER_AUX_NAMES."""
        assert "__cxa_finalize" in COMPILER_AUX_NAMES

    def test_cxa_finalize_glibc_not_in_raw(self):
        """The @@GLIBC version should NOT be in the set (you must normalize first)."""
        assert "__cxa_finalize@@GLIBC_2.17" not in COMPILER_AUX_NAMES


# ═══════════════════════════════════════════════════════════════════════════════
# Eligibility classifier
# ═══════════════════════════════════════════════════════════════════════════════

class TestEligibility:
    def test_no_range_excluded(self):
        ej, eg, reason = classify_eligibility(
            has_range=False, is_non_target=False,
            oracle_verdict="ACCEPT", dwarf_name="main",
        )
        assert not ej
        assert not eg
        assert reason == EXCL_NO_RANGE

    def test_non_target_excluded(self):
        ej, eg, reason = classify_eligibility(
            has_range=True, is_non_target=True,
            oracle_verdict="ACCEPT", dwarf_name="main",
        )
        assert not ej
        assert not eg
        assert reason == EXCL_NON_TARGET

    def test_accept_user_func_gold_eligible(self):
        ej, eg, reason = classify_eligibility(
            has_range=True, is_non_target=False,
            oracle_verdict="ACCEPT", dwarf_name="my_parser",
        )
        assert ej
        assert eg
        assert reason is None

    def test_warn_verdict_join_but_not_gold(self):
        ej, eg, reason = classify_eligibility(
            has_range=True, is_non_target=False,
            oracle_verdict="WARN", dwarf_name="my_func",
        )
        assert ej
        assert not eg
        assert reason is None  # not an exclusion, just gold-ineligible

    def test_aux_name_join_but_not_gold(self):
        ej, eg, reason = classify_eligibility(
            has_range=True, is_non_target=False,
            oracle_verdict="ACCEPT", dwarf_name="_start",
        )
        assert ej
        assert not eg

    def test_glibc_suffix_normalized(self):
        ej, eg, reason = classify_eligibility(
            has_range=True, is_non_target=False,
            oracle_verdict="ACCEPT", dwarf_name="__cxa_finalize@@GLIBC_2.17",
        )
        assert ej
        assert not eg  # normalized to __cxa_finalize, which is in aux names


# ═══════════════════════════════════════════════════════════════════════════════
# Verdict — is_high_confidence returns (bool, reason)
# ═══════════════════════════════════════════════════════════════════════════════

class TestHighConfidence:
    def _make_hc_args(self, **overrides):
        defaults = dict(
            dwarf_oracle_verdict="ACCEPT",
            align_verdict="MATCH",
            align_n_candidates=1,
            align_overlap_ratio=1.0,
            ghidra_match_kind="JOINED_STRONG",
            is_external_block=False,
            is_thunk=False,
            is_aux_function=False,
            is_import_proxy=False,
            cfg_completeness="HIGH",
            warning_tags=[],
            fatal_warnings=("DECOMPILE_TIMEOUT",),
        )
        defaults.update(overrides)
        return defaults

    def test_all_pass(self):
        hc, reason = is_high_confidence(**self._make_hc_args()) #type: ignore
        assert hc is True
        assert reason is None

    def test_oracle_warn_rejects(self):
        hc, reason = is_high_confidence(**self._make_hc_args( #type: ignore
            dwarf_oracle_verdict="WARN",
        ))
        assert hc is False
        assert reason == "ORACLE_NOT_ACCEPT"

    def test_align_ratio_095_passes(self):
        """Relaxed threshold: 0.95 should pass."""
        hc, reason = is_high_confidence(**self._make_hc_args( #type: ignore
            align_overlap_ratio=0.95,
        ))
        assert hc is True

    def test_align_ratio_094_fails(self):
        """Below 0.95 should fail."""
        hc, reason = is_high_confidence(**self._make_hc_args( #type: ignore
            align_overlap_ratio=0.94,
        ))
        assert hc is False
        assert reason == "ALIGN_RATIO_LOW"

    def test_cfg_low_rejects(self):
        hc, reason = is_high_confidence(**self._make_hc_args( #type: ignore
            cfg_completeness="LOW",
        ))
        assert hc is False
        assert reason == "CFG_LOW"

    def test_fatal_warning_rejects(self):
        hc, reason = is_high_confidence(**self._make_hc_args( #type: ignore
            warning_tags=["DECOMPILE_TIMEOUT"],
        ))
        assert hc is False
        assert reason == "FATAL_WARNING"

    def test_not_joined_strong_rejects(self):
        hc, reason = is_high_confidence(**self._make_hc_args( #type: ignore
            ghidra_match_kind="JOINED_WEAK",
        ))
        assert hc is False
        assert reason == "NOT_JOINED_STRONG"


# ═══════════════════════════════════════════════════════════════════════════════
# Invariant checks
# ═══════════════════════════════════════════════════════════════════════════════

def _make_row(**overrides) -> JoinedFunctionRow:
    defaults = dict(
        binary_sha256="abc123",
        job_id="j1",
        test_case="t1",
        opt="O0",
        variant="stripped",
        builder_profile_id="gcc",
        dwarf_function_id="f1",
        ghidra_match_kind="JOINED_STRONG",
        pc_overlap_ratio=0.95,
        is_high_confidence=False,
        eligible_for_join=True,
        eligible_for_gold=True,
    )
    defaults.update(overrides)
    return JoinedFunctionRow(**defaults) #type: ignore


class TestInvariants:
    def test_clean_rows_pass(self):
        rows = [_make_row()]
        violations = check_invariants(rows)
        assert violations == []

    def test_hc_not_gold_violates(self):
        rows = [_make_row(is_high_confidence=True, eligible_for_gold=False)]
        violations = check_invariants(rows)
        assert len(violations) == 1
        assert violations[0]["check"] == "hc_implies_gold"

    def test_overlap_ratio_out_of_bounds(self):
        rows = [_make_row(pc_overlap_ratio=1.5)]
        violations = check_invariants(rows)
        assert any(v["check"] == "overlap_ratio_bounds" for v in violations)

    def test_no_range_with_ghidra_id(self):
        rows = [_make_row(ghidra_match_kind="NO_RANGE", ghidra_func_id="g1")]
        violations = check_invariants(rows)
        assert any(v["check"] == "no_range_no_ghidra" for v in violations)

    def test_ineligible_without_reason(self):
        rows = [_make_row(eligible_for_join=False, exclusion_reason=None)]
        violations = check_invariants(rows)
        assert any(v["check"] == "exclusion_reason_present" for v in violations)


def _make_report(**overrides) -> JoinReport:
    """Build a minimal JoinReport with sane defaults for invariant tests."""
    defaults = dict(
        exclusion_summary=ExclusionSummary(
            n_total_dwarf=10,
            n_no_range=2,
            n_non_target=1,
            n_noise_aux=0,
            n_eligible_for_join=7,
            n_eligible_for_gold=5,
        ),
        confidence_funnel=ConfidenceFunnel(
            n_eligible_for_gold=5,
            n_pass_oracle_accept=5,
            n_pass_align_match=4,
            n_pass_align_unique=4,
            n_pass_align_ratio=3,
            n_pass_joined_strong=3,
            n_pass_not_noise=3,
            n_pass_cfg_not_low=2,
            n_pass_no_fatal_warnings=2,
            n_high_confidence=2,
        ),
        yield_by_align_verdict={"MATCH": 7, "NO_RANGE": 2, "NON_TARGET": 1},
        yield_by_quality_weight_bin={
            "==1.0": 4, "[0.95,1.0)": 1, "[0.5,0.8)": 2,
            "none_not_match": 1, "none_no_range": 2,
        },
    )
    defaults.update(overrides)
    return JoinReport(**defaults)


class TestReportInvariants:
    """Report-level sanity assertions (Task C)."""

    def test_clean_report_passes(self):
        report = _make_report()
        violations = check_report_invariants(report)
        assert violations == []

    def test_partition_mismatch(self):
        report = _make_report(
            exclusion_summary=ExclusionSummary(
                n_total_dwarf=10,
                n_no_range=2,
                n_non_target=1,
                n_noise_aux=0,
                n_eligible_for_join=5,  # 2+1+0+5=8 != 10
            ),
        )
        violations = check_report_invariants(report)
        assert any(v["check"] == "exclusion_partition" for v in violations)

    def test_partition_correct(self):
        report = _make_report(
            exclusion_summary=ExclusionSummary(
                n_total_dwarf=20,
                n_no_range=3,
                n_non_target=2,
                n_noise_aux=1,
                n_eligible_for_join=14,  # 3+2+1+14=20 ✓
            ),
        )
        violations = check_report_invariants(report)
        assert not any(v["check"] == "exclusion_partition" for v in violations)

    def test_funnel_monotonic_ok(self):
        report = _make_report()
        violations = check_report_invariants(report)
        assert not any(v["check"] == "funnel_monotonicity" for v in violations)

    def test_funnel_monotonic_violation(self):
        report = _make_report(
            confidence_funnel=ConfidenceFunnel(
                n_eligible_for_gold=5,
                n_pass_oracle_accept=5,
                n_pass_align_match=4,
                n_pass_align_unique=4,
                n_pass_align_ratio=3,
                n_pass_joined_strong=3,
                n_pass_not_noise=3,
                n_pass_cfg_not_low=2,
                n_pass_no_fatal_warnings=2,
                n_high_confidence=3,  # 3 > 2 — violates monotonicity
            ),
        )
        violations = check_report_invariants(report)
        assert any(v["check"] == "funnel_monotonicity" for v in violations)

    def test_crossfield_no_range_mismatch(self):
        report = _make_report(
            exclusion_summary=ExclusionSummary(
                n_total_dwarf=10,
                n_no_range=2,
                n_non_target=1,
                n_noise_aux=0,
                n_eligible_for_join=7,
            ),
            yield_by_align_verdict={"MATCH": 7, "NO_RANGE": 3, "NON_TARGET": 0},
        )
        violations = check_report_invariants(report)
        assert any(v["check"] == "verdict_vs_exclusion_no_range" for v in violations)

    def test_crossfield_non_target_mismatch(self):
        report = _make_report(
            exclusion_summary=ExclusionSummary(
                n_total_dwarf=10,
                n_no_range=2,
                n_non_target=0,
                n_noise_aux=0,
                n_eligible_for_join=8,
            ),
            yield_by_align_verdict={"MATCH": 8, "NO_RANGE": 2, "NON_TARGET": 5},
        )
        violations = check_report_invariants(report)
        assert any(v["check"] == "verdict_vs_exclusion_non_target" for v in violations)

    def test_crossfield_histogram_sum_mismatch(self):
        report = _make_report(
            exclusion_summary=ExclusionSummary(
                n_total_dwarf=10,
                n_no_range=2,
                n_non_target=1,
                n_noise_aux=0,
                n_eligible_for_join=7,
            ),
            yield_by_align_verdict={"MATCH": 5, "NO_RANGE": 2, "NON_TARGET": 1},
            # sum=8 != 10
        )
        violations = check_report_invariants(report)
        assert any(v["check"] == "verdict_histogram_sum" for v in violations)
