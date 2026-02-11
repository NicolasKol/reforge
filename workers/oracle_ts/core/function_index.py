"""
Function index — extract function_definition nodes from tree-sitter CST.

For each function_definition:
  - Name, line/byte spans, signature/body/preamble spans.
  - Stable IDs: span_id, context_hash, ts_func_id, node_hash_raw.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from oracle_ts.core.normalizer import normalize_and_hash, raw_hash
from oracle_ts.core.ts_parser import ParseResult

logger = logging.getLogger(__name__)


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SpanInfo:
    """A byte/line span."""
    start_byte: int
    end_byte: int
    start_line: int   # 0-based
    end_line: int      # 0-based


@dataclass
class TsFunctionEntry:
    """One function extracted from a translation unit."""
    name: Optional[str]

    # Byte/line spans
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int

    # Sub-spans
    signature_span: SpanInfo
    body_span: SpanInfo
    preamble_span: SpanInfo   # byte 0 → start_byte of function

    # Stable IDs
    span_id: str              # tu_path:start_byte:end_byte
    context_hash: str         # sha256 of normalized function text
    ts_func_id: str           # span_id:context_hash
    node_hash_raw: str        # sha256 of raw function text

    # Verdict (set later by policy)
    verdict: str = "ACCEPT"
    reasons: List[str] = field(default_factory=list)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _extract_function_name(node) -> Optional[str]:
    """
    Extract the function name from a function_definition node.

    Grammar structure:
        function_definition → ... declarator: (function_declarator
            declarator: (identifier) | (pointer_declarator → ... identifier)
            parameters: ...)
    """
    # Find the function_declarator child
    declarator = node.child_by_field_name("declarator")
    if declarator is None:
        return None

    return _find_identifier_in_declarator(declarator)


def _find_identifier_in_declarator(node) -> Optional[str]:
    """Recursively drill into declarator nodes to find the identifier."""
    if node.type == "identifier":
        return node.text.decode("utf-8", errors="replace")

    # function_declarator → declarator (which may be identifier,
    # pointer_declarator, or parenthesized_declarator)
    if node.type == "function_declarator":
        inner = node.child_by_field_name("declarator")
        if inner is not None:
            return _find_identifier_in_declarator(inner)

    # pointer_declarator → declarator
    if node.type == "pointer_declarator":
        inner = node.child_by_field_name("declarator")
        if inner is not None:
            return _find_identifier_in_declarator(inner)

    # parenthesized_declarator → children
    if node.type == "parenthesized_declarator":
        for child in node.children:
            result = _find_identifier_in_declarator(child)
            if result is not None:
                return result

    # array_declarator → declarator
    if node.type == "array_declarator":
        inner = node.child_by_field_name("declarator")
        if inner is not None:
            return _find_identifier_in_declarator(inner)

    return None


# ── Public API ───────────────────────────────────────────────────────────────

def index_functions(parse_result: ParseResult) -> List[TsFunctionEntry]:
    """
    Walk the CST root and extract all function_definition nodes.

    Parameters
    ----------
    parse_result : ParseResult
        Output from ``parse_tu()``.

    Returns
    -------
    List[TsFunctionEntry]
        One entry per function_definition node found.
    """
    root = parse_result.tree.root_node #type: ignore
    source = parse_result.source_bytes
    tu_path = parse_result.tu_path

    entries: List[TsFunctionEntry] = []

    for node in root.children:
        if node.type != "function_definition":
            continue

        name = _extract_function_name(node)

        start_byte = node.start_byte
        end_byte = node.end_byte
        start_line = node.start_point[0]
        end_line = node.end_point[0]

        # Signature span: start of function → start of body
        # Body span: the compound_statement
        body_node = node.child_by_field_name("body")

        if body_node is not None and body_node.type == "compound_statement":
            sig_span = SpanInfo(
                start_byte=start_byte,
                end_byte=body_node.start_byte,
                start_line=start_line,
                end_line=body_node.start_point[0],
            )
            body_span = SpanInfo(
                start_byte=body_node.start_byte,
                end_byte=body_node.end_byte,
                start_line=body_node.start_point[0],
                end_line=body_node.end_point[0],
            )
        else:
            # Fallback: entire node is signature, no distinct body
            sig_span = SpanInfo(
                start_byte=start_byte,
                end_byte=end_byte,
                start_line=start_line,
                end_line=end_line,
            )
            body_span = SpanInfo(
                start_byte=end_byte,
                end_byte=end_byte,
                start_line=end_line,
                end_line=end_line,
            )

        # Preamble: everything before this function
        preamble_span = SpanInfo(
            start_byte=0,
            end_byte=start_byte,
            start_line=0,
            end_line=start_line,
        )

        # Extract function text for hashing
        func_text = source[start_byte:end_byte]
        ctx_hash = normalize_and_hash(func_text)
        raw_h = raw_hash(func_text)

        span_id = f"{tu_path}:{start_byte}:{end_byte}"
        ts_func_id = f"{span_id}:{ctx_hash}"

        entries.append(TsFunctionEntry(
            name=name,
            start_line=start_line,
            end_line=end_line,
            start_byte=start_byte,
            end_byte=end_byte,
            signature_span=sig_span,
            body_span=body_span,
            preamble_span=preamble_span,
            span_id=span_id,
            context_hash=ctx_hash,
            ts_func_id=ts_func_id,
            node_hash_raw=raw_h,
        ))

    return entries
