"""
Diagnostics — post-join aggregation, noise tagging, high-confidence
gating, and report assembly.

Stage 3.5 + §4 of the join pipeline.  Pure functions, no IO.
"""
from __future__ import annotations

import logging
import statistics
from collections import Counter
from typing import Dict, List, Optional

from join_oracles_to_ghidra_decompile.core.address_join import JoinResult
from join_oracles_to_ghidra_decompile.core.build_context import BuildContext
from join_oracles_to_ghidra_decompile.io.schema import (
    BuildContextSummary,
    DecompilerDistributions,
    HighConfidenceSlice,
    JoinedFunctionRow,
    JoinedVariableRow,
    JoinReport,
    JoinYieldCounts,
    VariableJoinStatus,
)
from join_oracles_to_ghidra_decompile.policy.profile import (
    JoinOraclesGhidraProfile,
)
from join_oracles_to_ghidra_decompile.policy.verdict import is_high_confidence

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Noise tagging
# ═══════════════════════════════════════════════════════════════════════════════

def _classify_aux(ghidra_name: str, aux_names: tuple) -> bool:
    """Return True if the Ghidra function name is a known aux function."""
    return ghidra_name.strip() in aux_names


def _classify_import_proxy(
    is_thunk: bool,
    is_plt_or_stub: bool,
) -> bool:
    return is_thunk or is_plt_or_stub


# ═══════════════════════════════════════════════════════════════════════════════
# Many-to-one detection
# ═══════════════════════════════════════════════════════════════════════════════

def _compute_many_to_one(
    rows: List[JoinedFunctionRow],
) -> None:
    """Mutate rows in-place: set n_dwarf_funcs_per_ghidra_func and fat flag."""
    counter: Counter = Counter()
    for row in rows:
        if row.ghidra_func_id:
            counter[row.ghidra_func_id] += 1

    for row in rows:
        if row.ghidra_func_id:
            count = counter[row.ghidra_func_id]
            row.n_dwarf_funcs_per_ghidra_func = count
            row.fat_function_multi_dwarf = count >= 2


# ═══════════════════════════════════════════════════════════════════════════════
# Convert JoinResults → JoinedFunctionRows with tags
# ═══════════════════════════════════════════════════════════════════════════════

def build_joined_function_rows(
    join_results: List[JoinResult],
    build_ctx: BuildContext,
    profile: JoinOraclesGhidraProfile,
) -> List[JoinedFunctionRow]:
    """Convert internal join results to output schema rows with all tags."""
    rows: List[JoinedFunctionRow] = []

    for jr in join_results:
        drow = jr.dwarf
        grow = jr.ghidra_row

        # Noise tags from Ghidra side (when matched)
        is_ext = grow.is_external_block if grow else False
        is_thk = grow.is_thunk if grow else False
        is_aux = _classify_aux(
            grow.name if grow else "", profile.aux_function_names,
        )
        is_import = _classify_import_proxy(
            grow.is_thunk if grow else False,
            grow.is_plt_or_stub if grow else False,
        )

        # Decompiler view fields (when matched)
        decomp_status = grow.decompile_status if grow else None
        cfg_comp = grow.cfg_completeness if grow else None
        bb = grow.bb_count if grow else None
        edges = grow.edge_count if grow else None
        w_tags = list(grow.warnings) if grow else []
        goto_c = grow.goto_count if grow else 0
        loc = grow.c_line_count if grow else 0
        temp_v = grow.temp_var_count if grow else 0
        ph_rate = grow.placeholder_type_rate if grow else 0.0

        # High-confidence gate
        hc = is_high_confidence(
            dwarf_oracle_verdict=drow.oracle_verdict,
            align_verdict=drow.align_verdict,
            align_n_candidates=drow.align_n_candidates,
            align_overlap_ratio=drow.align_overlap_ratio,
            ghidra_match_kind=jr.match_kind,
            is_external_block=is_ext,
            is_thunk=is_thk,
            is_aux_function=is_aux,
            is_import_proxy=is_import,
            cfg_completeness=cfg_comp,
            warning_tags=w_tags,
            fatal_warnings=profile.fatal_warnings,
        )

        row = JoinedFunctionRow(
            # Provenance
            binary_sha256=build_ctx.binary_sha256,
            job_id=build_ctx.job_id,
            test_case=build_ctx.test_case,
            opt=build_ctx.opt,
            variant=build_ctx.variant,
            builder_profile_id=build_ctx.builder_profile_id,
            ghidra_binary_sha256=build_ctx.ghidra_binary_sha256,
            ghidra_variant=build_ctx.ghidra_variant,
            # DWARF identity
            dwarf_function_id=drow.function_id,
            dwarf_function_name=drow.name,
            dwarf_function_name_norm=drow.name_norm,
            decl_file=drow.decl_file,
            decl_line=drow.decl_line,
            decl_column=drow.decl_column,
            low_pc=drow.low_pc,
            high_pc=drow.high_pc,
            dwarf_total_range_bytes=drow.total_range_bytes,
            dwarf_oracle_verdict=drow.oracle_verdict,
            # Alignment
            align_verdict=drow.align_verdict,
            align_overlap_ratio=drow.align_overlap_ratio,
            align_gap_count=drow.align_gap_count,
            align_n_candidates=drow.align_n_candidates,
            quality_weight=drow.quality_weight,
            align_reason_tags=drow.align_reason_tags,
            # Ghidra mapping
            ghidra_match_kind=jr.match_kind,
            ghidra_func_id=jr.ghidra_func_id,
            ghidra_entry_va=jr.ghidra_entry_va,
            ghidra_name=jr.ghidra_name,
            # Decompiler view
            decompile_status=decomp_status,
            cfg_completeness=cfg_comp,
            bb_count=bb,
            edge_count=edges,
            warning_tags=w_tags,
            goto_count=goto_c,
            loc_decompiled=loc,
            temp_var_count=temp_v,
            placeholder_type_rate=ph_rate,
            # Join diagnostics
            pc_overlap_bytes=jr.pc_overlap_bytes,
            pc_overlap_ratio=jr.pc_overlap_ratio,
            n_near_ties=jr.n_near_ties,
            join_warnings=jr.join_warnings,
            # Tags
            is_high_confidence=hc,
            is_aux_function=is_aux,
            is_import_proxy=is_import,
            is_external_block=is_ext,
            is_non_target=drow.is_non_target,
            is_thunk=is_thk,
        )
        rows.append(row)

    # Many-to-one pass
    _compute_many_to_one(rows)

    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# Stub variable rows
