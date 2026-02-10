"""
builder_synth_v1 — Synthetic ELF Builder

Compile synthetic C to ELF with GCC; emit artifacts + receipt.
No DWARF semantics, no alignment, no repo builds.

Profile: linux-x86_64-elf-gcc-c
"""

__version__ = "1.0.0"
BUILDER_NAME = "builder_synth_v1"
BUILDER_VERSION = "v1"
PROFILE_ID = "linux-x86_64-elf-gcc-c"
