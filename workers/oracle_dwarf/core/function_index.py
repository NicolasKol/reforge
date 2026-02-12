"""
Function index — enumerate subprogram DIEs and normalize code ranges.

Responsibilities:
  - Walk the DIE tree of each CU and collect DW_TAG_subprogram entries.
  - Skip declaration-only DIEs (DW_AT_declaration = true).
  - Normalize code ranges into a canonical list of [low, high) segments
    using DW_AT_low_pc / DW_AT_high_pc (DWARF v4 offset form or address
    form) and DW_AT_ranges (via .debug_ranges / .debug_rnglists).
  - Assign a stable function_id: "cu<cu_offset>:die<die_offset>".
  - Extract optional DW_AT_name and DW_AT_linkage_name.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Iterator

from elftools.dwarf.compileunit import CompileUnit
from elftools.dwarf.die import DIE
from elftools.dwarf.dwarfinfo import DWARFInfo
from elftools.dwarf.ranges import RangeLists


@dataclass(frozen=True)
class AddressRange:
    """A half-open address range [low, high)."""
    low: int
    high: int

    @property
    def size(self) -> int:
        return self.high - self.low


@dataclass
class FunctionEntry:
    """A single non-library function candidate extracted from DWARF."""

    function_id: str                      # stable key: "cu0x...:die0x..."
    die_offset: int
    cu_offset: int

    name: Optional[str] = None            # DW_AT_name
    linkage_name: Optional[str] = None    # DW_AT_linkage_name / DW_AT_MIPS_linkage_name

    ranges: List[AddressRange] = field(default_factory=list)

    is_declaration: bool = False          # DW_AT_declaration
    is_external: bool = False             # DW_AT_external
    is_inlined: bool = False              # DW_AT_inline (not resolved in v0)

    decl_file_index: Optional[int] = None  # raw DW_AT_decl_file index (before resolution)
    decl_file: Optional[str] = None        # resolved path from DW_AT_decl_file
    decl_line: Optional[int] = None        # DW_AT_decl_line
    decl_column: Optional[int] = None      # DW_AT_decl_column
    decl_missing_reason: Optional[str] = None  # why decl_file is None


def _decode_attr(die: DIE, attr_name: str) -> Optional[str]:
    """Decode a string attribute from a DIE, returning None if absent."""
    if attr_name not in die.attributes:
        return None
    raw = die.attributes[attr_name].value
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


def _normalize_ranges(die: DIE, cu: CompileUnit, dwarf: DWARFInfo) -> List[AddressRange]:
    """
    Compute a list of [low, high) address ranges for a subprogram DIE.

    Handles three DWARF encodings:
      1. DW_AT_low_pc + DW_AT_high_pc  (address form — high is absolute)
      2. DW_AT_low_pc + DW_AT_high_pc  (offset form — high is size)
      3. DW_AT_ranges → .debug_ranges / .debug_rnglists section
    """
    attrs = die.attributes

    # ── Case 1 & 2: low_pc + high_pc ─────────────────────────────────
    if "DW_AT_low_pc" in attrs:
        low_pc = attrs["DW_AT_low_pc"].value

        if "DW_AT_high_pc" in attrs:
            high_attr = attrs["DW_AT_high_pc"]
            # DWARF v4: if form is DW_FORM_addr, high_pc is an address;
            # otherwise it's an offset (size) from low_pc.
            if high_attr.form == "DW_FORM_addr":
                high_pc = high_attr.value
            else:
                high_pc = low_pc + high_attr.value

            if high_pc > low_pc:
                return [AddressRange(low=low_pc, high=high_pc)]

        # low_pc without high_pc — single-address function (unusual but valid)
        # Treat as zero-size; will be flagged MISSING_RANGE downstream.
        return []

    # ── Case 3: DW_AT_ranges ─────────────────────────────────────────
    if "DW_AT_ranges" in attrs:
        ranges_offset = attrs["DW_AT_ranges"].value
        try:
            range_lists = dwarf.range_lists()
            if range_lists is None:
                return []
            entries = range_lists.get_range_list_at_offset(ranges_offset)
        except Exception:
            return []

        # Each entry has begin_offset / end_offset relative to CU base.
        # Obtain the CU base address.
        top_die = cu.get_top_DIE()
        cu_base = 0
        if "DW_AT_low_pc" in top_die.attributes:
            cu_base = top_die.attributes["DW_AT_low_pc"].value

        result: List[AddressRange] = []
        for entry in entries:
            # A base-address-selection entry has begin == max addr; skip.
            if hasattr(entry, "is_absolute") or hasattr(entry, "entry_offset"):
                # pyelftools RangeEntry: begin_offset, end_offset
                begin = entry.begin_offset
                end = entry.end_offset

                # Sentinel: begin == end == 0 marks end-of-list
                if begin == 0 and end == 0:
                    continue
                # Base address selector: begin == max address
                if begin == 0xFFFFFFFFFFFFFFFF or begin == 0xFFFFFFFF:
                    cu_base = end
                    continue

                abs_begin = cu_base + begin
                abs_end = cu_base + end
                if abs_end > abs_begin:
                    result.append(AddressRange(low=abs_begin, high=abs_end))
            else:
                # Fallback for plain tuple-like objects
                try:
                    b, e = entry.begin_offset, entry.end_offset
                    if e > b:
                        result.append(AddressRange(low=cu_base + b, high=cu_base + e))
                except AttributeError:
                    continue
        return result

    return []


def _walk_dies(die: DIE) -> Iterator[DIE]:
    """Depth-first walk of the DIE tree."""
    yield die
    for child in die.iter_children():
        yield from _walk_dies(child)


def index_functions(
    cu: CompileUnit,
    cu_offset: int,
    dwarf: DWARFInfo,
) -> List[FunctionEntry]:
    """
    Enumerate all DW_TAG_subprogram DIEs in *cu* and return FunctionEntry
    objects with normalized ranges.

    Skips:
      - Declaration-only subprograms (DW_AT_declaration = True).
        These are still *recorded* with is_declaration=True so that policy
        can emit a proper DECLARATION_ONLY reason if needed — but we return
        them separately for transparency; the caller should skip them.
    """
    top_die = cu.get_top_DIE()
    entries: List[FunctionEntry] = []

    for die in _walk_dies(top_die):
        if die.tag != "DW_TAG_subprogram":
            continue

        is_decl = False
        if "DW_AT_declaration" in die.attributes:
            val = die.attributes["DW_AT_declaration"].value
            is_decl = bool(val)

        name = _decode_attr(die, "DW_AT_name")
        linkage_name = (
            _decode_attr(die, "DW_AT_linkage_name")
            or _decode_attr(die, "DW_AT_MIPS_linkage_name")
        )

        is_external = False
        if "DW_AT_external" in die.attributes:
            is_external = bool(die.attributes["DW_AT_external"].value)

        is_inlined = False
        if "DW_AT_inline" in die.attributes:
            is_inlined = True

        decl_line = None
        if "DW_AT_decl_line" in die.attributes:
            decl_line = die.attributes["DW_AT_decl_line"].value

        decl_column = None
        if "DW_AT_decl_column" in die.attributes:
            decl_column = die.attributes["DW_AT_decl_column"].value

        decl_file_index = None
        if "DW_AT_decl_file" in die.attributes:
            decl_file_index = die.attributes["DW_AT_decl_file"].value

        ranges = _normalize_ranges(die, cu, dwarf) if not is_decl else []

        fid = f"cu{cu_offset:#x}:die{die.offset:#x}"

        entries.append(
            FunctionEntry(
                function_id=fid,
                die_offset=die.offset,
                cu_offset=cu_offset,
                name=name,
                linkage_name=linkage_name,
                ranges=ranges,
                is_declaration=is_decl,
                is_external=is_external,
                is_inlined=is_inlined,
                decl_file_index=decl_file_index,
                decl_line=decl_line,
                decl_column=decl_column,
            )
        )

    return entries
