"""
Core data loader for oracle pipeline artifacts.

Walks the synthetic artifact tree, validates JSON files through lightweight
Pydantic models, and assembles raw DataFrames — no derived columns,
no metrics, no plotting concerns.

Usage::

    from data.loader import load_dataset, load_ghidra_dataset

    ds = load_dataset(Path("../docker/local-files/artifacts/synthetic"))
    ds.pairs        # per-function alignment rows
    ds.non_targets  # oracle-rejected functions
    ds.reports      # one row per (test_case, opt) with aggregate counts
    ds.builds       # one row per build cell from the build receipt

    gds = load_ghidra_dataset()
    gds.functions   # per-DWARF-function joined rows
    gds.reports     # one row per (test_case, opt) with flattened report data
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from . import paths
from .schema import (
    AlignmentPairsOutput,
    AlignmentReport,
    BuildReceipt,
    OracleReport,
)

log = logging.getLogger(__name__)

# Default artifact root when running from ``reforge/scripts/``
DEFAULT_ARTIFACTS_ROOT = Path(__file__).resolve().parent.parent / "docker" / "local-files" / "artifacts" / "synthetic"


# ═══════════════════════════════════════════════════════════════════════════════
# Public dataclass
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class OracleDataset:
    """Container for the four raw DataFrames produced by :func:`load_dataset`.

    Attributes
    ----------
    pairs : pd.DataFrame
        One row per oracle-accepted DWARF function that entered alignment.

        Columns: ``test_case, opt, dwarf_function_id, dwarf_function_name,
        dwarf_function_name_norm, dwarf_verdict, verdict, overlap_ratio,
        overlap_count, total_count, gap_count, reasons, candidates,
        best_tu_path, best_ts_func_id, best_ts_function_name,
        decl_file, decl_line, decl_column, comp_dir``

    non_targets : pd.DataFrame
        One row per oracle-rejected function (never entered alignment).

        Columns: ``test_case, opt, dwarf_function_id, name, name_norm,
        dwarf_verdict, dwarf_reasons, decl_file, decl_line, decl_column,
        comp_dir``

    reports : pd.DataFrame
        One row per ``(test_case, opt)`` combination with aggregate verdict
        and reason counts.

        Columns: ``test_case, opt, match, ambiguous, no_match, non_target,
        oracle_accept, oracle_reject, oracle_warn, oracle_total,
        reason_<KEY>…`` (dynamic, one column per observed reason tag)

    builds : pd.DataFrame
        One row per build cell from the build receipt.

        Columns: ``test_case, opt, variant, status, binary_size,
        has_debug, build_id``

    test_cases : list[str]
        Ordered list of test-case names included in this dataset.

    opt_levels : list[str]
        Optimization levels loaded (e.g. ``["O0", "O1"]``).

    variant : str
        Build variant loaded (e.g. ``"debug"``).
    """

    pairs: pd.DataFrame
    non_targets: pd.DataFrame
    reports: pd.DataFrame
    builds: pd.DataFrame
    test_cases: List[str] = field(default_factory=list)
    opt_levels: List[str] = field(default_factory=list)
    variant: str = "debug"


# ═══════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    """Read and parse a JSON file, returning *None* if it does not exist."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _flatten_build_receipt(
    raw: Dict[str, Any], test_case: str,
) -> List[Dict[str, Any]]:
    """Extract rows for ``df_builds`` from a parsed ``build_receipt.json``."""
    receipt = BuildReceipt.model_validate(raw)
    rows: List[Dict[str, Any]] = []
    for b in receipt.builds:
        art = b.artifact
        rows.append({
            "test_case":   test_case,
            "opt":         b.optimization,
            "variant":     b.variant,
            "status":      b.status,
            "binary_size": art.size_bytes if art else None,
            "has_debug":   bool(art.debug_presence.has_debug_sections)
                           if art and art.debug_presence else False,
            "build_id":    art.elf.build_id if art else None,
        })
    return rows


