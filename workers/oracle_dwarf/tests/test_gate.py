"""
test_gate — binary-level gate (ACCEPT / REJECT).

Tests verify invariant properties:
  - A debug binary with .debug_info + .debug_line → ACCEPT at binary gate.
  - A stripped binary → REJECT with NO_DEBUG_INFO reason.
  - A non-ELF file → REJECT with DWARF_PARSE_ERROR.
"""
from oracle_dwarf.core.elf_reader import read_elf
from oracle_dwarf.policy.profile import Profile
from oracle_dwarf.policy.verdict import Verdict, gate_binary, BinaryRejectReason
from oracle_dwarf.runner import run_oracle


class TestBinaryGate:
    """Binary-level gate tests."""

    def test_debug_binary_accepted(self, debug_binary_O0):
        """A debug-variant binary must pass the binary gate."""
        meta = read_elf(str(debug_binary_O0))
        profile = Profile.v0()
        verdict, reasons = gate_binary(meta, profile)

        assert verdict == Verdict.ACCEPT
        assert reasons == []
        assert meta.has_debug_info is True
        assert meta.has_debug_line is True

    def test_stripped_binary_rejected(self, stripped_binary):
        """A stripped binary must be REJECT with NO_DEBUG_INFO."""
        meta = read_elf(str(stripped_binary))
        profile = Profile.v0()
        verdict, reasons = gate_binary(meta, profile)

        assert verdict == Verdict.REJECT
        assert BinaryRejectReason.NO_DEBUG_INFO.value in reasons

    def test_not_elf_rejected(self, not_elf):
        """A non-ELF file produces a REJECT report via run_oracle."""
        report, functions = run_oracle(str(not_elf))

        assert report.verdict == "REJECT"
        assert BinaryRejectReason.DWARF_PARSE_ERROR.value in report.reasons
        assert functions.functions == []

    def test_elf_meta_fields(self, debug_binary_O0):
        """ElfMeta must have consistent structural fields."""
        meta = read_elf(str(debug_binary_O0))

        assert meta.machine == "EM_X86_64"
        assert meta.elf_class == 64
        assert meta.file_size > 0
        assert len(meta.file_sha256) == 64  # hex SHA-256
        assert ".debug_info" in meta.debug_section_names
        assert ".debug_line" in meta.debug_section_names

    def test_runner_on_stripped_binary(self, stripped_binary):
        """run_oracle on stripped binary → binary-level REJECT, no functions."""
        report, functions = run_oracle(str(stripped_binary))

        assert report.verdict == "REJECT"
        assert report.function_counts.total == 0
        assert len(functions.functions) == 0
