"""
Runner — top-level orchestration: binary → 5 output files.

This module ties core extraction, policy verdicts, and IO together
into a single ``run_ghidra_decompile`` function that can be called
from the API endpoint, CLI, or notebook.

Architecture:
  1. Validate ELF + compute SHA256.
  2. Invoke Ghidra headless (via docker exec) if raw JSONL not provided.
  3. Parse raw JSONL.
  4. Binary-level gate.
  5. Pass 1: process each function (variables, CFG, calls, warnings, noise).
  6. Pass 2: compute percentile thresholds → fat_function_flag + INLINE_LIKELY.
  7. Assign function verdicts.
  8. Build summary stats.
  9. Write outputs.
"""
import logging
import hashlib
import statistics
import subprocess
import tempfile
import uuid
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from analyzer_ghidra_decompile import ANALYZER_VERSION, PACKAGE_NAME, SCHEMA_VERSION
from analyzer_ghidra_decompile.core.call_processor import process_calls
from analyzer_ghidra_decompile.core.cfg_processor import process_cfg
from analyzer_ghidra_decompile.core.elf_meta import compute_sha256, validate_elf
from analyzer_ghidra_decompile.core.function_processor import (
    compute_fat_function_flag,
    compute_inline_likely,
    compute_proxy_metrics,
    count_c_lines,
    is_temp_name,
    map_warnings,
)
from analyzer_ghidra_decompile.core.raw_parser import (
    RawFunctionRecord,
    RawSummary,
    parse_raw_jsonl,
)
from analyzer_ghidra_decompile.core.variable_processor import process_variables
from analyzer_ghidra_decompile.io.schema import (
    CfgBlockEntry,
    CfgSummary,
    FunctionCounts,
    GhidraCallEntry,
    GhidraCfgEntry,
    GhidraFunctionEntry,
    GhidraReport,
    GhidraVariableEntry,
    VariableSummary,
)
from analyzer_ghidra_decompile.io.writer import write_outputs
from analyzer_ghidra_decompile.policy.noise import (
    NOISE_LIST_VERSION,
    classify_noise,
)
from analyzer_ghidra_decompile.policy.profile import Profile
from analyzer_ghidra_decompile.policy.verdict import (
    BinaryVerdict,
    DecompileStatus,
    FunctionWarning,
    gate_binary,
    judge_function,
)

logger = logging.getLogger(__name__)


