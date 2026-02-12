"""
Candidate generation and overlap scoring.

For each DWARF target function, score all TS function candidates
by scanning the TS function's .i line span through the origin map
and counting hits against the DWARF line evidence multiset.

Scoring uses a *forward-map scan*: for each .i line in a TS function
span [start_line, end_line], look up the origin (file, line) and check
if it appears in the DWARF evidence.  This avoids building an inverse
index.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from join_dwarf_ts.core.origin_map import OriginMap, query_forward


@dataclass(frozen=True)
class CandidateResult:
    """Scored alignment candidate: one TS function for one DWARF function."""

    ts_func_id: str
    tu_path: str
    function_name: Optional[str]
    context_hash: str

    overlap_count: int        # hits in DWARF evidence
    total_count: int          # sum of DWARF line_rows counts
    overlap_ratio: float      # overlap_count / total_count
    gap_count: int            # total_count - overlap_count

    # TS function span for tie-breaking
    span_size: int            # end_byte - start_byte
    start_byte: int


@dataclass
class TsFunctionInfo:
    """Minimal TS function info needed for candidate scoring."""

    ts_func_id: str
    tu_path: str
    name: Optional[str]
    context_hash: str
    start_line: int           # 0-based .i line
    end_line: int             # 0-based .i line
    start_byte: int
    end_byte: int


def score_candidates(
    dwarf_evidence: Dict[Tuple[str, int], int],
    ts_functions: List[TsFunctionInfo],
    origin_map: OriginMap,
) -> List[CandidateResult]:
    """
    Score all TS functions in a single TU against a DWARF function's
    line evidence.

    Parameters
    ----------
    dwarf_evidence : Dict[Tuple[str, int], int]
        Multiset of (file_path, line_number) → count from DWARF line_rows.
    ts_functions : List[TsFunctionInfo]
        TS functions from this TU.
    origin_map : OriginMap
        Forward map for this TU.

    Returns
    -------
    List[CandidateResult]
        One entry per TS function that has overlap_count > 0.
        Sorted by tie-break order (highest overlap_ratio first).
    """
    total_count = sum(dwarf_evidence.values())
    if total_count == 0:
        return []

    results: List[CandidateResult] = []

    for ts_func in ts_functions:
        overlap_count = 0

        # Scan .i lines within the TS function span
        for i_line in range(ts_func.start_line, ts_func.end_line + 1):
            origin = query_forward(origin_map, i_line)
            if origin is None:
                continue
            count = dwarf_evidence.get(origin, 0)
            if count > 0:
                overlap_count += count

        if overlap_count == 0:
            continue

        overlap_ratio = overlap_count / total_count
        gap_count = total_count - overlap_count
        span_size = ts_func.end_byte - ts_func.start_byte

        results.append(CandidateResult(
            ts_func_id=ts_func.ts_func_id,
            tu_path=ts_func.tu_path,
            function_name=ts_func.name,
            context_hash=ts_func.context_hash,
            overlap_count=overlap_count,
            total_count=total_count,
            overlap_ratio=round(overlap_ratio, 6),
            gap_count=gap_count,
            span_size=span_size,
            start_byte=ts_func.start_byte,
        ))

    # Sort by tie-break order:
    # 1. highest overlap_ratio
    # 2. highest overlap_count
    # 3. smallest span
    # 4. deterministic (tu_path, start_byte)
    results.sort(key=lambda c: (
        -c.overlap_ratio,
        -c.overlap_count,
        c.span_size,
        c.tu_path,
        c.start_byte,
    ))

    return results


def select_best(
    all_candidates: List[CandidateResult],
    overlap_threshold: float,
    epsilon: float,
    min_overlap_lines: int,
) -> Tuple[Optional[CandidateResult], List[CandidateResult], List[str]]:
    """
    Select the best candidate and determine verdict reasons.

    Parameters
    ----------
    all_candidates : List[CandidateResult]
        Pre-sorted candidates across all TUs (best first).
    overlap_threshold : float
        Minimum overlap_ratio for MATCH (e.g. 0.7).
    epsilon : float
        Score tolerance for AMBIGUOUS detection (e.g. 0.02).
    min_overlap_lines : int
        Minimum overlap_count to be considered.

    Returns
    -------
    (best, near_ties, reasons)
        best: top candidate or None
        near_ties: candidates within epsilon of best
        reasons: list of reason strings
    """
    reasons: List[str] = []

    if not all_candidates:
        reasons.append("NO_CANDIDATES")
        return None, [], reasons

    best = all_candidates[0]

    if best.overlap_count < min_overlap_lines:
        reasons.append("NO_CANDIDATES")
        return None, [], reasons

    if best.overlap_ratio < overlap_threshold:
        reasons.append("LOW_OVERLAP_RATIO")

    # Find near-ties (within epsilon of best)
    near_ties = [
        c for c in all_candidates[1:]
        if abs(c.overlap_ratio - best.overlap_ratio) <= epsilon
    ]

    if near_ties:
        reasons.append("NEAR_TIE")
    elif "LOW_OVERLAP_RATIO" not in reasons:
        reasons.append("UNIQUE_BEST")

    if best.gap_count > 0:
        reasons.append("PC_LINE_GAP")

    return best, near_ties, reasons


def detect_header_replication(
    best: CandidateResult,
    near_ties: List[CandidateResult],
) -> bool:
    """
    Check if the best candidate and near-ties represent header
    replication (same context_hash across different TUs).

    Returns True if collision detected.
    """
    if not near_ties:
        return False

    best_hash = best.context_hash
    best_tu = best.tu_path

    for tie in near_ties:
        if tie.context_hash == best_hash and tie.tu_path != best_tu:
            return True

    return False
