"""
Lightweight read-only Pydantic models for deserializing oracle pipeline artifacts.

These mirror the subset of fields used by the data loader.  They are decoupled
from the worker packages so that ``reforge.data`` has no cross-package
dependencies.  All models use ``extra="ignore"`` to silently drop fields that
are not needed for analysis.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ═══════════════════════════════════════════════════════════════════════════════
# Oracle report  (oracle/oracle_report.json)
# ═══════════════════════════════════════════════════════════════════════════════

class FunctionCounts(BaseModel):
    model_config = ConfigDict(extra="ignore")

    total: int = 0
    accept: int = 0
    warn: int = 0
    reject: int = 0

    @model_validator(mode="after")
    def _check_total(self) -> "FunctionCounts":
        expected = self.accept + self.warn + self.reject
        if self.total != expected:
            raise ValueError(
                f"FunctionCounts.total={self.total} != "
                f"accept({self.accept})+warn({self.warn})"
                f"+reject({self.reject})={expected}"
            )
        return self


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
    overlap_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
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
    overlap_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
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


# ═══════════════════════════════════════════════════════════════════════════════
# LLM experiment results  (data/results/llm/<experiment_id>/results.jsonl)
# ═══════════════════════════════════════════════════════════════════════════════

class LLMResultRow(BaseModel):
    """One row of LLM experiment output, appended to a JSONL results file."""

    model_config = ConfigDict(extra="ignore")

    # Experiment identity
    experiment_id: str = Field(..., description="e.g. exp01-function-naming")
    run_id: str = Field(..., description="Controller-provided run ID")
    job_id: str = Field(
        ...,
        description=(
            "Deterministic per-row ID for idempotency. "
            "Typically sha256(experiment_id|run_id|dwarf_function_id|model|prompt_template_id|temperature)."
        ),
    )
    timestamp: str = Field(..., description="ISO-8601 timestamp")

    # Function identity
    test_case: str
    opt: str
    dwarf_function_id: str
    ghidra_func_id: Optional[str] = None

    # Model configuration
    model: str = Field(..., description="OpenRouter model identifier")
    prompt_template_id: str = Field(default="", description="Template name/version")
    temperature: float = 0.0

    # Prompt & response
    prompt_text: str = Field(default="", description="Full prompt sent to the model")
    response_text: str = Field(default="", description="Raw model response")

    # Telemetry
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0

    # Task-specific ground truth & prediction
    ground_truth_name: Optional[str] = Field(default=None, description="DWARF function name")
    predicted_name: Optional[str] = Field(default=None, description="LLM-predicted name")

    # Freeform extras for experiment-specific data
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RunRecord(BaseModel):
    """A benchmarking run — groups multiple jobs across models/repeats."""

    model_config = ConfigDict(extra="ignore")

    run_id: str = Field(..., description="Unique run identifier")
    experiment_id: str = Field(..., description="Experiment config ID")
    status: str = Field(default="pending", description="pending | running | completed | failed")
    models: List[str] = Field(default_factory=list, description="Models included in this run")
    repeats: int = Field(default=1, description="Number of repeat iterations")
    filters: Dict[str, Any] = Field(default_factory=dict, description="Data slice filters")
    planned_jobs: int = Field(default=0, description="Expected number of result rows")
    completed_jobs: int = Field(default=0, description="Completed result rows so far")
    created_at: str = Field(default="", description="ISO-8601 creation timestamp")
    updated_at: str = Field(default="", description="ISO-8601 last update timestamp")
    errors: List[Dict[str, Any]] = Field(default_factory=list, description="Captured error records")


class FunctionDataRow(BaseModel):
    """A joined function record served by the /data API.

    Combines identity from ``joined_functions.jsonl`` with the decompiled C
    from ``ghidra_decompile/functions.jsonl``.
    """

    model_config = ConfigDict(extra="ignore")

    # Identity
    test_case: str
    opt: str
    variant: str = "stripped"
    dwarf_function_id: str
    dwarf_function_name: Optional[str] = None
    dwarf_function_name_norm: Optional[str] = None

    # Ghidra mapping
    ghidra_func_id: Optional[str] = None
    ghidra_entry_va: Optional[int] = None
    ghidra_name: Optional[str] = None
    ghidra_match_kind: Optional[str] = None

    # Decompiled source (from ghidra_decompile/functions.jsonl)
    c_raw: Optional[str] = Field(None, description="Ghidra decompiled C code")
    decompile_status: Optional[str] = None

    # Source declaration
    decl_file: Optional[str] = None
    decl_line: Optional[int] = None

    # Quality
    confidence_tier: Optional[str] = None
    quality_weight: Optional[float] = None
    is_high_confidence: Optional[bool] = None
    eligible_for_gold: Optional[bool] = None

    # Decompiler metrics
    loc_decompiled: Optional[int] = None
    cyclomatic: Optional[int] = None
    bb_count: Optional[int] = None
