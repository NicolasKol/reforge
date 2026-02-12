"""
Lightweight read-only Pydantic models for deserializing oracle pipeline artifacts.

These mirror the subset of fields used by the data loader.  They are decoupled
from the worker packages so that ``reforge.data`` has no cross-package
dependencies.  All models use ``extra="ignore"`` to silently drop fields that
are not needed for analysis.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


# ═══════════════════════════════════════════════════════════════════════════════
# Oracle report  (oracle/oracle_report.json)
# ═══════════════════════════════════════════════════════════════════════════════

class FunctionCounts(BaseModel):
    model_config = ConfigDict(extra="ignore")

    total: int = 0
    accept: int = 0
    warn: int = 0
    reject: int = 0


class OracleReport(BaseModel):
    """Top-level oracle report produced by ``oracle_dwarf``."""

    model_config = ConfigDict(extra="ignore")

    schema_version: str = ""
    verdict: str = ""
    function_counts: FunctionCounts = FunctionCounts()


# ═══════════════════════════════════════════════════════════════════════════════
# Alignment report  (join_dwarf_ts/alignment_report.json)
# ═══════════════════════════════════════════════════════════════════════════════

class PairCounts(BaseModel):
    model_config = ConfigDict(extra="ignore")

    match: int = 0
    ambiguous: int = 0
    no_match: int = 0
    non_target: int = 0


class AlignmentReport(BaseModel):
    """Top-level alignment report produced by ``join_dwarf_ts``."""

    model_config = ConfigDict(extra="ignore")

    schema_version: str = ""
    pair_counts: PairCounts = PairCounts()
    reason_counts: Dict[str, int] = {}
    thresholds: Dict[str, Any] = {}


# ═══════════════════════════════════════════════════════════════════════════════
# Alignment pairs  (join_dwarf_ts/alignment_pairs.json)
# ═══════════════════════════════════════════════════════════════════════════════

class CandidateScore(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ts_func_id: str = ""
    tu_path: str = ""
    function_name: Optional[str] = None
    context_hash: str = ""
    overlap_count: int = 0
    overlap_ratio: float = 0.0
    gap_count: int = 0


class AlignmentPair(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dwarf_function_id: str
    dwarf_function_name: Optional[str] = None
    dwarf_verdict: str = ""
    best_ts_func_id: Optional[str] = None
    best_tu_path: Optional[str] = None
    best_ts_function_name: Optional[str] = None
    overlap_count: int = 0
    total_count: int = 0
    overlap_ratio: float = 0.0
    gap_count: int = 0
    verdict: str = ""
    reasons: List[str] = []
    candidates: List[CandidateScore] = []

    # Source declaration identity (oracle_dwarf v0.3 / joiner v0.2)
    decl_file: Optional[str] = None
    decl_line: Optional[int] = None
    decl_column: Optional[int] = None
    comp_dir: Optional[str] = None


class NonTargetEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dwarf_function_id: str
    name: Optional[str] = None
    dwarf_verdict: str = "REJECT"
    dwarf_reasons: List[str] = []

    # Source declaration identity (oracle_dwarf v0.3 / joiner v0.2)
    decl_file: Optional[str] = None
    decl_line: Optional[int] = None
    decl_column: Optional[int] = None
    comp_dir: Optional[str] = None


class AlignmentPairsOutput(BaseModel):
    """Wrapper for the full ``alignment_pairs.json`` document."""

    model_config = ConfigDict(extra="ignore")

    schema_version: str = ""
    pairs: List[AlignmentPair] = []
    non_targets: List[NonTargetEntry] = []


# ═══════════════════════════════════════════════════════════════════════════════
# Build receipt  (build_receipt.json)
# ═══════════════════════════════════════════════════════════════════════════════

class ElfMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    elf_type: str = ""
    arch: str = ""
    build_id: Optional[str] = None


class DebugPresence(BaseModel):
    model_config = ConfigDict(extra="ignore")

    has_debug_sections: bool = False


class ArtifactMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path_rel: str = ""
    sha256: str = ""
    size_bytes: Optional[int] = None
    elf: ElfMeta = ElfMeta()
    debug_presence: Optional[DebugPresence] = None


class BuildCell(BaseModel):
    model_config = ConfigDict(extra="ignore")

    optimization: str = ""
    variant: str = ""
    status: str = ""
    artifact: Optional[ArtifactMeta] = None


class BuildReceipt(BaseModel):
    """Top-level build receipt produced by the builder worker."""

    model_config = ConfigDict(extra="ignore")

    builds: List[BuildCell] = []
