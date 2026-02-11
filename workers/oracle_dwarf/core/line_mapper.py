"""
Line mapper — compute per-function line spans from .debug_line.

Responsibilities:
  - Parse the line program for a CU.
  - Given a function's address ranges, intersect the line rows to find:
      • The set of (file_path, line_number) pairs inside those ranges.
      • The *dominant* source file (highest row count).
      • dominant_file_ratio (rows in dominant file / total rows).
      • line_min, line_max (within the dominant file).
      • n_line_rows (total rows matching the ranges).
  - Resolve file indices to paths using the line program header file_entry
    list, adjusting for DWARF v4 (1-based) vs v5 (0-based) indexing.
"""
from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Dict, List, Optional, Tuple

from elftools.dwarf.compileunit import CompileUnit
from elftools.dwarf.dwarfinfo import DWARFInfo
from elftools.dwarf.lineprogram import LineProgram

from oracle_dwarf.core.function_index import AddressRange


@dataclass(frozen=True)
class LineRow:
    """A single row from the line-number state machine."""
    address: int
    file_index: int
    line: int
    is_stmt: bool


@dataclass(frozen=True)
class LineSpan:
    """Aggregated line information for a single function's address ranges."""

    dominant_file: Optional[str] = None
    dominant_file_ratio: float = 0.0
    line_min: Optional[int] = None
    line_max: Optional[int] = None
    n_line_rows: int = 0

    # All files that contributed rows (for MULTI_FILE_RANGE detection)
    file_row_counts: Dict[str, int] = field(default_factory=dict)

    # Per-(file, line) hit counts — multiset of DWARF line evidence.
    # Each key is (file_path, line_number), value is the count of
    # state-machine rows mapping to that pair.  Added in schema v0.2
    # to support join_dwarf_ts without re-parsing the binary.
    line_rows: Dict[Tuple[str, int], int] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return self.n_line_rows == 0


def _build_line_table(line_program: LineProgram) -> List[LineRow]:
    """
    Replay the line-number state machine and collect all rows.

    We iterate the *entries* (not get_entries()) because we need the
    state snapshots.  Each entry with a non-None state is a row.
    """
    rows: List[LineRow] = []
    for entry in line_program.get_entries():
        state = entry.state
        if state is None:
            continue
        # end_sequence entries mark the end of a contiguous block;
        # they point one past the last address and should not be
        # treated as real source locations.
        if state.end_sequence:
            continue
        rows.append(LineRow(
            address=state.address,
            file_index=state.file,
            line=state.line,
            is_stmt=state.is_stmt,
        ))
    return rows


def _resolve_file(
    file_index: int,
    line_program: LineProgram,
    comp_dir: Optional[str],
) -> str:
    """
    Resolve a file index to a path string.

    DWARF v4 uses 1-based file indices; DWARF v5 uses 0-based.
    The line program header has a ``file_entry`` list.
    """
    header = line_program.header
    version = header.get("version", 4)
    file_entries = header.get("file_entry", [])

    if not file_entries:
        return f"<unknown file {file_index}>"

    # Adjust for 0-based vs 1-based indexing
    if version >= 5:
        idx = file_index
    else:
        idx = file_index - 1

    if idx < 0 or idx >= len(file_entries):
        return f"<unknown file {file_index}>"

    entry = file_entries[idx]

    # entry.name may be bytes or str
    name = entry.name
    if isinstance(name, bytes):
        name = name.decode("utf-8", errors="replace")

    # entry.dir_index references the include_directory list
    dir_index = entry.dir_index
    include_dirs = header.get("include_directory", [])

    dir_path = ""
    if dir_index > 0 and include_dirs:
        # include_directory is 0-based in the header array,
        # but dir_index is 1-based in DWARF v4.
        adj = dir_index - 1 if version < 5 else dir_index
        if 0 <= adj < len(include_dirs):
            d = include_dirs[adj]
            if isinstance(d, bytes):
                d = d.decode("utf-8", errors="replace")
            dir_path = d

    if dir_path:
        full = str(PurePosixPath(dir_path) / name)
    else:
        full = name

    # If the path is relative and we have comp_dir, make it absolute
    if comp_dir and not PurePosixPath(full).is_absolute():
        full = str(PurePosixPath(comp_dir) / full)

    return full


def _in_ranges(address: int, ranges: List[AddressRange]) -> bool:
    """Check whether *address* falls inside any of the [low, high) ranges."""
    for r in ranges:
        if r.low <= address < r.high:
            return True
    return False


def compute_line_span(
    cu: CompileUnit,
    dwarf: DWARFInfo,
    comp_dir: Optional[str],
    ranges: List[AddressRange],
) -> LineSpan:
    """
    Given a function's address *ranges* and its parent CU,
    intersect the CU's line program to produce a LineSpan.
    """
    if not ranges:
        return LineSpan()

    line_program = dwarf.line_program_for_CU(cu)
    if line_program is None:
        return LineSpan()

    rows = _build_line_table(line_program)
    if not rows:
        return LineSpan()

    # Collect rows that fall inside the function ranges
    matched: List[Tuple[str, int]] = []  # (file_path, line)
    for row in rows:
        if _in_ranges(row.address, ranges):
            path = _resolve_file(row.file_index, line_program, comp_dir)
            matched.append((path, row.line))

    if not matched:
        return LineSpan(n_line_rows=0)

    # Count rows per file
    file_counts: Counter = Counter(path for path, _ in matched)
    dominant_file, dominant_count = file_counts.most_common(1)[0]
    total = len(matched)
    ratio = dominant_count / total if total > 0 else 0.0

    # Line span within the dominant file
    dominant_lines = [line for path, line in matched if path == dominant_file]
    line_min = min(dominant_lines)
    line_max = max(dominant_lines)

    # Per-(file, line) multiset — preserves granular evidence for join
    line_row_counts: Counter = Counter(matched)

    return LineSpan(
        dominant_file=dominant_file,
        dominant_file_ratio=round(ratio, 4),
        line_min=line_min,
        line_max=line_max,
        n_line_rows=total,
        file_row_counts=dict(file_counts),
        line_rows=dict(line_row_counts),
    )
