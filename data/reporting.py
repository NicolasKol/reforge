"""
Stratified reporting for LLM experiment results.

Generates structured JSON reports that aggregate scores across multiple
dimensions (optimisation level, confidence tier, quality-weight bin,
test case).  Each stratum includes sample count ``n`` for statistical
context.

Reports are JSON-only — notebook / thesis formatting is the caller's
responsibility.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from data.binning import quality_weight_bin
from data.scoring import SCORER_VERSION

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Aggregation helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _aggregate_scores(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute aggregate metrics for a list of scored rows.

    Each row must already have scoring fields from ``score_experiment()``:
    ``exact_match_norm``, ``token_precision``, ``token_recall``,
    ``token_f1``, ``is_trivial_prediction``.
    """
    n = len(rows)
    if n == 0:
        return {
            "n": 0,
            "exact_match_rate": 0.0,
            "mean_token_precision": 0.0,
            "mean_token_recall": 0.0,
            "mean_token_f1": 0.0,
            "trivial_rate": 0.0,
        }

    em = sum(1 for r in rows if r.get("exact_match_norm", False))
    trivial = sum(1 for r in rows if r.get("is_trivial_prediction", False))
    mean_p = sum(r.get("token_precision", 0.0) for r in rows) / n
    mean_r = sum(r.get("token_recall", 0.0) for r in rows) / n
    mean_f1 = sum(r.get("token_f1", 0.0) for r in rows) / n

    return {
        "n": n,
        "exact_match_rate": em / n,
        "mean_token_precision": round(mean_p, 4),
        "mean_token_recall": round(mean_r, 4),
        "mean_token_f1": round(mean_f1, 4),
        "trivial_rate": round(trivial / n, 4),
    }


def _group_by(
    rows: List[Dict[str, Any]],
    key: str,
) -> Dict[str, List[Dict[str, Any]]]:
    """Group rows by a string key, returning ordered dict."""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        val = str(row.get(key, "UNKNOWN"))
        groups.setdefault(val, []).append(row)
    return dict(sorted(groups.items()))


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════


def generate_report(
    experiment_id: str,
    run_id: Optional[str],
    scored_rows: List[Dict[str, Any]],
    function_metadata: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Produce a stratified JSON report from scored experiment results.

    Parameters
    ----------
    experiment_id
        Experiment identifier.
    run_id
        Run identifier (may be None if scoring across all runs).
    scored_rows
        Result rows enriched with scoring fields by ``score_experiment()``.
    function_metadata
        Optional list of ``FunctionDataRow`` dicts (from
        ``load_functions_with_decompiled``).  Used to attach stratification
        dimensions (``confidence_tier``, ``quality_weight``) that are NOT
        present in the LLM result rows (because they were stripped).

        Joined post-hoc on ``(dwarf_function_id, test_case, opt)``.

    Returns
    -------
    dict
        Structured report with ``meta``, ``overall``, ``by_opt``,
        ``by_tier``, ``by_quality_weight_bin``, ``by_test_case`` sections.
    """
    # ── Enrich rows with metadata (post-hoc join for stratification) ─────
    if function_metadata:
        meta_lookup: Dict[str, Dict[str, Any]] = {}
        for m in function_metadata:
            key = (
                m.get("dwarf_function_id", ""),
                m.get("test_case", ""),
                m.get("opt", ""),
            )
            meta_lookup[str(key)] = m

        for row in scored_rows:
            key = (
                row.get("dwarf_function_id", ""),
                row.get("test_case", ""),
                row.get("opt", ""),
            )
            meta = meta_lookup.get(str(key), {})
            # Attach stratification fields (post-hoc only — never in prompt)
            if "confidence_tier" not in row:
                row["confidence_tier"] = meta.get("confidence_tier", "UNKNOWN")
            if "quality_weight" not in row:
                row["quality_weight"] = meta.get("quality_weight")
            if "quality_weight_bin" not in row:
                row["quality_weight_bin"] = quality_weight_bin(
                    meta.get("quality_weight"),
                )

    # ── Ensure quality_weight_bin is present ─────────────────────────────
    for row in scored_rows:
        if "quality_weight_bin" not in row:
            row["quality_weight_bin"] = quality_weight_bin(
                row.get("quality_weight"),
            )

    # ── Build report ─────────────────────────────────────────────────────
    report: Dict[str, Any] = {
        "meta": {
            "experiment_id": experiment_id,
            "run_id": run_id,
            "scorer_version": SCORER_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n_total": len(scored_rows),
        },
        "overall": _aggregate_scores(scored_rows),
    }

    # By optimisation level
    by_opt = _group_by(scored_rows, "opt")
    report["by_opt"] = [
        {"opt": k, **_aggregate_scores(v)} for k, v in by_opt.items()
    ]

    # By confidence tier (post-hoc stratification)
    by_tier = _group_by(scored_rows, "confidence_tier")
    report["by_tier"] = [
        {"tier": k, **_aggregate_scores(v)} for k, v in by_tier.items()
    ]

    # By quality weight bin (post-hoc stratification)
    by_qw = _group_by(scored_rows, "quality_weight_bin")
    report["by_quality_weight_bin"] = [
        {"bin": k, **_aggregate_scores(v)} for k, v in by_qw.items()
    ]

    # By test case
    by_tc = _group_by(scored_rows, "test_case")
    report["by_test_case"] = [
        {"test_case": k, **_aggregate_scores(v)} for k, v in by_tc.items()
    ]

    return report
