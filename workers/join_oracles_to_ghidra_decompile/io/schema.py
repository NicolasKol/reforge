"""
Schema — Pydantic output models for join_oracles_to_ghidra_decompile.

Three outputs per binary variant:
  1. joined_functions.jsonl  — one row per DWARF function entry.
  2. joined_variables.jsonl  — stub in v1 (DWARF variable extraction not yet available).
  3. join_report.json        — aggregated counts, yield, distributions.

Runtime contract fields:
  package_name, joiner_version, schema_version, profile_id.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from join_oracles_to_ghidra_decompile import (
    JOINER_VERSION,
    PACKAGE_NAME,
    SCHEMA_VERSION,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Joined function row (joined_functions.jsonl)
# ═══════════════════════════════════════════════════════════════════════════════

class JoinedFunctionRow(BaseModel):
    """One row in joined_functions.jsonl — one DWARF function entry."""

    # ── Provenance ────────────────────────────────────────────────────────
    binary_sha256: str                          # oracle binary
    job_id: str
    test_case: str
    opt: str
    variant: str                                # oracle variant
    builder_profile_id: str
    ghidra_binary_sha256: Optional[str] = None  # set when cross-variant
    ghidra_variant: Optional[str] = None        # set when cross-variant

    # ── DWARF-side identity ───────────────────────────────────────────────
    dwarf_function_id: str
    dwarf_function_name: Optional[str] = None
    dwarf_function_name_norm: Optional[str] = None
    decl_file: Optional[str] = None
    decl_line: Optional[int] = None
    decl_column: Optional[int] = None
    low_pc: Optional[int] = None          # first range low (int)
    high_pc: Optional[int] = None         # first range high (int)
    dwarf_total_range_bytes: int = 0
    dwarf_oracle_verdict: str = ""

    # ── DWARF↔TS alignment ────────────────────────────────────────────────
    align_verdict: Optional[str] = None
    align_overlap_ratio: Optional[float] = None
    align_gap_count: Optional[int] = None
    align_n_candidates: Optional[int] = None
    quality_weight: float = 0.0
    align_reason_tags: List[str] = Field(default_factory=list)

    # ── Ghidra mapping result ─────────────────────────────────────────────
    ghidra_match_kind: str = ""           # GhidraMatchKind value
    ghidra_func_id: Optional[str] = None
    ghidra_entry_va: Optional[int] = None
    ghidra_name: Optional[str] = None

    # ── Decompiler view summary ───────────────────────────────────────────
    decompile_status: Optional[str] = None
    cfg_completeness: Optional[str] = None
    bb_count: Optional[int] = None
    edge_count: Optional[int] = None
    warning_tags: List[str] = Field(default_factory=list)
    goto_count: int = 0
    loc_decompiled: int = 0
    temp_var_count: int = 0
    placeholder_type_rate: float = 0.0

    # ── Join diagnostics ──────────────────────────────────────────────────
    pc_overlap_bytes: int = 0
    pc_overlap_ratio: float = 0.0
    n_near_ties: int = 0
    join_warnings: List[str] = Field(default_factory=list)

    # ── Many-to-one ──────────────────────────────────────────────────────
    n_dwarf_funcs_per_ghidra_func: int = 0

    # ── Tags (non-destructive filtering) ──────────────────────────────────
    is_high_confidence: bool = False
    is_aux_function: bool = False
    is_import_proxy: bool = False
    is_external_block: bool = False
    is_non_target: bool = False
    is_thunk: bool = False
    fat_function_multi_dwarf: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# Joined variable row — stub (joined_variables.jsonl)
# ═══════════════════════════════════════════════════════════════════════════════

class JoinedVariableRow(BaseModel):
    """Stub row for joined_variables.jsonl.

    Real DWARF variable evidence is not available from oracle_dwarf yet.
    This model serves as the placeholder so downstream consumers see a
    structurally valid (but empty) output file.
    """

    binary_sha256: str
    dwarf_function_id: str
    ghidra_func_id: Optional[str] = None
    var_join_status: str = "NOT_IMPLEMENTED"


# ═══════════════════════════════════════════════════════════════════════════════
# Report sub-models
# ═══════════════════════════════════════════════════════════════════════════════

class JoinYieldCounts(BaseModel):
    """Aggregate join yield counters."""

    n_dwarf_funcs: int = 0
    n_joined_to_ghidra: int = 0       # JOINED_STRONG + JOINED_WEAK
    n_joined_strong: int = 0
    n_joined_weak: int = 0
    n_no_range: int = 0
    n_multi_match: int = 0
    n_no_match: int = 0


class HighConfidenceSlice(BaseModel):
    """High-confidence subset yield."""

    total: int = 0
    high_confidence_count: int = 0
    yield_rate: float = 0.0
    by_opt: Dict[str, float] = Field(default_factory=dict)


class DecompilerDistributions(BaseModel):
    """Simple distribution summaries for decompiler quality indicators."""

    cfg_completeness_fractions: Dict[str, float] = Field(default_factory=dict)
    warning_prevalence: Dict[str, int] = Field(default_factory=dict)
    goto_density_percentiles: Dict[str, float] = Field(default_factory=dict)
    placeholder_type_rate_percentiles: Dict[str, float] = Field(default_factory=dict)
    n_fat_functions: int = 0
    n_many_to_one_ghidra_funcs: int = 0


class VariableJoinStatus(BaseModel):
    """Status of the variable join sub-system."""

    implemented: bool = False
    reason: str = "DWARF variable extraction not available in oracle_dwarf schema ≤0.2"
    n_stub_rows: int = 0


class BuildContextSummary(BaseModel):
    """Build context provenance in the report."""

    binary_sha256: str = ""                         # oracle binary
    job_id: str = ""
    test_case: str = ""
    opt: str = ""
    variant: str = ""                               # oracle variant
    builder_profile_id: str = ""
    ghidra_binary_sha256: Optional[str] = None      # cross-variant only
    ghidra_variant: Optional[str] = None            # cross-variant only


# ═══════════════════════════════════════════════════════════════════════════════
# Top-level report (join_report.json)
# ═══════════════════════════════════════════════════════════════════════════════

class JoinReport(BaseModel):
    """Binary-level join report — join_report.json."""

    # ── Contract fields ───────────────────────────────────────────────────
    package_name: str = PACKAGE_NAME
    joiner_version: str = JOINER_VERSION
    schema_version: str = SCHEMA_VERSION
    profile_id: str = ""

    # ── Provenance ────────────────────────────────────────────────────────
    binary_sha256: str = ""
    build_context: BuildContextSummary = Field(
        default_factory=BuildContextSummary
    )

    # ── Yield ─────────────────────────────────────────────────────────────
    yield_counts: JoinYieldCounts = Field(default_factory=JoinYieldCounts)
    high_confidence: HighConfidenceSlice = Field(
        default_factory=HighConfidenceSlice
    )

    # ── Stratifications ───────────────────────────────────────────────────
    yield_by_align_verdict: Dict[str, int] = Field(default_factory=dict)
    yield_by_n_candidates_bin: Dict[str, int] = Field(default_factory=dict)
    yield_by_quality_weight_bin: Dict[str, int] = Field(default_factory=dict)
    yield_by_opt: Dict[str, int] = Field(default_factory=dict)
    yield_by_match_kind: Dict[str, int] = Field(default_factory=dict)

    # ── Decompiler distributions ──────────────────────────────────────────
    decompiler: DecompilerDistributions = Field(
        default_factory=DecompilerDistributions
    )

    # ── Variable join status ──────────────────────────────────────────────
    variable_join: VariableJoinStatus = Field(
        default_factory=VariableJoinStatus
    )

    # ── Timestamp ─────────────────────────────────────────────────────────
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
