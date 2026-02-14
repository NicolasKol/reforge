"""
CFG processor — basic-block graph analysis per function.

Responsibilities:
  - Compute bb_count, edge_count, cyclomatic complexity.
  - Detect indirect jumps and compute unresolved_indirect_jump_count.
  - Assign cfg_completeness (HIGH | MEDIUM | LOW) per §7.2.
  - Build block descriptors with successor references.
"""
from typing import Dict, List, Optional

from analyzer_ghidra_decompile.core.raw_parser import RawBlock


def process_cfg(
    raw_blocks: List[RawBlock],
    warnings: List[str],
) -> dict:
    """
    Process raw basic blocks into a CFG record.

    Parameters
    ----------
    raw_blocks : list[RawBlock]
        Blocks emitted by the Java script for one function.
    warnings : list[str]
        Normalized function warning codes (used for completeness).

    Returns
    -------
    dict with bb_count, edge_count, cyclomatic, has_indirect_jumps,
    unresolved_indirect_jump_count, cfg_completeness, blocks[].
    """
    bb_count = len(raw_blocks)

    # Build address-to-block_id map for successor resolution
    addr_to_id: Dict[int, int] = {}
    for blk in raw_blocks:
        addr_to_id[blk.start_va] = blk.block_id

    # Build block descriptors with resolved successor block_ids
    blocks_out = []
    edge_count = 0

    for blk in raw_blocks:
        succ_ids = []
        for sva in blk.succ_va:
            bid = addr_to_id.get(sva)
            if bid is not None:
                succ_ids.append(bid)
                edge_count += 1

        blocks_out.append({
            "block_id": blk.block_id,
            "start_va": blk.start_va,
            "end_va": blk.end_va,
            "succ": succ_ids,
        })

    # Cyclomatic complexity: E - N + 2 for single-entry graphs
    cyclomatic = edge_count - bb_count + 2 if bb_count > 0 else 0

    # Indirect jump detection from warnings
    has_indirect = "UNRESOLVED_INDIRECT_JUMP" in warnings
    unresolved_count = warnings.count("UNRESOLVED_INDIRECT_JUMP")

    # CFG completeness (§7.2)
    cfg_completeness = compute_cfg_completeness(warnings)

    # Override: if no blocks at all, completeness cannot be HIGH
    if bb_count == 0 and cfg_completeness == "HIGH":
        cfg_completeness = "LOW"

    return {
        "bb_count": bb_count,
        "edge_count": edge_count,
        "cyclomatic": cyclomatic,
        "has_indirect_jumps": has_indirect,
        "unresolved_indirect_jump_count": unresolved_count,
        "cfg_completeness": cfg_completeness,
        "blocks": blocks_out,
    }


def compute_cfg_completeness(warnings: List[str]) -> str:
    """
    Compute coarse cfg_completeness score (§7.2).

    LOW if UNRESOLVED_INDIRECT_JUMP or TRUNCATED_CONTROL_FLOW.
    MEDIUM if UNREACHABLE_BLOCKS_REMOVED or SWITCH_RECOVERY_FAILED.
    HIGH otherwise.
    """
    low_triggers = {
        "UNRESOLVED_INDIRECT_JUMP",
        "TRUNCATED_CONTROL_FLOW",
        "BAD_INSTRUCTION_DATA",
    }
    medium_triggers = {
        "UNREACHABLE_BLOCKS_REMOVED",
        "SWITCH_RECOVERY_FAILED",
    }

    warning_set = set(warnings)

    if warning_set & low_triggers:
        return "LOW"
    if warning_set & medium_triggers:
        return "MEDIUM"
    return "HIGH"