# ═══════════════════════════════════════════════════════════════════════════════

def build_variable_stubs(
    rows: List[JoinedFunctionRow],
) -> List[JoinedVariableRow]:
    """Generate stub variable rows — empty in v1."""
    # No real DWARF variable evidence available yet.
    return []


# ═══════════════════════════════════════════════════════════════════════════════
# Percentile helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _percentiles(
    values: List[float],
    keys: tuple = ("p25", "p50", "p75", "p90"),
    quantiles: tuple = (0.25, 0.5, 0.75, 0.9),
) -> Dict[str, float]:
    """Compute percentile summary dict from a list of floats."""
    if not values:
        return {k: 0.0 for k in keys}
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    result: Dict[str, float] = {}
    for k, q in zip(keys, quantiles):
        idx = min(int(q * n), n - 1)
        result[k] = round(sorted_vals[idx], 6)
    return result


def _quality_weight_bin(qw: float) -> str:
    """Bin a quality_weight value."""
    if qw >= 0.8:
        return "[0.8,1.0]"
    if qw >= 0.5:
        return "[0.5,0.8)"
    return "[0,0.5)"


def _n_candidates_bin(n: Optional[int]) -> str:
    """Bin n_candidates count."""
    if n is None:
        return "none"
    if n == 1:
        return "1"
    if n <= 3:
        return "2-3"
    return "4+"


# ═══════════════════════════════════════════════════════════════════════════════
# Report assembly
# ═══════════════════════════════════════════════════════════════════════════════

