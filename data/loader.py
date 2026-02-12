"""
Core data loader for oracle pipeline artifacts.

Walks the synthetic artifact tree, validates JSON files through lightweight
Pydantic models, and assembles four raw DataFrames — no derived columns,
no metrics, no plotting concerns.

Usage::

    from data.loader import load_dataset

    ds = load_dataset(Path("../docker/local-files/artifacts/synthetic"))

    ds.pairs        # per-function alignment rows
    ds.non_targets  # oracle-rejected functions
    ds.reports      # one row per (test_case, opt) with aggregate counts
    ds.builds       # one row per build cell from the build receipt
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
