"""
Call processor — callsite normalization.

Responsibilities:
  - Build callsite records from raw data.
  - Classify call_kind (DIRECT | INDIRECT).
  - Tag external / import targets.
  - Sort by (caller_entry_va, callsite_va).
"""
from typing import List

from analyzer_ghidra_decompile.core.raw_parser import RawCall


def process_calls(
    raw_calls: List[RawCall],
    binary_id: str,
    function_id: str,
    caller_entry_va: int,
) -> List[dict]:
    """
    Process raw callsites into output-ready dicts.

    Returns list of dicts sorted by callsite_va.
    """
    results = []

    for rc in raw_calls:
        callee_hex = None
        if rc.callee_entry_va is not None:
            callee_hex = hex(rc.callee_entry_va)

        results.append({
            "binary_id": binary_id,
            "caller_function_id": function_id,
            "caller_entry_va": caller_entry_va,
            "callsite_va": rc.callsite_va,
            "callsite_hex": rc.callsite_hex,
            "call_kind": rc.call_kind,
            "callee_entry_va": rc.callee_entry_va,
            "callee_name": rc.callee_name,
            "is_external_target": rc.is_external_target,
            "is_import_proxy_target": rc.is_import_proxy_target,
        })

    # Sort by callsite_va per §2.5
    results.sort(key=lambda c: c["callsite_va"])
    return results
