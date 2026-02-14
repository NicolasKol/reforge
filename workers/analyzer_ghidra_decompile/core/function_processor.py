"""
Function processor — per-function transformations, warnings, proxy metrics.

Responsibilities:
  - Normalize Ghidra hex addresses to canonical form.
  - Map raw decompiler warnings to the §5.2 taxonomy.
  - Compute proxy metrics (§9): c_line_count, insn_to_c_ratio, temp_var_count.
  - Compute fat_function_flag (§9.2) and INLINE_LIKELY (§9.3).

This module is pure: no IO, no policy decisions (verdict assigned elsewhere).
"""
import re
from typing import Dict, List, Optional, Tuple

from analyzer_ghidra_decompile.policy.profile import Profile


# ═══════════════════════════════════════════════════════════════════════════════
# Address normalization (§3)
# ═══════════════════════════════════════════════════════════════════════════════

def normalize_address(hex_str: str) -> Tuple[int, str]:
    """
    Normalize a hex address string to (int_va, canonical_hex).

    Canonical hex: lowercase, ``0x`` prefix, no padding.
    Handles Ghidra formats: ``"00101159"``, ``"0x00101159"``, ``"101159"``.
    """
    cleaned = hex_str.strip().lower()
    if cleaned.startswith("0x"):
        val = int(cleaned, 16)
    else:
        val = int(cleaned, 16)
    return val, hex(val)


# ═══════════════════════════════════════════════════════════════════════════════
# Warning mapping (§5.2)
# ═══════════════════════════════════════════════════════════════════════════════

# Regex patterns mapping raw Ghidra messages to normalized warning codes.
# Order matters: first match wins.
_WARNING_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"unknown.*calling.*convention", re.I),
     "UNKNOWN_CALLING_CONVENTION"),
    (re.compile(r"param.*storage.*lock", re.I),
     "PARAM_STORAGE_LOCKED"),
    (re.compile(r"unreachable.*block", re.I),
     "UNREACHABLE_BLOCKS_REMOVED"),
    (re.compile(r"bad\s+(instruction|data)", re.I),
     "BAD_INSTRUCTION_DATA"),
    (re.compile(r"truncat.*control.*flow", re.I),
     "TRUNCATED_CONTROL_FLOW"),
    (re.compile(r"unresolved.*indirect.*jump", re.I),
     "UNRESOLVED_INDIRECT_JUMP"),
    (re.compile(r"non[_\-\s]*return", re.I),
     "NON_RETURNING_CALL_MISMODELED"),
    (re.compile(r"switch.*recov", re.I),
     "SWITCH_RECOVERY_FAILED"),
    # Broad patterns for known Ghidra warnings
    (re.compile(r"could not recover", re.I),
     "SWITCH_RECOVERY_FAILED"),
    (re.compile(r"indirect.*jump", re.I),
     "UNRESOLVED_INDIRECT_JUMP"),
    (re.compile(r"unreachable", re.I),
     "UNREACHABLE_BLOCKS_REMOVED"),
]


def map_warnings(
    error_msg: Optional[str],
    c_raw: Optional[str],
    warnings_raw: List[str],
) -> Tuple[List[str], List[str]]:
    """
    Map raw Ghidra warning messages to normalized §5.2 taxonomy codes.

    Sources checked:
      1. ``warnings_raw`` from the decompiler result messages.
      2. ``error_msg`` (may contain warnings even when decompile succeeds).
      3. ``c_raw`` header comments (Ghidra sometimes embeds warnings there).

    Returns
    -------
    (normalized_warnings, raw_warning_strings)
        Deduplicated lists. Unmatched raw strings map to
        DECOMPILER_INTERNAL_WARNING.
    """
    raw_lines: List[str] = list(warnings_raw)

    # Parse c_raw header comments for embedded warnings
    if c_raw:
        for line in c_raw.split("\n")[:10]:  # only check first 10 lines
            stripped = line.strip()
            if stripped.startswith("/*") or stripped.startswith("//"):
                # Check if it looks like a warning
                if any(kw in stripped.lower() for kw in
                       ("warning", "could not", "unresolved", "unreachable",
                        "bad instruction", "truncat")):
                    raw_lines.append(stripped)

    normalized: List[str] = []
    seen: set = set()

    for raw in raw_lines:
        matched = False
        for pattern, code in _WARNING_PATTERNS:
            if pattern.search(raw):
                if code not in seen:
                    normalized.append(code)
                    seen.add(code)
                matched = True
                break
        if not matched and raw.strip():
            code = "DECOMPILER_INTERNAL_WARNING"
            if code not in seen:
                normalized.append(code)
                seen.add(code)

    return normalized, raw_lines


# ═══════════════════════════════════════════════════════════════════════════════
# Proxy metrics (§9)
# ═══════════════════════════════════════════════════════════════════════════════

# Temp variable name patterns (§9.4)
_TEMP_NAME_RE = re.compile(
    r"^(uVar|iVar|bVar|cVar|lVar|sVar|fVar|dVar|ppVar|pVar|auVar|abVar|aiVar)\d+$"
)


def count_c_lines(c_raw: Optional[str]) -> int:
    """Count non-empty lines in decompiled C output."""
    if not c_raw:
        return 0
    return sum(1 for line in c_raw.split("\n") if line.strip())


def compute_proxy_metrics(
    c_raw: Optional[str],
    insn_count: int,
    temp_var_count: int,
) -> Dict[str, object]:
    """
    Compute derived proxy metrics for a function.

    Returns dict with:
      asm_insn_count, c_line_count, insn_to_c_ratio, temp_var_count
    """
    c_lines = count_c_lines(c_raw)
    ratio = insn_count / c_lines if c_lines > 0 else 0.0

    return {
        "asm_insn_count": insn_count,
        "c_line_count": c_lines,
        "insn_to_c_ratio": round(ratio, 4),
        "temp_var_count": temp_var_count,
    }


def is_temp_name(name: str) -> bool:
    """Check if a variable name matches the temp pattern (§9.4)."""
    return bool(_TEMP_NAME_RE.match(name))


def compute_fat_function_flag(
    size_bytes: Optional[int],
    bb_count: int,
    temp_var_count: int,
    insn_to_c_ratio: float,
    size_p90: float,
    profile: Profile,
) -> bool:
    """
    Determine if a function is "fat" (§9.2).

    True if ANY of:
      - size_bytes above P90 within binary
      - bb_count above threshold
      - temp_var_count above threshold
      - insn_to_c_ratio above threshold
    """
    if size_bytes is not None and size_bytes > size_p90:
        return True
    if bb_count > profile.fat_function_bb_threshold:
        return True
    if temp_var_count > profile.fat_function_temp_threshold:
        return True
    if insn_to_c_ratio > profile.fat_function_ratio_threshold:
        return True
    return False


def compute_inline_likely(
    fat_function_flag: bool,
    temp_var_count: int,
    bb_count: int,
    profile: Profile,
) -> bool:
    """
    Determine if INLINE_LIKELY warning should be added (§9.3).

    True if fat_function_flag AND temp_var_count high AND bb_count high.
    """
    return (
        fat_function_flag
        and temp_var_count >= profile.inline_likely_temp_threshold
        and bb_count >= profile.inline_likely_bb_threshold
    )
