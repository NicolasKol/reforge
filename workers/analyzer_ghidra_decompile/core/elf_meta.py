"""
ELF metadata — validate ELF binary and compute SHA256.

Responsibilities:
  - Validate that a file is a valid ELF binary.
  - Read architecture (EM_X86_64 required for v1 profile).
  - Compute file SHA256 for binary_id.
  - This module does NOT parse DWARF data.
"""
import hashlib
from pathlib import Path
from typing import Optional, Tuple


def compute_sha256(path: str | Path) -> str:
    """Compute SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_elf(path: str | Path) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate that *path* is a valid ELF binary and read its architecture.

    Returns
    -------
    (is_valid, machine_string, error_message)
        is_valid: True if the file is a valid ELF.
        machine_string: e.g. "EM_X86_64" or None.
        error_message: reason for invalid, or None.
    """
    p = Path(path)
    if not p.exists():
        return False, None, f"File not found: {path}"

    try:
        from elftools.elf.elffile import ELFFile
        from elftools.common.exceptions import ELFError

        with open(p, "rb") as f:
            try:
                elffile = ELFFile(f)
            except ELFError as e:
                return False, None, f"Not a valid ELF: {e}"

            machine = elffile.header.e_machine
            return True, machine, None
    except ImportError:
        # pyelftools not available — fallback to magic bytes
        with open(p, "rb") as f:
            magic = f.read(4)
        if magic == b"\x7fELF":
            return True, None, None
        return False, None, "Not an ELF file (bad magic bytes)"