def build_join_report(
    rows: List[JoinedFunctionRow],
    build_ctx: BuildContext,
    profile: JoinOraclesGhidraProfile,
) -> JoinReport:
    """Assemble the join_report.json from joined function rows."""

    n_total = len(rows)

    # ── Yield counts ──────────────────────────────────────────────────────
    match_counts: Counter = Counter()
    for r in rows:
        match_counts[r.ghidra_match_kind] += 1

    n_strong = match_counts.get("JOINED_STRONG", 0)
    n_weak = match_counts.get("JOINED_WEAK", 0)
    n_joined = n_strong + n_weak
    n_no_range = match_counts.get("NO_RANGE", 0)
    n_multi = match_counts.get("MULTI_MATCH", 0)
    n_no_match = match_counts.get("NO_MATCH", 0)

    yield_counts = JoinYieldCounts(
        n_dwarf_funcs=n_total,
        n_joined_to_ghidra=n_joined,
        n_joined_strong=n_strong,
        n_joined_weak=n_weak,
        n_no_range=n_no_range,
        n_multi_match=n_multi,
        n_no_match=n_no_match,
    )

    # ── High-confidence slice ─────────────────────────────────────────────
    hc_count = sum(1 for r in rows if r.is_high_confidence)
    hc_rate = hc_count / max(n_total, 1)

    # By opt (the join is single-binary so opt is constant, but kept for
    # downstream aggregations across multiple invocations)
    hc_by_opt: Dict[str, float] = {}
    opt_groups: Dict[str, List[JoinedFunctionRow]] = {}
    for r in rows:
        opt_groups.setdefault(r.opt, []).append(r)
    for opt, group in opt_groups.items():
        gc = sum(1 for g in group if g.is_high_confidence)
        hc_by_opt[opt] = round(gc / max(len(group), 1), 6)

    high_confidence = HighConfidenceSlice(
        total=n_total,
        high_confidence_count=hc_count,
        yield_rate=round(hc_rate, 6),
        by_opt=hc_by_opt,
    )

    # ── Stratifications ───────────────────────────────────────────────────
    yield_by_align: Counter = Counter()
    yield_by_ncand: Counter = Counter()
    yield_by_qw: Counter = Counter()
    yield_by_opt: Counter = Counter()

    for r in rows:
        yield_by_align[r.align_verdict or "NONE"] += 1
        yield_by_ncand[_n_candidates_bin(r.align_n_candidates)] += 1
        yield_by_qw[_quality_weight_bin(r.quality_weight)] += 1
        yield_by_opt[r.opt] += 1

    # ── Decompiler distributions ──────────────────────────────────────────
    cfg_comp_counter: Counter = Counter()
    warning_counter: Counter = Counter()
    goto_densities: List[float] = []
    ph_rates: List[float] = []

    joined_rows = [r for r in rows if r.ghidra_func_id is not None]
    for r in joined_rows:
        cfg_comp_counter[r.cfg_completeness or "UNKNOWN"] += 1
        for w in r.warning_tags:
            warning_counter[w] += 1
        goto_densities.append(r.goto_count / max(r.loc_decompiled, 1))
        ph_rates.append(r.placeholder_type_rate)

    n_joined_total = max(len(joined_rows), 1)
    cfg_fracs = {
        k: round(v / n_joined_total, 6)
        for k, v in sorted(cfg_comp_counter.items())
    }

    # Many-to-one stats
    ghidra_ids_with_multi = set()
    for r in rows:
        if r.fat_function_multi_dwarf and r.ghidra_func_id:
            ghidra_ids_with_multi.add(r.ghidra_func_id)

    decompiler = DecompilerDistributions(
        cfg_completeness_fractions=cfg_fracs,
        warning_prevalence=dict(sorted(warning_counter.items())),
        goto_density_percentiles=_percentiles(goto_densities),
        placeholder_type_rate_percentiles=_percentiles(ph_rates),
        n_fat_functions=sum(
            1 for r in rows if r.fat_function_multi_dwarf
        ),
        n_many_to_one_ghidra_funcs=len(ghidra_ids_with_multi),
    )

    # ── Variable join status ──────────────────────────────────────────────
    var_status = VariableJoinStatus(
        implemented=False,
        reason="DWARF variable extraction not available in oracle_dwarf schema ≤0.2",
        n_stub_rows=0,
    )

    # ── Assemble report ───────────────────────────────────────────────────
    return JoinReport(
        profile_id=profile.profile_id,
        binary_sha256=build_ctx.binary_sha256,
        build_context=BuildContextSummary(
            binary_sha256=build_ctx.binary_sha256,
            job_id=build_ctx.job_id,
            test_case=build_ctx.test_case,
            opt=build_ctx.opt,
            variant=build_ctx.variant,
            builder_profile_id=build_ctx.builder_profile_id,
            ghidra_binary_sha256=build_ctx.ghidra_binary_sha256,
            ghidra_variant=build_ctx.ghidra_variant,
        ),
        yield_counts=yield_counts,
        high_confidence=high_confidence,
        yield_by_align_verdict=dict(sorted(yield_by_align.items())),
        yield_by_n_candidates_bin=dict(sorted(yield_by_ncand.items())),
        yield_by_quality_weight_bin=dict(sorted(yield_by_qw.items())),
        yield_by_opt=dict(sorted(yield_by_opt.items())),
        yield_by_match_kind=dict(sorted(match_counts.items())),
        decompiler=decompiler,
        variable_join=var_status,
    )
