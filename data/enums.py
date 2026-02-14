"""
Frozen vocabulary for oracle pipeline verdicts and reason tags.

These enums mirror the string constants emitted by ``oracle_dwarf`` and
``join_dwarf_ts`` workers.  Freezing them here enforces type safety across
the metrics module and prevents lexical drift between pipeline versions.

A new reason value in the pipeline should trigger a version bump in both
the originating worker **and** this module, maintaining the audit trail
required for reproducible analysis.
"""

from __future__ import annotations

from enum import Enum


# ═══════════════════════════════════════════════════════════════════════════════
# Oracle verdicts  (per-binary and per-function)
# ═══════════════════════════════════════════════════════════════════════════════

class OracleVerdict(str, Enum):
    """DWARF oracle verdict assigned to each function (or binary)."""

    ACCEPT = "ACCEPT"
    WARN   = "WARN"
    REJECT = "REJECT"


# ═══════════════════════════════════════════════════════════════════════════════
# Oracle reject / warn reasons
# ═══════════════════════════════════════════════════════════════════════════════

class OracleBinaryRejectReason(str, Enum):
    """Reasons an entire binary is rejected by the oracle."""

    NO_DEBUG_INFO     = "NO_DEBUG_INFO"
    NO_DEBUG_LINE     = "NO_DEBUG_LINE"
    UNSUPPORTED_ARCH  = "UNSUPPORTED_ARCH"
    SPLIT_DWARF       = "SPLIT_DWARF"
    DWARF_PARSE_ERROR = "DWARF_PARSE_ERROR"


class OracleFunctionRejectReason(str, Enum):
    """Reasons a single function is rejected by the oracle."""

    DECLARATION_ONLY       = "DECLARATION_ONLY"
    MISSING_RANGE          = "MISSING_RANGE"
    NO_LINE_ROWS_IN_RANGE  = "NO_LINE_ROWS_IN_RANGE"


class OracleFunctionWarnReason(str, Enum):
    """Reasons a function receives WARN (accepted with caveats)."""

    MULTI_FILE_RANGE       = "MULTI_FILE_RANGE"
    SYSTEM_HEADER_DOMINANT = "SYSTEM_HEADER_DOMINANT"
    RANGES_FRAGMENTED      = "RANGES_FRAGMENTED"
    NAME_MISSING           = "NAME_MISSING"


# ═══════════════════════════════════════════════════════════════════════════════
# Alignment (join) verdicts
# ═══════════════════════════════════════════════════════════════════════════════

class AlignmentVerdict(str, Enum):
    """Outcome of DWARF↔TS alignment for a single function.

    ``NON_TARGET`` is not emitted by the joiner itself — it is assigned
    downstream to functions whose oracle verdict was REJECT (and thus
    never entered alignment).  It is included here because it is a valid
    state in the full function lifecycle.
    """

    MATCH      = "MATCH"
    AMBIGUOUS  = "AMBIGUOUS"
    NO_MATCH   = "NO_MATCH"
    NON_TARGET = "NON_TARGET"


# ═══════════════════════════════════════════════════════════════════════════════
# Alignment reason tags
# ═══════════════════════════════════════════════════════════════════════════════

class AlignmentReason(str, Enum):
    """Reason tags attached to alignment pairs by the joiner.

    Tags are **additive** — a single pair can carry multiple reasons
    (e.g. ``[NEAR_TIE, HEADER_REPLICATION_COLLISION]``).
    """

    # ── Match reasons ────────────────────────────────────────────────────
    UNIQUE_BEST                   = "UNIQUE_BEST"

    # ── Ambiguous reasons ────────────────────────────────────────────────
    NEAR_TIE                      = "NEAR_TIE"
    HEADER_REPLICATION_COLLISION   = "HEADER_REPLICATION_COLLISION"
    MULTI_FILE_RANGE_PROPAGATED    = "MULTI_FILE_RANGE_PROPAGATED"

    # ── No-match reasons ─────────────────────────────────────────────────
    NO_CANDIDATES                 = "NO_CANDIDATES"
    NO_OVERLAP                    = "NO_OVERLAP"
    LOW_OVERLAP_RATIO             = "LOW_OVERLAP_RATIO"
    BELOW_MIN_OVERLAP             = "BELOW_MIN_OVERLAP"
    ORIGIN_MAP_MISSING            = "ORIGIN_MAP_MISSING"

    # ── Gap tag (emitted by select_best, not in any worker enum) ─────────
    PC_LINE_GAP                   = "PC_LINE_GAP"


# ═══════════════════════════════════════════════════════════════════════════════
# Declaration identity quality  (data module v1)
# ═══════════════════════════════════════════════════════════════════════════════

class DeclMissingReason(str, Enum):
    """Reason why ``decl_file`` could not be resolved."""

    NO_DECL_FILE_ATTR     = "NO_DECL_FILE_ATTR"
    FILE_INDEX_UNRESOLVABLE = "FILE_INDEX_UNRESOLVABLE"


class StableKeyQuality(str, Enum):
    """Quality level of the stable cross-optimization function key.

    HIGH       — ``(test_case, decl_file, decl_line, decl_column, name)``
    MEDIUM     — ``(test_case, decl_file, decl_line, name)`` (no column)
    LOW        — ``(test_case, decl_file, name)`` (no line)
    UNRESOLVED — ``(test_case, "<decl_missing>", dwarf_function_id)``
    """

    HIGH       = "HIGH"
    MEDIUM     = "MEDIUM"
    LOW        = "LOW"
    UNRESOLVED = "UNRESOLVED"


# ═══════════════════════════════════════════════════════════════════════════════
# Ghidra decompile verdicts  (analyzer_ghidra_decompile v1)
# ═══════════════════════════════════════════════════════════════════════════════

