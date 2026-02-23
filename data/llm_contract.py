"""
LLM Input Contract — whitelist schema, deny-list, and sanitization.

This module defines the canonical payload the LLM is allowed to see.
Ground-truth labels (DWARF names, alignment verdicts, quality tiers) are
**never** included.  A deny-list pattern catches future field additions
that might accidentally leak.

Three metadata modes control how much context the LLM receives:

- **STRICT**        — decompiled C only (``c_raw``)
- **ANALYST**       — plus architecture (what a human analyst would know)
- **ANALYST_FULL**  — plus architecture *and* optimisation level

The mode is stored per-experiment in ``ExperimentConfig.metadata_mode``
so every run's information boundary is explicit and reproducible.
"""

from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Metadata mode
# ═══════════════════════════════════════════════════════════════════════════════

class MetadataMode(str, Enum):
    """Controls which contextual fields the LLM may see beyond ``c_raw``."""

    STRICT = "STRICT"               # c_raw only
    ANALYST = "ANALYST"             # + arch
    ANALYST_FULL = "ANALYST_FULL"   # + arch + opt


# ═══════════════════════════════════════════════════════════════════════════════
# Deny-list — fields that must NEVER reach the LLM
# ═══════════════════════════════════════════════════════════════════════════════

# Explicit key deny-list (names known today)
FORBIDDEN_KEYS: frozenset[str] = frozenset({
    # Ground-truth labels
    "dwarf_function_name",
    "dwarf_function_name_norm",
    # Dataset / provenance identity (leaks function origin)
    "test_case",
    "variant",
    # Source declaration identity
    "decl_file",
    "decl_line",
    "decl_column",
    "comp_dir",
    # Alignment / join provenance
    "confidence_tier",
    "quality_weight",
    "is_high_confidence",
    "eligible_for_gold",
    "ghidra_match_kind",
    "overlap_ratio",
    "gap_count",
    "verdict",
    "reasons",
    "candidates",
    # Alignment detail
    "dwarf_verdict",
    "best_tu_path",
    "best_ts_func_id",
    "best_ts_function_name",
    "overlap_count",
    "total_count",
})

# Prefix patterns — catch future fields that follow naming conventions
FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "dwarf_function_name",   # dwarf_function_name_*
    "decl_",                 # decl_file, decl_line, …
    "confidence_",           # confidence_tier, confidence_*
    "quality_",              # quality_weight, quality_*
    "eligible_",             # eligible_for_gold, eligible_*
    "is_high_",              # is_high_confidence, is_high_*
    "best_ts_",              # best_ts_func_id, …
    "best_tu_",              # best_tu_path, …
)

# Compiled regex for one-pass prefix check
_FORBIDDEN_PREFIX_RE = re.compile(
    r"^(?:" + "|".join(re.escape(p) for p in FORBIDDEN_PREFIXES) + r")",
)


def _is_forbidden(key: str) -> bool:
    """Return True if *key* is on the deny-list (explicit or prefix)."""
    return key in FORBIDDEN_KEYS or bool(_FORBIDDEN_PREFIX_RE.match(key))


# ═══════════════════════════════════════════════════════════════════════════════
# Whitelist schema — the canonical LLM input record
# ═══════════════════════════════════════════════════════════════════════════════

class LLMInputRow(BaseModel):
    """Sanitized function record safe to include in an LLM prompt.

    Pydantic serialization guarantees that only declared fields are emitted,
    even if the source dict contains additional data.
    """

    model_config = ConfigDict(extra="forbid")

    # Run-scoped identity (not a label — needed for bookkeeping)
    dwarf_function_id: str = Field(..., description="Stable function ID for result join")
    ghidra_func_id: Optional[str] = Field(None, description="Ghidra-assigned function ID")
    ghidra_entry_va: Optional[int] = Field(None, description="Entry virtual address")

    # ── Ghidra-derived artefacts (always allowed) ─────────────────────────
    c_raw: Optional[str] = Field(None, description="Ghidra decompiled C code")
    ghidra_name: Optional[str] = Field(
        None,
        description="Ghidra auto-name (FUN_XXXXXXXX from stripped binary)",
    )
    decompile_status: Optional[str] = Field(None, description="Ghidra decompile status")
    loc_decompiled: Optional[int] = Field(None, description="Lines of decompiled C")
    cyclomatic: Optional[int] = Field(None, description="Cyclomatic complexity")
    bb_count: Optional[int] = Field(None, description="Basic-block count")

    # NOTE: test_case and variant are intentionally EXCLUDED from this schema.
    # They identify the dataset origin and would taint evaluation if visible
    # to the LLM. They are carried separately for bookkeeping only.

    # ── Conditional metadata (controlled by MetadataMode) ─────────────────
    arch: Optional[str] = Field(None, description="Architecture, e.g. x86-64")
    opt: Optional[str] = Field(None, description="Optimisation level, e.g. O2")


