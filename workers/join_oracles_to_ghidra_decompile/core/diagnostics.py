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
    CollisionSummary,
    ConfidenceFunnel,
    DecompilerDistributions,
    ExclusionSummary,
    HighConfidenceSlice,
    JoinedFunctionRow,
    JoinedVariableRow,
    JoinReport,
    JoinYieldCounts,
    QualityWeightAudit,
    VariableJoinStatus,
)
from join_oracles_to_ghidra_decompile.policy.profile import (
    JoinOraclesGhidraProfile,
)
from join_oracles_to_ghidra_decompile.policy.verdict import is_high_confidence

from data.binning import (
    overlap_ratio_bin,
    quality_weight_bin_detailed,
)
from data.noise_lists import normalize_glibc_name

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Noise tagging
# ═══════════════════════════════════════════════════════════════════════════════

def _classify_aux(ghidra_name: str, aux_names: tuple) -> bool:
    """Return True if the Ghidra function name is a known aux function."""
    name_clean = ghidra_name.strip()
    return normalize_glibc_name(name_clean) in aux_names


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

        # High-confidence gate (returns bool + reject reason)
        hc, hc_reject = is_high_confidence(
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

        # Confidence tier (orthogonal to is_high_confidence)
        tier = _assign_confidence_tier(
            hc=hc,
            match_kind=jr.match_kind,
            eligible_for_gold=drow.eligible_for_gold,
        )

        # Upstream collapse reason
        collapse = _detect_upstream_collapse(drow)

        # Decompiler quality flags
        dq_flags = _decompiler_quality_flags(
            cfg_comp, w_tags, goto_c, loc, ph_rate, profile.fatal_warnings,
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
            # Eligibility
            eligible_for_join=drow.eligible_for_join,
            eligible_for_gold=drow.eligible_for_gold,
            exclusion_reason=drow.exclusion_reason,
            # Confidence
            confidence_tier=tier,
            hc_reject_reason=hc_reject,
            upstream_collapse_reason=collapse,
            decompiler_quality_flags=dq_flags,
        )
        rows.append(row)

    # Many-to-one pass
    _compute_many_to_one(rows)

    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# Confidence tier assignment
# ═══════════════════════════════════════════════════════════════════════════════

def _assign_confidence_tier(
    hc: bool,
    match_kind: str,
    eligible_for_gold: bool,
) -> str:
    """Assign a confidence tier label (orthogonal to is_high_confidence).

    GOLD   — is_high_confidence is True.
    SILVER — not HC but JOINED_STRONG and gold-eligible.
    BRONZE — JOINED_STRONG or JOINED_WEAK but not gold-eligible.
    ""     — everything else (NO_RANGE, NO_MATCH, MULTI_MATCH).
    """
    if hc:
        return "GOLD"
    if match_kind == "JOINED_STRONG" and eligible_for_gold:
        return "SILVER"
    if match_kind in ("JOINED_STRONG", "JOINED_WEAK"):
        return "BRONZE"
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
# Upstream collapse detection
# ═══════════════════════════════════════════════════════════════════════════════

def _detect_upstream_collapse(drow) -> Optional[str]:
    """Detect when a function was lost by upstream oracle/alignment stages.

    Returns a reason string, or None if no upstream collapse detected.
    """
    if not drow.has_range:
        return "NO_DWARF_RANGE"
    if drow.is_non_target:
        return "ALIGNMENT_NON_TARGET"
    if drow.oracle_verdict == "REJECT":
        return "DWARF_ORACLE_REJECT"
    if drow.align_verdict == "DISAPPEAR":
        return "ALIGNMENT_DISAPPEAR"
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Decompiler quality flags
# ═══════════════════════════════════════════════════════════════════════════════

_HIGH_GOTO_DENSITY_THRESHOLD = 0.1
_HIGH_PLACEHOLDER_THRESHOLD = 0.3

def _decompiler_quality_flags(
    cfg_completeness: Optional[str],
    warning_tags: List[str],
    goto_count: int,
    loc_decompiled: int,
    placeholder_type_rate: float,
    fatal_warnings: tuple[str, ...],
) -> List[str]:
    """Return a list of decompiler quality concern flags."""
    flags: List[str] = []

    if cfg_completeness == "LOW":
        flags.append("CFG_LOW")

    if any(w in fatal_warnings for w in warning_tags):
        flags.append("FATAL_WARNING")

    goto_density = goto_count / max(loc_decompiled, 1)
    if goto_density > _HIGH_GOTO_DENSITY_THRESHOLD:
        flags.append("HIGH_GOTO_DENSITY")

    if placeholder_type_rate > _HIGH_PLACEHOLDER_THRESHOLD:
        flags.append("HIGH_PLACEHOLDER_TYPES")

    return flags


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
    """Bin a quality_weight value (DEPRECATED — kept for reference)."""
    # Superseded by data.binning.quality_weight_bin_detailed
    raise NotImplementedError("Use data.binning.quality_weight_bin_detailed")


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

    # ── Exclusion summary (Phase 0) ───────────────────────────────────────
    excl_reason_counts: Counter = Counter()
    n_eligible_join = 0
    n_eligible_gold = 0
    for r in rows:
        if r.exclusion_reason:
            excl_reason_counts[r.exclusion_reason] += 1
        if r.eligible_for_join:
            n_eligible_join += 1
        if r.eligible_for_gold:
            n_eligible_gold += 1

    exclusion_summary = ExclusionSummary(
        n_total_dwarf=n_total,
        n_no_range=excl_reason_counts.get("NO_RANGE", 0),
        n_non_target=excl_reason_counts.get("NON_TARGET", 0),
        n_noise_aux=excl_reason_counts.get("NOISE_AUX", 0),
        n_oracle_reject=sum(
            1 for r in rows
            if r.eligible_for_join and not r.eligible_for_gold
            and r.dwarf_oracle_verdict != "ACCEPT"
        ),
        n_eligible_for_join=n_eligible_join,
        n_eligible_for_gold=n_eligible_gold,
        by_exclusion_reason=dict(sorted(excl_reason_counts.items())),
    )

    # ── High-confidence slice (denominator: eligible_for_gold) ────────────
    hc_count = sum(1 for r in rows if r.is_high_confidence)
    hc_denom = max(n_eligible_gold, 1)
    hc_rate = hc_count / hc_denom

    # By opt
    hc_by_opt: Dict[str, float] = {}
    opt_groups: Dict[str, List[JoinedFunctionRow]] = {}
    for r in rows:
        opt_groups.setdefault(r.opt, []).append(r)
    for opt, group in opt_groups.items():
        gc = sum(1 for g in group if g.is_high_confidence)
        gold_in_opt = sum(1 for g in group if g.eligible_for_gold)
        hc_by_opt[opt] = round(gc / max(gold_in_opt, 1), 6)

    high_confidence = HighConfidenceSlice(
        total=n_eligible_gold,
        high_confidence_count=hc_count,
        yield_rate=round(hc_rate, 6),
        by_opt=hc_by_opt,
    )

    # ── Confidence funnel ─────────────────────────────────────────────────
    gold_eligible_rows = [r for r in rows if r.eligible_for_gold]
    funnel = _build_confidence_funnel(gold_eligible_rows, profile)

    # ── Collision summary ─────────────────────────────────────────────────
    collision = _build_collision_summary(rows)

    # ── Stratifications ───────────────────────────────────────────────────
    yield_by_align: Counter = Counter()
    yield_by_ncand: Counter = Counter()
    yield_by_qw: Counter = Counter()
    yield_by_overlap: Counter = Counter()
    yield_by_opt: Counter = Counter()

    # ── Quality-weight audit counters ───────────────────────────────────────
    n_qw_gt_1 = 0
    n_qw_lt_0 = 0
    max_qw = 0.0
    n_overlap_gt_1 = 0
    max_overlap = 0.0

    for r in rows:
        # Align-verdict histogram (exclusion-aware)
        if r.exclusion_reason:
            yield_by_align[r.exclusion_reason] += 1
        else:
            yield_by_align[r.align_verdict or "NONE"] += 1

        yield_by_ncand[_n_candidates_bin(r.align_n_candidates)] += 1

        # quality_weight bins — use DWARF has_range (derived from
        # exclusion_reason == "NO_RANGE" which is the DWARF property,
        # NOT the join-outcome ghidra_match_kind).
        dwarf_has_range = r.exclusion_reason != "NO_RANGE"
        qw_for_bin: Optional[float] = (
            r.quality_weight if r.align_verdict == "MATCH" else None
        )
        yield_by_qw[
            quality_weight_bin_detailed(
                qw_for_bin,
                has_range=dwarf_has_range,
                align_verdict=r.align_verdict,
            )
        ] += 1

        # align_overlap_ratio bins
        yield_by_overlap[
            overlap_ratio_bin(
                r.align_overlap_ratio
                if r.align_verdict == "MATCH"
                else None
            )
        ] += 1

        yield_by_opt[r.opt] += 1

        # Audit counters
        if r.quality_weight > 1.0:
            n_qw_gt_1 += 1
        if r.quality_weight < 0.0:
            n_qw_lt_0 += 1
        max_qw = max(max_qw, r.quality_weight)

        if r.align_overlap_ratio is not None:
            if r.align_overlap_ratio > 1.0:
                n_overlap_gt_1 += 1
            max_overlap = max(max_overlap, r.align_overlap_ratio)

    qw_audit = QualityWeightAudit(
        n_quality_weight_gt_1=n_qw_gt_1,
        n_quality_weight_lt_0=n_qw_lt_0,
        max_quality_weight=round(max_qw, 9),
        n_align_overlap_ratio_gt_1=n_overlap_gt_1,
        max_align_overlap_ratio=round(max_overlap, 9),
    )

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
        exclusion_summary=exclusion_summary,
        confidence_funnel=funnel,
        collision_summary=collision,
        yield_by_align_verdict=dict(sorted(yield_by_align.items())),
        yield_by_n_candidates_bin=dict(sorted(yield_by_ncand.items())),
        yield_by_quality_weight_bin=dict(sorted(yield_by_qw.items())),
        yield_by_align_overlap_ratio_bin=dict(sorted(yield_by_overlap.items())),
        yield_by_opt=dict(sorted(yield_by_opt.items())),
        yield_by_match_kind=dict(sorted(match_counts.items())),
        quality_weight_audit=qw_audit,
        decompiler=decompiler,
        variable_join=var_status,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Confidence funnel builder
# ═══════════════════════════════════════════════════════════════════════════════

def _build_confidence_funnel(
    gold_eligible_rows: List[JoinedFunctionRow],
    profile: JoinOraclesGhidraProfile,
) -> ConfidenceFunnel:
    """Build gate-by-gate attrition counts for the confidence funnel.

    Each counter represents the number of rows that **pass** that gate
    (cumulative AND of all prior gates).
    """
    n = len(gold_eligible_rows)

    # Gate 1: oracle ACCEPT (should be all, since eligible_for_gold requires it)
    pass_oracle = [r for r in gold_eligible_rows if r.dwarf_oracle_verdict == "ACCEPT"]
    # Gate 2: align MATCH
    pass_align = [r for r in pass_oracle if r.align_verdict == "MATCH"]
    # Gate 3: unique candidate
    pass_unique = [r for r in pass_align if r.align_n_candidates == 1]
    # Gate 4: overlap ratio >= 0.95
    pass_ratio = [
        r for r in pass_unique
        if r.align_overlap_ratio is not None and r.align_overlap_ratio >= 0.95
    ]
    # Gate 5: JOINED_STRONG
    pass_strong = [r for r in pass_ratio if r.ghidra_match_kind == "JOINED_STRONG"]
    # Gate 6: not noise
    pass_noise = [
        r for r in pass_strong
        if not (r.is_external_block or r.is_thunk or r.is_aux_function or r.is_import_proxy)
    ]
    # Gate 7: CFG not LOW
    pass_cfg = [r for r in pass_noise if r.cfg_completeness != "LOW"]
    # Gate 8: no fatal warnings
    fatal = set(profile.fatal_warnings)
    pass_fatal = [r for r in pass_cfg if not any(w in fatal for w in r.warning_tags)]

    return ConfidenceFunnel(
        n_eligible_for_gold=n,
        n_pass_oracle_accept=len(pass_oracle),
        n_pass_align_match=len(pass_align),
        n_pass_align_unique=len(pass_unique),
        n_pass_align_ratio=len(pass_ratio),
        n_pass_joined_strong=len(pass_strong),
        n_pass_not_noise=len(pass_noise),
        n_pass_cfg_not_low=len(pass_cfg),
        n_pass_no_fatal_warnings=len(pass_fatal),
        n_high_confidence=len(pass_fatal),  # final gate = HC
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Collision summary builder
# ═══════════════════════════════════════════════════════════════════════════════

def _build_collision_summary(
    rows: List[JoinedFunctionRow],
    top_n: int = 5,
) -> CollisionSummary:
    """Build many-to-one collision diagnostics."""
    ghidra_to_dwarf: Dict[str, List[str]] = {}
    for r in rows:
        if r.ghidra_func_id:
            ghidra_to_dwarf.setdefault(r.ghidra_func_id, []).append(
                r.dwarf_function_id
            )

    n_unique = len(ghidra_to_dwarf)
    multi = {gid: dids for gid, dids in ghidra_to_dwarf.items() if len(dids) >= 2}
    max_per = max((len(dids) for dids in ghidra_to_dwarf.values()), default=0)

    # Top collisions (sorted by count descending)
    sorted_multi = sorted(multi.items(), key=lambda x: -len(x[1]))[:top_n]
    top_collisions = [
        {"ghidra_func_id": gid, "n_dwarf": len(dids), "dwarf_ids": dids}
        for gid, dids in sorted_multi
    ]

    return CollisionSummary(
        n_unique_ghidra_funcs_matched=n_unique,
        n_ghidra_funcs_with_multi_dwarf=len(multi),
        max_dwarf_per_ghidra=max_per,
        top_collisions=top_collisions,
    )
