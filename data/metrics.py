"""
Core metric computation for oracle pipeline analysis.

This module transforms the raw DataFrames produced by :mod:`data.loader`
into analysis-ready tables.  It implements four operations:

1. **enrich_pairs** — add ``n_candidates`` and ``gap_rate`` to raw pairs.
2. **compute_transitions** — match functions across two optimization levels
   and produce per-function rows with verdict transitions and deltas.
3. **compute_verdict_rates** — add rate columns to the report-level summary.
4. **compute_reason_shift** — reason distribution at each opt level + Δpp.

All functions accept and return plain DataFrames.  No side effects,
no plotting, no file I/O.
"""

from __future__ import annotations

import logging
from typing import List, Optional

import pandas as pd

from .enums import AlignmentVerdict

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. enrich_pairs
# ═══════════════════════════════════════════════════════════════════════════════

def enrich_pairs(df_pairs: pd.DataFrame) -> pd.DataFrame:
    """Add core derived columns to the raw pairs DataFrame.

    Added columns
    -------------
    n_candidates : int
        Number of tree-sitter candidate functions competing for this
        DWARF function (1 + len(candidates list)).
    gap_rate : float
        Normalised gap severity: ``gap_count / total_count``, ∈ [0, 1].
        Allows cross-function comparison regardless of function size.

    Parameters
    ----------
    df_pairs
        Raw pairs DataFrame from :func:`data.loader.load_dataset`.

    Returns
    -------
    pd.DataFrame
        Copy of *df_pairs* with the new columns appended.
    """
    df = df_pairs.copy()

    if df.empty:
        df["n_candidates"] = pd.Series(dtype=int)
        df["gap_rate"] = pd.Series(dtype=float)
        return df

    df["n_candidates"] = df["candidates"].apply(lambda c: 1 + len(c))
    df["gap_rate"] = (
        df["gap_count"] / df["total_count"].replace(0, 1)
    ).clip(0, 1)

    return df


# ═══════════════════════════════════════════════════════════════════════════════
# 2. compute_transitions
# ═══════════════════════════════════════════════════════════════════════════════

