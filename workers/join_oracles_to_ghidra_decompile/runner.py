"""
Runner — top-level orchestration for the oracle↔Ghidra join.

Public entry point: ``run_join_oracles_ghidra()``.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Tuple

from join_oracles_to_ghidra_decompile.core.address_join import (
    join_dwarf_to_ghidra,
)
from join_oracles_to_ghidra_decompile.core.build_context import (
    BuildContext,
    resolve_build_context,
)
from join_oracles_to_ghidra_decompile.core.diagnostics import (
    build_join_report,
    build_joined_function_rows,
    build_variable_stubs,
)
from join_oracles_to_ghidra_decompile.core.function_table import (
    apply_eligibility,
    build_dwarf_function_table,
    build_ghidra_function_table,
)
from join_oracles_to_ghidra_decompile.core.invariants import (
    check_invariants,
    check_report_invariants,
)
from join_oracles_to_ghidra_decompile.io.loader import (
    cross_validate_sha256,
    load_alignment_outputs,
    load_build_receipt,
    load_ghidra_outputs,
    load_oracle_outputs,
    resolve_target_build_entry,
)
from join_oracles_to_ghidra_decompile.io.schema import (
    JoinedFunctionRow,
    JoinedVariableRow,
    JoinReport,
)
from join_oracles_to_ghidra_decompile.io.writer import write_outputs
from join_oracles_to_ghidra_decompile.policy.profile import (
    JoinOraclesGhidraProfile,
)

log = logging.getLogger(__name__)


def run_join_oracles_ghidra(
    oracle_dir: Path,
    alignment_dir: Path,
    ghidra_dir: Path,
    receipt_path: Path,
    binary_sha256: str,
    profile: Optional[JoinOraclesGhidraProfile] = None,
    output_dir: Optional[Path] = None,
    ghidra_binary_sha256: Optional[str] = None,
    ghidra_variant: Optional[str] = None,
) -> Tuple[JoinReport, List[JoinedFunctionRow], List[JoinedVariableRow]]:
    """Run the full oracle↔Ghidra join pipeline for one binary.

    Parameters
    ----------
    oracle_dir:
        Directory containing ``oracle_report.json`` and ``oracle_functions.json``.
    alignment_dir:
        Directory containing ``alignment_report.json`` and ``alignment_pairs.json``.
    ghidra_dir:
        Directory containing Ghidra outputs (``report.json``, ``functions.jsonl``, etc.).
    receipt_path:
        Path to ``build_receipt.json``.
    binary_sha256:
        SHA-256 hex digest of the **oracle** binary artifact.
    profile:
        Join profile.  Defaults to ``JoinOraclesGhidraProfile.v1()``.
    output_dir:
        If provided, write outputs to this directory.
    ghidra_binary_sha256:
        SHA-256 of the Ghidra-analysed binary.  When *None* (or equal
        to *binary_sha256*) the join is same-variant; otherwise it is a
        cross-variant join (e.g. oracle=debug, ghidra=stripped).
    ghidra_variant:
        Build variant of the Ghidra binary (e.g. ``"stripped"``).
        Only meaningful for cross-variant joins.

    Returns
    -------
    (JoinReport, List[JoinedFunctionRow], List[JoinedVariableRow])
    """
    if profile is None:
        profile = JoinOraclesGhidraProfile.v1()

    log.info("Starting oracle↔Ghidra join for %s", binary_sha256[:16])

    # ── Normalise cross-variant parameters ────────────────────────────────
    is_cross_variant = (
        ghidra_binary_sha256 is not None
        and ghidra_binary_sha256 != binary_sha256
    )
    effective_ghidra_sha = ghidra_binary_sha256 if is_cross_variant else binary_sha256

    # ── Stage 0: Load + validate ──────────────────────────────────────────
    receipt = load_build_receipt(receipt_path)
    build_entry = resolve_target_build_entry(receipt, binary_sha256)

    # In cross-variant mode, also confirm the ghidra binary exists in the
    # receipt (same opt level, different variant).
    if is_cross_variant:
        resolve_target_build_entry(receipt, effective_ghidra_sha) #type: ignore

    build_ctx = resolve_build_context(
        receipt, build_entry, binary_sha256,
        ghidra_binary_sha256=effective_ghidra_sha if is_cross_variant else None,
        ghidra_variant=ghidra_variant,
    )

    oracle_report, oracle_functions = load_oracle_outputs(oracle_dir)
    align_report, align_pairs = load_alignment_outputs(alignment_dir)
    ghidra_report, ghidra_funcs, ghidra_vars, ghidra_cfg, ghidra_calls = (
        load_ghidra_outputs(ghidra_dir)
    )

    # Cross-validate SHA-256 across all sources
    cross_validate_sha256(
        oracle_sha=oracle_report.get("binary_sha256", ""),
        alignment_sha=align_pairs.get("binary_sha256", ""),
        ghidra_sha=ghidra_report.get("binary_sha256", ""),
        oracle_receipt_sha=binary_sha256,
        ghidra_receipt_sha=effective_ghidra_sha if is_cross_variant else None,
    )

    log.info("Stage 0 complete — build context: %s", build_ctx)

    # ── Stage 1: Build DWARF function table ───────────────────────────────
    dwarf_table = build_dwarf_function_table(oracle_functions, align_pairs)
    log.info("Stage 1 complete — %d DWARF functions indexed", len(dwarf_table))

    # ── Stage 1.5: Eligibility classification (Phase 0) ──────────────────
    excl_counts = apply_eligibility(dwarf_table, profile.aux_function_names)
    if excl_counts:
        log.info("Eligibility exclusions: %s", excl_counts)

    # ── Stage 2: Build Ghidra function table ──────────────────────────────
    image_base = ghidra_report.get("image_base") or 0
    ghidra_table, interval_index = build_ghidra_function_table(
        ghidra_funcs, ghidra_cfg, ghidra_vars,
        image_base=image_base,
    )
    log.info(
        "Stage 2 complete — %d Ghidra functions, %d with body ranges",
        len(ghidra_table),
        len(interval_index),
    )

    # ── Stage 3: Address join ─────────────────────────────────────────────
    join_results = join_dwarf_to_ghidra(
        dwarf_table, ghidra_table, interval_index, profile,
    )
    log.info("Stage 3 complete — %d join results", len(join_results))

    # ── Stage 3.5: Build output rows + diagnostics ────────────────────────
    joined_functions = build_joined_function_rows(
        join_results, build_ctx, profile,
    )
    joined_variables = build_variable_stubs(joined_functions)

    # ── Invariant checks ──────────────────────────────────────────────────
    violations = check_invariants(joined_functions)
    if violations:
        log.warning("Pipeline invariant violations: %d", len(violations))

    # ── Report ────────────────────────────────────────────────────────────
    report = build_join_report(joined_functions, build_ctx, profile)

    # ── Report-level invariant checks ─────────────────────────────────────
    report_violations = check_report_invariants(report)
    if report_violations:
        log.warning("Report invariant violations: %d", len(report_violations))
        violations.extend(report_violations)

    log.info(
        "Join report: %d total, %d joined, %d HC (%.1f%%)",
        report.yield_counts.n_dwarf_funcs,
        report.yield_counts.n_joined_to_ghidra,
        report.high_confidence.high_confidence_count,
        report.high_confidence.yield_rate * 100,
    )

    # ── Write outputs ─────────────────────────────────────────────────────
    if output_dir is not None:
        write_outputs(report, joined_functions, joined_variables, output_dir)

    return report, joined_functions, joined_variables
