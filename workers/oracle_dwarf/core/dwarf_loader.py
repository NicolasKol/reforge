"""
DWARF loader — load DWARFInfo and iterate Compilation Units.

Responsibilities:
  - Open a validated ELF binary and obtain a DWARFInfo handle.
  - Iterate CUs and yield lightweight CUHandle descriptors.
  - Provide CU-scoped access to line programs and DIE trees.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from elftools.elf.elffile import ELFFile
from elftools.dwarf.dwarfinfo import DWARFInfo
from elftools.dwarf.compileunit import CompileUnit


@dataclass
class CUHandle:
    """Lightweight descriptor for a single Compilation Unit."""

    cu_offset: int         # byte offset of the CU header in .debug_info
    cu_index: int          # 0-based sequential index
    comp_dir: Optional[str]  # DW_AT_comp_dir (absolute build directory)
    cu_name: Optional[str]   # DW_AT_name (main source file)
    language: Optional[int]  # DW_AT_language constant
    cu: CompileUnit        # pyelftools CU object (needed by function_index/line_mapper)


class DwarfLoader:
    """
    Holds an open ELF file handle and its DWARFInfo.

    Usage::

        with DwarfLoader(path) as loader:
            for cu_handle in loader.iter_cus():
                ...

    The file handle is kept open for the lifetime of the context manager
    because pyelftools lazily reads DWARF data on demand.
    """

    def __init__(self, path: str):
        self._path = path
        self._file = None
        self._elffile: Optional[ELFFile] = None
        self._dwarfinfo: Optional[DWARFInfo] = None

    # -- context manager -------------------------------------------------------

    def __enter__(self) -> "DwarfLoader":
        self._file = open(self._path, "rb")
        self._elffile = ELFFile(self._file)
        if not self._elffile.has_dwarf_info():
            raise ValueError(f"No DWARF info in {self._path}")
        self._dwarfinfo = self._elffile.get_dwarf_info()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._file is not None:
            self._file.close()
        return False

    # -- public API ------------------------------------------------------------

    @property
    def dwarf(self) -> DWARFInfo:
        assert self._dwarfinfo is not None, "DwarfLoader not entered as context manager"
        return self._dwarfinfo

    def iter_cus(self) -> Iterator[CUHandle]:
        """Yield a CUHandle for every Compilation Unit."""
        for idx, cu in enumerate(self.dwarf.iter_CUs()):
            top_die = cu.get_top_DIE()
            attrs = top_die.attributes

            comp_dir = None
            if "DW_AT_comp_dir" in attrs:
                raw = attrs["DW_AT_comp_dir"].value
                comp_dir = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)

            cu_name = None
            if "DW_AT_name" in attrs:
                raw = attrs["DW_AT_name"].value
                cu_name = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)

            lang = None
            if "DW_AT_language" in attrs:
                lang = attrs["DW_AT_language"].value

            yield CUHandle(
                cu_offset=cu.cu_offset,
                cu_index=idx,
                comp_dir=comp_dir,
                cu_name=cu_name,
                language=lang,
                cu=cu,
            )
