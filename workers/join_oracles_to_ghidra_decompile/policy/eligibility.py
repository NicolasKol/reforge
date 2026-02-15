"""
Eligibility — Phase 0 classifier for DWARF function rows.

Every DWARF function is classified *before* the address join so that
downstream denominators are never diluted by unjoinable rows.

Two tiers:
  eligible_for_join  — has usable address ranges and is not a NON_TARGET.
  eligible_for_gold  — join-eligible AND DWARF oracle ACCEPT AND not
                       tagged as noise / aux / init-fini.

Functions that fail eligibility are tagged with an ``exclusion_reason``
and excluded from all yield / HC denominators.

Pure functions, no IO, no state.
"""
from __future__ import annotations

from typing import Optional

from data.noise_lists import (
    ALL_AUX_NAMES,
    normalize_glibc_name,
)


# ── Exclusion reason constants ────────────────────────────────────────

EXCL_NO_RANGE = "NO_RANGE"
EXCL_NON_TARGET = "NON_TARGET"
EXCL_ORACLE_REJECT = "ORACLE_REJECT"
EXCL_NOISE_AUX = "NOISE_AUX"


def classify_eligibility(
    *,
    has_range: bool,
    is_non_target: bool,
    oracle_verdict: str,
    dwarf_name: Optional[str],
    aux_names: tuple[str, ...] | frozenset[str] = ALL_AUX_NAMES,
) -> tuple[bool, bool, Optional[str]]:
    """Classify a DWARF function for join/gold eligibility.

    Parameters
    ----------
    has_range:
        Whether the DWARF DIE has usable PC ranges.
    is_non_target:
        Whether the alignment stage tagged this as NON_TARGET.
    oracle_verdict:
        DWARF oracle verdict string (``ACCEPT`` | ``WARN`` | ``REJECT``).
    dwarf_name:
        DWARF function name (for noise lookup after GLIBC normalization).
    aux_names:
        Set of aux/init-fini/compiler names to check against.

    Returns
    -------
    (eligible_for_join, eligible_for_gold, exclusion_reason)
        exclusion_reason is *None* when eligible_for_join is True.
        When eligible_for_join is True but eligible_for_gold is False,
        exclusion_reason is still None (gold ineligibility is not an
        exclusion — it just means the row won't enter the GOLD tier).
    """
    # ── Join eligibility ──────────────────────────────────────────────────
    if not has_range:
        return False, False, EXCL_NO_RANGE

    if is_non_target:
        return False, False, EXCL_NON_TARGET

    # Join-eligible from here on.
    eligible_for_join = True

    # ── Gold eligibility ──────────────────────────────────────────────────
    if oracle_verdict != "ACCEPT":
        return eligible_for_join, False, None

    # Noise check — normalize GLIBC version suffixes before lookup
    name_clean = (dwarf_name or "").strip()
    name_norm = normalize_glibc_name(name_clean)
    if name_norm in aux_names:
        return eligible_for_join, False, None

    return eligible_for_join, True, None
