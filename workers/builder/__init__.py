"""
builder_synth_v2 — Synthetic ELF Builder

Compile synthetic C to ELF with GCC; emit artifacts, preprocessed TUs, and receipt.
No DWARF semantics, no alignment, no repo builds.

Profile: linux-x86_64-elf-gcc-c
Supersedes: builder_synth_v1
"""

__version__ = "2.0.0"
BUILDER_NAME = "builder_synth_v2"
BUILDER_VERSION = "v2"
PROFILE_ID = "linux-x86_64-elf-gcc-c"
