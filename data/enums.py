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
