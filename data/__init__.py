"""
reforge.data — Structured data access and metrics for oracle pipeline artifacts.

This package loads, validates, and analyses the JSON artifacts produced by the
synthetic build / oracle / alignment pipeline.

Quick start::

    from data import load_dataset, enrich_pairs, compute_transitions

    ds = load_dataset()
    pairs = enrich_pairs(ds.pairs)
    trans = compute_transitions(pairs, ds.non_targets)

Layers
------
loader   Raw JSON → typed DataFrames (no derived columns).
enums    Frozen vocabulary for pipeline verdicts and reason tags.
metrics  Derived columns, cross-opt transitions, verdict rates, reason shift.
"""

PACKAGE_NAME = "reforge_data"
SCHEMA_VERSION = "0.2"

from .loader import OracleDataset, load_dataset

from .enums import (
    AlignmentReason,
    AlignmentVerdict,
    OracleBinaryRejectReason,
    OracleFunctionRejectReason,
    OracleFunctionWarnReason,
    OracleVerdict,
    StableKeyQuality,
)

from .metrics import (
    compute_reason_shift,
    compute_transitions,
    compute_verdict_rates,
    enrich_pairs,
)

__all__ = [
    # loader
    "load_dataset",
    "OracleDataset",
    # enums
    "OracleVerdict",
    "OracleBinaryRejectReason",
    "OracleFunctionRejectReason",
    "OracleFunctionWarnReason",
    "AlignmentVerdict",
    "AlignmentReason",
    "StableKeyQuality",
    # metrics
    "enrich_pairs",
    "compute_transitions",
    "compute_verdict_rates",
    "compute_reason_shift",
    # meta
    "PACKAGE_NAME",
    "SCHEMA_VERSION",
]
