"""
Verdict — structured ACCEPT / WARN / REJECT decisions with reason enums.

Two layers:
  1. Binary-level gate  (gate_binary)  — can we process this binary at all?
  2. Function-level judge (judge_function) — OK / WARN / FAIL per function.

Policy rules reference the Profile for thresholds but never import core/.
"""
from enum import Enum, unique
from typing import List, Tuple

from analyzer_ghidra_decompile.policy.profile import Profile


# ═══════════════════════════════════════════════════════════════════════════════
# Verdict enums
# ═══════════════════════════════════════════════════════════════════════════════

@unique
class BinaryVerdict(str, Enum):
    ACCEPT = "ACCEPT"
    WARN = "WARN"
    REJECT = "REJECT"


@unique
class FunctionVerdict(str, Enum):
    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"


# ═══════════════════════════════════════════════════════════════════════════════
# Binary-level reject / warn reasons (§4)
# ═══════════════════════════════════════════════════════════════════════════════

@unique
class BinaryRejectReason(str, Enum):
    NOT_ELF = "NOT_ELF"
    UNSUPPORTED_ARCH = "UNSUPPORTED_ARCH"
    GHIDRA_HEADLESS_FAILED = "GHIDRA_HEADLESS_FAILED"
    PROJECT_DB_ERROR = "PROJECT_DB_ERROR"
    ANALYSIS_TIMEOUT = "ANALYSIS_TIMEOUT"
    SCRIPT_EXCEPTION = "SCRIPT_EXCEPTION"


@unique
class BinaryWarnReason(str, Enum):
    PARTIAL_ANALYSIS = "PARTIAL_ANALYSIS"
    DECOMPILER_INIT_WARN = "DECOMPILER_INIT_WARN"
    IMPORTS_UNRESOLVED_HIGH = "IMPORTS_UNRESOLVED_HIGH"
    HIGH_DECOMPILE_FAIL_RATE = "HIGH_DECOMPILE_FAIL_RATE"


# ═══════════════════════════════════════════════════════════════════════════════
# Function-level warning taxonomy (§5.2)
# ═══════════════════════════════════════════════════════════════════════════════

@unique
class FunctionWarning(str, Enum):
    UNKNOWN_CALLING_CONVENTION = "UNKNOWN_CALLING_CONVENTION"
    PARAM_STORAGE_LOCKED = "PARAM_STORAGE_LOCKED"
    UNREACHABLE_BLOCKS_REMOVED = "UNREACHABLE_BLOCKS_REMOVED"
    BAD_INSTRUCTION_DATA = "BAD_INSTRUCTION_DATA"
    TRUNCATED_CONTROL_FLOW = "TRUNCATED_CONTROL_FLOW"
    UNRESOLVED_INDIRECT_JUMP = "UNRESOLVED_INDIRECT_JUMP"
    NON_RETURNING_CALL_MISMODELED = "NON_RETURNING_CALL_MISMODELED"
    SWITCH_RECOVERY_FAILED = "SWITCH_RECOVERY_FAILED"
    DECOMPILER_INTERNAL_WARNING = "DECOMPILER_INTERNAL_WARNING"
    INLINE_LIKELY = "INLINE_LIKELY"


# ═══════════════════════════════════════════════════════════════════════════════
# Decompile status
# ═══════════════════════════════════════════════════════════════════════════════

@unique
class DecompileStatus(str, Enum):
    OK = "OK"
    FAIL = "FAIL"


# ═══════════════════════════════════════════════════════════════════════════════
# Binary gate
# ═══════════════════════════════════════════════════════════════════════════════