def _compute_script_hash(script_path: str) -> str | None:
    """
    Compute SHA256 hash of the Java decompilation script.
    
    Parameters
    ----------
    script_path : str
        Host or container path to ExportDecompJsonl.java
        
    Returns
    -------
    str | None
        Hex digest of SHA256, or None if file not found
    """
    try:
        with open(script_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception as e:
        logger.warning("Failed to compute script hash from %s: %s", script_path, e)
        return None


def _get_script_path() -> str:
    """
    Get path to ExportDecompJsonl.java, handling both container and host environments.
    
    Returns
    -------
    str
        Path to the script file
    """
    # Try container path first (when worker runs in Docker)
    container_path = "/files/ghidra/scripts/ExportDecompJsonl.java"
    if Path(container_path).exists():
        return container_path
    
    # Fall back to host path (when worker runs on host)
    host_path = Path(__file__).parent.parent.parent / "docker" / "local-files" / "ghidra" / "scripts" / "ExportDecompJsonl.java"
    return str(host_path)


# ═══════════════════════════════════════════════════════════════════════════════
# Ghidra headless invocation
# ═══════════════════════════════════════════════════════════════════════════════

def _invoke_ghidra_headless(
    binary_container_path: str,
    output_jsonl_container_path: str,
    profile: Profile,
) -> Tuple[int, str]:
    """
    Invoke Ghidra headless inside the Docker container via ``docker exec``.

    Parameters
    ----------
    binary_container_path : str
        Path to the binary inside the container (e.g. /files/artifacts/...).
    output_jsonl_container_path : str
        Path where raw JSONL will be written inside the container.
    profile : Profile
        Active profile (for container name and script path).

    Returns
    -------
    (exit_code, stderr_output)
    """
    project_name = f"reforge_{uuid.uuid4().hex[:8]}"
    project_dir = profile.ghidra_project_dir

    cmd = [
        "docker", "exec",
        profile.ghidra_container,
        "/ghidra/support/analyzeHeadless",
        project_dir, project_name,
        "-import", binary_container_path,
        "-scriptPath", profile.ghidra_script_path,
        "-postScript", "ExportDecompJsonl.java", output_jsonl_container_path,
        "-deleteProject",
    ]

    logger.info("Running Ghidra headless: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=profile.analysis_timeout,
        )
        return result.returncode, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "Analysis timed out"
    except Exception as e:
        return -1, str(e)


def _host_to_container_path(host_path: str) -> str:
    """
    Convert a host path to a container path.

    The container mounts ``./local-files`` → ``/files``.
    Handles both Windows-style and Unix-style paths.
    """
    # Normalize to forward slashes
    normalized = host_path.replace("\\", "/")

    # Look for the local-files segment
    markers = ["local-files/", "local-files\\"]
    for marker in markers:
        idx = normalized.find(marker)
        if idx >= 0:
            relative = normalized[idx + len(marker):]
            return f"/files/{relative}"

    # If path is already container-style
    if normalized.startswith("/files/"):
        return normalized

    # Fallback: just use the path as-is (may work if paths match)
    return normalized


# ═══════════════════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════════════════

def run_ghidra_decompile(
    binary_path: str,
    profile: Profile | None = None,
    output_dir: Path | None = None,
    raw_jsonl_path: str | None = None,
) -> Tuple[
    GhidraReport,
    List[GhidraFunctionEntry],
    List[GhidraVariableEntry],
    List[GhidraCfgEntry],
    List[GhidraCallEntry],
]:
    """
    Run the Ghidra decompiler analysis on a single binary.

    Parameters
    ----------
    binary_path : str
        Path to the ELF binary.
    profile : Profile, optional
        Support profile. Defaults to Profile.v1().
    output_dir : Path, optional
        Directory to write output files. If None, outputs not written to disk.
    raw_jsonl_path : str, optional
        Path to a pre-generated raw JSONL. If provided, skips Ghidra invocation.

    Returns
    -------
    (GhidraReport, functions, variables, cfg, calls)
    """
    if profile is None:
        profile = Profile.v1()

    # ── Step 1: Validate ELF + compute SHA256 ────────────────────────
    is_valid, machine, elf_error = validate_elf(binary_path)
    binary_sha256 = ""
    if is_valid:
        binary_sha256 = compute_sha256(binary_path)
    binary_id = binary_sha256

    # Early reject if not valid ELF
    if not is_valid:
        verdict, reasons = gate_binary(
            is_valid_elf=False,
            machine=machine,
            ghidra_exit_code=None,
            ghidra_error=elf_error,
            summary=None,
            profile=profile,
        )
        report = _build_reject_report(
            binary_path, binary_sha256, verdict, reasons, profile,
        )
        empty: tuple = (report, [], [], [], [])
        if output_dir:
            write_outputs(report, [], [], [], [], output_dir)
        return empty

    # ── Step 2: Invoke Ghidra (or use pre-generated JSONL) ───────────
    ghidra_exit_code = None
    ghidra_error = None

    if raw_jsonl_path is None:
        # Convert paths for container
        container_binary = _host_to_container_path(binary_path)
        container_jsonl = f"/files/ghidra/out/_raw_{uuid.uuid4().hex[:8]}.jsonl"
        raw_jsonl_path = _container_to_host_path(container_jsonl, binary_path)

        ghidra_exit_code, ghidra_error = _invoke_ghidra_headless(
            container_binary, container_jsonl, profile,
        )

        if ghidra_exit_code != 0:
            logger.error(
                "Ghidra headless failed (exit=%d) for %s: %s",
                ghidra_exit_code, binary_path, ghidra_error,
            )
            verdict, reasons = gate_binary(
                is_valid_elf=True,
                machine=machine,
                ghidra_exit_code=ghidra_exit_code,
                ghidra_error=ghidra_error,
                summary=None,
                profile=profile,
            )
            report = _build_reject_report(
                binary_path, binary_sha256, verdict, reasons, profile,
            )
            if output_dir:
                write_outputs(report, [], [], [], [], output_dir)
            return report, [], [], [], []

    # ── Step 3: Parse raw JSONL ──────────────────────────────────────
    try:
        summary, raw_functions = parse_raw_jsonl(raw_jsonl_path)
    except Exception as e:
        logger.error("Failed to parse raw JSONL: %s", e)
        verdict, reasons = gate_binary(
            is_valid_elf=True,
            machine=machine,
            ghidra_exit_code=1,
            ghidra_error=f"JSONL parse error: {e}",
            summary=None,
            profile=profile,
        )
        report = _build_reject_report(
            binary_path, binary_sha256, verdict, reasons, profile,
        )
        if output_dir:
            write_outputs(report, [], [], [], [], output_dir)
        return report, [], [], [], []

    # ── Step 4: Binary-level gate ────────────────────────────────────
    binary_verdict, binary_reasons = gate_binary(
        is_valid_elf=True,
        machine=machine,
        ghidra_exit_code=ghidra_exit_code,
        ghidra_error=ghidra_error,
        summary={
            "total_functions": summary.total_functions,
            "decompile_fail": summary.decompile_fail,
        },
        profile=profile,
    )

    if binary_verdict == BinaryVerdict.REJECT:
        report = _build_reject_report(
            binary_path, binary_sha256, binary_verdict, binary_reasons, profile,
            ghidra_version=summary.ghidra_version,
            java_version=summary.java_version,
        )
        if output_dir:
            write_outputs(report, [], [], [], [], output_dir)
        return report, [], [], [], []

    # ── Step 5: Pass 1 — process each function ───────────────────────
    func_entries: List[GhidraFunctionEntry] = []
    var_entries: List[GhidraVariableEntry] = []
    cfg_entries: List[GhidraCfgEntry] = []
    call_entries: List[GhidraCallEntry] = []

    # Intermediate data for pass 2
    pass1_data: List[Dict] = []

    for rf in raw_functions:
        function_id = f"{binary_sha256}:{rf.entry_va}"
        entry_hex = rf.entry_hex

        # Decompile status
        decompile_status = (
            DecompileStatus.OK.value
            if rf.c_raw is not None and rf.error is None
            else DecompileStatus.FAIL.value
        )

        # Warnings
        warnings, warnings_raw = map_warnings(
            rf.error, rf.c_raw, rf.warnings_raw
        )

        # Noise classification
        is_plt, is_init_fini, is_comp_aux, is_lib_like = classify_noise(
            rf.name, rf.section_hint, rf.is_external_block, rf.is_thunk, rf.is_import
        )

        # Variables
        var_dicts = process_variables(
            rf.variables, function_id, rf.entry_va, binary_id
        )

        # Temp var count
        temp_count = sum(
            1 for vd in var_dicts if vd["var_kind"] == "TEMP"
        )

        # Proxy metrics
        metrics = compute_proxy_metrics(rf.c_raw, rf.insn_count, temp_count)

        # CFG
        cfg_result = process_cfg(rf.blocks, warnings)

        # Calls
        call_dicts = process_calls(
            rf.calls, binary_id, function_id, rf.entry_va
        )

        pass1_data.append({
            "rf": rf,
            "function_id": function_id,
            "entry_hex": entry_hex,
            "decompile_status": decompile_status,
            "warnings": warnings,
            "warnings_raw": warnings_raw,
            "is_plt": is_plt,
            "is_init_fini": is_init_fini,
            "is_comp_aux": is_comp_aux,
            "is_lib_like": is_lib_like,
            "var_dicts": var_dicts,
            "temp_count": temp_count,
            "metrics": metrics,
            "cfg_result": cfg_result,
            "call_dicts": call_dicts,
        })

    # ── Step 6: Pass 2 — fat function thresholds ─────────────────────
    all_sizes = [
        d["rf"].size_bytes
        for d in pass1_data
        if d["rf"].size_bytes is not None and d["rf"].size_bytes > 0
    ]
    size_p90 = (
        sorted(all_sizes)[int(len(all_sizes) * profile.fat_function_size_percentile)]
        if all_sizes
        else 0
    )

    fat_thresholds = {
        "size_p90": size_p90,
        "bb_threshold": profile.fat_function_bb_threshold,
        "temp_threshold": profile.fat_function_temp_threshold,
        "ratio_threshold": profile.fat_function_ratio_threshold,
    }

    # Counters for report
    counts = FunctionCounts()
    warning_prevalence: Counter = Counter()
    all_bb_counts: List[int] = []
    total_unresolved_indirect = 0
    total_vars = 0
    total_temps = 0
    total_placeholder_types = 0
    total_var_entries = 0

    for d in pass1_data:
        rf: RawFunctionRecord = d["rf"]
        cfg_result = d["cfg_result"]
        var_dicts = d["var_dicts"]
        metrics = d["metrics"]
        warnings = d["warnings"]

        bb_count = cfg_result["bb_count"]

        # Fat function flag
        fat_flag = compute_fat_function_flag(
            rf.size_bytes,
            bb_count,
            d["temp_count"],
            metrics["insn_to_c_ratio"],
            size_p90,
            profile,
        )

        # INLINE_LIKELY
        inline_likely = compute_inline_likely(
            fat_flag, d["temp_count"], bb_count, profile,
        )
        if inline_likely and FunctionWarning.INLINE_LIKELY.value not in warnings:
            warnings.append(FunctionWarning.INLINE_LIKELY.value)

        # Noise
        is_noise = d["is_plt"] or d["is_init_fini"] or d["is_comp_aux"]

        # Function verdict
        func_verdict, func_reasons = judge_function(
            d["decompile_status"],
            warnings,
            rf.body_start_va,
            rf.body_end_va,
            is_noise,
        )

        # Build function entry
        func_entry = GhidraFunctionEntry(
            binary_id=binary_id,
            function_id=d["function_id"],
            entry_va=rf.entry_va,
            entry_hex=d["entry_hex"],
            name=rf.name,
            namespace=rf.namespace,
            body_start_va=rf.body_start_va,
            body_end_va=rf.body_end_va,
            size_bytes=rf.size_bytes,
            is_external_block=rf.is_external_block,
            is_thunk=rf.is_thunk,
            is_import=rf.is_import,
            section_hint=rf.section_hint,
            decompile_status=d["decompile_status"],
            c_raw=rf.c_raw or "",
            decompile_error=rf.error,
            warnings=warnings,
            warnings_raw=d["warnings_raw"],
            verdict=func_verdict.value,
            is_plt_or_stub=d["is_plt"],
            is_init_fini_aux=d["is_init_fini"],
            is_compiler_aux=d["is_comp_aux"],
            is_library_like=d["is_lib_like"],
            asm_insn_count=metrics["asm_insn_count"],
            c_line_count=metrics["c_line_count"],
            insn_to_c_ratio=metrics["insn_to_c_ratio"],
            temp_var_count=d["temp_count"],
            fat_function_flag=fat_flag,
        )
        func_entries.append(func_entry)

        # Build variable entries
        for vd in var_dicts:
            var_entry = GhidraVariableEntry(**vd)
            var_entries.append(var_entry)

        # Build CFG entry
        cfg_entry = GhidraCfgEntry(
            binary_id=binary_id,
            function_id=d["function_id"],
            entry_va=rf.entry_va,
            bb_count=cfg_result["bb_count"],
            edge_count=cfg_result["edge_count"],
            cyclomatic=cfg_result["cyclomatic"],
            has_indirect_jumps=cfg_result["has_indirect_jumps"],
            unresolved_indirect_jump_count=cfg_result["unresolved_indirect_jump_count"],
            cfg_completeness=cfg_result["cfg_completeness"],
            blocks=[CfgBlockEntry(**b) for b in cfg_result["blocks"]],
        )
        cfg_entries.append(cfg_entry)

        # Build call entries
        for cd in d["call_dicts"]:
            call_entry = GhidraCallEntry(**cd)
            call_entries.append(call_entry)

        # ── Accumulate summary stats ─────────────────────────────────
        counts.n_functions_total += 1
        if func_verdict.value == "OK":
            counts.n_functions_ok += 1
        elif func_verdict.value == "WARN":
            counts.n_functions_warn += 1
        else:
            counts.n_functions_fail += 1

        if rf.is_thunk:
            counts.n_thunks += 1
        if rf.is_import:
            counts.n_imports += 1
        if rf.is_external_block:
            counts.n_externals += 1
        if d["is_plt"]:
            counts.n_plt_or_stub += 1
        if d["is_init_fini"]:
            counts.n_init_fini_aux += 1
        if d["is_comp_aux"]:
            counts.n_compiler_aux += 1
        if d["decompile_status"] == DecompileStatus.FAIL.value:
            counts.n_decompile_fail += 1

        for w in warnings:
            warning_prevalence[w] += 1

        all_bb_counts.append(bb_count)
        total_unresolved_indirect += cfg_result["unresolved_indirect_jump_count"]

        total_vars += len(var_dicts)
        total_temps += d["temp_count"]
        for vd in var_dicts:
            total_var_entries += 1
            ts = vd.get("type_str", "") or ""
            if ts.startswith("undefined"):
                total_placeholder_types += 1

    # ── Step 7: Sort all outputs deterministically ───────────────────
    func_entries.sort(key=lambda f: f.entry_va)
    var_entries.sort(key=lambda v: (v.function_id, v.var_kind, v.storage_key))
    cfg_entries.sort(key=lambda c: c.entry_va)
    call_entries.sort(key=lambda c: (c.caller_entry_va, c.callsite_va))

    # ── Step 8: Build report ─────────────────────────────────────────
    cfg_summary = CfgSummary(
        mean_bb_count=round(statistics.mean(all_bb_counts), 2) if all_bb_counts else 0.0,
        median_bb_count=round(statistics.median(all_bb_counts), 2) if all_bb_counts else 0.0,
        unresolved_indirect_jumps_total=total_unresolved_indirect,
    )

    placeholder_rate = (
        total_placeholder_types / total_var_entries
        if total_var_entries > 0
        else 0.0
    )
    var_summary = VariableSummary(
        total_vars=total_vars,
        total_temps=total_temps,
        placeholder_type_rate=round(placeholder_rate, 4),
    )

    # Compute script hash for reproducibility
    script_hash = _compute_script_hash(_get_script_path())

    report = GhidraReport(
        profile_id=profile.profile_id,
        binary_sha256=binary_sha256,
        binary_path=binary_path,
        ghidra_version=summary.ghidra_version,
        java_version=summary.java_version,
        script_hash=script_hash,
        analysis_options=summary.analysis_options,
        binary_verdict=binary_verdict.value,
        reasons=binary_reasons,
        function_counts=counts,
        warning_prevalence=dict(warning_prevalence.most_common()),
        cfg_summary=cfg_summary,
        variable_summary=var_summary,
        fat_function_thresholds=fat_thresholds,
        noise_list_version=NOISE_LIST_VERSION,
    )

    # ── Step 9: Write outputs ────────────────────────────────────────
    if output_dir:
        write_outputs(report, func_entries, var_entries, cfg_entries, call_entries, output_dir)

    return report, func_entries, var_entries, cfg_entries, call_entries


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _build_reject_report(
    binary_path: str,
    binary_sha256: str,
    verdict: BinaryVerdict,
    reasons: List[str],
    profile: Profile,
    ghidra_version: str = "unknown",
    java_version: str = "unknown",
) -> GhidraReport:
    """Build a report for a rejected binary."""
    # Compute script hash even for rejections
    script_hash = _compute_script_hash(_get_script_path())
    
    return GhidraReport(
        profile_id=profile.profile_id,
        binary_sha256=binary_sha256,
        binary_path=binary_path,
        ghidra_version=ghidra_version,
        java_version=java_version,
        script_hash=script_hash,
        binary_verdict=verdict.value,
        reasons=reasons,
        noise_list_version=NOISE_LIST_VERSION,
    )


def _container_to_host_path(container_path: str, reference_host_path: str) -> str:
    """
    Convert a container path back to a host path.

    Uses *reference_host_path* to find the local-files root on the host.
    """
    normalized = reference_host_path.replace("\\", "/")
    markers = ["local-files/", "local-files\\"]
    for marker in markers:
        idx = normalized.find(marker)
        if idx >= 0:
            host_root = reference_host_path[:idx + len("local-files")]
            relative = container_path.removeprefix("/files/")
            return str(Path(host_root) / relative)

    # Fallback: try docker/local-files relative to reference path
    ref = Path(reference_host_path)
    for parent in ref.parents:
        candidate = parent / "docker" / "local-files"
        if candidate.exists():
            relative = container_path.removeprefix("/files/")
            return str(candidate / relative)

    # Last resort
    return container_path
