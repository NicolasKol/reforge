"""
test_cfg_clamp — Verify cyclomatic complexity is never negative.

Exercises Fix A2: max(0, E - N + 2) clamp for unresolved successors.
"""
from analyzer_ghidra_decompile.core.cfg_processor import process_cfg
from analyzer_ghidra_decompile.core.raw_parser import RawBlock


class TestCyclomaticClamp:
    """Cyclomatic complexity must be >= 0 even with unresolved edges."""

    def test_no_resolved_successors(self):
        """3 blocks, all successors point outside the function → 0 resolved edges.
        Without clamp: E-N+2 = 0-3+2 = -1.  With clamp: max(0, -1) = 0."""
        blocks = [
            RawBlock(block_id=0, start_va=0x1000, end_va=0x1010, succ_va=[0x9999]),
            RawBlock(block_id=1, start_va=0x1010, end_va=0x1020, succ_va=[0x9998]),
            RawBlock(block_id=2, start_va=0x1020, end_va=0x1030, succ_va=[0x9997]),
        ]
        result = process_cfg(blocks, warnings=[])

        assert result["bb_count"] == 3
        assert result["edge_count"] == 0
        assert result["cyclomatic"] >= 0
        assert result["cyclomatic"] == 0

    def test_all_resolved_successors(self):
        """Normal case: 3 blocks, 3 edges → cyclomatic = 3-3+2 = 2."""
        blocks = [
            RawBlock(block_id=0, start_va=0x1000, end_va=0x1010, succ_va=[0x1010]),
            RawBlock(block_id=1, start_va=0x1010, end_va=0x1020, succ_va=[0x1020, 0x1000]),
            RawBlock(block_id=2, start_va=0x1020, end_va=0x1030, succ_va=[]),
        ]
        result = process_cfg(blocks, warnings=[])

        assert result["cyclomatic"] == 2

    def test_single_block_no_edges(self):
        """Single block: E-N+2 = 0-1+2 = 1."""
        blocks = [
            RawBlock(block_id=0, start_va=0x1000, end_va=0x1010, succ_va=[]),
        ]
        result = process_cfg(blocks, warnings=[])
        assert result["cyclomatic"] == 1

    def test_empty_blocks(self):
        """No blocks → cyclomatic = 0."""
        result = process_cfg([], warnings=[])
        assert result["cyclomatic"] == 0