def gate_binary(
    is_valid_elf: bool,
    machine: str | None,
    ghidra_exit_code: int | None,
    ghidra_error: str | None,
    summary: dict | None,
    profile: Profile,
) -> Tuple[BinaryVerdict, List[str]]:
    """
    Evaluate binary-level facts.

    Parameters
    ----------
    is_valid_elf : bool
        Whether the binary is a valid ELF.
    machine : str | None
        ELF machine string (e.g. "EM_X86_64").
    ghidra_exit_code : int | None
        Exit code of analyzeHeadless (None if not invoked).
    ghidra_error : str | None
        Error message from Ghidra invocation.
    summary : dict | None
        The parsed summary record from raw JSONL.
    profile : Profile
        Active profile.

    Returns
    -------
    (BinaryVerdict, list_of_reason_strings)
    """
    reasons: List[str] = []

    # ELF validation
    if not is_valid_elf:
        reasons.append(BinaryRejectReason.NOT_ELF.value)

    # Architecture check
    if machine and machine not in ("EM_X86_64", "EM_386"):
        reasons.append(BinaryRejectReason.UNSUPPORTED_ARCH.value)

    # Ghidra execution errors
    if ghidra_exit_code is not None and ghidra_exit_code != 0:
        if ghidra_error and "timeout" in ghidra_error.lower():
            reasons.append(BinaryRejectReason.ANALYSIS_TIMEOUT.value)
        elif ghidra_error and "project" in ghidra_error.lower():
            reasons.append(BinaryRejectReason.PROJECT_DB_ERROR.value)
        elif ghidra_error and "script" in ghidra_error.lower():
            reasons.append(BinaryRejectReason.SCRIPT_EXCEPTION.value)
        else:
            reasons.append(BinaryRejectReason.GHIDRA_HEADLESS_FAILED.value)

    if reasons:
        return BinaryVerdict.REJECT, reasons

    # ── Warn-level checks ────────────────────────────────────────────
    warn_reasons: List[str] = []

    if summary:
        total = summary.get("total_functions", 0)
        fail = summary.get("decompile_fail", 0)
        if total > 0 and (fail / total) > profile.high_decompile_fail_rate:
            warn_reasons.append(BinaryWarnReason.HIGH_DECOMPILE_FAIL_RATE.value)

    if warn_reasons:
        return BinaryVerdict.WARN, warn_reasons

    return BinaryVerdict.ACCEPT, []


# ═══════════════════════════════════════════════════════════════════════════════
# Function judge
# ═══════════════════════════════════════════════════════════════════════════════

def judge_function(
    decompile_status: str,
    warnings: List[str],
    body_start_va: int | None,
    body_end_va: int | None,
    is_noise: bool,
) -> Tuple[FunctionVerdict, List[str]]:
    """
    Assign a verdict to a single function.

    Parameters
    ----------
    decompile_status : str
        "OK" or "FAIL".
    warnings : list[str]
        Normalized warning codes.
    body_start_va : int | None
        Body start address.
    body_end_va : int | None
        Body end address.
    is_noise : bool
        True if any noise flag is set.

    Returns
    -------
    (FunctionVerdict, reasons[])
    """
    reasons: List[str] = []

    # ── FAIL conditions (§5.3) ────────────────────────────────────────
    if decompile_status == DecompileStatus.FAIL.value:
        reasons.append("DECOMPILE_FAIL")

    if FunctionWarning.BAD_INSTRUCTION_DATA.value in warnings:
        reasons.append(FunctionWarning.BAD_INSTRUCTION_DATA.value)

    if body_start_va is None or body_end_va is None:
        reasons.append("NO_BODY_RANGE")

    if reasons:
        return FunctionVerdict.FAIL, reasons

    # ── WARN conditions ──────────────────────────────────────────────
    structuring_warnings = {
        FunctionWarning.UNREACHABLE_BLOCKS_REMOVED.value,
        FunctionWarning.TRUNCATED_CONTROL_FLOW.value,
        FunctionWarning.UNRESOLVED_INDIRECT_JUMP.value,
        FunctionWarning.SWITCH_RECOVERY_FAILED.value,
        FunctionWarning.NON_RETURNING_CALL_MISMODELED.value,
        FunctionWarning.UNKNOWN_CALLING_CONVENTION.value,
        FunctionWarning.PARAM_STORAGE_LOCKED.value,
        FunctionWarning.DECOMPILER_INTERNAL_WARNING.value,
        FunctionWarning.INLINE_LIKELY.value,
    }

    for w in warnings:
        if w in structuring_warnings:
            reasons.append(w)

    if is_noise:
        reasons.append("NOISE_FUNCTION")

    if reasons:
        return FunctionVerdict.WARN, reasons

    return FunctionVerdict.OK, []
