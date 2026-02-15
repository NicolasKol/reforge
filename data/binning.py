"""
Canonical binning functions for quality_weight and overlap_ratio.

These are the **single source of truth** used by both:
- ``join_oracles_to_ghidra_decompile.core.diagnostics`` (report aggregation)
- analysis notebooks (data/results/)

Bin edges are chosen to align with the confidence-tier gates in
``join_oracles_to_ghidra_decompile.policy.verdict.is_high_confidence``:

    ==1.0       → perfect single-candidate match  (GOLD tier)
    [0.95,1.0)  → near-perfect                    (HIGH gate threshold)
    [0.8,0.95)  → strong but degraded
    [0.5,0.8)   → moderate quality
    [0,0.5)     → poor quality
    none        → missing / not applicable

Semantics
---------
``quality_weight`` is only meaningful when ``align_verdict == "MATCH"``.
For non-MATCH rows (including NO_RANGE) the stored value ``0.0`` is a
placeholder and should be treated as missing.  Callers decide whether to
pass ``None`` (→ ``"none"`` bin) or the raw ``0.0`` (→ ``"[0,0.5)"`` bin)
depending on context.
"""
from __future__ import annotations

from typing import List, Optional

# ── quality_weight bins ───────────────────────────────────────────────────────

QUALITY_WEIGHT_BIN_ORDER: List[str] = [
    "==1.0",
    "[0.95,1.0)",
    "[0.8,0.95)",
    "[0.5,0.8)",
    "[0,0.5)",
    "none",
]

QUALITY_WEIGHT_BIN_DETAILED_ORDER: List[str] = [
    "==1.0",
    "[0.95,1.0)",
    "[0.8,0.95)",
    "[0.5,0.8)",
    "[0,0.5)",
    "none_not_match",
    "none_no_range",
]

OVERLAP_RATIO_BIN_ORDER: List[str] = [
    "==1.0",
    "[0.95,1.0)",
    "[0.8,0.95)",
    "[0.5,0.8)",
    "[0,0.5)",
    "none",
]


def _bin_unit_value(v: Optional[float]) -> str:
    """Bin a value assumed to be in [0, 1] (or None).

    Shared logic for both quality_weight and overlap_ratio.
    """
    if v is None:
        return "none"
    if v >= 1.0:          # exact 1.0 (or floating-point ≥1.0 within tolerance)
        return "==1.0"
    if v >= 0.95:
        return "[0.95,1.0)"
    if v >= 0.8:
        return "[0.8,0.95)"
    if v >= 0.5:
        return "[0.5,0.8)"
    return "[0,0.5)"


def quality_weight_bin(qw: Optional[float]) -> str:
    """Assign a quality_weight value to one of the 6 canonical bins.

    Pass ``None`` for rows where ``align_verdict != "MATCH"`` to get the
    ``"none"`` bin instead of the misleading ``"[0,0.5)"``.
    """
    return _bin_unit_value(qw)


def quality_weight_bin_detailed(
    qw: Optional[float],
    *,
    has_range: bool,
    align_verdict: Optional[str],
) -> str:
    """Like :func:`quality_weight_bin` but splits the ``none`` bin.

    Returns
    -------
    str
        One of :data:`QUALITY_WEIGHT_BIN_DETAILED_ORDER`.

        ``"none_no_range"``  — ``has_range`` is False (DWARF property).
        ``"none_not_match"`` — ``has_range`` is True but
                               ``align_verdict != "MATCH"``.
    """
    if qw is not None and align_verdict == "MATCH":
        return _bin_unit_value(qw)

    # None path — split by root cause
    if not has_range:
        return "none_no_range"
    return "none_not_match"


def overlap_ratio_bin(ratio: Optional[float]) -> str:
    """Bin an ``align_overlap_ratio`` value using the same thresholds.

    Pass ``None`` for rows where the ratio is not available.
    """
    return _bin_unit_value(ratio)
