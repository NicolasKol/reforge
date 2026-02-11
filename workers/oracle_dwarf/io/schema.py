"""
Schema — Pydantic models for oracle JSON outputs.

Two outputs per binary:
  1. oracle_report.json   — binary-level verdict + summary counts.
  2. oracle_functions.json — per-function verdicts + alignment targets.

Runtime contract fields (present in every output):
  package_name, oracle_version, profile_id, schema_version.
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from oracle_dwarf import ORACLE_VERSION, PACKAGE_NAME, SCHEMA_VERSION


# ── Shared range model ───────────────────────────────────────────────────────

class RangeModel(BaseModel):
    low: str   # hex string for stable JSON serialization
    high: str


# ── Per-function entry ───────────────────────────────────────────────────────

class LineRowEntry(BaseModel):
    """A single (file, line) hit count from DWARF .debug_line evidence."""
    file: str
    line: int
    count: int


class OracleFunctionEntry(BaseModel):
    """One function alignment target."""

    function_id: str
    die_offset: str          # hex
    cu_offset: str           # hex

    name: Optional[str] = None
    linkage_name: Optional[str] = None

    ranges: List[RangeModel] = Field(default_factory=list)

    dominant_file: Optional[str] = None
    dominant_file_ratio: float = 0.0
    line_min: Optional[int] = None
    line_max: Optional[int] = None
    n_line_rows: int = 0

    # v0.2: granular line evidence for join_dwarf_ts.
    # Populated for ACCEPT and WARN functions; empty for REJECT.
    line_rows: List[LineRowEntry] = Field(default_factory=list)
    file_row_counts: Dict[str, int] = Field(default_factory=dict)

    verdict: str             # ACCEPT | WARN | REJECT
    reasons: List[str] = Field(default_factory=list)

    # Future hooks (v0 always NO / None)
    source_extract: Optional[str] = None
    source_ready: str = "NO"


# ── Functions output wrapper ─────────────────────────────────────────────────

class OracleFunctionsOutput(BaseModel):
    """Wrapper for oracle_functions.json."""

    package_name: str = PACKAGE_NAME
    oracle_version: str = ORACLE_VERSION
    schema_version: str = SCHEMA_VERSION
    profile_id: str

    binary_path: str
    binary_sha256: str

    functions: List[OracleFunctionEntry] = Field(default_factory=list)


# ── Binary-level report ─────────────────────────────────────────────────────

class FunctionCounts(BaseModel):
    total: int = 0
    accept: int = 0
    warn: int = 0
    reject: int = 0


class OracleReport(BaseModel):
    """Binary-level summary — oracle_report.json."""

    package_name: str = PACKAGE_NAME
    oracle_version: str = ORACLE_VERSION
    schema_version: str = SCHEMA_VERSION
    profile_id: str

    binary_path: str
    binary_sha256: str
    build_id: Optional[str] = None

    verdict: str              # ACCEPT | WARN | REJECT (binary gate)
    reasons: List[str] = Field(default_factory=list)

    function_counts: FunctionCounts = Field(default_factory=FunctionCounts)

    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
