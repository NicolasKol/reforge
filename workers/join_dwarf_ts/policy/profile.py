"""
Profile — frozen configuration for join_dwarf_ts.

A profile captures every tunable parameter that affects the join outcome.
The ``v0()`` classmethod returns the default v0 profile.

Contract: the profile_id is deterministic and uniquely identifies the
configuration.  Changing any parameter changes the profile_id.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class JoinProfile:
    """Immutable join configuration."""

    # ── Scoring thresholds ───────────────────────────────────────────
    overlap_threshold: float = 0.7
    epsilon: float = 0.02
    min_overlap_lines: int = 1

    # ── Origin-map filtering ─────────────────────────────────────────
    excluded_path_prefixes: Tuple[str, ...] = (
        "/usr/include",
        "/usr/lib/gcc",
        "<built-in>",
        "<command-line>",
    )

    # ── Identity ─────────────────────────────────────────────────────
    profile_id: str = "join-dwarf-ts-v0"

    @classmethod
    def v0(cls) -> JoinProfile:
        """Return the canonical v0 profile (all defaults)."""
        return cls()
