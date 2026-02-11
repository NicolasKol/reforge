"""
Origin map — parse GCC #line directives from .i files to build
a mapping from .i line numbers to original source (path, line) pairs.

The forward map is the authoritative data structure:
  .i_line_number  →  (original_path, original_line) | None

Lines that map to synthetic (<built-in>, <command-line>) or system-header
paths are mapped to None so they do not dilute overlap scoring.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# GCC preprocessor line markers:
#   # 123 "path"
#   # 123 "path" 1 3 4
#   #line 123 "path"
# The path may contain escaped characters (rare).
_LINE_DIRECTIVE_RE = re.compile(
    r'^#(?:\s*line)?\s+(\d+)\s+"((?:[^"\\]|\\.)*)"(?:\s+([\d\s]*))?$'
)

# Synthetic/built-in markers that GCC emits — not real source files.
_SYNTHETIC_PATH_PATTERNS = frozenset({
    "<built-in>",
    "<command-line>",
})


@dataclass
class OriginMap:
    """
    Forward map from .i line numbers to original source locations.

    Attributes
    ----------
    tu_path : str
        Path to the .i file this map was built from.
    forward : List[Optional[Tuple[str, int]]]
        Index = 0-based .i line number.
        Value = (original_path, original_line) or None for excluded lines.
    origin_available : bool
        True if at least one #line directive was found.
    n_total_lines : int
        Total number of lines in the .i file.
    excluded_prefixes : Tuple[str, ...]
        Path prefixes that were excluded from mapping.
    """

    tu_path: str
    forward: List[Optional[Tuple[str, int]]]
    origin_available: bool
    n_total_lines: int
    excluded_prefixes: Tuple[str, ...] = ()


def _is_excluded_path(
    path: str,
    excluded_prefixes: Tuple[str, ...],
) -> bool:
    """Check if a path is synthetic or matches excluded prefixes."""
    if path in _SYNTHETIC_PATH_PATTERNS:
        return True
    # Angle-bracket markers like <built-in>
    if path.startswith("<") and path.endswith(">"):
        return True
    for prefix in excluded_prefixes:
        if path.startswith(prefix):
            return True
    return False


def build_origin_map(
    i_content: str,
    tu_path: str,
    excluded_prefixes: Tuple[str, ...] = (),
) -> OriginMap:
    """
    Parse a .i file's content and build a forward origin map.

    Parameters
    ----------
    i_content : str
        Full text content of the .i file.
    tu_path : str
        Path identifier for the .i file.
    excluded_prefixes : Tuple[str, ...]
        Path prefixes to exclude (system headers, etc.).

    Returns
    -------
    OriginMap
        Forward map from .i line → original (path, line).
    """
    lines = i_content.split("\n")
    n_lines = len(lines)

    # Pre-fill forward map with None (unmapped)
    forward: List[Optional[Tuple[str, int]]] = [None] * n_lines

    # Current origin state (set by #line directives)
    current_path: Optional[str] = None
    current_line: Optional[int] = None
    current_excluded: bool = True
    found_any_directive = False

    for i_line_idx, raw_line in enumerate(lines):
        stripped = raw_line.rstrip()

        m = _LINE_DIRECTIVE_RE.match(stripped)
        if m is not None:
            found_any_directive = True
            orig_line = int(m.group(1))
            orig_path = m.group(2)
            # Unescape any backslash-escaped characters
            orig_path = orig_path.replace("\\\\", "\\").replace('\\"', '"')

            current_path = orig_path
            current_line = orig_line
            current_excluded = _is_excluded_path(orig_path, excluded_prefixes)

            # GCC flag 3 = system header → treat as excluded
            flags_str = m.group(3)
            if flags_str and "3" in flags_str.split():
                current_excluded = True

            # The #line directive itself does not map to source content
            forward[i_line_idx] = None
            continue

        # Regular content line
        if current_path is not None and current_line is not None:
            if not current_excluded:
                forward[i_line_idx] = (current_path, current_line)
            # else: excluded path → stays None
            current_line += 1
        # else: before any #line directive → stays None

    return OriginMap(
        tu_path=tu_path,
        forward=forward,
        origin_available=found_any_directive,
        n_total_lines=n_lines,
        excluded_prefixes=excluded_prefixes,
    )


def query_forward(
    origin_map: OriginMap,
    i_line: int,
) -> Optional[Tuple[str, int]]:
    """
    Look up the original (path, line) for a given .i line number.

    Parameters
    ----------
    origin_map : OriginMap
    i_line : int
        0-based .i line number.

    Returns
    -------
    (original_path, original_line) or None if unmapped/excluded.
    """
    if 0 <= i_line < len(origin_map.forward):
        return origin_map.forward[i_line]
    return None
