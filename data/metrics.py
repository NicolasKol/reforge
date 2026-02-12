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

from .enums import AlignmentVerdict, StableKeyQuality

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. enrich_pairs
# ═══════════════════════════════════════════════════════════════════════════════

def enrich_pairs(df_pairs: pd.DataFrame) -> pd.DataFrame:
    """Add core derived columns to the raw pairs DataFrame.

    Added columns
    -------------
    n_candidates : int
        Number of tree-sitter candidate functions considered for this
        DWARF function (``len(candidates)``; includes the best match).
    gap_rate : float
        Normalised gap severity: ``gap_count / total_count``, ∈ [0, 1].
        Allows cross-function comparison regardless of function size.

        .. note::

           ``gap_rate == 1 − overlap_ratio`` by construction
           (``gap_count = total_count − overlap_count``).  It is kept as
           a convenience column but carries **no independent information**
           beyond ``overlap_ratio``.

    quality_weight : float
        Alignment-quality weight for downstream scoring, ∈ [0, 1].

        Combines two **independent** dimensions:

        *   **overlap_ratio** — fidelity of the line-table match
            (how much of the DWARF function's address range maps to the
            best tree-sitter candidate).
        *   **1 / n_candidates** — ambiguity penalty (how many competing
            TS candidates existed; more candidates → less certainty that
            the best one is the *right* one).

        For non-MATCH verdicts (AMBIGUOUS, NO_MATCH) the weight is forced
        to 0 because those pairs should never serve as ground truth.

        Formula::

            if verdict == MATCH:
                quality_weight = overlap_ratio / n_candidates
            else:
                quality_weight = 0

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
        df["quality_weight"] = pd.Series(dtype=float)
        return df

    df["n_candidates"] = df["candidates"].apply(len)

    # gap_rate: NaN when total_count is 0 (unmeasurable, not "perfect")
    df["gap_rate"] = pd.Series(float("nan"), index=df.index)
    measurable = df["total_count"] > 0
    df.loc[measurable, "gap_rate"] = (
        df.loc[measurable, "gap_count"] / df.loc[measurable, "total_count"]
    ).clip(0, 1)

    # Quality weight: overlap fidelity × ambiguity penalty, zero for
    # non-MATCH verdicts.  The two factors are genuinely independent:
    # overlap_ratio depends on line-table coverage, n_candidates depends
    # on how many TU copies of the function exist.
    is_match = df["verdict"] == AlignmentVerdict.MATCH.value
    df["quality_weight"] = 0.0
    df.loc[is_match, "quality_weight"] = (
        df.loc[is_match, "overlap_ratio"]
        / df.loc[is_match, "n_candidates"].replace(0, 1)
    ).clip(0.0, 1.0)

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

    Each row represents a single function matched via a stable
    source-level key ``(test_case, decl_file, decl_line, decl_column,
    dwarf_function_name_norm)``.  Functions whose declaration location is
    unavailable are tagged ``key_quality = UNRESOLVED`` and appear as
    unmatched singletons.  When ``decl_column`` is missing but file/line
    are present the key degrades to ``MEDIUM`` quality.

    If the data lacks declaration-location columns (pre-v0.3 oracle
    output), a name-only fallback is used with a logged warning.

    .. versionchanged:: oracle_decl_identity_v1
       Replaced name-based dedup + name-based merge with stable
       source-level identity.  See ``data/Audit.md`` BUG-1.

    Returned columns
    ----------------
    test_case, dwarf_function_name, dwarf_function_name_norm : str
        Function identity.
    decl_file : str or NaN
        Source file from ``DW_AT_decl_file`` (when available).
    decl_line : int or NaN
        Source line from ``DW_AT_decl_line`` (when available).
    key_quality : str
        ``HIGH`` — matched on full stable key incl. ``decl_column``.
        ``MEDIUM`` — ``decl_file`` + ``decl_line`` present but
        ``decl_column`` missing; rare collisions possible for
        macro-generated functions on the same source line.
        ``LOW`` — name-only fallback (pre-v0.3 data).
        ``UNRESOLVED`` — declaration info missing; cross-opt match impossible.
    dwarf_function_id_{opt_a}, dwarf_function_id_{opt_b} : str
        Per-opt DIE identifier (not stable across optimisation levels).
    verdict_{opt_a}, verdict_{opt_b} : str
        Alignment verdict at each level (MATCH / AMBIGUOUS / NO_MATCH /
        NON_TARGET / ABSENT).
    overlap_{opt_a}, overlap_{opt_b} : float or NaN
        Overlap ratio at each level.
    gap_{opt_a}, gap_{opt_b} : int or NaN
        Gap count at each level.
    delta_overlap : float
        ``overlap_{opt_b} − overlap_{opt_a}``.
    delta_gap : int
        ``gap_{opt_b} − gap_{opt_a}``.
    dropped : bool
        True if the function was targetable at *opt_a* but absent/non-target
        at *opt_b* (complete alignment loss).
    transition : str
        Compact label ``"MATCH→NO_MATCH"`` etc.

    Parameters
    ----------
    df_pairs
        Enriched pairs DataFrame (should have ``gap_rate`` from
        :func:`enrich_pairs`).
    df_non_targets
        Non-target DataFrame from the loader.
    opt_a, opt_b
        The two optimization levels to compare (arbitrary pair).
    """

    # ── capability check ─────────────────────────────────────────────────
    _has_stable = all(
        c in df_pairs.columns
        for c in ("decl_file", "decl_line", "dwarf_function_name_norm")
    )
    if not _has_stable:
        log.warning(
            "Stable identity columns unavailable (pre-v0.3 data); "
            "falling back to name-based matching — duplicate names "
            "may collapse"
        )

    # ── helpers ───────────────────────────────────────────────────────────

    def _build_function_table(opt: str) -> pd.DataFrame:
        """Merge pairs + non-targets for one opt level.

        Unlike the pre-patch version, this does **not** call
        ``drop_duplicates`` by name.  ``dwarf_function_id`` is unique
        within an optimisation level.
        """
        # --- Pairs ---
        core = ["test_case", "dwarf_function_id", "dwarf_function_name",
                "verdict", "overlap_ratio", "gap_count"]
        extras = [c for c in ("dwarf_function_name_norm",
                               "decl_file", "decl_line", "decl_column")
                  if c in df_pairs.columns]

        p = df_pairs.loc[df_pairs["opt"] == opt, core + extras].copy()

        if "gap_rate" in df_pairs.columns:
            p["gap_rate"] = df_pairs.loc[p.index, "gap_rate"]
        elif "total_count" in df_pairs.columns:
            tc = df_pairs.loc[p.index, "total_count"]
            p["gap_rate"] = pd.Series(float("nan"), index=p.index)
            ok = tc > 0
            p.loc[ok, "gap_rate"] = (p.loc[ok, "gap_count"] / tc[ok]).clip(0, 1)
        else:
            p["gap_rate"] = float("nan")

        # --- Non-targets ---
        nt_cols = ["test_case", "dwarf_function_id", "name"]
        nt_extras = [c for c in ("name_norm",
                                  "decl_file", "decl_line", "decl_column")
                     if c in df_non_targets.columns]

        nt = df_non_targets.loc[
            df_non_targets["opt"] == opt, nt_cols + nt_extras
        ].copy()
        nt = nt.rename(columns={"name": "dwarf_function_name"})
        if "name_norm" in nt.columns:
            nt = nt.rename(columns={
                "name_norm": "dwarf_function_name_norm",
            })
        nt["verdict"] = AlignmentVerdict.NON_TARGET.value
        nt["overlap_ratio"] = float("nan")
        nt["gap_count"] = float("nan")
        nt["gap_rate"] = float("nan")

        combined = pd.concat([p, nt], ignore_index=True)
        # NO drop_duplicates — dwarf_function_id is unique within an opt
        return combined

    def _add_merge_key(df: pd.DataFrame, tag: str) -> None:
        """Add ``_mk`` column — composite string for cross-opt joining.

        *tag* (``"a"`` or ``"b"``) is embedded in fallback keys so that
        unresolvable rows from different opt levels never accidentally
        match each other.
        """
        if _has_stable:
            has_decl = df["decl_file"].notna() & df["decl_line"].notna()
            # Normalise anonymous names for stable cross-opt matching:
            # "<anon@cu0:die1>" → "<anon>" (the ID suffix is not
            # stable across optimisation levels).
            name_for_key = df["dwarf_function_name_norm"].astype(str)
            is_anon = name_for_key.str.startswith("<anon@")
            name_for_key = name_for_key.where(~is_anon, "<anon>")
            col_str = (
                df["decl_column"].fillna(-1).astype(int).astype(str)
                if "decl_column" in df.columns
                else pd.Series("-1", index=df.index)
            )
            resolved = (
                df["test_case"].astype(str) + "|"
                + df["decl_file"].fillna("").astype(str) + "|"
                + df["decl_line"].fillna(-1).astype(int).astype(str) + "|"
                + col_str + "|"
                + name_for_key
            )
            # Unmatchable sentinel — different prefix per opt side
            fallback = (
                f"_unresolved_{tag}_" + df["dwarf_function_id"].astype(str)
            )
            df["_mk"] = resolved.where(has_decl, fallback)
        else:
            # Legacy name-only key (may collapse true duplicates)
            df["_mk"] = (
                df["test_case"].astype(str) + "|"
                + df["dwarf_function_name"].astype(str)
            )

    # ── build per-opt tables ─────────────────────────────────────────────
    tbl_a = _build_function_table(opt_a)
    tbl_b = _build_function_table(opt_b)

    _add_merge_key(tbl_a, "a")
    _add_merge_key(tbl_b, "b")

    # ── rename value columns with opt suffix ─────────────────────────────
    val_renames = {
        "verdict":       "verdict",
        "overlap_ratio": "overlap",
        "gap_count":     "gap",
        "gap_rate":      "gap_rate",
        "dwarf_function_id": "dwarf_function_id",
    }
    tbl_a = tbl_a.rename(
        columns={k: f"{v}_{opt_a}" for k, v in val_renames.items()},
    )
    tbl_b = tbl_b.rename(
        columns={k: f"{v}_{opt_b}" for k, v in val_renames.items()},
    )

    # ── outer merge on composite key ─────────────────────────────────────
    id_cols = ["test_case", "dwarf_function_name"]
    if _has_stable:
        id_cols += ["dwarf_function_name_norm", "decl_file", "decl_line"]
        if "decl_column" in tbl_a.columns:
            id_cols.append("decl_column")

    merged = tbl_a.merge(
        tbl_b, on=["_mk"], how="outer", suffixes=("", "_rhs"),
    )

    # Coalesce identity columns (prefer left; fill from right-only rows)
    for c in id_cols:
        rhs = f"{c}_rhs"
        if rhs in merged.columns:
            merged[c] = merged[c].fillna(merged[rhs])
            merged = merged.drop(columns=[rhs])

    merged = merged.drop(columns=["_mk"])

    # Fill verdicts for rows present on only one side
    merged[f"verdict_{opt_a}"] = merged[f"verdict_{opt_a}"].fillna("ABSENT")
    merged[f"verdict_{opt_b}"] = merged[f"verdict_{opt_b}"].fillna("ABSENT")

    # ── Deduplicate Cartesian-product inflation ──────────────────────────
    # Static-inline and extern functions included via multiple TUs produce
    # M DWARF entries on one opt side and N on the other, all sharing the
    # same stable merge key.  The outer join above creates M×N rows where
    # only max(M, N) are meaningful.  We collapse each group of identical
    # merge-key rows to a single representative, keeping the worst-case
    # (minimum) overlap on each side so the chart is conservative.
    #
    # This does NOT collapse distinct functions — those have different
    # merge keys (different decl_file/decl_line/decl_column).
    _dedup_key = [c for c in id_cols if c in merged.columns]
    if _dedup_key:
        _pre = len(merged)

        # Fast path: sort so worst overlap is first, then drop duplicates
        merged = merged.sort_values(
            [f"overlap_{opt_a}", f"overlap_{opt_b}"],
            ascending=[True, True],
            na_position="first",
        )
        merged = merged.drop_duplicates(subset=_dedup_key, keep="first")
        merged = merged.reset_index(drop=True)

        _post = len(merged)
        if _pre != _post:
            log.info(
                "dedup: collapsed %d → %d rows (%d Cartesian-product "
                "duplicates from static-inline / extern multi-TU entries)",
                _pre, _post, _pre - _post,
            )

    # ── key quality label ────────────────────────────────────────────────
    if _has_stable:
        has_file_line = merged["decl_file"].notna() & merged["decl_line"].notna()
        has_column = (
            merged["decl_column"].notna()
            if "decl_column" in merged.columns
            else pd.Series(False, index=merged.index)
        )
        merged["key_quality"] = StableKeyQuality.UNRESOLVED.value
        merged.loc[has_file_line & ~has_column, "key_quality"] = (
            StableKeyQuality.MEDIUM.value
        )
        merged.loc[has_file_line & has_column, "key_quality"] = (
            StableKeyQuality.HIGH.value
        )
    else:
        merged["key_quality"] = StableKeyQuality.LOW.value

    # ── Deltas ───────────────────────────────────────────────────────────
    merged["delta_overlap"] = (
        merged[f"overlap_{opt_b}"] - merged[f"overlap_{opt_a}"]
    )
    merged["delta_gap"] = (
        merged[f"gap_{opt_b}"] - merged[f"gap_{opt_a}"]
    )
    # NOTE: delta_gap_rate removed — it equals -delta_overlap by
    # construction (gap_rate = 1 - overlap_ratio) and carries no
    # independent information.

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
        "transitions %s→%s: %d functions (%d HIGH, %d MEDIUM, "
        "%d UNRESOLVED), %d dropped",
        opt_a, opt_b, len(merged),
        (merged["key_quality"] == StableKeyQuality.HIGH.value).sum(),
        (merged["key_quality"] == StableKeyQuality.MEDIUM.value).sum(),
        (merged["key_quality"] == StableKeyQuality.UNRESOLVED.value).sum(),
        merged["dropped"].sum(),
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
    - ``share_{opt_a}``, ``share_{opt_b}`` — prevalence rate: percentage of
      aligned pairs carrying this reason tag.  Because pairs can carry
      multiple tags, shares may sum to > 100% within an opt level.
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

    # Shares (%) — denominated by *number of aligned pairs*, not by
    # total reason-tag events.  Because a single pair can carry multiple
    # reason tags, shares can sum to > 100%.  This makes each share a
    # "prevalence rate" (fraction of pairs affected by this reason).
    pair_cols = ["match", "ambiguous", "no_match"]
    pairs_per_opt = df_report.groupby("opt")[pair_cols].sum().sum(axis=1)
    total_a = pairs_per_opt.get(opt_a, 1) or 1
    total_b = pairs_per_opt.get(opt_b, 1) or 1
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
