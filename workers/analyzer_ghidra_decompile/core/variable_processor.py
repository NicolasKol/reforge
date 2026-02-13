"""
Variable processor — variable identity, storage keys, access signatures.

Responsibilities:
  - Classify var_kind (PARAM, LOCAL, GLOBAL_REF, TEMP) from raw data.
  - Compute deterministic storage_key per §6.4.
  - Compute access_sig per §6.3.
  - Detect temp singletons (§9.4).
  - Build stable var_id: "{function_id}:{var_kind}:{storage_key}:{access_sig}".

This module is pure: no IO, no policy.
"""
import hashlib
import re
from typing import List, Optional

from analyzer_ghidra_decompile.core.raw_parser import RawVariable


# ── Var kind classification (§6.2) ───────────────────────────────────

# Temp name patterns (§9.4)
_TEMP_NAME_RE = re.compile(
    r"^(uVar|iVar|bVar|cVar|lVar|sVar|fVar|dVar|ppVar|pVar|auVar|abVar|aiVar)\d+$"
)


def classify_var_kind(
    is_param: bool,
    storage_class: str,
    name: str,
    addr_va: Optional[int],
) -> str:
    """
    Classify a variable into PARAM | LOCAL | GLOBAL_REF | TEMP.

    Rules:
      - is_param=True → PARAM
      - storage_class=MEMORY and has addr_va → GLOBAL_REF
      - storage_class=UNIQUE or name matches temp pattern → TEMP
      - otherwise → LOCAL
    """
    if is_param:
        return "PARAM"
    if storage_class == "MEMORY" and addr_va is not None:
        return "GLOBAL_REF"
    if storage_class == "UNIQUE" or _TEMP_NAME_RE.match(name):
        return "TEMP"
    return "LOCAL"


# ── Storage key (§6.4) ──────────────────────────────────────────────

def compute_storage_key(
    storage_class: str,
    stack_offset: Optional[int],
    register_name: Optional[str],
    addr_va: Optional[int],
    name: str,
) -> str:
    """
    Compute the deterministic storage key for a variable.

    Rules (§6.4):
      STACK:    "stack:off:{sign}0x{abs_offset}"
      REGISTER: "reg:{register_name}"
      MEMORY:   "mem:0x{addr_hex}"
      UNIQUE:   "uniq:{name}"
      UNKNOWN:  "unk:{name}"
    """
    if storage_class == "STACK" and stack_offset is not None:
        sign = "+" if stack_offset >= 0 else "-"
        return f"stack:off:{sign}0x{abs(stack_offset):x}"
    elif storage_class == "REGISTER" and register_name:
        return f"reg:{register_name}"
    elif storage_class == "MEMORY" and addr_va is not None:
        return f"mem:0x{addr_va:x}"
    elif storage_class == "UNIQUE":
        return f"uniq:{name}"
    else:
        return f"unk:{name}"


# ── Access signature (§6.3) ──────────────────────────────────────────

def compute_access_sig(
    access_sites: List[int],
    storage_key: str,
) -> str:
    """
    Compute stable access signature.

    Default: sha256(",".join(sorted(access_sites)))[:16]
    Fallback if no sites: sha256(storage_key)[:16]
    """
    if access_sites:
        data = ",".join(str(a) for a in sorted(access_sites))
    else:
        data = storage_key
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]


# ── Temp singleton heuristic (§9.4) ─────────────────────────────────

def is_temp_singleton(
    name: str,
    var_kind: str,
    storage_class: str,
) -> bool:
    """
    A variable qualifies as temp singleton if:
      - var_kind=TEMP OR name matches temp pattern, AND
      - storage_class=UNIQUE (decompiler temporary)

    Without pcode read/write counts (deferred), we use naming + storage
    as the best-effort heuristic.
    """
    if var_kind == "TEMP":
        return True
    if _TEMP_NAME_RE.match(name) and storage_class == "UNIQUE":
        return True
    return False


# ── Var ID (§3.2) ───────────────────────────────────────────────────

def build_var_id(
    function_id: str,
    var_kind: str,
    storage_key: str,
    access_sig: str,
) -> str:
    """
    Build stable variable identifier.

    Format: "{function_id}:{var_kind}:{storage_key}:{access_sig}"
    """
    return f"{function_id}:{var_kind}:{storage_key}:{access_sig}"


# ── Process all variables for a function ─────────────────────────────

def process_variables(
    raw_vars: List[RawVariable],
    function_id: str,
    entry_va: int,
    binary_id: str,
) -> list:
    """
    Process raw variables into output-ready dicts.

    Returns list of dicts sorted by (var_kind, storage_key).
    """
    results = []

    for rv in raw_vars:
        var_kind = classify_var_kind(
            rv.is_param, rv.storage_class, rv.name, rv.addr_va
        )

        storage_key = compute_storage_key(
            rv.storage_class,
            rv.stack_offset,
            rv.register_name,
            rv.addr_va,
            rv.name,
        )

        access_sig = compute_access_sig(rv.access_sites, storage_key)

        var_id = build_var_id(function_id, var_kind, storage_key, access_sig)

        is_temp = is_temp_singleton(rv.name, var_kind, rv.storage_class)

        results.append({
            "binary_id": binary_id,
            "function_id": function_id,
            "entry_va": entry_va,
            "var_id": var_id,
            "var_kind": var_kind,
            "name": rv.name,
            "type_str": rv.type_str,
            "size_bytes": rv.size_bytes if rv.size_bytes > 0 else None,
            "storage_class": rv.storage_class,
            "storage_key": storage_key,
            "stack_offset": rv.stack_offset,
            "register_name": rv.register_name,
            "addr_va": rv.addr_va,
            "is_temp_singleton": is_temp,
            "access_sites": sorted(rv.access_sites),
            "access_sites_truncated": rv.access_sites_truncated,
            "access_sig": access_sig,
        })

    # Sort by (var_kind, storage_key) per §2.3
    results.sort(key=lambda v: (v["var_kind"], v["storage_key"]))
    return results
