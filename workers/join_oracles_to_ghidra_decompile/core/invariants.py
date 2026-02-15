"""
Invariants — post-pipeline assertion checks for academic defensibility.

Called after ``build_joined_function_rows`` and before report assembly.
Each check logs a warning and returns a violation dict; the violations
are appended to a ``pipeline_warnings`` list in the join report.

Pure functions, no IO.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from join_oracles_to_ghidra_decompile.io.schema import (
    JoinedFunctionRow,
    JoinReport,
)

log = logging.getLogger(__name__)


def check_invariants(
    rows: List[JoinedFunctionRow],
) -> List[Dict[str, Any]]:
    """Run all invariant checks.  Returns a list of violation dicts."""
    violations: List[Dict[str, Any]] = []
    violations.extend(_check_hc_implies_gold_eligible(rows))
    violations.extend(_check_overlap_ratio_bounds(rows))
    violations.extend(_check_no_range_has_no_ghidra(rows))
    violations.extend(_check_exclusion_consistency(rows))
    if violations:
        log.warning("Invariant violations detected: %d", len(violations))
    else:
        log.info("All invariant checks passed")
    return violations


def _check_hc_implies_gold_eligible(
    rows: List[JoinedFunctionRow],
) -> List[Dict[str, Any]]:
    """HC=True implies eligible_for_gold=True."""
    bad = [
        r.dwarf_function_id for r in rows
        if r.is_high_confidence and not r.eligible_for_gold
    ]
    if bad:
        msg = f"HC but not gold-eligible: {bad}"
        log.warning("INVARIANT: %s", msg)
        return [{"check": "hc_implies_gold", "ids": bad, "message": msg}]
    return []


def _check_overlap_ratio_bounds(
    rows: List[JoinedFunctionRow],
) -> List[Dict[str, Any]]:
    """pc_overlap_ratio must be in [0, 1]."""
    bad = [
        (r.dwarf_function_id, r.pc_overlap_ratio) for r in rows
        if r.pc_overlap_ratio < 0.0 or r.pc_overlap_ratio > 1.0001
    ]
    if bad:
        msg = f"pc_overlap_ratio out of [0,1]: {bad}"
        log.warning("INVARIANT: %s", msg)
        return [{"check": "overlap_ratio_bounds", "ids": bad, "message": msg}]
    return []


def _check_no_range_has_no_ghidra(
    rows: List[JoinedFunctionRow],
) -> List[Dict[str, Any]]:
    """NO_RANGE rows must not have a ghidra_func_id."""
    bad = [
        r.dwarf_function_id for r in rows
        if r.ghidra_match_kind == "NO_RANGE" and r.ghidra_func_id is not None
    ]
    if bad:
        msg = f"NO_RANGE with ghidra_func_id: {bad}"
        log.warning("INVARIANT: %s", msg)
        return [{"check": "no_range_no_ghidra", "ids": bad, "message": msg}]
    return []


def _check_exclusion_consistency(
    rows: List[JoinedFunctionRow],
) -> List[Dict[str, Any]]:
    """Excluded rows (eligible_for_join=False) must have an exclusion_reason."""
    bad = [
        r.dwarf_function_id for r in rows
        if not r.eligible_for_join and r.exclusion_reason is None
    ]
    if bad:
        msg = f"Ineligible without exclusion_reason: {bad}"
        log.warning("INVARIANT: %s", msg)
        return [{"check": "exclusion_reason_present", "ids": bad, "message": msg}]
    return []


# ═══════════════════════════════════════════════════════════════════════════════
# Report-level invariants (run AFTER build_join_report)
# ═══════════════════════════════════════════════════════════════════════════════

def check_report_invariants(
    report: JoinReport,
) -> List[Dict[str, Any]]:
    """Run report-level sanity checks.  Returns a list of violation dicts."""
    violations: List[Dict[str, Any]] = []
    violations.extend(_check_exclusion_partition(report))
    violations.extend(_check_funnel_monotonicity(report))
    violations.extend(_check_verdict_exclusion_crossfield(report))
    violations.extend(_check_quality_weight_bin_partition(report))
    violations.extend(_check_quality_weight_audit(report))
    if violations:
        log.warning("Report invariant violations detected: %d", len(violations))
    else:
        log.info("All report invariant checks passed")
    return violations


def _check_exclusion_partition(
    report: JoinReport,
) -> List[Dict[str, Any]]:
    """n_total_dwarf must equal excluded + eligible_for_join (partition)."""
    es = report.exclusion_summary
    excluded = es.n_no_range + es.n_non_target + es.n_noise_aux
    expected = excluded + es.n_eligible_for_join
    if expected != es.n_total_dwarf:
        msg = (
            f"Exclusion partition mismatch: "
            f"n_total_dwarf={es.n_total_dwarf} != "
            f"(n_no_range={es.n_no_range} + n_non_target={es.n_non_target} "
            f"+ n_noise_aux={es.n_noise_aux}) + "
            f"n_eligible_for_join={es.n_eligible_for_join} = {expected}"
        )
        log.warning("INVARIANT: %s", msg)
        return [{"check": "exclusion_partition", "message": msg}]
    return []


def _check_funnel_monotonicity(
    report: JoinReport,
) -> List[Dict[str, Any]]:
    """Confidence funnel gates must be monotonically non-increasing."""
    f = report.confidence_funnel
    gates = [
        ("n_eligible_for_gold", f.n_eligible_for_gold),
        ("n_pass_oracle_accept", f.n_pass_oracle_accept),
        ("n_pass_align_match", f.n_pass_align_match),
        ("n_pass_align_unique", f.n_pass_align_unique),
        ("n_pass_align_ratio", f.n_pass_align_ratio),
        ("n_pass_joined_strong", f.n_pass_joined_strong),
        ("n_pass_not_noise", f.n_pass_not_noise),
        ("n_pass_cfg_not_low", f.n_pass_cfg_not_low),
        ("n_pass_no_fatal_warnings", f.n_pass_no_fatal_warnings),
        ("n_high_confidence", f.n_high_confidence),
    ]
    violations: List[Dict[str, Any]] = []
    for i in range(1, len(gates)):
        prev_name, prev_val = gates[i - 1]
        curr_name, curr_val = gates[i]
        if curr_val > prev_val:
            msg = (
                f"Funnel not monotonic: {curr_name}={curr_val} > "
                f"{prev_name}={prev_val}"
            )
            log.warning("INVARIANT: %s", msg)
            violations.append({
                "check": "funnel_monotonicity",
                "gate": curr_name,
                "message": msg,
            })
    return violations


def _check_verdict_exclusion_crossfield(
    report: JoinReport,
) -> List[Dict[str, Any]]:
    """yield_by_align_verdict must be consistent with exclusion_summary."""
    es = report.exclusion_summary
    v = report.yield_by_align_verdict
    violations: List[Dict[str, Any]] = []

    # NO_RANGE count must match
    v_norange = v.get("NO_RANGE", 0)
    if v_norange != es.n_no_range:
        msg = (
            f"yield_by_align_verdict['NO_RANGE']={v_norange} != "
            f"exclusion_summary.n_no_range={es.n_no_range}"
        )
        log.warning("INVARIANT: %s", msg)
        violations.append({"check": "verdict_vs_exclusion_no_range", "message": msg})

    # NON_TARGET count must match
    v_nontarget = v.get("NON_TARGET", 0)
    if v_nontarget != es.n_non_target:
        msg = (
            f"yield_by_align_verdict['NON_TARGET']={v_nontarget} != "
            f"exclusion_summary.n_non_target={es.n_non_target}"
        )
        log.warning("INVARIANT: %s", msg)
        violations.append({"check": "verdict_vs_exclusion_non_target", "message": msg})

    # Sum of histogram must equal total rows
    hist_sum = sum(v.values())
    if hist_sum != es.n_total_dwarf:
        msg = (
            f"sum(yield_by_align_verdict)={hist_sum} != "
            f"n_total_dwarf={es.n_total_dwarf}"
        )
        log.warning("INVARIANT: %s", msg)
        violations.append({"check": "verdict_histogram_sum", "message": msg})

    return violations


def _check_quality_weight_bin_partition(
    report: JoinReport,
) -> List[Dict[str, Any]]:
    """yield_by_quality_weight_bin must partition all DWARF rows exactly."""
    hist_sum = sum(report.yield_by_quality_weight_bin.values())
    expected = report.exclusion_summary.n_total_dwarf
    if hist_sum != expected:
        msg = (
            f"sum(yield_by_quality_weight_bin)={hist_sum} != "
            f"n_total_dwarf={expected}"
        )
        log.warning("INVARIANT: %s", msg)
        return [{"check": "qw_bin_partition", "message": msg}]
    return []


def _check_quality_weight_audit(
    report: JoinReport,
) -> List[Dict[str, Any]]:
    """quality_weight and overlap_ratio must be in [0, 1]."""
    violations: List[Dict[str, Any]] = []
    audit = report.quality_weight_audit
    if audit.n_quality_weight_gt_1 > 0:
        msg = (
            f"quality_weight > 1.0 in {audit.n_quality_weight_gt_1} rows "
            f"(max={audit.max_quality_weight})"
        )
        log.warning("INVARIANT: %s", msg)
        violations.append({"check": "qw_bounds_gt1", "message": msg})
    if audit.n_quality_weight_lt_0 > 0:
        msg = f"quality_weight < 0.0 in {audit.n_quality_weight_lt_0} rows"
        log.warning("INVARIANT: %s", msg)
        violations.append({"check": "qw_bounds_lt0", "message": msg})
    if audit.n_align_overlap_ratio_gt_1 > 0:
        msg = (
            f"align_overlap_ratio > 1.0 in {audit.n_align_overlap_ratio_gt_1} rows "
            f"(max={audit.max_align_overlap_ratio})"
        )
        log.warning("INVARIANT: %s", msg)
        violations.append({"check": "overlap_ratio_bounds_gt1", "message": msg})
    return violations