def compute_transitions(
    df_pairs: pd.DataFrame,
    df_non_targets: pd.DataFrame,
    opt_a: str = "O0",
    opt_b: str = "O1",
) -> pd.DataFrame:
    """Match functions across two optimization levels and compute deltas.

    Each row in the result represents a single function identified by
    ``(test_case, dwarf_function_name)``.

    Returned columns
    ----------------
    test_case, dwarf_function_name : str
        Function identity.
    verdict_{opt_a}, verdict_{opt_b} : str
        Alignment verdict at each level (MATCH / AMBIGUOUS / NO_MATCH /
        NON_TARGET / ABSENT).
    overlap_{opt_a}, overlap_{opt_b} : float or NaN
        Overlap ratio at each level (NaN if function was NON_TARGET or ABSENT).
    gap_{opt_a}, gap_{opt_b} : int or NaN
        Gap count at each level.
    gap_rate_{opt_a}, gap_rate_{opt_b} : float or NaN
        Normalised gap rate at each level.
    delta_overlap : float
        ``overlap_{opt_b} − overlap_{opt_a}``.  NaN if either side is missing.
    delta_gap : int
        ``gap_{opt_b} − gap_{opt_a}``.   NaN if either side is missing.
    delta_gap_rate : float
        ``gap_rate_{opt_b} − gap_rate_{opt_a}``.
    dropped : bool
        True if the function was targetable at *opt_a* but absent/non-target
        at *opt_b* (complete alignment loss).
    transition : str
        Compact label ``"MATCH→NO_MATCH"`` etc.

    Parameters
    ----------
    df_pairs
        Enriched pairs DataFrame (must have ``n_candidates``, ``gap_rate``
        if you want ``gap_rate`` deltas — otherwise they'll be NaN).
    df_non_targets
        Non-target DataFrame from the loader.
    opt_a, opt_b
        The two optimization levels to compare (arbitrary pair).
    """

    def _build_function_table(opt: str) -> pd.DataFrame:
        """Merge pairs + non-targets into a single function-level table."""
        # Pairs at this opt level
        p = df_pairs[df_pairs["opt"] == opt][
            ["test_case", "dwarf_function_name", "verdict",
             "overlap_ratio", "gap_count"]
        ].copy()

        # Add gap_rate if available
        if "gap_rate" in df_pairs.columns:
            p["gap_rate"] = df_pairs.loc[p.index, "gap_rate"]
        else:
            p["gap_rate"] = (
                p["gap_count"] / p.pop("total_count").replace(0, 1)  # type: ignore[arg-type]
            ).clip(0, 1) if "total_count" in p.columns else float("nan")

        # Non-targets at this opt level
        nt = df_non_targets[df_non_targets["opt"] == opt][
            ["test_case", "name"]
        ].copy()
        nt = nt.rename(columns={"name": "dwarf_function_name"})
        nt["verdict"] = AlignmentVerdict.NON_TARGET.value
        nt["overlap_ratio"] = float("nan")
        nt["gap_count"] = float("nan")
        nt["gap_rate"] = float("nan")

        combined = pd.concat([p, nt], ignore_index=True)
        # De-duplicate (keep first occurrence per function)
        combined = combined.drop_duplicates(
            subset=["test_case", "dwarf_function_name"], keep="first",
        )
        return combined

    tbl_a = _build_function_table(opt_a)
    tbl_b = _build_function_table(opt_b)

    # Rename columns to distinguish the two opt levels
    tbl_a = tbl_a.rename(columns={
        "verdict":       f"verdict_{opt_a}",
        "overlap_ratio": f"overlap_{opt_a}",
        "gap_count":     f"gap_{opt_a}",
        "gap_rate":      f"gap_rate_{opt_a}",
    })
    tbl_b = tbl_b.rename(columns={
        "verdict":       f"verdict_{opt_b}",
        "overlap_ratio": f"overlap_{opt_b}",
        "gap_count":     f"gap_{opt_b}",
        "gap_rate":      f"gap_rate_{opt_b}",
    })

    # Full outer join on function identity
    merged = tbl_a.merge(
        tbl_b, on=["test_case", "dwarf_function_name"], how="outer",
    )
    merged[f"verdict_{opt_a}"] = merged[f"verdict_{opt_a}"].fillna("ABSENT")
    merged[f"verdict_{opt_b}"] = merged[f"verdict_{opt_b}"].fillna("ABSENT")

    # ── Deltas ───────────────────────────────────────────────────────────
    merged["delta_overlap"] = (
        merged[f"overlap_{opt_b}"] - merged[f"overlap_{opt_a}"]
    )
    merged["delta_gap"] = (
        merged[f"gap_{opt_b}"] - merged[f"gap_{opt_a}"]
    )
    merged["delta_gap_rate"] = (
        merged[f"gap_rate_{opt_b}"] - merged[f"gap_rate_{opt_a}"]
    )

    # ── Dropped flag ─────────────────────────────────────────────────────
    targetable_verdicts = {
        AlignmentVerdict.MATCH.value,
        AlignmentVerdict.AMBIGUOUS.value,
        AlignmentVerdict.NO_MATCH.value,
    }
    non_targetable = {"ABSENT", AlignmentVerdict.NON_TARGET.value}

    merged["dropped"] = (
        merged[f"verdict_{opt_a}"].isin(targetable_verdicts)
        & merged[f"verdict_{opt_b}"].isin(non_targetable)
    )

    # ── Transition label ─────────────────────────────────────────────────
    merged["transition"] = (
        merged[f"verdict_{opt_a}"] + "→" + merged[f"verdict_{opt_b}"] #type: ignore[union-attr]
    )

    log.info(
        "transitions %s→%s: %d functions, %d dropped",
        opt_a, opt_b, len(merged), merged["dropped"].sum(),
    )

    return merged


# ═══════════════════════════════════════════════════════════════════════════════
# 3. compute_verdict_rates
# ═══════════════════════════════════════════════════════════════════════════════

def compute_verdict_rates(df_report: pd.DataFrame) -> pd.DataFrame:
    """Add oracle and alignment verdict *rate* columns to the report DataFrame.

    Added columns (all as percentages 0–100)
    -----------------------------------------
    accept_rate, warn_rate, reject_rate
        Oracle verdict rates relative to ``oracle_total``.
    match_rate, ambiguous_rate, no_match_rate, non_target_rate
        Alignment verdict rates relative to total aligned+non-target count.

    Parameters
    ----------
    df_report
        Report-level DataFrame from the loader.

    Returns
    -------
    pd.DataFrame
        Copy with rate columns appended.
    """
    df = df_report.copy()

    # Oracle rates
    oracle_total = df["oracle_total"].replace(0, 1)
    df["accept_rate"] = (df["oracle_accept"] / oracle_total * 100).round(2)
    df["warn_rate"]   = (df["oracle_warn"]   / oracle_total * 100).round(2)
    df["reject_rate"] = (df["oracle_reject"] / oracle_total * 100).round(2)

    # Alignment rates
    align_total = (
        df["match"] + df["ambiguous"] + df["no_match"] + df["non_target"]
    ).replace(0, 1)
    df["match_rate"]      = (df["match"]      / align_total * 100).round(2)
    df["ambiguous_rate"]  = (df["ambiguous"]  / align_total * 100).round(2)
    df["no_match_rate"]   = (df["no_match"]   / align_total * 100).round(2)
    df["non_target_rate"] = (df["non_target"] / align_total * 100).round(2)

    return df


