"""
Schema — Pydantic models for join_dwarf_ts JSON outputs.

Two output files:
  1. alignment_pairs.json   — per-function alignment pairs with scoring.
  2. alignment_report.json  — summary metrics and provenance anchors.

Runtime contract fields (present in every output):
  package_name, joiner_version, profile_id, schema_version.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from join_dwarf_ts import JOINER_VERSION, PACKAGE_NAME, SCHEMA_VERSION


# ── Candidate score (transparency record) ───────────────────────────────────

class CandidateScoreModel(BaseModel):
    """Scored candidate for transparency — included in each alignment pair."""

    ts_func_id: str
    tu_path: str
    function_name: Optional[str] = None
    context_hash: str = ""
    overlap_count: int = 0
    overlap_ratio: float = 0.0
    gap_count: int = 0


# ── Alignment pair ───────────────────────────────────────────────────────────

class AlignmentPair(BaseModel):
    """One DWARF function → best TS function candidate (or none)."""

    dwarf_function_id: str
    dwarf_function_name: Optional[str] = None
    dwarf_verdict: str = ""                    # ACCEPT | WARN (from DWARF)

    # Source declaration identity (propagated from oracle_dwarf v0.3)
    decl_file: Optional[str] = None
    decl_line: Optional[int] = None
    decl_column: Optional[int] = None
    comp_dir: Optional[str] = None

    best_ts_func_id: Optional[str] = None
    best_tu_path: Optional[str] = None
    best_ts_function_name: Optional[str] = None

    overlap_count: int = 0
    total_count: int = 0
    overlap_ratio: float = 0.0
    gap_count: int = 0

    verdict: str = ""                          # MATCH | AMBIGUOUS | NO_MATCH
    reasons: List[str] = Field(default_factory=list)

    candidates: List[CandidateScoreModel] = Field(default_factory=list)


# ── Non-target entry ─────────────────────────────────────────────────────────

class NonTargetEntry(BaseModel):
    """A DWARF function that was not a join target (REJECT)."""

    dwarf_function_id: str
    name: Optional[str] = None
    dwarf_verdict: str = "REJECT"
    dwarf_reasons: List[str] = Field(default_factory=list)

    # Source declaration identity (propagated from oracle_dwarf v0.3)
    decl_file: Optional[str] = None
    decl_line: Optional[int] = None
    decl_column: Optional[int] = None
    comp_dir: Optional[str] = None


# ── Pair counts ──────────────────────────────────────────────────────────────

class PairCounts(BaseModel):
    match: int = 0
    ambiguous: int = 0
    no_match: int = 0
    non_target: int = 0


# ── Top-level outputs ───────────────────────────────────────────────────────

class AlignmentPairsOutput(BaseModel):
    """alignment_pairs.json — per-function alignment results."""

    package_name: str = PACKAGE_NAME
    joiner_version: str = JOINER_VERSION
    schema_version: str = SCHEMA_VERSION
    profile_id: str = "join-dwarf-ts-v0"

    binary_sha256: str = ""
    build_id: Optional[str] = None
    dwarf_profile_id: str = ""
    ts_profile_id: str = ""

    pairs: List[AlignmentPair] = Field(default_factory=list)
    non_targets: List[NonTargetEntry] = Field(default_factory=list)


class AlignmentReport(BaseModel):
    """alignment_report.json — summary metrics and provenance."""

    package_name: str = PACKAGE_NAME
    joiner_version: str = JOINER_VERSION
    schema_version: str = SCHEMA_VERSION
    profile_id: str = "join-dwarf-ts-v0"

    binary_sha256: str = ""
    build_id: Optional[str] = None
    dwarf_profile_id: str = ""
    ts_profile_id: str = ""

    tu_hashes: Dict[str, str] = Field(default_factory=dict)

    pair_counts: PairCounts = Field(default_factory=PairCounts)
    reason_counts: Dict[str, int] = Field(default_factory=dict)

    thresholds: Dict[str, Any] = Field(default_factory=dict)
    excluded_path_prefixes: List[str] = Field(default_factory=list)

    # NOTE: timestamp is the sole non-deterministic field in the report.
    # The determinism guarantee (LOCK.md §7) applies to alignment_pairs.json;
    # alignment_report.json differs only in this field across runs.
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