class GhidraBinaryVerdict(str, Enum):
    """Binary-level verdict from Ghidra decompilation analysis."""

    ACCEPT = "ACCEPT"
    WARN   = "WARN"
    REJECT = "REJECT"


class GhidraFunctionVerdict(str, Enum):
    """Per-function verdict from Ghidra decompiler output analysis."""

    OK   = "OK"
    WARN = "WARN"
    FAIL = "FAIL"


class GhidraDecompileStatus(str, Enum):
    """Whether Ghidra successfully decompiled a function."""

    OK   = "OK"
    FAIL = "FAIL"


# ═══════════════════════════════════════════════════════════════════════════════
# Ghidra binary reject / warn reasons
# ═══════════════════════════════════════════════════════════════════════════════

class GhidraBinaryRejectReason(str, Enum):
    """Reasons an entire binary is rejected by the Ghidra analyzer."""

    NOT_ELF               = "NOT_ELF"
    UNSUPPORTED_ARCH      = "UNSUPPORTED_ARCH"
    GHIDRA_CRASH          = "GHIDRA_CRASH"
    GHIDRA_TIMEOUT        = "GHIDRA_TIMEOUT"
    NO_FUNCTIONS_FOUND    = "NO_FUNCTIONS_FOUND"
    JSONL_PARSE_ERROR     = "JSONL_PARSE_ERROR"


class GhidraBinaryWarnReason(str, Enum):
    """Reasons a binary receives WARN from the Ghidra analyzer."""

    HIGH_DECOMPILE_FAIL_RATE = "HIGH_DECOMPILE_FAIL_RATE"
    GHIDRA_NONZERO_EXIT      = "GHIDRA_NONZERO_EXIT"
    MISSING_SECTIONS          = "MISSING_SECTIONS"
    PARTIAL_ANALYSIS          = "PARTIAL_ANALYSIS"


# ═══════════════════════════════════════════════════════════════════════════════
# Ghidra function warning taxonomy  (§5.2)
# ═══════════════════════════════════════════════════════════════════════════════

class GhidraFunctionWarning(str, Enum):
    """Taxonomy of per-function warnings in Ghidra decompilation (§5.2)."""

    DECOMPILE_TIMEOUT              = "DECOMPILE_TIMEOUT"
    UNKNOWN_CALLING_CONVENTION     = "UNKNOWN_CALLING_CONVENTION"
    UNREACHABLE_BLOCKS_REMOVED     = "UNREACHABLE_BLOCKS_REMOVED"
    BAD_INSTRUCTION_DATA           = "BAD_INSTRUCTION_DATA"
    UNRESOLVED_INDIRECT_JUMP       = "UNRESOLVED_INDIRECT_JUMP"
    OVERLAPPING_RANGES             = "OVERLAPPING_RANGES"
    SWITCH_TABLE_INCOMPLETE        = "SWITCH_TABLE_INCOMPLETE"
    NORETURN_MISMATCH              = "NORETURN_MISMATCH"
    STRUCTURE_WARNING              = "STRUCTURE_WARNING"
    DECOMPILER_INTERNAL_WARNING    = "DECOMPILER_INTERNAL_WARNING"


# ═══════════════════════════════════════════════════════════════════════════════
# Ghidra CFG / variable classification
# ═══════════════════════════════════════════════════════════════════════════════

class GhidraCfgCompleteness(str, Enum):
    """CFG completeness level (§7.2)."""

    HIGH   = "HIGH"
    MEDIUM = "MEDIUM"
    LOW    = "LOW"


class GhidraVarKind(str, Enum):
    """Variable kind as classified from Ghidra's HighSymbol."""

    PARAM      = "PARAM"
    LOCAL      = "LOCAL"
    GLOBAL_REF = "GLOBAL_REF"
    TEMP       = "TEMP"
    UNKNOWN    = "UNKNOWN"


class GhidraStorageClass(str, Enum):
    """Storage class from Ghidra's VariableStorage."""

    REGISTER = "REGISTER"
    STACK    = "STACK"
    MEMORY   = "MEMORY"
    UNIQUE   = "UNIQUE"
    UNKNOWN  = "UNKNOWN"


# ═══════════════════════════════════════════════════════════════════════════════
# Ghidra join match kinds  (join_oracles_to_ghidra_decompile v1)
# ═══════════════════════════════════════════════════════════════════════════════

class GhidraMatchKind(str, Enum):
    """Result of DWARF→Ghidra function mapping by PC-range overlap.

    JOINED_STRONG — ≥ 90 % of DWARF range bytes overlap a single Ghidra func.
    JOINED_WEAK   — 30–89 % overlap.
    MULTI_MATCH   — multiple Ghidra candidates within ε of the best overlap.
    NO_MATCH      — no Ghidra function body overlaps the DWARF range.
    NO_RANGE      — DWARF ranges missing / unusable; join not attempted.
    """

    JOINED_STRONG = "JOINED_STRONG"
    JOINED_WEAK   = "JOINED_WEAK"
    MULTI_MATCH   = "MULTI_MATCH"
    NO_MATCH      = "NO_MATCH"
    NO_RANGE      = "NO_RANGE"


class VarJoinVerdict(str, Enum):
    """Verdict for DWARF→Ghidra variable mapping (future — v1 stub).

    MATCH      — exactly one Ghidra variable shares the same storage identity.
    ALIAS      — multiple Ghidra variables share the same storage identity.
    DISAPPEAR  — DWARF storage identity exists, no Ghidra variable has it.
    UNSCOPED   — DWARF storage identity missing / optimized out.
    """

    MATCH     = "MATCH"
    ALIAS     = "ALIAS"
    DISAPPEAR = "DISAPPEAR"
    UNSCOPED  = "UNSCOPED"