# ═══════════════════════════════════════════════════════════════════════════════
# 4. compute_reason_shift
# ═══════════════════════════════════════════════════════════════════════════════

def compute_reason_shift(
    df_report: pd.DataFrame,
    opt_a: str = "O0",
    opt_b: str = "O1",
    *,
    top_k: Optional[int] = None,
) -> pd.DataFrame:
    """Compute alignment-reason distribution shift between two opt levels.

    Returns one row per reason tag with columns:

    - ``reason`` — human-readable reason name (title-cased, underscores removed)
    - ``reason_raw`` — original column name (``reason_UNIQUE_BEST`` etc.)
    - ``count_{opt_a}``, ``count_{opt_b}`` — absolute counts
    - ``share_{opt_a}``, ``share_{opt_b}`` — percentage share within that opt
    - ``delta_pp`` — shift in percentage points (``share_b − share_a``)

    Parameters
    ----------
    df_report
        Report-level DataFrame from the loader.
    opt_a, opt_b
        Optimization levels to compare.
    top_k
        If set, keep only the *top_k* reasons by max share across both
        levels and fold the remainder into an ``Other`` row.
    """
    reason_cols = [c for c in df_report.columns if c.startswith("reason_")]
    if not reason_cols:
        log.warning("No reason_* columns found in df_report")
        return pd.DataFrame()

    # Aggregate counts per opt level
    by_opt = df_report.groupby("opt")[reason_cols].sum()

    for opt in (opt_a, opt_b):
        if opt not in by_opt.index:
            raise ValueError(f"Optimization level '{opt}' not found in df_report")

    counts_a = by_opt.loc[opt_a]
    counts_b = by_opt.loc[opt_b]

    # Shares (%)
    total_a = counts_a.sum() or 1
    total_b = counts_b.sum() or 1
    share_a = counts_a / total_a * 100
    share_b = counts_b / total_b * 100

    # Build result DataFrame
    result = pd.DataFrame({
        "reason_raw":       reason_cols,
        "reason":           [c.replace("reason_", "").replace("_", " ").title()
                             for c in reason_cols],
        f"count_{opt_a}":   counts_a.values.astype(int),
        f"count_{opt_b}":   counts_b.values.astype(int),
        f"share_{opt_a}":   share_a.values.round(2), #type: ignore[union-attr]
        f"share_{opt_b}":   share_b.values.round(2), #type: ignore[union-attr]
    })
    result["delta_pp"] = (result[f"share_{opt_b}"] - result[f"share_{opt_a}"]).round(2)

    # Drop zero-only rows
    result = result[
        (result[f"count_{opt_a}"] > 0) | (result[f"count_{opt_b}"] > 0)
    ].copy()

    # Optional top-K folding
    if top_k is not None and len(result) > top_k:
        max_share = result[[f"share_{opt_a}", f"share_{opt_b}"]].max(axis=1)
        result = result.assign(_max_share=max_share)
        result = result.sort_values("_max_share", ascending=False)
        keep = result.head(top_k)
        rest = result.tail(len(result) - top_k)

        other_row = pd.DataFrame([{
            "reason_raw":       "reason_OTHER",
            "reason":           "Other",
            f"count_{opt_a}":   rest[f"count_{opt_a}"].sum(),
            f"count_{opt_b}":   rest[f"count_{opt_b}"].sum(),
            f"share_{opt_a}":   rest[f"share_{opt_a}"].sum().round(2),
            f"share_{opt_b}":   rest[f"share_{opt_b}"].sum().round(2),
            "delta_pp":         rest["delta_pp"].sum().round(2),
        }])
        result = pd.concat([keep, other_row], ignore_index=True)
        result = result.drop(columns=["_max_share"], errors="ignore")

    # Sort by delta for easy consumption
    result = result.sort_values("delta_pp", ascending=True).reset_index(drop=True)

    return result
