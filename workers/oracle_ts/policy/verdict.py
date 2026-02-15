"""
Verdict logic for oracle_ts v0.

All verdicts are strictly syntactic — derived from parse-tree properties.
No semantic inference.
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import List, Set, Tuple

from oracle_ts.core.function_index import TsFunctionEntry
from oracle_ts.core.node_index import StructuralNode
from oracle_ts.core.ts_parser import ParseResult
from oracle_ts.policy.profile import TsProfile

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────────

class Verdict(str, Enum):
    ACCEPT = "ACCEPT"
    WARN = "WARN"
    REJECT = "REJECT"


class TuRejectReason(str, Enum):
    TU_PARSE_ERROR = "TU_PARSE_ERROR"


class FunctionRejectReason(str, Enum):
    INVALID_SPAN = "INVALID_SPAN"
    MISSING_FUNCTION_NAME = "MISSING_FUNCTION_NAME"


class FunctionWarnReason(str, Enum):
    DUPLICATE_FUNCTION_NAME = "DUPLICATE_FUNCTION_NAME"
    DEEP_NESTING = "DEEP_NESTING"
    ANONYMOUS_AGGREGATE_PRESENT = "ANONYMOUS_AGGREGATE_PRESENT"
    NONSTANDARD_EXTENSION_PATTERN = "NONSTANDARD_EXTENSION_PATTERN"


# ── TU-level gate ────────────────────────────────────────────────────────────

def gate_tu(
    parse_result: ParseResult,
) -> Tuple[Verdict, List[str]]:
    """
    TU-level verdict.

    Returns REJECT only if the TU has parse errors and we consider
    it unreliable.  In v0 we are lenient: parse errors produce WARN
    unless the root has zero children (completely unparseable).
    """
    reasons: List[str] = []

    if parse_result.parse_status == "ERROR":
        root = parse_result.tree.root_node #type: ignore
        # If the root has no meaningful children, reject
        if root.child_count == 0:
            reasons.append(TuRejectReason.TU_PARSE_ERROR.value)
            return Verdict.REJECT, reasons
        # Otherwise warn — partial parse is usable
        reasons.append(TuRejectReason.TU_PARSE_ERROR.value)
        return Verdict.WARN, reasons

    return Verdict.ACCEPT, reasons


# ── Function-level judge ─────────────────────────────────────────────────────

def judge_function(
    func: TsFunctionEntry,
    duplicate_names: Set[str],
    structural_nodes: List[StructuralNode],
    func_node,
    source_bytes: bytes,
    profile: TsProfile,
) -> Tuple[Verdict, List[str]]:
    """
    Per-function verdict.

    Parameters
    ----------
    func : TsFunctionEntry
        The function entry to judge.
    duplicate_names : Set[str]
        Set of function names that appear more than once in the TU.
    structural_nodes : List[StructuralNode]
        Structural nodes already indexed for this function.
    func_node
        The tree-sitter Node for this function_definition, or None
        if ``_find_func_node`` could not locate it.
    source_bytes : bytes
        Full TU source bytes.
    profile : TsProfile
        Active profile (for thresholds).
    """
    reasons: List[str] = []

    # ── REJECT checks ────────────────────────────────────────────────

    # Invalid span
    if func.start_byte >= func.end_byte:
        reasons.append(FunctionRejectReason.INVALID_SPAN.value)
        return Verdict.REJECT, reasons

    # Missing name
    if func.name is None:
        reasons.append(FunctionRejectReason.MISSING_FUNCTION_NAME.value)
        return Verdict.REJECT, reasons

    # ── WARN checks ──────────────────────────────────────────────────

    # Duplicate function name
    if func.name in duplicate_names:
        reasons.append(FunctionWarnReason.DUPLICATE_FUNCTION_NAME.value)

    # Deep nesting in structural nodes
    for sn in structural_nodes:
        if "DEEP_NESTING" in sn.uncertainty_flags:
            reasons.append(FunctionWarnReason.DEEP_NESTING.value)
            break

    # Anonymous aggregates: search for unnamed struct/union/enum in
    # the function subtree.  Only check when we have the actual
    # function node — using root_node would scan the entire TU and
    # produce false WARNs.
    if func_node is not None and _has_anonymous_aggregate(func_node):
        reasons.append(FunctionWarnReason.ANONYMOUS_AGGREGATE_PRESENT.value)

    # Nonstandard extensions: best-effort __attribute__, __asm__, etc.
    func_text = source_bytes[func.start_byte:func.end_byte]
    if _has_nonstandard_extension(func_text):
        reasons.append(FunctionWarnReason.NONSTANDARD_EXTENSION_PATTERN.value)

    if reasons:
        return Verdict.WARN, reasons

    return Verdict.ACCEPT, reasons


# ── Helpers ──────────────────────────────────────────────────────────────────

def _has_anonymous_aggregate(node) -> bool:
    """Check if a node subtree contains anonymous struct/union/enum."""
    if node.type in ("struct_specifier", "union_specifier", "enum_specifier"):
        # Anonymous if there is no name child
        name = node.child_by_field_name("name")
        if name is None:
            # Check if it has a body (field list) — pure forward decls
            # without names are not anonymous aggregates
            body = node.child_by_field_name("body")
            if body is not None:
                return True
    for child in node.children:
        if _has_anonymous_aggregate(child):
            return True
    return False


def _has_nonstandard_extension(func_text: bytes) -> bool:
    """Best-effort detection of GCC/Clang extensions in function text."""
    text = func_text.decode("utf-8", errors="replace")
    markers = ("__attribute__", "__asm__", "__asm", "__extension__",
               "__typeof__", "__builtin_", "_Pragma")
    for m in markers:
        if m in text:
            return True
    return False
