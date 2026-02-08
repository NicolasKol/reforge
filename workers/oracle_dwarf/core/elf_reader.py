"""
ELF reader — open an ELF binary and extract structural metadata.

Responsibilities:
  - Validate that the file is a valid ELF binary.
  - Check architecture (EM_X86_64 required for v0 profile).
  - Detect presence of .debug_info and .debug_line sections.
  - Read the build-id from .note.gnu.build-id if present.
  - Return an ElfMeta dataclass with all gate-relevant facts.

This module intentionally does NOT parse DWARF data.
"""
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from elftools.elf.elffile import ELFFile
from elftools.common.exceptions import ELFError


@dataclass(frozen=True)
class ElfMeta:
    """Structural metadata extracted from an ELF binary."""

    path: str
    file_sha256: str
    file_size: int

    # ELF header fields
    elf_class: int           # ELFCLASS32=1 or ELFCLASS64=2
    machine: str             # e.g. "EM_X86_64", "EM_386"
    endianness: str          # "little" or "big"

    # Debug section presence
    has_debug_info: bool
    has_debug_line: bool
    has_debug_ranges: bool
    has_debug_str: bool
    debug_section_names: List[str] = field(default_factory=list)

    # Build-ID (GNU .note section)
    build_id: Optional[str] = None

    # Split-DWARF indicator
    has_split_dwarf: bool = False


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_build_id(elffile: ELFFile) -> Optional[str]:
    """Read GNU build-id from .note.gnu.build-id section."""
    for section in elffile.iter_sections():
        if section.name == ".note.gnu.build-id":
            # The note section has a data payload; build-id is the desc field
            # of the first NT_GNU_BUILD_ID note.
            try:
                for note in section.iter_notes():
                    if note["n_type"] == "NT_GNU_BUILD_ID":
                        return note["n_desc"]
            except Exception:
                pass
    return None


def read_elf(path: str) -> ElfMeta:
    """
    Open *path* as an ELF file and return structural metadata.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    ELFError
        If the file is not a valid ELF binary.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Binary not found: {path}")

    file_sha256 = _sha256(p)
    file_size = p.stat().st_size

    with open(p, "rb") as f:
        try:
            elffile = ELFFile(f)
        except ELFError:
            raise

        machine = elffile.header.e_machine
        elf_class = elffile.elfclass  # 32 or 64
        endianness = "little" if elffile.little_endian else "big"

        # Collect section names
        section_names = [s.name for s in elffile.iter_sections()]
        debug_sections = [n for n in section_names if n.startswith(".debug_")]

        has_debug_info = ".debug_info" in section_names
        has_debug_line = ".debug_line" in section_names
        has_debug_ranges = ".debug_ranges" in section_names or ".debug_rnglists" in section_names
        has_debug_str = ".debug_str" in section_names

        # Split-DWARF: presence of .debug_info.dwo or .gnu_debugaltlink
        has_split_dwarf = any(
            n.endswith(".dwo") or n == ".gnu_debugaltlink"
            for n in section_names
        )

        build_id = _read_build_id(elffile)

    return ElfMeta(
        path=str(p),
        file_sha256=file_sha256,
        file_size=file_size,
        elf_class=elf_class,
        machine=machine,
        endianness=endianness,
        has_debug_info=has_debug_info,
        has_debug_line=has_debug_line,
        has_debug_ranges=has_debug_ranges,
        has_debug_str=has_debug_str,
        debug_section_names=debug_sections,
        build_id=build_id,
        has_split_dwarf=has_split_dwarf,
    )
