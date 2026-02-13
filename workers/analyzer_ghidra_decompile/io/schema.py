"""
Schema — Pydantic models for analyzer_ghidra_decompile JSON outputs.

Five outputs per binary:
  1. report.json         — binary-level verdict + provenance + summary.
  2. functions.jsonl     — one record per function.
  3. variables.jsonl     — one record per decompiler-visible variable.
  4. cfg.jsonl           — one record per function CFG.
  5. calls.jsonl         — one record per callsite.

Runtime contract fields (present in report):
  package_name, analyzer_version, schema_version, profile_id.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from analyzer_ghidra_decompile import (
    ANALYZER_VERSION,
    PACKAGE_NAME,
    SCHEMA_VERSION,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Function entry (functions.jsonl)  — §5
# ═══════════════════════════════════════════════════════════════════════════════

class GhidraFunctionEntry(BaseModel):
    """One function record for functions.jsonl."""

    binary_id: str
    function_id: str

    entry_va: int
    entry_hex: str

    name: str
    namespace: Optional[str] = None

    body_start_va: Optional[int] = None
    body_end_va: Optional[int] = None
    size_bytes: Optional[int] = None

    is_external_block: bool = False  # True if function lives in Ghidra's EXTERNAL memory block
    is_thunk: bool = False
    is_import: bool = False            # Same as is_external_block (kept for readability)

    section_hint: Optional[str] = None

    decompile_status: str        # OK | FAIL
    c_raw: str = ""
    decompile_error: Optional[str] = None

    # Warning taxonomy (§5.2)
    warnings: List[str] = Field(default_factory=list)
    warnings_raw: List[str] = Field(default_factory=list)

    # Function verdict (§5.3)
    verdict: str                 # OK | WARN | FAIL

    # Noise classification flags (§5.4)
    is_plt_or_stub: bool = False
    is_init_fini_aux: bool = False
    is_compiler_aux: bool = False
    is_library_like: bool = False

    # Proxy metrics (§9.1)
    asm_insn_count: int = 0
    c_line_count: int = 0
    insn_to_c_ratio: float = 0.0
    temp_var_count: int = 0

    # Fat function (§9.2, §9.3)
    fat_function_flag: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# Variable entry (variables.jsonl)  — §6
# ═══════════════════════════════════════════════════════════════════════════════

class GhidraVariableEntry(BaseModel):
    """One variable record for variables.jsonl."""

    binary_id: str
    function_id: str
    entry_va: int
    var_id: str

    var_kind: str                # PARAM | LOCAL | GLOBAL_REF | TEMP
    name: str
    type_str: Optional[str] = None
    size_bytes: Optional[int] = None

    storage_class: str           # STACK | REGISTER | MEMORY | UNIQUE | UNKNOWN
    storage_key: str

    stack_offset: Optional[int] = None
    register_name: Optional[str] = None
    addr_va: Optional[int] = None

    is_temp_singleton: bool = False

    access_sites: List[int] = Field(default_factory=list)
    access_sites_truncated: bool = False
    access_sig: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# CFG entry (cfg.jsonl)  — §7
# ═══════════════════════════════════════════════════════════════════════════════

class CfgBlockEntry(BaseModel):
    """A single basic block within a function CFG."""
    block_id: int
    start_va: int
    end_va: int
    succ: List[int] = Field(default_factory=list)


class GhidraCfgEntry(BaseModel):
    """One CFG record for cfg.jsonl."""

    binary_id: str
    function_id: str
    entry_va: int

    bb_count: int = 0
    edge_count: int = 0
    cyclomatic: int = 0

    has_indirect_jumps: bool = False
    unresolved_indirect_jump_count: int = 0
    cfg_completeness: str = "HIGH"   # HIGH | MEDIUM | LOW

    blocks: List[CfgBlockEntry] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# Call entry (calls.jsonl)  — §8
# ═══════════════════════════════════════════════════════════════════════════════

class GhidraCallEntry(BaseModel):
    """One callsite record for calls.jsonl."""

    binary_id: str
    caller_function_id: str
    caller_entry_va: int

    callsite_va: int
    callsite_hex: str

    call_kind: str               # DIRECT | INDIRECT
    callee_entry_va: Optional[int] = None
    callee_name: Optional[str] = None
    is_external_target: bool = False          # callee.isExternal() per Ghidra API
    is_import_proxy_target: bool = False       # callee is external OR thunk (PLT proxy)


# ═══════════════════════════════════════════════════════════════════════════════
# Report (report.json)  — §10
# ═══════════════════════════════════════════════════════════════════════════════

class FunctionCounts(BaseModel):
    """Summary counts for function-level verdicts.

    Note on fail counts:
      - n_decompile_fail: functions where the Ghidra decompiler itself returned
        an error (decompile_status == FAIL).
      - n_functions_fail: functions whose **policy verdict** is FAIL. This
        includes decompiler failures AND functions that decompiled successfully
        but have fatal warnings (e.g., BAD_INSTRUCTION_DATA).

    Typically n_functions_fail >= n_decompile_fail.
    """
    n_functions_total: int = 0
    n_functions_ok: int = 0
    n_functions_warn: int = 0
    n_functions_fail: int = 0           # policy verdict failures
    n_thunks: int = 0
    n_imports: int = 0
    n_externals: int = 0
    n_plt_or_stub: int = 0
    n_init_fini_aux: int = 0
    n_compiler_aux: int = 0
    n_decompile_fail: int = 0           # decompiler-returned failures


class CfgSummary(BaseModel):
    """Summary statistics for CFG data."""
    mean_bb_count: float = 0.0
    median_bb_count: float = 0.0
    unresolved_indirect_jumps_total: int = 0


class VariableSummary(BaseModel):
    """Summary statistics for variable data."""
    total_vars: int = 0
    total_temps: int = 0
    placeholder_type_rate: float = 0.0  # undefined* proportion


class GhidraReport(BaseModel):
    """Binary-level report — report.json."""

    # Provenance (§10.1)
    package_name: str = PACKAGE_NAME
    analyzer_version: str = ANALYZER_VERSION
    schema_version: str = SCHEMA_VERSION
    profile_id: str

    binary_sha256: str
    binary_path: str

    ghidra_version: str = "unknown"
    java_version: str = "unknown"
    script_hash: Optional[str] = None  # SHA256 of ExportDecompJsonl.java
    analysis_options: str = "default"

    # Binary verdict (§4)
    binary_verdict: str          # ACCEPT | WARN | REJECT
    reasons: List[str] = Field(default_factory=list)

    # Counts (§10.2)
    function_counts: FunctionCounts = Field(default_factory=FunctionCounts)
    warning_prevalence: Dict[str, int] = Field(default_factory=dict)
    cfg_summary: CfgSummary = Field(default_factory=CfgSummary)
    variable_summary: VariableSummary = Field(default_factory=VariableSummary)

    # Fat function thresholds used (for auditability)
    fat_function_thresholds: Dict[str, Any] = Field(default_factory=dict)

    # Noise list version
    noise_list_version: str = ""

    # Timestamp (provenance only, not in content used for diffs)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
