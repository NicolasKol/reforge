"""
Tree-sitter C parser wrapper.

Parses preprocessed C translation units (.i) using the tree-sitter C
grammar and reports parse status, errors, and the concrete syntax tree.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path
from typing import List, Tuple

import tree_sitter_c as tsc
from tree_sitter import Language, Parser, Node

logger = logging.getLogger(__name__)

# ── Language / parser singletons ─────────────────────────────────────────────

_C_LANGUAGE = Language(tsc.language())
_PARSER: Parser | None = None


def _get_parser() -> Parser:
    """Return a cached tree-sitter C parser."""
    global _PARSER
    if _PARSER is None:
        _PARSER = Parser(_C_LANGUAGE)
    return _PARSER


def _parser_version_string() -> str:
    """Runtime + grammar version for provenance."""
    try:
        ts_version = version("tree-sitter")
    except Exception:
        ts_version = "unknown"
    
    try:
        tsc_version = version("tree-sitter-c")
    except Exception:
        tsc_version = "unknown"
    
    return f"tree-sitter=={ts_version}; tree-sitter-c=={tsc_version}"


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ParseError:
    """A single error node found in the parse tree."""
    line: int        # 0-based
    column: int      # 0-based
    message: str


@dataclass
class ParseResult:
    """Result of parsing a single translation unit."""
    tree: object                         # tree_sitter.Tree
    source_bytes: bytes                  # raw file content
    tu_path: str                         # as supplied (may be relative)
    tu_hash: str                         # sha256 of raw text
    parser_version: str
    parse_status: str                    # "OK" | "ERROR"
    parse_errors: List[ParseError] = field(default_factory=list)


# ── Error collection ─────────────────────────────────────────────────────────

def _collect_errors(node: Node, errors: List[ParseError]) -> None:
    """Walk the tree and collect ERROR / MISSING nodes."""
    if node.type == "ERROR" or node.is_missing:
        row, col = node.start_point
        msg = f"MISSING({node.type})" if node.is_missing else "ERROR"
        errors.append(ParseError(line=row, column=col, message=msg))
    for child in node.children:
        _collect_errors(child, errors)


# ── Public API ───────────────────────────────────────────────────────────────

def parse_tu(i_path: Path) -> ParseResult:
    """
    Parse a preprocessed C translation unit.

    Parameters
    ----------
    i_path : Path
        Path to the ``.i`` file.

    Returns
    -------
    ParseResult
        Contains the CST, raw bytes, hash, parser version, and any
        parse errors found.
    """
    source_bytes = i_path.read_bytes()
    tu_hash = hashlib.sha256(source_bytes).hexdigest()

    parser = _get_parser()
    tree = parser.parse(source_bytes)

    # Collect errors
    errors: List[ParseError] = []
    _collect_errors(tree.root_node, errors)

    parse_status = "ERROR" if errors else "OK"

    return ParseResult(
        tree=tree,
        source_bytes=source_bytes,
        tu_path=str(i_path),
        tu_hash=tu_hash,
        parser_version=_parser_version_string(),
        parse_status=parse_status,
        parse_errors=errors,
    )
