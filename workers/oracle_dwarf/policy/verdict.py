"""
Verdict — structured ACCEPT / WARN / REJECT decisions with reason enums.

Two layers:
  1. Binary-level gate  (gate_binary)  — can we evaluate *any* functions?
  2. Function-level judge (judge_function) — is this individual function usable?

Policy rules reference the Profile for thresholds but never import core/.
"""
from enum import Enum, unique
from typing import List, Tuple

from oracle_dwarf.core.elf_reader import ElfMeta
from oracle_dwarf.core.function_index import FunctionEntry
from oracle_dwarf.core.line_mapper import LineSpan
from oracle_dwarf.policy.profile import Profile


# ── Verdict enum ──────────────────────────────────────────────────────────────

@unique
class Verdict(str, Enum):
    ACCEPT = "ACCEPT"
    WARN = "WARN"
    REJECT = "REJECT"


# ── Binary-level reject reasons ──────────────────────────────────────────────

@unique
class BinaryRejectReason(str, Enum):
    NO_DEBUG_INFO = "NO_DEBUG_INFO"
    NO_DEBUG_LINE = "NO_DEBUG_LINE"
    UNSUPPORTED_ARCH = "UNSUPPORTED_ARCH"
    SPLIT_DWARF = "SPLIT_DWARF"
    DWARF_PARSE_ERROR = "DWARF_PARSE_ERROR"


# ── Function-level verdict reasons ───────────────────────────────────────────

@unique
class FunctionRejectReason(str, Enum):
    DECLARATION_ONLY = "DECLARATION_ONLY"
    MISSING_RANGE = "MISSING_RANGE"
    NO_LINE_ROWS_IN_RANGE = "NO_LINE_ROWS_IN_RANGE"


@unique
class FunctionWarnReason(str, Enum):
    MULTI_FILE_RANGE = "MULTI_FILE_RANGE"
    SYSTEM_HEADER_DOMINANT = "SYSTEM_HEADER_DOMINANT"
    RANGES_FRAGMENTED = "RANGES_FRAGMENTED"
    NAME_MISSING = "NAME_MISSING"


# ── Binary gate ──────────────────────────────────────────────────────────────

def gate_binary(meta: ElfMeta, profile: Profile) -> Tuple[Verdict, List[str]]:
    """
    Evaluate binary-level facts against the profile.

    Returns (Verdict, list_of_reason_strings).
    Any single reject reason → REJECT.
    """
    reasons: List[str] = []

    if not meta.has_debug_info:
        reasons.append(BinaryRejectReason.NO_DEBUG_INFO.value)

    if not meta.has_debug_line:
        reasons.append(BinaryRejectReason.NO_DEBUG_LINE.value)

    # v0 requires ELF x86-64
    if meta.machine != "EM_X86_64":
        reasons.append(BinaryRejectReason.UNSUPPORTED_ARCH.value)

    if meta.has_split_dwarf:
        reasons.append(BinaryRejectReason.SPLIT_DWARF.value)

    if reasons:
        return Verdict.REJECT, reasons
    return Verdict.ACCEPT, []


# ── Function judge ───────────────────────────────────────────────────────────

def judge_function(
    func: FunctionEntry,
    span: LineSpan,
    profile: Profile,
) -> Tuple[Verdict, List[str]]:
    """
    Evaluate a single function against the profile.

    Returns (Verdict, list_of_reason_strings).
    """
    rejects: List[str] = []
    warns: List[str] = []

    # ── Rejects ──────────────────────────────────────────────────────
    if func.is_declaration:
        rejects.append(FunctionRejectReason.DECLARATION_ONLY.value)

    if not func.ranges:
        rejects.append(FunctionRejectReason.MISSING_RANGE.value)

    if not func.is_declaration and func.ranges and span.is_empty:
        rejects.append(FunctionRejectReason.NO_LINE_ROWS_IN_RANGE.value)

    if rejects:
        return Verdict.REJECT, rejects

    # ── Warnings ─────────────────────────────────────────────────────
    if func.name is None and func.linkage_name is None:
        warns.append(FunctionWarnReason.NAME_MISSING.value)

    if span.dominant_file_ratio < profile.min_dominant_file_ratio:
        warns.append(FunctionWarnReason.MULTI_FILE_RANGE.value)

    if span.dominant_file:
        for excl in profile.exclude_paths:
            if span.dominant_file.startswith(excl):
                warns.append(FunctionWarnReason.SYSTEM_HEADER_DOMINANT.value)
                break

    if len(func.ranges) > profile.max_fragments_warn:
        warns.append(FunctionWarnReason.RANGES_FRAGMENTED.value)

    if warns:
        return Verdict.WARN, warns

    return Verdict.ACCEPT, []
