"""
Profile descriptor for oracle_ts.

Frozen dataclass with thresholds and parser identity.
Not user-selectable in v0 — use ``TsProfile.v0()``.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TsProfile:
    """oracle_ts v0 support profile."""

    profile_id: str
    parser_name: str = "tree-sitter-c"
    deep_nesting_threshold: int = 8

    @classmethod
    def v0(cls) -> TsProfile:
        """The single supported profile for oracle_ts v0."""
        return cls(profile_id="source-c-treesitter")
