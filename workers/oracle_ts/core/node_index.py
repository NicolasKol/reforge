"""
Structural node index — extract control-flow nodes within functions.

Fixed allowlist of node types indexed per function_definition:
  compound_statement, if_statement, for_statement, while_statement,
  switch_statement, return_statement.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

from oracle_ts.core.normalizer import raw_hash

logger = logging.getLogger(__name__)

# Allowlist of node types to index
STRUCTURAL_NODE_TYPES = frozenset({
    "compound_statement",
    "if_statement",
    "for_statement",
    "while_statement",
    "switch_statement",
    "return_statement",
})


@dataclass(frozen=True)
class StructuralNode:
    """One structural node within a function body."""
    node_type: str
    start_line: int    # 0-based
    end_line: int      # 0-based
    start_byte: int
    end_byte: int
    node_hash_raw: str
    depth: int
    uncertainty_flags: List[str] = field(default_factory=list)


def index_structural_nodes(
    func_node,
    source_bytes: bytes,
    *,
    deep_nesting_threshold: int = 8,
) -> List[StructuralNode]:
    """
    Walk a function_definition node and collect structural nodes.

    Parameters
    ----------
    func_node
        A tree-sitter Node of type ``function_definition``.
    source_bytes : bytes
        Full TU source bytes (for text extraction).
    deep_nesting_threshold : int
        Depth at which ``DEEP_NESTING`` flag is raised.

    Returns
    -------
    List[StructuralNode]
    """
    results: List[StructuralNode] = []
    _walk(func_node, source_bytes, 0, deep_nesting_threshold, results)
    return results


def _walk(
    node,
    source_bytes: bytes,
    depth: int,
    threshold: int,
    out: List[StructuralNode],
) -> None:
    """Recursive walk collecting allowlisted nodes."""
    if node.type in STRUCTURAL_NODE_TYPES:
        text = source_bytes[node.start_byte:node.end_byte]
        flags: List[str] = []
        if depth >= threshold:
            flags.append("DEEP_NESTING")

        out.append(StructuralNode(
            node_type=node.type,
            start_line=node.start_point[0],
            end_line=node.end_point[0],
            start_byte=node.start_byte,
            end_byte=node.end_byte,
            node_hash_raw=raw_hash(text),
            depth=depth,
            uncertainty_flags=flags,
        ))

    for child in node.children:
        _walk(child, source_bytes, depth + 1, threshold, out)
