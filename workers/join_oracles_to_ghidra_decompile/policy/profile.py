"""
Profile — frozen configuration for the oracle↔Ghidra join.

All tunable parameters live here.  The profile is immutable at
construction time and threaded through every core function so that
results are fully reproducible given the same profile + inputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from data.noise_lists import ALL_AUX_NAMES


_DEFAULT_FATAL_WARNINGS: Tuple[str, ...] = (
    "DECOMPILE_TIMEOUT",
    "UNRESOLVED_INDIRECT_JUMP",
)


@dataclass(frozen=True)
class JoinOraclesGhidraProfile:
    """Immutable configuration for the oracle↔Ghidra join (v1)."""

    # ── Address-overlap thresholds ────────────────────────────────────────
    strong_overlap_threshold: float = 0.9
    weak_overlap_threshold: float = 0.3
    near_tie_epsilon: float = 0.05          # fraction of best overlap_bytes

    # ── Noise / aux function name sets ────────────────────────────────────
    aux_function_names: Tuple[str, ...] = tuple(sorted(ALL_AUX_NAMES))

    # ── High-confidence gate: fatal warning codes ─────────────────────────
    fatal_warnings: Tuple[str, ...] = _DEFAULT_FATAL_WARNINGS

    # ── Identity ──────────────────────────────────────────────────────────
    profile_id: str = "join-oracles-ghidra-v1"

    @classmethod
    def v1(cls) -> JoinOraclesGhidraProfile:
        """Return the canonical v1 profile with all defaults."""
        return cls()
