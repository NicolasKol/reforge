"""
Verdict — classification functions for the oracle↔Ghidra join.

Pure functions; no IO, no state.
"""
from __future__ import annotations

from typing import List, Optional

from data.enums import GhidraMatchKind


def classify_match_kind(
    pc_overlap_ratio: float,
    n_near_ties: int,
    has_range: bool,
    *,
    strong_threshold: float = 0.9,
    weak_threshold: float = 0.3,
) -> GhidraMatchKind:
    """Classify a DWARF→Ghidra function mapping by PC-range overlap.

    Parameters
    ----------
    pc_overlap_ratio:
        ``overlap_bytes / dwarf_total_range_bytes`` for the best candidate.
    n_near_ties:
        Number of Ghidra candidates within ε of the best overlap.
    has_range:
        Whether the DWARF function has usable address ranges.
    strong_threshold:
        Minimum overlap ratio for JOINED_STRONG.
    weak_threshold:
        Minimum overlap ratio for JOINED_WEAK.
    """
    if not has_range:
        return GhidraMatchKind.NO_RANGE

    if pc_overlap_ratio <= 0.0:
        return GhidraMatchKind.NO_MATCH

    if n_near_ties >= 1:
        return GhidraMatchKind.MULTI_MATCH

    if pc_overlap_ratio >= strong_threshold:
        return GhidraMatchKind.JOINED_STRONG

    if pc_overlap_ratio >= weak_threshold:
        return GhidraMatchKind.JOINED_WEAK

    return GhidraMatchKind.NO_MATCH


def is_high_confidence(
    dwarf_oracle_verdict: str,
    align_verdict: Optional[str],
    align_n_candidates: Optional[int],
    align_overlap_ratio: Optional[float],
    ghidra_match_kind: str,
    is_external_block: bool,
    is_thunk: bool,
    is_aux_function: bool,
    is_import_proxy: bool,
    cfg_completeness: Optional[str],
    warning_tags: List[str],
    fatal_warnings: tuple[str, ...],
) -> tuple[bool, Optional[str]]:
    """Return (is_hc, reject_reason) for high-confidence classification.

    High-confidence rows form the "gold" subset for LLM evaluation
    tasks where we need maximal alignment certainty.

    The *reject_reason* is the **first** gate that fails, or ``None``
    when all gates pass.  This provides a failure-ladder for diagnostics.
    """
    # DWARF oracle must be ACCEPT (not WARN — provenance uncertainty)
    if dwarf_oracle_verdict != "ACCEPT":
        return False, "ORACLE_NOT_ACCEPT"

    # Alignment: perfect unique match
    if align_verdict != "MATCH":
        return False, "ALIGN_NOT_MATCH"
    if align_n_candidates != 1:
        return False, "ALIGN_NOT_UNIQUE"
    if align_overlap_ratio is None or align_overlap_ratio < 0.95:
        return False, "ALIGN_RATIO_LOW"

    # Ghidra join: strong overlap
    if ghidra_match_kind != GhidraMatchKind.JOINED_STRONG.value:
        return False, "NOT_JOINED_STRONG"

    # Not noise / infrastructure
    if is_external_block or is_thunk or is_aux_function or is_import_proxy:
        return False, "IS_NOISE_FUNCTION"

    # CFG completeness must not be LOW
    if cfg_completeness == "LOW":
        return False, "CFG_LOW"

    # No fatal warnings
    if any(w in fatal_warnings for w in warning_tags):
        return False, "FATAL_WARNING"

    return True, None