# Set of field names that LLMInputRow declares
_WHITELIST_KEYS: frozenset[str] = frozenset(LLMInputRow.model_fields.keys())

# Fields that only appear under certain metadata modes
_MODE_CONDITIONAL: dict[MetadataMode, frozenset[str]] = {
    MetadataMode.STRICT:       frozenset(),
    MetadataMode.ANALYST:      frozenset({"arch"}),
    MetadataMode.ANALYST_FULL: frozenset({"arch", "opt"}),
}

# Which conditional keys each mode EXCLUDES
_MODE_EXCLUDES: dict[MetadataMode, frozenset[str]] = {
    MetadataMode.STRICT:       frozenset({"arch", "opt"}),
    MetadataMode.ANALYST:      frozenset({"opt"}),
    MetadataMode.ANALYST_FULL: frozenset(),
}


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════


def validate_no_leakage(payload: Dict[str, Any]) -> List[str]:
    """Return a list of forbidden keys found in *payload*.

    An empty list means the payload is clean.  This is a fast check
    suitable for use in n8n guard nodes or test assertions.
    """
    return [k for k in payload if _is_forbidden(k)]


def sanitize_for_llm(
    row: Dict[str, Any],
    mode: MetadataMode = MetadataMode.STRICT,
    *,
    arch: Optional[str] = None,
) -> LLMInputRow:
    """Build an :class:`LLMInputRow` from a raw function-data dict.

    Only whitelisted fields are picked.  Forbidden keys in *row* are
    logged for audit.

    Parameters
    ----------
    row
        Typically a dict from ``load_functions_with_decompiled()``.
    mode
        Metadata visibility level for this experiment.
    arch
        Architecture string to inject (e.g. ``"x86-64"``).  Currently
        constant across the dataset; passed explicitly so the caller
        controls it.
    """
    # Audit: detect forbidden keys in the source (informational)
    leaked = validate_no_leakage(row)
    if leaked:
        log.debug(
            "sanitize_for_llm: stripped %d forbidden key(s): %s",
            len(leaked),
            leaked,
        )

    excludes = _MODE_EXCLUDES[mode]

    # Build kwargs from whitelist only
    kwargs: Dict[str, Any] = {}
    for key in _WHITELIST_KEYS:
        if key in excludes:
            continue
        if key == "arch":
            kwargs["arch"] = arch
        elif key in row:
            kwargs[key] = row[key]

    return LLMInputRow(**kwargs)


def sanitize_batch(
    rows: List[Dict[str, Any]],
    mode: MetadataMode = MetadataMode.STRICT,
    *,
    arch: Optional[str] = None,
) -> List[LLMInputRow]:
    """Sanitize a list of function-data dicts in one call."""
    return [sanitize_for_llm(r, mode, arch=arch) for r in rows]


def audit_leakage_counts(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    """Return a counter of forbidden keys found across all *rows*.

    Useful as a per-run metric — zero means no leakage opportunity existed.
    """
    counts: Dict[str, int] = {}
    for row in rows:
        for key in validate_no_leakage(row):
            counts[key] = counts.get(key, 0) + 1
    return counts


def scan_c_raw_for_gt_leak(
    c_raw: str,
    ground_truth_name: str,
    *,
    min_length: int = 4,
) -> bool:
    """Heuristic: check whether the ground-truth name appears in ``c_raw``.

    This catches indirect leakage through string literals, error messages,
    or comments that Ghidra might preserve.  Not a hard fail — some names
    like ``main`` will legitimately appear as callees.

    Parameters
    ----------
    c_raw
        The Ghidra decompiled C code.
    ground_truth_name
        The DWARF function name (label).
    min_length
        Ignore very short names (≤3 chars) that would false-positive.

    Returns
    -------
    bool
        True if the ground-truth name is found in ``c_raw``.
    """
    if not c_raw or not ground_truth_name:
        return False
    if len(ground_truth_name) <= min_length:
        return False  # too short — high false-positive rate
    return ground_truth_name.lower() in c_raw.lower()