def _flatten_report(
    test_case: str,
    opt: str,
    alignment_report: AlignmentReport,
    oracle_report: OracleReport,
) -> Dict[str, Any]:
    """Build a single report-level row for ``df_reports``."""
    pc = alignment_report.pair_counts
    fc = oracle_report.function_counts

    row: Dict[str, Any] = {
        "test_case":     test_case,
        "opt":           opt,
        # alignment verdicts
        "match":         pc.match,
        "ambiguous":     pc.ambiguous,
        "no_match":      pc.no_match,
        "non_target":    pc.non_target,
        # oracle verdicts
        "oracle_accept": fc.accept,
        "oracle_reject": fc.reject,
        "oracle_warn":   fc.warn,
        "oracle_total":  fc.total,
    }
    # Flatten reason counts into ``reason_<key>`` columns
    for reason, count in alignment_report.reason_counts.items():
        row[f"reason_{reason}"] = count
    # Flatten alignment thresholds into ``threshold_<key>`` columns
    for key, val in alignment_report.thresholds.items():
        row[f"threshold_{key}"] = val
    return row


def _flatten_pairs(
    test_case: str, opt: str, pairs_output: AlignmentPairsOutput,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Extract pair-level and non-target rows from ``alignment_pairs.json``."""
    pair_rows: List[Dict[str, Any]] = []
    nt_rows: List[Dict[str, Any]] = []

    for p in pairs_output.pairs:
        # Normalize null names → stable placeholder
        name_norm = (
            p.dwarf_function_name
            if p.dwarf_function_name is not None
            else f"<anon@{p.dwarf_function_id}>"
        )
        pair_rows.append({
            "test_case":             test_case,
            "opt":                   opt,
            "dwarf_function_id":     p.dwarf_function_id,
            "dwarf_function_name":   p.dwarf_function_name,
            "dwarf_function_name_norm": name_norm,
            "dwarf_verdict":         p.dwarf_verdict,
            "verdict":               p.verdict,
            "overlap_ratio":         p.overlap_ratio,
            "overlap_count":         p.overlap_count,
            "total_count":           p.total_count,
            "gap_count":             p.gap_count,
            "reasons":               p.reasons,
            "candidates":            [c.model_dump() for c in p.candidates],
            "best_tu_path":          p.best_tu_path or "",
            "best_ts_func_id":       p.best_ts_func_id or "",
            "best_ts_function_name": p.best_ts_function_name or "",
            # Source declaration identity
            "decl_file":             p.decl_file,
            "decl_line":             p.decl_line,
            "decl_column":           p.decl_column,
            "comp_dir":              p.comp_dir,
        })

    for nt in pairs_output.non_targets:
        # Normalize null names → stable placeholder
        name_norm = (
            nt.name
            if nt.name is not None
            else f"<anon@{nt.dwarf_function_id}>"
        )
        nt_rows.append({
            "test_case":         test_case,
            "opt":               opt,
            "dwarf_function_id": nt.dwarf_function_id,
            "name":              nt.name,
            "name_norm":         name_norm,
            "dwarf_verdict":     nt.dwarf_verdict,
            "dwarf_reasons":     nt.dwarf_reasons,
            # Source declaration identity
            "decl_file":         nt.decl_file,
            "decl_line":         nt.decl_line,
            "decl_column":       nt.decl_column,
            "comp_dir":          nt.comp_dir,
        })

    return pair_rows, nt_rows


# ═══════════════════════════════════════════════════════════════════════════════
# Public entry point
# ═══════════════════════════════════════════════════════════════════════════════

def load_dataset(
    artifacts_root: Optional[Path] = None,
    *,
    test_cases: Optional[List[str]] = None,
    opt_levels: Optional[List[str]] = None,
    variant: str = "debug",
) -> OracleDataset:
    """Load oracle pipeline artifacts into an :class:`OracleDataset`.

    Parameters
    ----------
    artifacts_root
        Path to the ``artifacts/synthetic`` directory.
        Defaults to ``<reforge>/docker/local-files/artifacts/synthetic``.
    test_cases
        Explicit list of test-case directory names to include.
        ``None`` (default) discovers all directories starting with ``t``.
    opt_levels
        Optimization levels to load.  Defaults to ``["O0", "O1"]``.
    variant
        Build variant to load.  Defaults to ``"debug"``.

    Returns
    -------
    OracleDataset
        Dataclass with four DataFrames and metadata.
    """
    if artifacts_root is None:
        artifacts_root = DEFAULT_ARTIFACTS_ROOT
    artifacts_root = Path(artifacts_root).resolve()

    if opt_levels is None:
        opt_levels = ["O0", "O1"]

    # ── Discover test cases ──────────────────────────────────────────────
    all_tests = paths.discover_test_cases(artifacts_root)

    if test_cases is not None:
        selected = [t for t in all_tests if t in test_cases]
        if not selected:
            raise ValueError(
                f"None of {test_cases} found in {all_tests}"
            )
    else:
        selected = all_tests

    log.info(
        "loading %d test case(s), opts=%s, variant=%s",
        len(selected), opt_levels, variant,
    )

    # ── Accumulators ─────────────────────────────────────────────────────
    rows_pairs:       List[Dict[str, Any]] = []
    rows_non_targets: List[Dict[str, Any]] = []
    rows_reports:     List[Dict[str, Any]] = []
    rows_builds:      List[Dict[str, Any]] = []

    for tc in selected:
        # ── Build receipt (per test case) ────────────────────────────────
        receipt_raw = _load_json(
            paths.build_receipt_path(artifacts_root, tc)
        )
        if receipt_raw is not None:
            rows_builds.extend(_flatten_build_receipt(receipt_raw, tc))

        # ── Per optimization level ───────────────────────────────────────
        for opt in opt_levels:
            ar_raw = _load_json(
                paths.alignment_report_path(artifacts_root, tc, opt, variant)
            )
            orc_raw = _load_json(
                paths.oracle_report_path(artifacts_root, tc, opt, variant)
            )
            ap_raw = _load_json(
                paths.alignment_pairs_path(artifacts_root, tc, opt, variant)
            )

            if ar_raw is None or orc_raw is None or ap_raw is None:
                log.warning("missing data for %s/%s — skipping", tc, opt)
                continue

            # Validate through Pydantic
            alignment_report = AlignmentReport.model_validate(ar_raw)
            oracle_report = OracleReport.model_validate(orc_raw)
            pairs_output = AlignmentPairsOutput.model_validate(ap_raw)

            # Report-level row
            rows_reports.append(
                _flatten_report(tc, opt, alignment_report, oracle_report)
            )

            # Pair-level + non-target rows
            p_rows, nt_rows = _flatten_pairs(tc, opt, pairs_output)
            rows_pairs.extend(p_rows)
            rows_non_targets.extend(nt_rows)

    # ── Assemble DataFrames ──────────────────────────────────────────────
    df_pairs       = pd.DataFrame(rows_pairs)
    df_non_targets = pd.DataFrame(rows_non_targets)
    df_reports     = pd.DataFrame(rows_reports).fillna(0)
    df_builds      = pd.DataFrame(rows_builds)

    # Coerce integer columns in df_reports
    int_cols = [
        c for c in df_reports.columns
        if c.startswith("reason_")
        or c in (
            "match", "ambiguous", "no_match", "non_target",
            "oracle_accept", "oracle_reject", "oracle_warn", "oracle_total",
        )
    ]
    if int_cols:
        df_reports[int_cols] = df_reports[int_cols].astype(int)

    log.info(
        "loaded %d pairs, %d non-targets, %d report rows, %d build rows",
        len(df_pairs), len(df_non_targets), len(df_reports), len(df_builds),
    )

    return OracleDataset(
        pairs=df_pairs,
        non_targets=df_non_targets,
        reports=df_reports,
        builds=df_builds,
        test_cases=selected,
        opt_levels=opt_levels,
        variant=variant,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Ghidra-join dataset
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class GhidraJoinDataset:
    """Container for the Ghidra-join DataFrames.

    Attributes
    ----------
    functions : pd.DataFrame
        One row per DWARF function from ``joined_functions.jsonl``.
        All fields from :class:`JoinedFunctionRow` are preserved as columns.

    reports : pd.DataFrame
        One row per ``(test_case, opt)`` with flattened yield counts,
        confidence funnel, exclusion summary, high-confidence slice,
        and decompiler distribution percentiles.

    test_cases : list[str]
        Ordered list of test-case names included.

    opt_levels : list[str]
        Optimization levels loaded.
    """

    functions: pd.DataFrame
    reports: pd.DataFrame
    test_cases: List[str] = field(default_factory=list)
    opt_levels: List[str] = field(default_factory=list)


def _flatten_join_report(
    test_case: str, opt: str, raw: Dict[str, Any],
) -> Dict[str, Any]:
    """Flatten a join_report.json into a single dict for df_reports."""
    row: Dict[str, Any] = {"test_case": test_case, "opt": opt}

    # Yield counts
    yc = raw.get("yield_counts", {})
    for k, v in yc.items():
        row[k] = v

    # High confidence
    hc = raw.get("high_confidence", {})
    row["hc_total"] = hc.get("total", 0)
    row["hc_count"] = hc.get("high_confidence_count", 0)
    row["hc_yield_rate"] = hc.get("yield_rate", 0.0)

    # Exclusion summary
    es = raw.get("exclusion_summary", {})
    for k in ("n_total_dwarf", "n_no_range", "n_non_target",
              "n_noise_aux", "n_oracle_reject",
              "n_eligible_for_join", "n_eligible_for_gold"):
        row[f"excl_{k}"] = es.get(k, 0)

    # Confidence funnel
    cf = raw.get("confidence_funnel", {})
    for k, v in cf.items():
        row[f"funnel_{k}"] = v

    # Decompiler distributions
    dec = raw.get("decompiler", {})
    # CFG completeness fractions
    for level, frac in dec.get("cfg_completeness_fractions", {}).items():
        row[f"cfg_frac_{level}"] = frac
    # Warning prevalence
    for warn, cnt in dec.get("warning_prevalence", {}).items():
        row[f"dec_warn_{warn}"] = cnt
    # Percentile distributions
    for metric in ("cyclomatic", "insn_to_c_ratio", "asm_insn_count",
                   "placeholder_type_rate", "goto_density"):
        for pct, val in dec.get(f"{metric}_percentiles", {}).items():
            row[f"dec_{metric}_{pct}"] = val
    row["dec_n_fat_functions"] = dec.get("n_fat_functions", 0)
    row["dec_n_indirect_jumps"] = dec.get("n_has_indirect_jumps", 0)

    # Join warnings
    for warn, cnt in raw.get("join_warning_histogram", {}).items():
        row[f"jw_{warn}"] = cnt

    # QW audit
    qa = raw.get("quality_weight_audit", {})
    row["qa_n_qw_gt_1"] = qa.get("n_quality_weight_gt_1", 0)
    row["qa_n_qw_lt_0"] = qa.get("n_quality_weight_lt_0", 0)

    # Collision summary
    cs = raw.get("collision_summary", {})
    row["collision_max_dwarf_per_ghidra"] = cs.get("max_dwarf_per_ghidra", 0)
    row["collision_n_multi_dwarf"] = cs.get(
        "n_ghidra_funcs_with_multi_dwarf", 0,
    )

    # Invariant violations
    row["n_invariant_violations"] = len(raw.get("invariant_violations", []))

    return row


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Read a JSONL file, returning a list of parsed dicts."""
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_ghidra_dataset(
    artifacts_root: Optional[Path] = None,
    *,
    test_cases: Optional[List[str]] = None,
    opt_levels: Optional[List[str]] = None,
    variant: str = "stripped",
) -> GhidraJoinDataset:
    """Load Ghidra-join artifacts into a :class:`GhidraJoinDataset`.

    Parameters
    ----------
    artifacts_root
        Path to the ``artifacts/synthetic`` directory.
        Defaults to ``<reforge>/docker/local-files/artifacts/synthetic``.
    test_cases
        Explicit list of test-case directory names to include.
        ``None`` discovers all directories.
    opt_levels
        Optimization levels to load.  Defaults to all four.
    variant
        Build variant.  Defaults to ``"stripped"``.
    """
    if artifacts_root is None:
        artifacts_root = DEFAULT_ARTIFACTS_ROOT
    artifacts_root = Path(artifacts_root).resolve()

    if opt_levels is None:
        opt_levels = ["O0", "O1", "O2", "O3"]

    all_tests = paths.discover_test_cases(artifacts_root)
    if test_cases is not None:
        selected = [t for t in all_tests if t in test_cases]
        if not selected:
            raise ValueError(
                f"None of {test_cases} found in {all_tests}"
            )
    else:
        selected = all_tests

    log.info(
        "loading ghidra-join: %d test case(s), opts=%s, variant=%s",
        len(selected), opt_levels, variant,
    )

    rows_functions: List[Dict[str, Any]] = []
    rows_reports: List[Dict[str, Any]] = []

    for tc in selected:
        for opt in opt_levels:
            # Functions (JSONL)
            func_path = paths.joined_functions_path(
                artifacts_root, tc, opt, variant,
            )
            rows_functions.extend(_load_jsonl(func_path))

            # Report (JSON)
            report_raw = _load_json(
                paths.join_report_path(artifacts_root, tc, opt, variant)
            )
            if report_raw is not None:
                rows_reports.append(
                    _flatten_join_report(tc, opt, report_raw)
                )
            else:
                log.warning(
                    "missing join report for %s/%s — skipping", tc, opt,
                )

    df_functions = pd.DataFrame(rows_functions)
    df_reports = pd.DataFrame(rows_reports).fillna(0)

    # Coerce integer columns in reports
    int_cols = [
        c for c in df_reports.columns
        if c.startswith(("excl_", "funnel_", "jw_", "qa_", "collision_"))
        or c in ("hc_total", "hc_count", "n_invariant_violations",
                 "n_dwarf_funcs", "n_joined_to_ghidra", "n_joined_strong",
                 "n_joined_weak", "n_no_range", "n_multi_match", "n_no_match")
    ]
    int_cols = [c for c in int_cols if c in df_reports.columns]
    if int_cols:
        df_reports[int_cols] = df_reports[int_cols].astype(int)

    log.info(
        "loaded %d joined functions, %d report rows",
        len(df_functions), len(df_reports),
    )

    return GhidraJoinDataset(
        functions=df_functions,
        reports=df_reports,
        test_cases=selected,
        opt_levels=opt_levels,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Joined function loader  (identity + decompiled C)
# ═══════════════════════════════════════════════════════════════════════════════

def load_functions_with_decompiled(
    test_case: str,
    opt: str,
    variant: str = "stripped",
    *,
    tier: Optional[str] = None,
    artifacts_root: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Load joined function rows enriched with Ghidra decompiled C.

    Reads ``joined_functions.jsonl`` for identity / ground truth and
    ``ghidra_decompile/functions.jsonl`` for the ``c_raw`` field, joining
    on ``ghidra_func_id`` ↔ ``function_id``.

    Parameters
    ----------
    test_case
        Test-case directory name (e.g. ``"t02"``).
    opt
        Optimization level (e.g. ``"O0"``).
    variant
        Build variant.  Defaults to ``"stripped"``.
    tier
        If given, filter to rows matching this ``confidence_tier``
        (e.g. ``"GOLD"``).
    artifacts_root
        Override the default artifact root path.

    Returns
    -------
    list[dict]
        Each dict contains all fields from ``joined_functions.jsonl``
        plus ``c_raw`` from the Ghidra decompilation.
    """
    if artifacts_root is None:
        artifacts_root = DEFAULT_ARTIFACTS_ROOT
    artifacts_root = Path(artifacts_root).resolve()

    # 1) Load joined functions (identity + ground truth)
    joined_path = paths.joined_functions_path(
        artifacts_root, test_case, opt, variant,
    )
    joined_rows = _load_jsonl(joined_path)

    if not joined_rows:
        return []

    # 2) Load ghidra decompiled functions (for c_raw)
    ghidra_path = paths.ghidra_functions_path(
        artifacts_root, test_case, opt, variant,
    )
    ghidra_rows = _load_jsonl(ghidra_path)

    # Build lookup: function_id → c_raw (+ decompile_status)
    ghidra_lookup: Dict[str, Dict[str, Any]] = {}
    for gr in ghidra_rows:
        fid = gr.get("function_id", "")
        if fid:
            ghidra_lookup[fid] = {
                "c_raw": gr.get("c_raw"),
                "decompile_status": gr.get("decompile_status"),
                "loc_decompiled": gr.get("c_line_count"),
                "cyclomatic": gr.get("cyclomatic"),
                "bb_count": gr.get("bb_count"),
            }

    # 3) Merge
    results: List[Dict[str, Any]] = []
    for row in joined_rows:
        # Optional tier filter
        if tier and row.get("confidence_tier", "") != tier:
            continue

        gfid = row.get("ghidra_func_id", "")
        ghidra_info = ghidra_lookup.get(gfid, {})

        merged = {
            "test_case": test_case,
            "opt": opt,
            "variant": variant,
            "dwarf_function_id": row.get("dwarf_function_id", ""),
            "dwarf_function_name": row.get("dwarf_function_name"),
            "dwarf_function_name_norm": row.get("dwarf_function_name_norm"),
            "ghidra_func_id": gfid,
            "ghidra_entry_va": row.get("ghidra_entry_va"),
            "ghidra_name": row.get("ghidra_name"),
            "ghidra_match_kind": row.get("ghidra_match_kind"),
            "c_raw": ghidra_info.get("c_raw"),
            "decompile_status": ghidra_info.get("decompile_status")
                                or row.get("decompile_status"),
            "decl_file": row.get("decl_file"),
            "decl_line": row.get("decl_line"),
            "confidence_tier": row.get("confidence_tier", ""),
            "quality_weight": row.get("quality_weight"),
            "is_high_confidence": row.get("is_high_confidence"),
            "eligible_for_gold": row.get("eligible_for_gold"),
            "loc_decompiled": ghidra_info.get("loc_decompiled"),
            "cyclomatic": ghidra_info.get("cyclomatic"),
            "bb_count": ghidra_info.get("bb_count"),
        }
        results.append(merged)

    log.info(
        "load_functions_with_decompiled: %s/%s/%s → %d rows (tier=%s)",
        test_case, opt, variant, len(results), tier,
    )
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# Structural context loaders  (calls, CFG, variables)
# ═══════════════════════════════════════════════════════════════════════════════

def load_ghidra_calls(
    test_case: str,
    opt: str,
    variant: str = "stripped",
    *,
    artifacts_root: Optional[Path] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Load Ghidra call-graph edges, grouped by caller function ID.

    Returns
    -------
    dict[str, list[dict]]
        ``function_id → [{callee_name, call_kind, is_external_target}, …]``
    """
    if artifacts_root is None:
        artifacts_root = DEFAULT_ARTIFACTS_ROOT
    artifacts_root = Path(artifacts_root).resolve()

    call_path = paths.ghidra_calls_path(artifacts_root, test_case, opt, variant)
    rows = _load_jsonl(call_path)

    lookup: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        fid = r.get("caller_function_id", "")
        if not fid:
            continue
        lookup.setdefault(fid, []).append({
            "callee_name": r.get("callee_name"),
            "call_kind": r.get("call_kind", "UNKNOWN"),
            "is_external_target": r.get("is_external_target", False),
        })
    return lookup


def load_ghidra_cfg(
    test_case: str,
    opt: str,
    variant: str = "stripped",
    *,
    artifacts_root: Optional[Path] = None,
) -> Dict[str, Dict[str, Any]]:
    """Load Ghidra CFG summaries, keyed by function ID.

    Returns
    -------
    dict[str, dict]
        ``function_id → {bb_count, edge_count, cyclomatic,
        has_indirect_jumps, cfg_completeness}``
    """
    if artifacts_root is None:
        artifacts_root = DEFAULT_ARTIFACTS_ROOT
    artifacts_root = Path(artifacts_root).resolve()

    cfg_path = paths.ghidra_cfg_path(artifacts_root, test_case, opt, variant)
    rows = _load_jsonl(cfg_path)

    lookup: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        fid = r.get("function_id", "")
        if not fid:
            continue
        lookup[fid] = {
            "bb_count": r.get("bb_count", 0),
            "edge_count": r.get("edge_count", 0),
            "cyclomatic": r.get("cyclomatic", 0),
            "has_indirect_jumps": r.get("has_indirect_jumps", False),
            "cfg_completeness": r.get("cfg_completeness", "UNKNOWN"),
        }
    return lookup


def load_ghidra_variables(
    test_case: str,
    opt: str,
    variant: str = "stripped",
    *,
    artifacts_root: Optional[Path] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Load Ghidra variable declarations, grouped by owning function ID.

    Returns
    -------
    dict[str, list[dict]]
        ``function_id → [{name, type_str, var_kind, storage_class}, …]``
    """
    if artifacts_root is None:
        artifacts_root = DEFAULT_ARTIFACTS_ROOT
    artifacts_root = Path(artifacts_root).resolve()

    var_path = paths.ghidra_variables_path(artifacts_root, test_case, opt, variant)
    rows = _load_jsonl(var_path)

    lookup: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        fid = r.get("function_id", "")
        if not fid:
            continue
        lookup.setdefault(fid, []).append({
            "name": r.get("name", ""),
            "type_str": r.get("type_str", ""),
            "var_kind": r.get("var_kind", ""),
            "storage_class": r.get("storage_class", ""),
        })
    return lookup


# ── Formatters: structured data → prompt-ready text ──────────────────────────

def format_calls_for_prompt(calls: List[Dict[str, Any]]) -> str:
    """Format a function's call edges into prompt text.

    Example output::

        This function calls:
        - printf (DIRECT, external)
        - FUN_00401234 (DIRECT)
        - <indirect call> (INDIRECT)
    """
    if not calls:
        return "(no outgoing calls)"
    lines = ["This function calls:"]
    for c in calls:
        name = c.get("callee_name") or "<indirect call>"
        kind = c.get("call_kind", "UNKNOWN")
        ext = ", external" if c.get("is_external_target") else ""
        lines.append(f"  - {name} ({kind}{ext})")
    return "\n".join(lines)


def format_cfg_for_prompt(cfg: Dict[str, Any]) -> str:
    """Format a CFG summary into prompt text.

    Example output::

        Control-flow summary:
        - Basic blocks: 5
        - Edges: 7
        - Cyclomatic complexity: 3
        - Has indirect jumps: no
        - CFG completeness: HIGH
    """
    if not cfg:
        return "(no CFG data)"
    indirect = "yes" if cfg.get("has_indirect_jumps") else "no"
    return (
        "Control-flow summary:\n"
        f"  - Basic blocks: {cfg.get('bb_count', '?')}\n"
        f"  - Edges: {cfg.get('edge_count', '?')}\n"
        f"  - Cyclomatic complexity: {cfg.get('cyclomatic', '?')}\n"
        f"  - Has indirect jumps: {indirect}\n"
        f"  - CFG completeness: {cfg.get('cfg_completeness', '?')}"
    )


def format_variables_for_prompt(variables: List[Dict[str, Any]]) -> str:
    """Format a function's variables into prompt text.

    Example output::

        Variables:
        - __c: int (PARAM, REGISTER)
        - local_10: long (LOCAL, STACK)
    """
    if not variables:
        return "(no variable data)"
    lines = ["Variables:"]
    for v in variables:
        name = v.get("name", "?")
        tstr = v.get("type_str", "?")
        kind = v.get("var_kind", "?")
        storage = v.get("storage_class", "?")
        lines.append(f"  - {name}: {tstr} ({kind}, {storage})")
    return "\n".join(lines)
