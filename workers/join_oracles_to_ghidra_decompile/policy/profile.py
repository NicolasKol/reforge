"""
Profile — frozen configuration for the oracle↔Ghidra join.

All tunable parameters live here.  The profile is immutable at
construction time and threaded through every core function so that
results are fully reproducible given the same profile + inputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple


# Frozen name sets copied from analyzer_ghidra_decompile/policy/noise.py
# so this package has zero import-time dependency on the analyzer.

_AUX_INIT_FINI_NAMES: Tuple[str, ...] = (
    "_init",
    "_fini",
    "_DT_INIT",
    "_DT_FINI",
    "_INIT_0",
    "_FINI_0",
)

_COMPILER_AUX_NAMES: Tuple[str, ...] = (
    "frame_dummy",
    "register_tm_clones",
    "deregister_tm_clones",
    "__do_global_dtors_aux",
    "__libc_csu_init",
    "__libc_csu_fini",
    "__cxa_finalize",
    "__cxa_atexit",
    "__stack_chk_fail",
    "__gmon_start__",
    "_start",
    "__libc_start_main",
    "_dl_relocate_static_pie",
    "__x86.get_pc_thunk.bx",
    "__x86.get_pc_thunk.ax",
    "_ITM_registerTMCloneTable",
    "_ITM_deregisterTMCloneTable",
    "__cxa_finalize@@GLIBC_2.17",
)

_DEFAULT_AUX_NAMES: Tuple[str, ...] = _AUX_INIT_FINI_NAMES + _COMPILER_AUX_NAMES

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
    aux_function_names: Tuple[str, ...] = _DEFAULT_AUX_NAMES

    # ── High-confidence gate: fatal warning codes ─────────────────────────
    fatal_warnings: Tuple[str, ...] = _DEFAULT_FATAL_WARNINGS

    # ── Identity ──────────────────────────────────────────────────────────
    profile_id: str = "join-oracles-ghidra-v1"

    @classmethod
    def v1(cls) -> JoinOraclesGhidraProfile:
        """Return the canonical v1 profile with all defaults."""
        return cls()
