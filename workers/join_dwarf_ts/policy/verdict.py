"""
Verdict — join outcome classification.

Each DWARF target function is classified into one of three verdicts.
Reason tags are accumulated to explain *why* the verdict was assigned.
"""
from __future__ import annotations

from enum import Enum


class JoinVerdict(str, Enum):
    """Final alignment verdict for one DWARF function."""

    MATCH = "MATCH"
    AMBIGUOUS = "AMBIGUOUS"
    NO_MATCH = "NO_MATCH"


class MatchReason(str, Enum):
    """Reason tags that may appear alongside MATCH."""

    UNIQUE_BEST = "UNIQUE_BEST"


class AmbiguousReason(str, Enum):
    """Reason tags that may appear alongside AMBIGUOUS."""

    NEAR_TIE = "NEAR_TIE"
    HEADER_REPLICATION_COLLISION = "HEADER_REPLICATION_COLLISION"
    MULTI_FILE_RANGE_PROPAGATED = "MULTI_FILE_RANGE_PROPAGATED"


class NoMatchReason(str, Enum):
    """Reason tags that may appear alongside NO_MATCH."""

    NO_CANDIDATES = "NO_CANDIDATES"
    LOW_OVERLAP_RATIO = "LOW_OVERLAP_RATIO"
    ORIGIN_MAP_MISSING = "ORIGIN_MAP_MISSING"


class InformationalReason(str, Enum):
    """Reason tags that may accompany any verdict (informational, not decisive)."""

    PC_LINE_GAP = "PC_LINE_GAP"
