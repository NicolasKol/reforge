"""
Schema — Pydantic models for oracle_ts JSON outputs.

Three output files:
  1. oracle_ts_report.json      — TU-level parse reports.
  2. oracle_ts_functions.json   — Per-function index + structural nodes.
  3. extraction_recipes.json    — Deterministic extraction recipes.

Runtime contract fields (present in every output):
  package_name, oracle_version, profile_id, schema_version.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from oracle_ts import ORACLE_VERSION, PACKAGE_NAME, SCHEMA_VERSION


# ── Structural node ──────────────────────────────────────────────────────────

class TsStructuralNode(BaseModel):
    """One structural node within a function body."""
    node_type: str
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int
    node_hash_raw: str
    depth: int
    uncertainty_flags: List[str] = Field(default_factory=list)


# ── Span info (for JSON serialization) ───────────────────────────────────────

class SpanModel(BaseModel):
    """Byte/line span."""
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int


# ── Per-function entry ───────────────────────────────────────────────────────

class TsFunctionEntryModel(BaseModel):
    """One function extracted from a TU."""
    name: Optional[str] = None
    ts_func_id: str
    span_id: str
    context_hash: str
    node_hash_raw: str

    start_line: int
    end_line: int
    start_byte: int
    end_byte: int

    signature_span: SpanModel
    body_span: SpanModel
    preamble_span: SpanModel

    verdict: str             # ACCEPT | WARN | REJECT
    reasons: List[str] = Field(default_factory=list)

    structural_nodes: List[TsStructuralNode] = Field(default_factory=list)


# ── TU parse report ─────────────────────────────────────────────────────────

class ParseErrorModel(BaseModel):
    """A single parse error."""
    line: int
    column: int
    message: str


class TuParseReport(BaseModel):
    """Parse report for one translation unit."""
    tu_path: str
    tu_hash: str
    parser: str              # runtime + grammar version string
    parse_status: str        # OK | ERROR
    parse_errors: List[ParseErrorModel] = Field(default_factory=list)
    verdict: str             # ACCEPT | WARN | REJECT
    reasons: List[str] = Field(default_factory=list)


# ── Function counts ─────────────────────────────────────────────────────────

class FunctionCounts(BaseModel):
    total: int = 0
    accept: int = 0
    warn: int = 0
    reject: int = 0


# ── Top-level outputs ───────────────────────────────────────────────────────

class OracleTsReport(BaseModel):
    """
    oracle_ts_report.json — TU-level summaries.
    """
    package_name: str = PACKAGE_NAME
    oracle_version: str = ORACLE_VERSION
    schema_version: str = SCHEMA_VERSION
    profile_id: str
    tu_reports: List[TuParseReport] = Field(default_factory=list)
    function_counts: FunctionCounts = FunctionCounts()


class OracleTsFunctions(BaseModel):
    """
    oracle_ts_functions.json — per-function index with structural nodes.
    """
    package_name: str = PACKAGE_NAME
    oracle_version: str = ORACLE_VERSION
    schema_version: str = SCHEMA_VERSION
    profile_id: str
    functions: List[TsFunctionEntryModel] = Field(default_factory=list)


# ── Extraction recipe ───────────────────────────────────────────────────────

class ExtractionRecipe(BaseModel):
    """
    Extraction recipe for a single function.
    Two modes: function_only and function_with_file_preamble.
    """
    function_name: Optional[str] = None
    ts_func_id: str
    tu_path: str

    function_only: SpanModel
    function_with_file_preamble: SpanModel


class ExtractionRecipesOutput(BaseModel):
    """
    extraction_recipes.json — deterministic extraction instructions.
    """
    package_name: str = PACKAGE_NAME
    oracle_version: str = ORACLE_VERSION
    schema_version: str = SCHEMA_VERSION
    profile_id: str
    recipes: List[ExtractionRecipe] = Field(default_factory=list)
