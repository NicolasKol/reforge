"""
Address join — DWARF→Ghidra function mapping by PC-range overlap.

Stage 3 of the join pipeline.  Pure functions, no IO.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from join_oracles_to_ghidra_decompile.core.build_context import BuildContext
from join_oracles_to_ghidra_decompile.core.function_table import (
    DwarfFunctionRow,
    GhidraFunctionRow,
    IntervalEntry,
)
from join_oracles_to_ghidra_decompile.policy.profile import (
    JoinOraclesGhidraProfile,
)
from join_oracles_to_ghidra_decompile.policy.verdict import classify_match_kind

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Overlap candidate
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class OverlapCandidate:
    """One Ghidra function overlapping a DWARF range."""

    function_id: str
    entry_va: int
    name: str
    overlap_bytes: int
    is_thunk: bool = False
    is_external_block: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# Join result row (internal)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class JoinResult:
    """Internal join result for one DWARF function.

    Converted to ``JoinedFunctionRow`` at the schema boundary.
    """

    dwarf: DwarfFunctionRow
    match_kind: str = ""

    ghidra_func_id: Optional[str] = None
    ghidra_entry_va: Optional[int] = None
    ghidra_name: Optional[str] = None

    pc_overlap_bytes: int = 0
    pc_overlap_ratio: float = 0.0
    n_near_ties: int = 0
    join_warnings: List[str] = field(default_factory=list)

    # Ghidra-side metrics (populated when matched)
    ghidra_row: Optional[GhidraFunctionRow] = None


# ═══════════════════════════════════════════════════════════════════════════════
# Interval overlap queries
# ═══════════════════════════════════════════════════════════════════════════════

def _find_overlapping_ghidra(
    dwarf_ranges: List[Tuple[int, int]],
    interval_index: List[IntervalEntry],
    ghidra_table: Dict[str, GhidraFunctionRow],
) -> Dict[str, int]:
    """Find all Ghidra functions whose body overlaps the DWARF ranges.

    Returns a dict of ``{ghidra_function_id: total_overlap_bytes}``.
    """
    overlaps: Dict[str, int] = {}

    for d_low, d_high in dwarf_ranges:
        for entry in interval_index:
            # Early termination: if entry starts beyond DWARF high, done
            if entry.body_start >= d_high:
                break

            # Skip entries that end before DWARF range starts
            if entry.body_end <= d_low:
                continue

            # Compute overlap
            overlap_start = max(d_low, entry.body_start)
            overlap_end = min(d_high, entry.body_end)
            overlap_bytes = max(0, overlap_end - overlap_start)

            if overlap_bytes > 0:
                overlaps[entry.function_id] = (
                    overlaps.get(entry.function_id, 0) + overlap_bytes
                )

    return overlaps


# ═══════════════════════════════════════════════════════════════════════════════
# Main join logic
# ═══════════════════════════════════════════════════════════════════════════════

def join_dwarf_to_ghidra(
    dwarf_table: Dict[str, DwarfFunctionRow],
    ghidra_table: Dict[str, GhidraFunctionRow],
    interval_index: List[IntervalEntry],
    profile: JoinOraclesGhidraProfile,
) -> List[JoinResult]:
    """Execute the DWARF→Ghidra function mapping (Stage 3).

    One *JoinResult* per DWARF function.  Functions without ranges get
    ``NO_RANGE``; those with ranges that find no overlap get ``NO_MATCH``.
    Near-ties are detected and flagged as ``MULTI_MATCH``.

    No fabrication of joins for ``NO_RANGE`` rows — they are tagged and
    left unmapped.

    Parameters
    ----------
    dwarf_table:
        Indexed DWARF function table from Stage 1.
    ghidra_table:
        Indexed Ghidra function table from Stage 2.
    interval_index:
        Sorted body-range index from Stage 2.
    profile:
        Join profile with thresholds.

    Returns
    -------
    List of ``JoinResult``, one per DWARF function.
    """
    results: List[JoinResult] = []

    for fid, drow in dwarf_table.items():
        # ── NO_RANGE fast path ────────────────────────────────────────────
        if not drow.has_range:
            results.append(JoinResult(
                dwarf=drow,
                match_kind="NO_RANGE",
                join_warnings=["DWARF_RANGE_MISSING"],
            ))
            continue

        # ── Find overlapping Ghidra functions ─────────────────────────────
        overlaps = _find_overlapping_ghidra(
            drow.ranges, interval_index, ghidra_table,
        )

        if not overlaps:
            results.append(JoinResult(
                dwarf=drow,
                match_kind="NO_MATCH",
                join_warnings=["NO_GHIDRA_OVERLAP"],
            ))
            continue

        # ── Build + sort candidates ───────────────────────────────────────
        candidates: List[OverlapCandidate] = []
        for gfid, obytes in overlaps.items():
            grow = ghidra_table.get(gfid)
            if grow is None:
                continue
            candidates.append(OverlapCandidate(
                function_id=gfid,
                entry_va=grow.entry_va,
                name=grow.name,
                overlap_bytes=obytes,
                is_thunk=grow.is_thunk,
                is_external_block=grow.is_external_block,
            ))

        if not candidates:
            results.append(JoinResult(
                dwarf=drow,
                match_kind="NO_MATCH",
                join_warnings=["NO_GHIDRA_OVERLAP"],
            ))
            continue

        # Sort: max overlap_bytes, min distance to DWARF low_pc,
        #        prefer non-thunk, non-external
        d_low = drow.low_pc or 0
        candidates.sort(key=lambda c: (
            -c.overlap_bytes,
            abs(c.entry_va - d_low),
            c.is_thunk,
            c.is_external_block,
        ))

        best = candidates[0]
        best_overlap = best.overlap_bytes
        pc_ratio = best_overlap / max(drow.total_range_bytes, 1)

        # ── Near-tie detection ────────────────────────────────────────────
        threshold_bytes = best_overlap * profile.near_tie_epsilon
        near_ties = [
            c for c in candidates[1:]
            if (best_overlap - c.overlap_bytes) <= threshold_bytes
        ]
        n_near_ties = len(near_ties)

        # ── Classify ─────────────────────────────────────────────────────
        match_kind = classify_match_kind(
            pc_overlap_ratio=pc_ratio,
            n_near_ties=n_near_ties,
            has_range=True,
            strong_threshold=profile.strong_overlap_threshold,
            weak_threshold=profile.weak_overlap_threshold,
        )

        # ── Join warnings ─────────────────────────────────────────────────
        warnings: List[str] = []
        if n_near_ties > 0:
            warnings.append("NEAR_TIE_CANDIDATES")
        if pc_ratio < profile.weak_overlap_threshold:
            warnings.append("LOW_PC_OVERLAP")

        grow_best = ghidra_table.get(best.function_id)

        results.append(JoinResult(
            dwarf=drow,
            match_kind=match_kind.value if hasattr(match_kind, 'value') else str(match_kind),
            ghidra_func_id=best.function_id,
            ghidra_entry_va=best.entry_va,
            ghidra_name=best.name,
            pc_overlap_bytes=best_overlap,
            pc_overlap_ratio=pc_ratio,
            n_near_ties=n_near_ties,
            join_warnings=warnings,
            ghidra_row=grow_best,
        ))

    log.info("Join completed: %d DWARF functions processed", len(results))
    return results
